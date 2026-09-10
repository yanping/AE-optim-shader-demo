# Google Cloud AlphaEvolve Shader Optimization Framework

基于 **Google Cloud AlphaEvolve** 与 **Playwright WebGL 2.0 硬件加速环境** 的高性能片元着色器（Fragment Shader / GLSL）闭环演化优化系统。

本项目针对任意输入的复杂着色器（如高负载 Raymarching、SDF 距离场、分形噪声等），在严格保障人眼感知渲染画质（**NVIDIA FLIP 相似度 $\ge 98\%$**）的前提下，通过 Google Cloud AlphaEvolve 调度 Gemini 大模型驱动代码重构与演化，最小化真实 GPU 硬件耗时，实现自动化性能极致压榨。

---

## 🌟 核心特性与架构亮点

1. **真实硬件级微秒计时 (Hardware GPU Timing)**: （可换成自己的测速工具）
   - 基于 Playwright 驱动的独立 Chromium 实例，通过 WebGL 2.0 扩展 `EXT_disjoint_timer_query_webgl2` 执行纳秒/微秒级硬件时间戳轮询。
   - 彻底避免传统 CPU 端 `performance.now()` 因驱动排队与管线缓冲造成的测量误差。

2. **串行化硬件基准测速 (Serialized GPU Benchmarking)**:
   - 本地 GPU 测速采用串行单任务模式（`concurrency: 1`, `worker_concurrency: 1`, `parallel_evaluation: false`）。
   - 杜绝多浏览器页面并发争抢物理 GPU 命令队列和上下文切换带来的抖动，保证每次测量的加速比精准可复现。

3. **多目标适应度仲裁与感知画质门控 (Multi-Objective Fitness & NVIDIA FLIP Gate)**:
   - 集成 NVIDIA HPG 2020 官方 FLIP 算法，结合 Wang et al. 2004 结构相似度（SSIM）与峰值信噪比（PSNR）；
   - 引入平滑 Sigmoid 门控函数 $G(q) = \frac{1}{1 + \exp(-50(q - \tau))}$，综合适应度 $\text{Fitness} = G(q) \times \text{Speedup}$，在保障画质的前提下最大化提速；
   - **严格单调提速准则（No Performance Regression）**：仅当候选变体通过画质门控且 $\text{Speedup} > 1.0$ 时方可入选新 Champion，杜绝性能倒退；
   - **四级分级防御与诊断反馈**：编译失败（-200 分）与画质劣化（-100 分）自动提取编译器诊断与视觉差异作为 Diagnostic Insights 回传大模型，指导下一代精准自我修正；
   - **自适应动态松弛（Adaptive Relaxation）**：若连续 10 代无变体满足 $98\%$ 门槛，自动自适应放宽至 $95\%$ 门槛。

4. **全类型纹理与 6 面 Cubemap 立方体贴图支持**:
   - 自动解析 `manifest.json` 各通道输入类型，支持 2D 贴图与 6 面 Cubemap 立方体贴图（`TEXTURE_CUBE_MAP`）；
   - WebGL2 环境下动态注入重载兼容垫片，完美支持复杂光追着色器对环境贴图的反射/折射采样（`texture(iChannel3, reflect(...))`）。

5. **统一可见配置文件 (Single Source of Truth: `config.yaml`)**:
   - 所有 GCP 凭证、AlphaEvolve 超参数、模型权重、画质门控与基准测试参数均统一收拢于项目根目录下显式可见的 `config.yaml` 中，无隐藏 `.env` 文件，结构清晰、单一真实源。

6. **智能瓶颈分析与动态锚定 (Automatic Bottleneck Detection)**:
   - 若着色器代码包含 `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END`（或 `//`、`/*` 格式），系统将严格限制演化范围在指定代码块内；
   - 若未显式标注，系统自动触发 AST / 静态启发式瓶颈分析器，定位核心 Raymarching Loop 或重度计算循环并自动标记注入。

