# Google Cloud AlphaEvolve Shader Optimization Framework

**English** | [简体中文](README_CN.md)

A closed-loop evolutionary optimization system for high-performance fragment shaders (GLSL / WebGL) powered by **Google Cloud AlphaEvolve** and a **Playwright WebGL 2.0 hardware-accelerated execution environment**.

This framework targets complex input shaders (such as heavy raymarching, Signed Distance Fields (SDF), and procedural fractal noise). While strictly preserving perceptual visual fidelity (**NVIDIA FLIP similarity ≥ 98%**), it leverages Google Cloud AlphaEvolve orchestrating Gemini Large Language Models to refactor and evolve shader code, minimizing physical GPU execution time and squeezing out maximum hardware performance.

> 📘 **Architecture & Mathematical Derivations**:
> - For in-depth architectural design, multi-pass rendering topology, and the formal mathematical model of multi-objective fitness arbitration, see [PLAN.md](PLAN.md) (Chinese version: [PLAN_CN.md](PLAN_CN.md)).

---

## 1. Directory Structure & File Manifest

```text
shader-optim-test/
├── Makefile                     # Automated workflow entry point (setup, auth, baseline, run, report, profile, test, mask)
├── config.yaml                  # 🌟 Single Source of Truth (visible, self-explanatory global configuration)
├── requirements.txt             # Core Python dependency manifest
├── PLAN.md                      # Comprehensive architecture design and mathematical derivations (English)
├── PLAN_CN.md                   # Comprehensive architecture design and mathematical derivations (简体中文)
├── README.md                    # User manual and technical guide (English)
├── README_CN.md                 # User manual and technical guide (简体中文)
├── alpha_evolve/                # Google Cloud AlphaEvolve official library (read-only)
├── scripts/                     # Operational delivery & maintenance scripts
│   └── mask_credentials.py     # 🔒 Automated credential sanitization tool (zero hardcoded secrets, pure stdlib)
├── inputs/                      # Input shader projects to be optimized <== Place your shader code here
│   ├── 01/                      # Single-pass project (Tokyo Rainy Night raymarching shader)
│   ├── 02_unmarked/             # Single-pass project without evolve blocks (tests automated bottleneck detection)
│   └── 03/                      # Multi-pass complex project (Buffer A -> Buffer B -> Image with 6-face Cubemap)
├── src/                         # Core framework implementation
│   ├── bottleneck.py            # AST bottleneck analysis, block extraction, and code reassembly
│   ├── browser_worker.py        # Playwright Chromium WebGL 2.0 local worker process
│   ├── config.py                # Configuration loader and dynamic sys.path injection
│   ├── evaluator.py             # Multi-objective fitness evaluator and adaptive quality gate
│   ├── evaluator_web/           # WebGL 2.0 benchmark harness frontend and compatibility layer
│   ├── models.py                # Pydantic telemetry, evaluation records, and configuration models
│   ├── pipeline.py              # 🌟 Multi-pass pipeline DAG resolution, baseline profiling, and cascaded budget scheduling
│   ├── quality.py               # NVIDIA FLIP, SSIM, and PSNR image quality assessment
│   ├── report.py                # Interactive HTML report generator with Pipeline Breakdown
│   └── run_evolution.py         # Main evolutionary controller CLI
├── artifacts/                   # Output artifacts directory (segregated by project ID)
│   └── 03/                      # Output directory for sample project 03
│       ├── baseline_frames/     # Golden reference frame snapshots (subdirectories per pass)
│       ├── baseline_profile.json # Pipeline performance profiling metadata
│       ├── champion_buffer_a.glsl # Optimized champion shader for Buffer A
│       ├── champion_optimized.glsl # Final optimized master shader (markers stripped)
│       ├── evaluations.jsonl    # Comprehensive history of all candidate evaluations
│       ├── metrics.json         # Performance summary and pipeline breakdown metadata
│       └── report.html          # Self-contained interactive HTML evaluation report
└── tests/                       # Automated unit and integration test suite (72 tests)
```

---

## 2. Prerequisites & Environment Setup

### 2.1 OS & Software Requirements
- **Operating System**: macOS (Apple Silicon / Intel) or Linux (with GPU hardware acceleration and Chrome support).
- **Python**: Python 3.11+.
- **Playwright Browser Driver**: Playwright Chromium with WebGL 2.0 hardware acceleration and the `EXT_disjoint_timer_query_webgl2` extension (enabling microsecond/nanosecond hardware GPU timer queries).
- **GNU Make**: Workflow automation utility (`make --version`).
- **Google Cloud SDK**: `gcloud` CLI (for GCP Application Default Credentials authentication and API interaction).

