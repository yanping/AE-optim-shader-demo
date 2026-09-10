import pytest
from src.models import EvaluationRecord
from src.report import build_html_report, summarize_improvements

def test_build_html_report():
    record = EvaluationRecord(
        evaluation_index=1,
        program_id="candidate_001",
        compile_ok=True,
        runtime_ok=True,
        flip_similarity=0.985,
        mean_ssim=0.988,
        worst_ssim=0.981,
        psnr_db=34.5,
        baseline_gpu_ms=16.0,
        candidate_gpu_ms=10.0,
        speedup=1.6,
        score=1.58,
        accepted=True,
        timestamp="2026-09-07T20:00:00"
    )

    html = build_html_report(
        project_id="test_proj",
        title="Test Shader Optimization",
        baseline_gpu_ms=16.0,
        champion_gpu_ms=10.0,
        flip_similarity=0.985,
        mean_ssim=0.988,
        psnr_db=34.5,
        seed_code="void main() { float x = 1.0; }",
        champion_code="void main() { float x = 2.0; }",
        records=[record]
    )

    assert "<!DOCTYPE html>" in html
    assert "1.60x" in html
    assert "98.50%" in html
    assert "candidate_001" in html
