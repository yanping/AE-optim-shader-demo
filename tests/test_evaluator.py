"""Unit tests for ShaderEvaluator multi-objective gating and scoring."""

from unittest.mock import AsyncMock, MagicMock
import numpy as np
import pytest
from src.evaluator import ShaderEvaluator


@pytest.fixture
def dummy_frames():
    return [np.full((32, 32, 3), 128, dtype=np.uint8)]


@pytest.fixture
def mock_worker():
    worker = MagicMock()
    return worker


def test_evaluator_compile_failure(mock_worker, dummy_frames):
    mock_worker.evaluate_shader = AsyncMock(return_value={
        "compileOk": False,
        "compileError": "Syntax error at line 42"
    })

    evaluator = ShaderEvaluator(
        browser_worker=mock_worker,
        baseline_frames=dummy_frames,
        baseline_gpu_ms=16.0,
        seed_code="void main() {}",
        initial_flip_threshold=0.98
    )

    candidate = {
        "name": "cand_001",
        "content": {"files": [{"path": "shader.glsl", "content": "bad glsl code"}]}
    }

    res = evaluator.evaluate_program(candidate)
    score = res["scores"]["scores"][0]["score"]
    assert score <= -1000.0
    assert "GLSL Compilation Error" in res["insights"]["insights"][0]["text"]
    assert evaluator.records[0].compile_ok is False


def test_evaluator_visual_quality_rejection(mock_worker, dummy_frames):
    import base64
    import io
    from PIL import Image

    # Return black frame when baseline was gray 128
    img = Image.new("RGB", (32, 32), color=(0, 0, 0))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    black_frame_data = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

    mock_worker.evaluate_shader = AsyncMock(return_value={
        "compileOk": True,
        "gpuTimeMs": 8.0,
        "frames": [{"time": 0.0, "dataUrl": black_frame_data}]
    })

    evaluator = ShaderEvaluator(
        browser_worker=mock_worker,
        baseline_frames=dummy_frames,
        baseline_gpu_ms=16.0,
        seed_code="void main() {}",
        initial_flip_threshold=0.98
    )

    candidate = {
        "name": "cand_002",
        "content": {"files": [{"path": "shader.glsl", "content": "void main() {}"}]}
    }

    res = evaluator.evaluate_program(candidate)
    score = res["scores"]["scores"][0]["score"]
    assert score < 0.0
    assert evaluator.records[0].accepted is False
    assert evaluator.best_candidate_record is None


def test_evaluator_successful_speedup(mock_worker, dummy_frames):
    import io
    from PIL import Image
    import base64

    # Generate data url for identical frame
    img = Image.fromarray(dummy_frames[0])
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    data_url = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("utf-8")

    mock_worker.evaluate_shader = AsyncMock(return_value={
        "compileOk": True,
        "gpuTimeMs": 8.0,
        "frames": [{"time": 0.0, "dataUrl": data_url}]
    })

    evaluator = ShaderEvaluator(
        browser_worker=mock_worker,
        baseline_frames=dummy_frames,
        baseline_gpu_ms=16.0,
        seed_code="void main() {}",
        initial_flip_threshold=0.98
    )

    candidate = {
        "name": "cand_003",
        "content": {"files": [{"path": "shader.glsl", "content": "void main() {}"}]}
    }

    res = evaluator.evaluate_program(candidate)
    score = res["scores"]["scores"][0]["score"]
    assert score > 1.2
    assert evaluator.records[0].accepted is True
    assert evaluator.best_candidate_record is not None
    assert evaluator.best_candidate_record.speedup == 2.0


def test_evaluator_channel_types_passed_to_worker(mock_worker, dummy_frames):
    mock_worker.evaluate_shader = AsyncMock(return_value={
        "compileOk": False,
        "compileError": "Test stop"
    })

    evaluator = ShaderEvaluator(
        browser_worker=mock_worker,
        baseline_frames=dummy_frames,
        baseline_gpu_ms=16.0,
        seed_code="void main() {}",
        channel_types=["2d", "2d", "2d", "cubemap"]
    )

    candidate = {
        "name": "cand_cube",
        "content": {"files": [{"path": "shader.glsl", "content": "void main() {}"}]}
    }

    evaluator.evaluate_program(candidate)
    mock_worker.evaluate_shader.assert_called_once()
    _, kwargs = mock_worker.evaluate_shader.call_args
    assert kwargs.get("channel_types") == ["2d", "2d", "2d", "cubemap"]


def test_resolve_project_input_cubemap():
    from src.run_evolution import resolve_project_input
    pid, proj_dir, rel_path, code, channel_types = resolve_project_input("03")
    assert pid == "03"
    assert rel_path == "shaders/buffer_a.glsl"
    assert channel_types == ["2d", "2d", "2d", "cubemap"]
    assert len(code) > 0