7. **全管线渲染剖析与级联演化优化 (Multi-Pass Cascaded Pipeline Optimization)**:
   - 自动解析 `manifest.json` 或着色器文件目录，构建跨通道渲染流水线（如 `Buffer A -> Buffer B -> Image`）；
   - `make baseline` 自动对管线下所有着色器执行微秒级耗时剖析，输出占比清单（Breakdown）、核心瓶颈 Pass 与 `baseline_profile.json`；支持传入 `SHADER=` 仅测试单一着色器；
   - 采用 **方案 2（依赖感知级联演化）**：依据拓扑排序与耗时权重自动分摊大模型搜索预算，优先攻克核心瓶颈 Pass，固化 Champion 变体并向前传递上下文依赖，实现整帧全流水线联合提速。

8. **全自包含交互式 HTML 演化报告 (Interactive HTML Report)**:
   - `make report` 一键生成无外部网络依赖的自包含单文件报告，集成：
     - 核心性能指标看板（加速比、Baseline vs Champion 耗时、FLIP 画质、能耗削减比例）；
     - 多通道渲染管线性能分解表（Multi-Pass Pipeline Breakdown）；
     - 优化要点与技术改进中文摘要；
     - 黄金参考帧 vs 冠军输出帧 Base64 像素级对比预览；
     - 演化收敛历史轨迹（矢量 SVG 曲线）；
     - 种子代码与优化代码行级彩色 Diff；
     - 历代所有候选变体评估判定明细表。

---

## 📁 目录规范

```text
shader-optim-test/
├── alpha_evolve/              # Google Cloud AlphaEvolve 官方核心代码 (只读)
├── artifacts/                 # 演化产物输出目录 (按项目 ID 分离)
│   └── 03/                    # 示例项目03的产物目录 (多通道管线)
│       ├── baseline_frames/   # 黄金基准帧快照 (各 Pass 子目录)
│       ├── baseline_profile.json # 全管线各 Pass 性能开销剖析文件
│       ├── champion_buffer_a.glsl # 各 Pass 优化后的代码
│       ├── champion_optimized.glsl # 最终优化后的主 Shader 代码 (已剔除标记)
│       ├── evaluations.jsonl  # 历代评估记录全量 JSONL
│       ├── metrics.json       # 性能摘要与管线分解元数据
│       └── report.html        # 全自包含交互式 HTML 报告
├── config.yaml                # 🌟 唯一全局配置文件 (可见、自解释、单一真实源)
├── inputs/                    # 待优化的着色器项目输入目录 <== 用户从这里导入shader代码
│   ├── 01/                    # 单 Pass 项目 (含雨夜东京 Shader)
│   ├── 02_unmarked/           # 单 Pass 项目 (无标记，用于测试自动瓶颈挖掘)
│   └── 03/                    # 多 Pass 复杂项目 (Buffer A -> Buffer B -> Image，带 6 面 Cubemap)
├── src/                       # 本项目核心实现
│   ├── bottleneck.py          # 瓶颈分析、标记提取与代码重组器
│   ├── browser_worker.py      # Playwright Chromium WebGL2 本地工作进程
│   ├── config.py              # config.yaml 解析加载器与动态 sys.path 注入
│   ├── evaluator.py           # 多目标评估器与自适应画质门控
│   ├── evaluator_web/         # WebGL2 前端基准测试 Harness 页面与着色器兼容层
│   ├── models.py              # Pydantic 遥测数据与配置模型
│   ├── pipeline.py            # 🌟 多 Pass 管线拓扑解析、基线开销剖析与级联预算调度
│   ├── quality.py             # NVIDIA FLIP、SSIM、PSNR 画质核算模块
│   ├── report.py              # HTML 演化报告渲染引擎 (支持 Pipeline Breakdown)
│   └── run_evolution.py       # Google Cloud AlphaEvolve 演化主控制器 CLI
├── tests/                     # 自动化单元测试套件 (71 项测试)
├── Makefile                   # 统一构建与执行入口
├── requirements.txt           # 生产与测试依赖项
└── PLAN.md                    # 项目完整设计与执行规划
```

