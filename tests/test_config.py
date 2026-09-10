import os
import tempfile
from pathlib import Path
import pytest
import yaml

from src.config import load_yaml_config, PROJECT_ID, GE_APP_ID, CONCURRENCY, WORKER_CONCURRENCY, PARALLEL_EVALUATION


def test_load_yaml_config():
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        yaml.dump({
            "gcp": {"project_id": "test-project-123"},
            "evolution": {"concurrency": 1, "worker_concurrency": 1, "parallel_evaluation": False}
        }, f)
        temp_path = Path(f.name)

    try:
        data = load_yaml_config(temp_path)
        assert data["gcp"]["project_id"] == "test-project-123"
        assert data["evolution"]["concurrency"] == 1
        assert data["evolution"]["worker_concurrency"] == 1
        assert data["evolution"]["parallel_evaluation"] is False
    finally:
        if temp_path.exists():
            temp_path.unlink()


def test_current_config_values():
    assert PROJECT_ID == "spartan-figure-500309-g2"
    assert GE_APP_ID == "gemini-enterprise-17845428_1784542814283"
    assert CONCURRENCY == 1
    assert WORKER_CONCURRENCY == 1
    assert PARALLEL_EVALUATION is False
