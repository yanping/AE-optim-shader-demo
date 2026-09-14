# 📋 AlphaEvolve Shader Optimization Tool - Architecture & Evolution Plan (PLAN.md)

**English** | [简体中文](PLAN_CN.md)

This technical planning document is formulated based on the specifications in [`TASK_SPEC.md`](TASK_SPEC.md). Drawing upon the shader optimization algorithms developed in the predecessor project (`~/Projects/shader-optim/`) and adhering to the engineering standards of official Google Cloud AlphaEvolve examples ([https://github.com/Google-Cloud-AI/alphaevolve-on-googlecloud/tree/main/examples](https://github.com/Google-Cloud-AI/alphaevolve-on-googlecloud/tree/main/examples)), this project decouples core algorithms and systems into a modular, production-ready framework for **arbitrary input shader projects** (supporting both complex single-pass and multi-pass rendering pipelines).

> 📖 **User Manual & Quickstart**:
> - For operational instructions, environment setup, and CLI workflows, see [README.md](README.md) (Chinese version: [README_CN.md](README_CN.md)).

---

## 1. 🎯 Project Scope & Core Objectives

1. **Core Logic Decoupling & Modular Tooling**:
   Extract and formalize generalized evolutionary optimization modules from one-off demo scripts:
   - **Local Hardware GPU Evaluator**: Built on Playwright + WebGL 2.0 utilizing the `EXT_disjoint_timer_query_webgl2` hardware extension for nanosecond/microsecond GPU timer queries, eliminating CPU scheduling jitter.
   - **Full Pipeline Profiling & Cascaded Multi-Pass Evolution (Approach 2)**: Native support for multi-pass FBO pipelines (e.g., `Buffer A -> Buffer B -> Image`). Automatically resolves the directed acyclic graph (DAG), produces a GPU execution time breakdown, pinpoints the primary bottleneck pass, allocates evolutionary search budgets proportionally, and propagates upstream Champion interface contracts downstream for holistic pipeline speedup.
   - **Authoritative Perceptual Quality Gate**: Leverages the official NVIDIA FLIP metric (ACM TOG / HPG 2020) as the primary fidelity standard, complemented by Wang et al. 2004 SSIM and PSNR, featuring adaptive dynamic relaxation (initial 98% threshold dynamically relaxing to 95%).
   - **Multi-Objective Fitness Arbitration System**: Balances hardware speedup ratios with a smooth Sigmoid correctness gate, heavily penalizing compilation failures, syntax errors, and visual artifacts, while enforcing strict monotonic acceleration ( $`\text{Speedup} > 1.0`$ ) to prevent any performance regression.
   - **Cloud-Native Closed-Loop Feedback**: Direct integration with Google Cloud AlphaEvolve (leveraging Gemini 3.5 Flash and Gemini 3.1 Pro hybrid LLM mixtures), generating structured Diagnostic Insights to guide the LLM's iterative self-correction.
   - **Automated Bottleneck Detection & Marking**: Supports explicit user tagging via `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END`. When untagged, the system runs static AST and heuristic analysis to locate computational hotspots (raymarching loops, dense FBM procedural noise, heavy transcendental functions) and automatically injects delimiters.
   - **Pareto Selection & Artifact Export**: Automatically identifies Pareto-optimal candidates and the overall Champion code, exporting clean GLSL code for each pass alongside comprehensive telemetry.

2. **Standardized Engineering & Delivery**:
   - Mirrors the clean structure of `alphaevolve-on-googlecloud/examples`, providing a unified `Makefile` (`setup`, `auth`, `baseline`, `run`, `report`, `profile`, `test`, `mask`, `clean`).
   - Single Source of Truth: All GCP credentials, LLM weights, evolution hyperparameters, and WebGL benchmark settings reside in the explicit, self-documenting [`config.yaml`](config.yaml).
   - Generates an interactive, standalone HTML report (`make report`) featuring multi-pass breakdown cards, SVG convergence trajectories, side-by-side snapshot visualizers, line-by-line diffs, and engineering improvement summaries.
   - Strictly preserves the external `alpha_evolve/` library as read-only.

---

## 2. 🏗️ System Architecture & Data Flow

```text
+---------------------------------------------------------------------------------+
| 1. Input Layer (inputs/<project_id>/)                                            |
|    - Shader sources (shaders/*.glsl)                                            |
|    - manifest.json: Defines multi-pass pipeline and channel inputs (2D/Cubemap) |
+---------------------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
| 2. Pipeline Topology & Bottleneck Analysis (src/pipeline.py & src/bottleneck.py)|
|    - Topological Sort: Resolves inter-buffer dependencies to build a DAG        |
|    - Hotspot Detection: Injects # EVOLVE-BLOCK around compute-heavy loops       |
|    - Full Baseline Profiling (make baseline): GPU timing & CORE BOTTLENECK tag  |
+---------------------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
| 3. Cloud Evolutionary Engine: Google Cloud AlphaEvolve (src/run_evolution.py)   |
|    - Connects to Google Cloud Gemini Enterprise App & Discovery Engine          |
|    - Dynamic Budget Scheduling: Allocates generations by pass execution weight |
|    - Approach 2 Cascaded Evolution: Sequential evolution with Champion contracts|
+---------------------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
| 4. Local Hardware Evaluation Loop (src/evaluator.py + src/browser_worker.py)   |
|    - Playwright Chromium WebGL 2.0 (Headless Metal/ANGLE hardware rendering)    |
|    - EXT_disjoint_timer_query nanosecond/microsecond hardware GPU timing        |
|    - Perceptual Quality: NVIDIA FLIP (HPG 2020) + SSIM + PSNR                   |
|    - Multi-Objective Arbitration (Speedup x Sigmoid Gate, Monotonic Rule)       |
|    - Structured Diagnostic Insights returned to Gemini for self-correction     |
+---------------------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
| 5. Artifacts & Deliverables (artifacts/<project_id>/)                           |
|    - Pass Champions & Final Optimized Shader (champion_optimized.glsl)          |
|    - Pipeline Baseline Profile (baseline_profile.json) & Golden Frame Snapshots |
|    - Complete Evaluation History (evaluations.jsonl) & Metrics (metrics.json)   |
|    - Interactive HTML Report (report.html, with Multi-Pass Pipeline Breakdown)  |
+---------------------------------------------------------------------------------+
```

---

## 3. 📂 Project Layout & Module Responsibilities

```text
shader-optim-test/
├── PLAN.md                     # 📋 Architecture design and mathematical derivations (English)
├── PLAN_CN.md                  # 📋 Architecture design and mathematical derivations (简体中文)
├── TASK_SPEC.md                # 📝 Original task specifications
├── Makefile                    # ⚙️ Unified operational entry point (setup, auth, run, report, etc.)
├── requirements.txt            # 📦 Core Python dependency manifest
├── config.yaml                 # 🌟 Single Source of Truth configuration (visible, no hidden files)
├── README.md                   # 📖 User manual and operational instructions (English)
├── README_CN.md                # 📖 User manual and operational instructions (简体中文)
├── venv/                       # 🐍 Python 3.11+ isolated virtual environment
├── alpha_evolve/               # 🔒 Google Cloud official AlphaEvolve client library (read-only)
├── tests/                      # 🧪 Automated test suite (72 unit and integration tests, 100% passing)
│   ├── test_pipeline.py        # Pipeline DAG, channel binding, budget allocation tests
│   ├── test_evaluator.py       # Evaluator logic, monotonic speedup, and manifest tests
│   ├── test_bottleneck.py      # AST bottleneck detection and block injection tests
│   ├── test_quality.py         # NVIDIA FLIP, SSIM, and PSNR quality tests
│   ├── test_report.py          # HTML report rendering tests
│   ├── test_sanitize.py        # Delivery credential sanitization & restore tests
│   └── ...
├── inputs/                     # 📥 Input shader projects
│   ├── 01/                     # Single-pass project (with EVOLVE-BLOCK markers, Tokyo Rainy Night)
│   ├── 02_unmarked/            # Single-pass project (unmarked, validates AST analyzer)
│   └── 03/                     # Multi-pass complex project (Buffer A -> Buffer B -> Image, 6-face Cubemap)
│       ├── manifest.json       # Metadata, buffer dependencies, and channel input definitions
│       └── shaders/
│           ├── buffer_a.glsl   # Terrain Raymarching compute-intensive pass
│           ├── buffer_b.glsl   # Radial blur post-processing pass
│           └── image.glsl      # Composite display output pass
├── artifacts/                  # 📤 Optimization outputs and evolution artifacts (per project)
│   └── 03/                     # Output directory for sample project 03
│       ├── baseline_profile.json # Pipeline GPU timing breakdown and bottleneck metadata
│       ├── baseline_frames/    # Golden reference frame snapshots per pass
│       │   ├── buffer_a/
│       │   ├── buffer_b/
│       │   └── image/
│       ├── champion_buffer_a.glsl # Optimized champion shader for Buffer A
│       ├── champion_optimized.glsl # Clean optimized master shader (markers removed)
│       ├── evaluations.jsonl   # Comprehensive candidate evaluation log
│       ├── metrics.json        # Performance summary and pipeline breakdown metadata
│       └── report.html         # Standalone interactive HTML report
└── src/                        # 💻 Source code implementation
    ├── __init__.py
    ├── config.py               # Central config loader and dynamic sys.path hook
    ├── models.py               # Pydantic data models (candidates, evaluations, pipeline)
    ├── bottleneck.py           # AST bottleneck analyzer, marker parser, and code assembler
    ├── quality.py              # NVIDIA FLIP, SSIM, PSNR calculation and Sigmoid gate
    ├── browser_worker.py       # Playwright browser process controller and local HTTP server
    ├── evaluator_web/          # WebGL 2.0 evaluation frontend harness
    │   ├── index.html          # WebGL canvas host page
    │   ├── evaluator.js        # WebGL2 context setup and dynamic texture binding (2D & Cubemap)
    │   ├── gpuTimer.js         # EXT_disjoint_timer_query asynchronous query wrapper
    │   └── shadertoyCompat.js  # Shadertoy uniform injection, dynamic preamble, and shims
    ├── pipeline.py             # 🌟 Multi-pass pipeline DAG analysis, baseline profiling, and budget scheduler
    ├── evaluator.py            # Multi-objective fitness evaluator, dynamic gate, and diagnostic generator
    ├── report.py               # Standalone interactive HTML report rendering engine
    └── run_evolution.py        # AlphaEvolve main evolution controller CLI
```

---

## 4. 🧩 Detailed Component Specifications

### 4.1 Automated Bottleneck Identification & Marker Parsing (`src/bottleneck.py`)
- **Marker Syntax**: Supports `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` as well as standard C/GLSL comments `// EVOLVE-BLOCK-START` / `// EVOLVE-BLOCK-END`.
- **Automated Detection Algorithm**:
  If the input code lacks explicit markers, the analyzer executes:
  1. **AST & Syntax Scanning**: Traverses all function bodies and the primary entry points (`mainImage` / `main`).
  2. **Heuristic Hotspot Weight Calculation**:
     - Raymarching loops (loops invoking scene SDF functions such as `map()`, `scene()`, `castRay()`): weight +50.
     - Deeply nested or high-iteration loops (`for (... < 64 ...)` / `< 128`): weight +30.
     - Clusters of transcendental and expensive math operations (`sin`, `cos`, `pow`, `exp`, `atan`, `reflect`, `refract`): weight +20.
     - Fractal Brownian Motion (FBM) and iterative noise procedures: weight +25.
  3. **Automatic Delimiter Injection**: Selects the highest-scoring computational block, wraps it with `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END`, generates the seed code for AlphaEvolve, and injects bottleneck context into the LLM system prompt.

### 4.2 WebGL 2.0 Hardware Benchmarking & Multi-Type Texture Binding (`src/evaluator_web/` & `src/browser_worker.py`)
- **Hardware GPU Timer Queries**: Leverages the `EXT_disjoint_timer_query_webgl2` extension under Chromium (backed by native Metal or ANGLE). Following a 30-frame GPU warmup phase, 12 independent nanosecond timer queries are sampled, with the median value adopted as the definitive GPU execution time.
- **Comprehensive Texture Channel Binding (2D & 6-Face Cubemap)**:
  - Parses input types from `manifest.json`. When a channel is marked as `cubemap`, the harness dynamically allocates a WebGL `TEXTURE_CUBE_MAP` and binds seamless cube face textures across all six faces (`TEXTURE_CUBE_MAP_POSITIVE_X` through `NEGATIVE_Z`).
  - Automatically prepends GLSL shims for `samplerCube iChannelN`, ensuring functions such as `texture(iChannel3, reflect(...))` compile cleanly under WebGL 2.0.
- **Shadertoy Uniform Emulation**: Injects standard uniforms (`iResolution`, `iTime`, `iTimeDelta`, `iFrame`, `iMouse`, `iChannel0~3`).
- **Multi-Timestamp Visual Capture**: Captures high-resolution frame data at fixed time intervals ( $`t = [0.0, 1.5, 3.0, 4.5, 6.0]`$ seconds) to evaluate dynamic scene consistency.

### 4.3 Multi-Objective Fitness Arbitration Mathematical Model (`src/evaluator.py` & `src/quality.py`)

In automated shader evolution, the central challenge is the **bi-objective trade-off between computational execution speed and perceptual rendering fidelity**. Maximizing speed alone leads to degeneration (e.g., clearing the screen or omitting lighting calculations), whereas rigid step-function cutoffs stall search progress due to zero-gradient plateaus. To solve this, the framework implements a hybrid system combining **smooth continuous gradient guidance**, **multi-tier defensive gating**, and **strict monotonic Pareto progression**.

#### 1. Bi-Objective Mathematical Formulation
Let $`P`$ denote a candidate shader variant, $`T(P)`$ its physical GPU execution time in milliseconds, and $`T_{\text{baseline}}`$ the baseline GPU execution time. The hardware acceleration ratio (Speedup) is defined as:

```math
\text{Speedup}(P) = \frac{T_{\text{baseline}}}{T(P)}
```

Visual quality is assessed using the NVIDIA FLIP perceptual metric. Across the discrete temporal sampling set $`\mathcal{T} = \{t_1, t_2, \dots, t_N\}`$, the average perceptual fidelity between candidate frame $`I_{\text{cand}}(t)`$ and baseline frame $`I_{\text{base}}(t)`$ is:

```math
q(P) = 1.0 - \frac{1}{\lvert \mathcal{T} \rvert} \sum_{t \in \mathcal{T}} \text{FLIP}_{\text{error}}\left(I_{\text{cand}}(t), I_{\text{base}}(t)\right)
```

Structural Similarity ($`\text{SSIM}(P)`$) and Peak Signal-to-Noise Ratio ($`\text{PSNR}(P)`$) are tracked as secondary diagnostics.

#### 2. Smooth Sigmoid Correctness Gate
To eliminate fitness discontinuities at threshold boundaries, a continuous nonlinear gating function $`G(q)`$ is formulated:

```math
G(q) = \frac{1}{1 + \exp\left(-k \cdot (q - \tau)\right)}
```

Where:
- $`\tau`$ is the perceptual quality threshold (default initial value: $`\tau = 0.980`$, representing 98% FLIP similarity);
- $`k`$ is the curve steepness factor ($`k = 50.0`$).
- **Function Properties**:
  - When $`q \ge \tau`$, $`G(q) \in [0.5, 1.0]`$, rapidly converging toward $`1.0`$;
  - When $`q < \tau`$, $`G(q)`$ decays smoothly but exponentially; when $`q < \tau - 0.05`$, $`G(q) < 0.08`$.

#### 3. Composite Fitness Formulation
For candidate variants that compile successfully and satisfy baseline validity, the composite fitness score is defined as:

```math
\text{Fitness}(P) = G(q(P)) \times \text{Speedup}(P)
```

- **Optimization Incentive**: When perceptual quality meets expectations ( $`q \ge \tau`$ ), $`G(q) \approx 1.0`$, making fitness directly proportional to hardware speedup and encouraging AlphaEvolve to maximize performance gains;
- **Fidelity Protection**: Any degradation of geometric boundaries or lighting models lowers $`q`$, drastically diminishing the $`G(q)`$ multiplier. Even variants with immense raw speedup receive a net fitness penalty if visual degradation occurs.

#### 4. Four-Tier Hierarchical Arbitration & Defensive Gating
The evaluation pipeline applies a four-tiered decision cascade:

| Tier | Candidate State | Decision Criteria | Fitness Score $`\text{Score}`$ | Action & Diagnostic Insights |
| :---: | :--- | :--- | :---: | :--- |
| **Tier 1** | **Compilation / Link Failure** | WebGL `compileOk == False` | $`\mathbf{-200.0}`$ | **Hard Rejection**. Extracts and cleans GLSL compiler error messages and line numbers, sending structured remediation prompts to Gemini. |
| **Tier 2** | **Severe Visual Degradation** | $`q < \tau`$ or $`G(q) < 0.1`$ | $`\mathbf{-100.0 - 100 \times (1 - q)}`$ | **Hard Rejection**. Does not update Champion. Dispatches FLIP, SSIM, and PSNR metrics to Gemini, highlighting artifact locations to constrain mutation variance. |
| **Tier 3** | **No Effective Modification** | Code hash identical to baseline | $`\mathbf{1.0}`$ | Assigns neutral score; prevents pollution of the Champion pool. |
| **Tier 4** | **Valid Optimized Variant** | `compileOk` and $`q \ge \tau`$ | $`G(q) \times \text{Speedup}`$ | **Accepted**. Stores frame captures, GPU timings, and metrics into the Champion candidate pool. |

#### 5. Adaptive Threshold Dynamic Relaxation
For highly complex shaders where a 98% FLIP threshold is excessively stringent, an adaptive failure counter $`C_{\text{fail}}`$ is maintained:
- If $`N_{\text{patience}} = 10`$ consecutive candidates are rejected solely because their FLIP score lies within $`[0.950, 0.980)`$, the threshold $`\tau`$ is dynamically relaxed to $`\tau_{\text{relaxed}} = 0.950`$ (95%);
- This prevents evolutionary stagnation on intricate shaders while maintaining a strict 95% perceptual baseline.

#### 6. Monotonic Pareto Champion Rule (Zero Performance Regression)
To guarantee that the evolutionary process never degrades runtime performance:
- **Necessary and Sufficient Condition for Champion Promotion**: A candidate variant is accepted as a new Champion if and only if:

```math
\text{Candidate Accepted} \quad \land \quad \text{Speedup}(P) > 1.0
```

- **Anti-Regression Safeguard**: If a candidate variant achieves near-perfect fidelity (e.g., $`\text{FLIP} = 0.9998`$) but introduces extra branching or arithmetic that increases execution time (e.g., $`\text{Speedup} = 0.594\times`$), it is **strictly rejected as a Champion**. The baseline code retains its status, ensuring delivered code is always strictly faster than or equal to the original baseline.
- **Pareto Selection**: Among all candidates meeting $`\text{Speedup} > 1.0`$, the variant with the highest overall $`\text{Fitness}`$ is preserved as the final deliverable.

---

## 4.4 Multi-Pass Pipeline Topology & Approach 2 Cascaded Evolution (`src/pipeline.py`)

#### 1. Cross-Channel Pipeline Data Structures
For multi-pass rendering pipelines commonly found in Shadertoy and WebGL (e.g., `Buffer A` terrain rendering → `Buffer B` radial blur → `Image` screen composite), uniform abstractions are defined:
- **`PassInfo`**: Encapsulates pass name, source path, code string, 4 channel input bindings (2D or Cubemap), upstream buffer dependencies, baseline timing, champion timing, and speedup ratio.
- **`Pipeline`**: Encapsulates the complete rendering DAG, implementing Kahn's algorithm for topological sorting (`get_topological_order()`) and breaking temporal Ping-Pong self-dependencies.

#### 2. Full Pipeline Baseline Profiling (`make baseline`)
- Launches the local WebGL2 hardware harness, sequentially profiling GPU milliseconds $`T_i`$ for each pass;
- Calculates total frame time $`T_{\text{frame}} = \sum_{i=1}^{M} T_i`$ and baseline framerate $`\text{FPS} = \frac{1000}{T_{\text{frame}}}`$;
- Determines pass overhead percentage: $`W_i = \frac{T_i}{T_{\text{frame}}} \times 100\%`$;
- Tags the pass with $`\max(T_i)`$ as the `CORE BOTTLENECK`, persisting results to `artifacts/<project>/baseline_profile.json`.

#### 3. Approach 2: Dependency-Aware Cascaded Multi-Pass Evolution
- **Weighted Budget Allocation (`allocate_pass_budget`)**:
  Given a total generation budget $`B`$, lightweight passes ( $`W_i < 5\%`$ ) are skipped to conserve LLM budget. The remaining budget is partitioned proportionally according to execution weights $`W_i`$ (if $`B \le 2`$, 100% of the budget is concentrated on the primary bottleneck pass).
- **Topological Cascade & Forward Context Propagation**:
  Evolution proceeds sequentially through the topological sort. When an upstream pass (e.g., Buffer A) completes and yields an optimized Champion, its interface signatures and optimized routines are injected as context into the prompts for downstream passes (e.g., Buffer B, Image).
- **Total Pipeline Speedup & Energy Reduction**:

```math
\text{Pipeline Speedup} = \frac{\sum_{i=1}^M T_{\text{baseline}, i}}{\sum_{i=1}^M T_{\text{champion}, i}}
```

```math
\text{Energy Reduction} = \max\left(0, \left(1.0 - \frac{\sum_{i=1}^M T_{\text{champion}, i}}{\sum_{i=1}^M T_{\text{baseline}, i}}\right)\right) \times 100\%
```

---

### 4.5 Interactive HTML Report Generator (`src/report.py`)
Running `make report` produces a standalone HTML file (`artifacts/<project_id>/report.html`):
1. **Executive Metrics Scorecard**: Displays Baseline GPU time, Optimized GPU time, Speedup, FLIP similarity, and estimated energy reduction.
2. **Multi-Pass Pipeline Breakdown**: Interactive cards showing pass paths, line counts, baseline timing, percentage overhead, optimized timing, and per-pass speedup.
3. **Source Code Diff Visualizer**: Side-by-side color-coded diff highlighting added, modified, and eliminated GLSL instructions.
4. **Engineering Improvements Summary**: Highlights specific algorithmic and shader optimizations applied (loop clamping, fast inverse square root expansions, transcendental approximations, register pressure relief).
5. **Convergence Trajectory Curves**: Vector SVG visualization of Best-So-Far speedup alongside candidate scatter distributions.
6. **Visual Inspection Gallery**: Pixel-level comparisons of golden reference frames against champion outputs across all sampled timestamps.

---

### 4.6 Makefile Command Reference

| Target | Options | Core Functionality | Example |
| :--- | :--- | :--- | :--- |
| `make setup` | None | Creates Python `venv`, installs dependencies and Playwright Chromium, validates `config.yaml` | `make setup` |
| `make auth` | None | Authenticates with Google Cloud ADC (`gcloud auth application-default login`) | `make auth` |
| `make baseline` | `PROJECT`, `SHADER` | **Full Pipeline Profiling**: Profiles all passes, outputs breakdown and bottleneck, generates `baseline_profile.json` (or single pass if `SHADER=` is set) | `make baseline PROJECT=03`<br>`make baseline PROJECT=03 SHADER=shaders/buffer_b.glsl` |
| `make run` | `PROJECT`, `PROGRAMS`, `SHADER` | **Launches Evolution**: Multi-pass projects default to Approach 2 cascaded evolution; single pass if `SHADER=` is provided | `make run PROJECT=03 PROGRAMS=50`<br>`make run PROJECT=01 PROGRAMS=50` |
| `make report` | `PROJECT` | Compiles and exports the self-contained interactive HTML optimization report | `make report PROJECT=03` |
| `make profile` | `PROJECT` | Runs static AST bottleneck analyzer, displaying code lines and hotspot scores | `make profile PROJECT=03` |
| `make test` | None | Runs automated unit and integration tests (72 tests, 100% passing) | `make test` |
| `make mask` | None | **Delivery Sanitization**: Masks credentials across configs and docs with placeholders | `make mask` |
| `make mask-dry` | None | **Sanitization Preview**: Dry-run preview of files and occurrences to be masked | `make mask-dry` |
| `make clean` | None | Removes Python bytecode caches and temporary artifacts | `make clean` |

---

## 5. 🗓️ Implementation & Delivery Retrospective

| Phase | Milestone | Scope & Completed Deliverables | Key Artifacts |
| :--- | :--- | :--- | :--- |
| **Phase 1** | Environment & Unified Config | Established Python 3.11 venv, unified configuration into single source of truth `config.yaml`. | `config.yaml`, `venv/` |
| **Phase 2** | Evaluation Harness & Textures | WebGL 2.0 hardware timer queries, 6-face Cubemap binding, and dynamic preamble compatibility shims. | `src/evaluator_web/`, `browser_worker.py` |
| **Phase 3** | Quality Gates & Multi-Objective Arbitration | NVIDIA FLIP integration, smooth Sigmoid gating, four-tier arbitration, and monotonic speedup guarantee. | `src/quality.py`, `src/evaluator.py` |
| **Phase 4** | Pipeline Topology & Cascaded Evolution | DAG dependency resolution (`src/pipeline.py`), `make baseline` pipeline profiling, Approach 2 cascaded evolution loop. | `src/pipeline.py`, `src/run_evolution.py` |
| **Phase 5** | Reporting & Test Suite | HTML report with Multi-Pass Breakdown; 72 automated tests passing; end-to-end verification. | `src/report.py`, `tests/` |

---

## 6. Verification & Acceptance Criteria

1. **Environment & Dependencies**: `make setup` executes reliably; Playwright drives local Chromium leveraging Metal/ANGLE WebGL 2.0 hardware acceleration.
2. **GCP & AlphaEvolve Compatibility**: Seamlessly communicates with Google Cloud Gemini Enterprise and the official AlphaEvolve runtime using credentials from `config.yaml`.
3. **Multi-Pass & Channel Asset Support**:
   - Accurately renders multi-pass shaders with 2D textures and 6-face Cubemaps (e.g., Project 03 ValleyRace).
   - `make baseline PROJECT=03` outputs clear pass overhead breakdowns and flags the primary bottleneck.
4. **Approach 2 Cascaded Optimization Effectiveness**:
   - Allocates evolution budgets proportionally to baseline costs, evolves passes along the topological order, and passes upstream Champion contracts forward.
   - Enforces strict monotonicity: only candidates with $`\text{Speedup} > 1.0`$ can become Champions, preventing performance regressions.
5. **Automated Testing**: Complete test suite (`make test`) passes with 100% success rate across all 72 tests.
6. **Report Quality**: `make report` produces an interactive, single-file HTML report with pipeline breakdowns, source diffs, and visual metrics viewable offline in any browser.
