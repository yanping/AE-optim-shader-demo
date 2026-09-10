"""Central configuration module for AlphaEvolve Shader Optimization Tool.

Loads and exposes configuration strictly from the unified `config.yaml` in the project root.
"""

import os
import sys
from pathlib import Path
from typing import Any, Dict, List
import yaml

# Base Project Directories
SRC_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SRC_DIR.parent
INPUTS_DIR = PROJECT_ROOT / "inputs"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
EVALUATOR_WEB_DIR = SRC_DIR / "evaluator_web"

# ------------------------------------------------------------------------------
# Load Unified config.yaml (Single Source of Truth)
# ------------------------------------------------------------------------------
CONFIG_PATH = Path(os.getenv("CONFIG_PATH", PROJECT_ROOT / "config.yaml"))

def load_yaml_config(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
        return data or {}

_raw_config = load_yaml_config(CONFIG_PATH)

_gcp = _raw_config.get("gcp", {})
_evolution = _raw_config.get("evolution", {})
_models = _raw_config.get("models", [])
_quality = _raw_config.get("quality", {})
_benchmark = _raw_config.get("benchmark", {})

# ------------------------------------------------------------------------------
# AlphaEvolve Library Path Resolution & Dynamic Import Hook
# ------------------------------------------------------------------------------
# Supports configuring custom path to official alpha_evolve package
alpha_evolve_cfg = _gcp.get("alpha_evolve_path", "./alpha_evolve")
alpha_evolve_env = os.getenv("ALPHA_EVOLVE_PATH", alpha_evolve_cfg)
alpha_evolve_candidate = (PROJECT_ROOT / alpha_evolve_env).resolve() if not os.path.isabs(alpha_evolve_env) else Path(alpha_evolve_env)

search_paths = [
    PROJECT_ROOT,
    alpha_evolve_candidate,
    alpha_evolve_candidate.parent,
    PROJECT_ROOT / "alpha_evolve",
    Path.home() / "Projects" / "alphaevolve-on-googlecloud" / "src"
]

for p in search_paths:
    if p.exists() and str(p) not in sys.path:
        # Check if alpha_evolve package is inside or if p is the package parent
        if (p / "alpha_evolve").is_dir() or (p.name == "alpha_evolve" and (p / "__init__.py").exists()):
            target_import_root = str(p.parent if p.name == "alpha_evolve" else p)
            if target_import_root not in sys.path:
                sys.path.insert(0, target_import_root)

# ------------------------------------------------------------------------------
# Google Cloud & Gemini Enterprise Settings
# ------------------------------------------------------------------------------
PROJECT_ID = os.getenv("PROJECT_ID", _gcp.get("project_id", "<YOUR_GCP_PROJECT_ID>"))
LOCATION = os.getenv("LOCATION", _gcp.get("location", "global"))
COLLECTION = os.getenv("COLLECTION", _gcp.get("collection", "default_collection"))
GE_APP_ID = os.getenv("GE_APP_ID", _gcp.get("ge_app_id", "<YOUR_GE_APP_ID>"))
ASSISTANT = os.getenv("ASSISTANT", _gcp.get("assistant", "default_assistant"))
BASE_URL = os.getenv("BASE_URL", _gcp.get("base_url", "discoveryengine.googleapis.com"))

# ------------------------------------------------------------------------------
# Model Mixture Settings
# ------------------------------------------------------------------------------
if _models and len(_models) >= 2:
    MODEL_1 = _models[0].get("name", "gemini-3.5-flash")
    MODEL_1_WEIGHT = float(_models[0].get("weight", 0.7))
    MODEL_2 = _models[1].get("name", "gemini-3.1-pro-preview")
    MODEL_2_WEIGHT = float(_models[1].get("weight", 0.3))
else:
    MODEL_1 = os.getenv("MODEL_1", "gemini-3.5-flash")
    MODEL_1_WEIGHT = float(os.getenv("MODEL_1_WEIGHT", "0.7"))
    MODEL_2 = os.getenv("MODEL_2", "gemini-3.1-pro-preview")
    MODEL_2_WEIGHT = float(os.getenv("MODEL_2_WEIGHT", "0.3"))

# ------------------------------------------------------------------------------
# Evolutionary Search Hyperparameters (Serialized Hardware Evaluation)
# ------------------------------------------------------------------------------
MAX_PROGRAMS_GENERATED = int(os.getenv("MAX_PROGRAMS_GENERATED", _evolution.get("max_programs_generated", 50)))
MAX_PROGRAMS_EVALUATED = int(os.getenv("MAX_PROGRAMS_EVALUATED", _evolution.get("max_programs_evaluated", 50)))
CONCURRENCY = int(os.getenv("CONCURRENCY", _evolution.get("concurrency", 1)))
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", _evolution.get("worker_concurrency", 1)))
PARALLEL_EVALUATION = os.getenv("PARALLEL_EVALUATION", str(_evolution.get("parallel_evaluation", False))).lower() == "true"
IDLE_TIMEOUT_S = int(os.getenv("IDLE_TIMEOUT_S", _evolution.get("idle_timeout_s", 120)))

# ------------------------------------------------------------------------------
# Evaluator & Quality Gate Configuration
# ------------------------------------------------------------------------------
FLIP_INITIAL_THRESHOLD = float(os.getenv("FLIP_INITIAL_THRESHOLD", _quality.get("flip_initial_threshold", 0.980)))
FLIP_RELAXED_THRESHOLD = float(os.getenv("FLIP_RELAXED_THRESHOLD", _quality.get("flip_relaxed_threshold", 0.950)))
RELAXATION_PATIENCE = int(os.getenv("RELAXATION_PATIENCE", _quality.get("relaxation_patience", 10)))
MIN_SSIM_THRESHOLD = float(os.getenv("MIN_SSIM_THRESHOLD", _quality.get("min_ssim_threshold", 0.950)))

# ------------------------------------------------------------------------------
# Benchmark Settings
# ------------------------------------------------------------------------------
EVALUATOR_PORT = int(os.getenv("EVALUATOR_PORT", _benchmark.get("port", 8099)))
EVALUATOR_HEADLESS = os.getenv("EVALUATOR_HEADLESS", str(_benchmark.get("headless", True))).lower() == "true"
BENCHMARK_RESOLUTION = _benchmark.get("resolution", [1280, 720])
BENCHMARK_RESOLUTION_WIDTH = int(BENCHMARK_RESOLUTION[0]) if len(BENCHMARK_RESOLUTION) > 0 else 1280
BENCHMARK_RESOLUTION_HEIGHT = int(BENCHMARK_RESOLUTION[1]) if len(BENCHMARK_RESOLUTION) > 1 else 720
SAMPLE_TIMES = _benchmark.get("sample_times", [0.0, 1.5, 3.0, 4.5, 6.0])
BENCHMARK_WARMUP_FRAMES = int(_benchmark.get("warmup_frames", 30))
BENCHMARK_TIMED_SAMPLES = int(_benchmark.get("timed_samples", 12))
PLAYWRIGHT_CHANNEL = os.getenv("PLAYWRIGHT_CHANNEL", _benchmark.get("playwright_channel", "chrome"))
