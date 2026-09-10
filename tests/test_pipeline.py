"""
Unit tests for Pipeline and Multi-Pass Cascaded Evolution modules.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from src.pipeline import (
    load_pipeline,
    allocate_pass_budget,
    format_pipeline_breakdown,
    profile_pipeline,
    Pipeline,
    PassInfo
)


def test_load_pipeline_single_pass():
    pipe = load_pipeline("01")
    assert pipe.project_id == "01"
    assert len(pipe.passes) == 1
    assert pipe.passes[0].name == "Image"
    assert pipe.passes[0].rel_path == "shaders/image.glsl"
    assert pipe.passes[0].channel_types == ["2d", "2d", "2d", "2d"]


def test_load_pipeline_multipass_03():
    pipe = load_pipeline("03")
    assert pipe.project_id == "03"
    assert pipe.title == "ValleyRace"
    assert len(pipe.passes) == 3

    pass_names = [p.name for p in pipe.passes]
    assert pass_names == ["Buffer A", "Buffer B", "Image"]

    # Check cubemap on channel 3 of Buffer A
    buffer_a = pipe.get_pass("Buffer A")
    assert buffer_a is not None
    assert buffer_a.channel_types == ["2d", "2d", "2d", "cubemap"]

    # Check dependencies
    buffer_b = pipe.get_pass("Buffer B")
    assert "Buffer A" in buffer_b.dependencies

    image_pass = pipe.get_pass("Image")
    assert "Buffer A" in image_pass.dependencies
    assert "Buffer B" in image_pass.dependencies


def test_topological_order():
    pipe = load_pipeline("03")
    topo = [p.name for p in pipe.get_topological_order()]
    assert topo == ["Buffer A", "Buffer B", "Image"]


def test_allocate_pass_budget_small():
    pipe = load_pipeline("03")
    pipe.passes[0].baseline_gpu_ms = 2.80
    pipe.passes[1].baseline_gpu_ms = 0.40
    pipe.passes[2].baseline_gpu_ms = 0.20
    pipe.passes[0].cost_percent = 82.4
    pipe.passes[1].cost_percent = 11.8
    pipe.passes[2].cost_percent = 5.8

    # Small budget (<= 2) should concentrate on the core bottleneck pass
    alloc = allocate_pass_budget(pipe, 2)
    assert alloc == {"Buffer A": 2}


def test_allocate_pass_budget_proportional():
    pipe = load_pipeline("03")
    pipe.passes[0].baseline_gpu_ms = 2.80
    pipe.passes[1].baseline_gpu_ms = 0.40
    pipe.passes[2].baseline_gpu_ms = 0.20
    pipe.passes[0].cost_percent = 82.4
    pipe.passes[1].cost_percent = 11.8
    pipe.passes[2].cost_percent = 5.8

    alloc = allocate_pass_budget(pipe, 50)
    assert sum(alloc.values()) == 50
    assert alloc["Buffer A"] > alloc["Buffer B"]
    assert "Buffer B" in alloc
    assert "Image" in alloc


def test_format_pipeline_breakdown():
    pipe = load_pipeline("03")
    pipe.passes[0].baseline_gpu_ms = 2.80
    pipe.passes[0].cost_percent = 82.4
    pipe.passes[0].baseline_fps = 357.1
    pipe.passes[1].baseline_gpu_ms = 0.40
    pipe.passes[1].cost_percent = 11.8
    pipe.passes[1].baseline_fps = 2500.0
    pipe.passes[2].baseline_gpu_ms = 0.20
    pipe.passes[2].cost_percent = 5.8
    pipe.passes[2].baseline_fps = 5000.0

    report = format_pipeline_breakdown(pipe, "Apple M5 Pro", True)
    assert "MULTI-PASS BASELINE PERFORMANCE BREAKDOWN" in report
    assert "Buffer A" in report
    assert "🚨 [CORE BOTTLENECK]" in report
    assert "TOTAL PIPELINE FRAME GPU TIME" in report


@pytest.mark.asyncio
async def test_profile_pipeline_mock_worker(tmp_path):
    pipe = load_pipeline("03")
    mock_worker = MagicMock()
    mock_worker.evaluate_shader = AsyncMock(return_value={
        "compileOk": True,
        "gpuTimeMs": 1.5,
        "frames": [{"time": 0.0, "dataUrl": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="}]
    })

    breakdown = await profile_pipeline(pipe, mock_worker, [0.0], out_dir=tmp_path)
    assert breakdown["project_id"] == "03"
    assert len(breakdown["passes"]) == 3
    assert (tmp_path / "baseline_profile.json").exists()