---

## ⚙️ 配置文件说明 (`config.yaml`)

项目配置统一收敛在根目录 `config.yaml` 中，主要包含五个区块：

```yaml
# 1. Google Cloud 凭证与端点
gcp:
  project_id: "<填入你的project_id>"
  ge_app_id: "<填入你的Gemini Enterprise APP id>"
  alpha_evolve_path: "./alpha_evolve"   # 可改为更新后的alpha_evolve库的路径

# 2. 演化超参数 (串行 GPU 评测)
evolution:
  max_programs_generated: 50  # 需按自己的预算设置
  max_programs_evaluated: 50  # 需按自己的预算设置
  concurrency: 1              # 采样并发数
  worker_concurrency: 1       # 评估并发数 (物理 GPU 必须为 1)
  parallel_evaluation: false  # 串行化评测，杜绝硬件资源争抢
  idle_timeout_s: 120

# 3. 大模型混合配比
models:
  - name: "gemini-3.5-flash"
    weight: 0.70
  - name: "gemini-3.1-pro-preview"
    weight: 0.30

# 4. 画质门控
quality:
  flip_initial_threshold: 0.980
  flip_relaxed_threshold: 0.950
  relaxation_patience: 10

# 5. WebGL2 硬件基准测试
benchmark:
  port: 8099
  resolution: [1280, 720]
  sample_times: [0.0, 1.5, 3.0, 4.5, 6.0]
  warmup_frames: 30
  timed_samples: 12
```

---

## 🚀 快速上手

### 1. 环境初始化

```bash
# 自动创建 Python 3.11 虚拟环境、安装依赖、安装 Playwright Chromium 浏览器并核验 config.yaml
make setup
```

### 2. Google Cloud 授权

```bash
make auth
```

### 3. 运行演化优化流程

```bash
# 1. 级联演化：对多 Pass 项目（如 03）执行全管线拓扑级联优化（自动按开销分配预算、前序 Champion 固化传递）
make run PROJECT=03 PROGRAMS=50

# 2. 单 Shader 演化：仅指定优化某一特定 Pass
make run PROJECT=03 SHADER=shaders/buffer_a.glsl PROGRAMS=50

# 3. 单 Pass 项目演化（如 01）
make run PROJECT=01 PROGRAMS=50
```

### 4. 查看 HTML 可视化报告

```bash
make report PROJECT=03
```

控制台将输出生成的报告链接，例如：
`./artifacts/03/report.html`，双击或在浏览器中打开即可查看完整的交互式报告（包含多通道渲染管线性能分解表）。

---

## 🛠️ 常用 Makefile 命令参考

| 命令 | 说明 | 示例 |
| :--- | :--- | :--- |
| `make setup` | 初始化 Python venv、安装 pip 依赖及 Playwright 浏览器，校验 config.yaml | `make setup` |
| `make auth` | 执行 Google Cloud ADC 认证 (`gcloud auth application-default login`) | `make auth` |
| `make baseline` | **全管线性能剖析**：对项目下所有 Pass 执行 GPU 测速，输出耗时占比清单与核心瓶颈 | `make baseline PROJECT=03` |
| `make baseline` (单着色器) | 仅针对指定单一 shader 文件捕获基准帧与 GPU 耗时 | `make baseline PROJECT=03 SHADER=shaders/buffer_a.glsl` |
| `make profile` | 静态/AST 分析着色器代码性能瓶颈，输出建议优化的代码区间 | `make profile PROJECT=03` |
| `make run` | 连接 Google Cloud AlphaEvolve 执行闭环演化优化（支持方案 2 级联多 Pass 演化） | `make run PROJECT=03 PROGRAMS=50` |
| `make report` | 生成/展示自包含交互式 HTML 优化报告（含管线 Breakdown） | `make report PROJECT=03` |
| `make test` | 执行全量单元测试套件 (包含 71 个测试项) | `make test` |
| `make clean` | 清除 Python 字节码缓存和测试缓存 | `make clean` |