### 2.2 Virtual Environment & Dependency Installation (Required for First Run)
> [!IMPORTANT]
> **Delivery Notice**: To avoid dependency conflicts and redundant repository bloat, the `venv/` directory is deliberately excluded from project deliveries. Before running any evolution experiments or test suites, **you must create a virtual environment and install all dependencies in the project root**.
>
> Choose either of the following methods:
>
> **Method 1: One-Click Automated Setup via Makefile (Strongly Recommended)**
> ```bash
> make setup
> ```
> This command automatically creates the `venv` environment, upgrades pip, installs all requirements from `requirements.txt`, downloads the Playwright Chromium browser binary, and validates `config.yaml`.
>
> **Method 2: Manual Step-by-Step CLI Execution**
> ```bash
> # 1. Create a Python 3.11+ virtual environment
> python3.11 -m venv venv
>
> # 2. Activate the virtual environment
> source venv/bin/activate
>
> # 3. Upgrade pip and install core dependencies
> pip install --upgrade pip
> pip install -r requirements.txt
>
> # 4. Install Playwright Chromium browser driver
> playwright install chromium
> ```

### 2.3 GCP Account & Gemini Enterprise App Configuration
1. **Google Cloud Project**:
   - Ensure you have a Google Cloud Project with billing enabled (note your `PROJECT_ID`).
2. **Enable Discovery Engine API**:
   ```bash
   gcloud services enable discoveryengine.googleapis.com --project=<YOUR_GCP_PROJECT_ID>
   ```
3. **Obtain Gemini Enterprise App ID**:
   - Open the Google Cloud Console, navigate to Gemini Enterprise / Discovery Engine, create or view your app, and note down the App/Engine ID (`GE_APP_ID`).
4. **IAM Role Permissions**:
   - The user or service account executing the tool must possess the **Discovery Engine Editor** (`roles/discoveryengine.editor`) role or equivalent administrative permissions.
   - Reference: [AlphaEvolve Environment and API Access Setup Documentation](https://docs.cloud.google.com/gemini/enterprise/docs/alphaevolve/developer-guide/environment-and-api-access-setup).
5. **Local Authentication (ADC)**:
   ```bash
   make auth
   # Or manually: gcloud auth application-default login
   ```

---

## 3. Global Configuration Guide (`config.yaml`)

All parameters are centrally managed in `config.yaml` at the project root—no hidden `.env` files are required. Before your initial run, fill in your GCP project credentials:

```yaml
# 1. Google Cloud & Gemini Enterprise Credentials and Service Settings
gcp:
  project_id: "<YOUR_GCP_PROJECT_ID>" # Enter your Google Cloud Project ID here
  location: "global"
  collection: "default_collection"
  ge_app_id: "<YOUR_GE_APP_ID>"       # Enter your Gemini Enterprise App/Engine ID here
  assistant: "default_assistant"
  base_url: "discoveryengine.googleapis.com"
  alpha_evolve_path: "./alpha_evolve"   # Path to official alpha_evolve library

# 2. Evolution Control & Hyperparameter Settings (Serialized GPU Evaluation)
evolution:
  max_programs_generated: 50    # Adjust according to your evaluation budget
  max_programs_evaluated: 50    # Adjust according to your evaluation budget
  concurrency: 1                # Generation concurrency
  worker_concurrency: 1         # Evaluation concurrency (Must be 1 for physical GPU precision)
  parallel_evaluation: false    # Serialized hardware evaluation
  idle_timeout_s: 120

# 3. Gemini LLM Generation Mixture Weights
models:
  - name: "gemini-3.5-flash"
    weight: 0.70
  - name: "gemini-3.1-pro-preview"
    weight: 0.30

# 4. Perceptual Quality Gate Thresholds
quality:
  flip_initial_threshold: 0.980    # NVIDIA FLIP initial threshold (≥ 98%)
  flip_relaxed_threshold: 0.950    # Relaxed minimum quality gate (≥ 95%)
  relaxation_patience: 10          # Consecutive failed generations before relaxing gate
  min_ssim_threshold: 0.950        # SSIM auxiliary threshold

# 5. WebGL 2.0 Local Hardware Benchmark Harness Settings
benchmark:
  port: 8099                       # Local HTTP static server port
  headless: true                   # Run Playwright Chromium in headless mode
  resolution: [1280, 720]          # Benchmark canvas resolution [width, height]
  sample_times: [0.0, 1.5, 3.0, 4.5, 6.0]  # Sampled animation timestamps (seconds)
  warmup_frames: 30                # GPU warmup frames (bypasses pipeline compilation overhead)
  timed_samples: 12                # Hardware GPU timer query samples per timestamp (median taken)
  playwright_channel: "chrome"     # Browser channel (chrome / chromium)
```

---

## 4. Quickstart & Makefile Workflow

### 4.1 Makefile Command Reference

| Command | Description | Example |
| :--- | :--- | :--- |
| **`make setup`** | Initialize Python venv, install packages & Playwright browser, validate `config.yaml` | `make setup` |
| **`make auth`** | Authenticate with Google Cloud ADC via browser (`gcloud auth application-default login`) | `make auth` |
| **`make baseline`** | **Full Pipeline Profiling**: Measure hardware GPU time for all passes, output breakdown and core bottleneck | `make baseline PROJECT=03` |
| **`make baseline` (Single Pass)** | Measure baseline GPU time and capture frames for a specific shader file | `make baseline PROJECT=03 SHADER=shaders/buffer_a.glsl` |
| **`make run`** | Run closed-loop evolution via AlphaEvolve (supports Approach 2 cascaded multi-pass optimization) | `make run PROJECT=03 PROGRAMS=50` |
| **`make run` (Single Pass)** | Optimize only a specific pass within a multi-pass project | `make run PROJECT=03 SHADER=shaders/buffer_a.glsl PROGRAMS=50` |
| **`make profile`** | Static/AST bottleneck analysis to pinpoint performance hotspots in shaders | `make profile PROJECT=03` |
| **`make report`** | Generate and display the interactive self-contained HTML optimization report | `make report PROJECT=03` |
| **`make test`** | Run the comprehensive test suite (all 72 unit and integration tests) | `make test` |
| **`make mask`** | **Delivery Sanitization**: Mask all credentials (`project_id`, `ge_app_id`) with placeholders | `make mask` |
| **`make mask-dry`** | **Sanitization Preview**: Preview files and frequencies to be masked without writing changes | `make mask-dry` |
| **`make clean`** | Remove Python bytecode caches and test artifacts | `make clean` |

### 4.2 End-to-End Workflow Example

```bash
# 1. Environment initialization and cloud authentication
make setup
make auth

# 2. Pipeline Baseline Profiling: measure all passes and identify the primary bottleneck
make baseline PROJECT=03

# 3. Execute Evolutionary Optimization
# Scenario A: Cascaded evolution across all passes (weighted budget allocation, topological champion propagation)
make run PROJECT=03 PROGRAMS=50

# Scenario B: Single-pass evolution (target a specific pass)
make run PROJECT=03 SHADER=shaders/buffer_a.glsl PROGRAMS=50

# Scenario C: Single-pass project evolution (e.g., project 01)
make run PROJECT=01 PROGRAMS=50

# 4. Generate and inspect the self-contained HTML report
make report PROJECT=03
```

---

## 5. 🌟 Core Features & Technical Highlights

1. **Physical GPU Microsecond Timer Queries**:
   - Uses Playwright to orchestrate an isolated Chromium instance querying the WebGL 2.0 extension `EXT_disjoint_timer_query_webgl2` for nanosecond/microsecond hardware timestamps;
   - Eliminates CPU-side `performance.now()` measurement errors caused by driver queuing, command serialization, and pipeline buffering.

2. **Serialized GPU Hardware Benchmarking**:
   - Local GPU benchmarking enforces strict single-worker serialization (`concurrency: 1`, `worker_concurrency: 1`, `parallel_evaluation: false`);
   - Completely avoids physical GPU command queue contention and context-switch jitter caused by concurrent browser tabs, ensuring deterministic and reproducible speedup measurements.

3. **Multi-Objective Fitness Arbitration & Perceptual Quality Gate**:
   - Integrates the official NVIDIA HPG 2020 FLIP metric alongside Structural Similarity (SSIM) and Peak Signal-to-Noise Ratio (PSNR);
   - Employs a smooth Sigmoid correctness gate $`G(q) = \frac{1}{1 + \exp(-50(q - \tau))}`$ with composite fitness $`\text{Fitness} = G(q) \times \text{Speedup}`$, maximizing acceleration while preserving visual perfection;
   - **Monotonic Pareto Champion Rule (Zero Performance Regression)**: A candidate variant is accepted as a new Champion if and only if it passes the perceptual quality gate AND achieves $`\text{Speedup} > 1.0`$;
   - **Four-Tier Hierarchical Defense & Diagnostic Feedback**: Compilation failures (-200 score) and quality degradation (-100 score) automatically extract compiler diagnostics and visual discrepancy maps as Diagnostic Insights returned to Gemini for targeted self-correction;
   - **Adaptive Dynamic Relaxation**: If 10 consecutive generations fail to meet the 98% threshold, the gate dynamically and safely relaxes to 95%.

4. **Comprehensive Texture Support & 6-Face Cubemap Integration**:
   - Automatically parses input channels from `manifest.json`, supporting 2D textures and 6-face Cubemap textures (`TEXTURE_CUBE_MAP`);
   - Dynamically injects overloaded compatibility shims under WebGL 2.0, supporting complex raytracers sampling environment maps via `texture(iChannel3, reflect(...))`.

5. **Single Source of Truth (`config.yaml`)**:
   - All GCP credentials, AlphaEvolve hyperparameters, LLM mixture weights, quality gates, and benchmarking parameters are centralized in a clearly structured, visible `config.yaml` with zero hidden files.

6. **Automated AST Bottleneck Analysis**:
   - If `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` markers exist (in `#`, `//`, or `/*` syntax), evolution strictly refactors code inside the designated block;
   - If markers are absent, the system automatically runs an AST and static heuristic bottleneck analyzer to detect the core Raymarching loop or compute-heavy loops and injects the markers dynamically.

7. **Multi-Pass Pipeline Breakdown & Cascaded Evolution (Approach 2)**:
   - Automatically parses `manifest.json` or shader directories to reconstruct the cross-channel render pipeline DAG (`Buffer A -> Buffer B -> Image`);
   - `make baseline` measures GPU milliseconds for all passes, exporting a breakdown summary, core bottleneck designation, and `baseline_profile.json`;
   - Implements **Approach 2 (Dependency-Aware Cascaded Evolution)**: Allocates search budgets proportionally to baseline execution times, prioritizes the primary bottleneck pass, and passes upstream Champion code forward as interface contracts to downstream passes.

8. **Self-Contained Interactive HTML Optimization Report**:
   - `make report` compiles a zero-external-dependency, standalone single-file HTML report featuring:
     - Executive metrics scorecard (Speedup, baseline vs. champion timing, FLIP quality, estimated energy savings);
     - Multi-Pass Pipeline Breakdown table;
     - Key engineering improvements summary;
     - Pixel-level side-by-side snapshot comparison (golden reference vs. champion);
     - Vector SVG convergence trajectory chart;
     - Syntax-highlighted line-by-line source code diff;
     - Complete evaluation log of all candidate variants.

---

## 6. 🔒 Delivery Sanitization & Privacy Protection

To protect personal Google Cloud credentials (`project_id`, `ge_app_id`, GCP project numbers) when sharing the repository or delivering code to clients, an automated sanitization utility is provided:

### 6.1 Sanitization Workflow
Before packaging or publishing the code, follow these steps:

1. **Run the Masking Script** (replaces sensitive credentials across `config.yaml`, documentation, and configs with `<YOUR_GCP_PROJECT_ID>` and `<YOUR_GE_APP_ID>`):
   ```bash
   make mask
   # To preview changes without modifying files (Dry-run):
   make mask-dry
   ```
   > 💡 **Security by Design**: [`scripts/mask_credentials.py`](scripts/mask_credentials.py) contains **zero hardcoded credentials**, relies strictly on the Python 3 standard library (executable even without an active virtual environment), and injects helpful setup comments into `config.yaml`.

2. **Restore / Inject Custom Credentials (Optional)**:
   To rapidly inject credentials in a new deployment environment, use restore mode:
   ```bash
   python3 scripts/mask_credentials.py --restore --project-id <NEW_PROJECT_ID> --app-id <NEW_GE_APP_ID>
   ```

3. **Clean Local Virtual Environment**:
   ```bash
   rm -rf venv/
   ```
   Recipients can simply follow Section 2.2 and run `make setup` to reconstruct their environment in one step.
