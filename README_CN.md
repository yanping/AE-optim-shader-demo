# Google Cloud AlphaEvolve Shader Optimization Framework

[English](README.md) | **简体中文**

基于 **Google Cloud AlphaEvolve** 与 **Playwright WebGL 2.0 硬件加速环境** 的高性能片元着色器（Fragment Shader / GLSL）闭环演化优化系统。

本项目针对任意输入的复杂着色器（如高负载 Raymarching、SDF 距离场、分形噪声等），在严格保障人眼感知渲染画质（**NVIDIA FLIP 相似度 ≥ 98%**）的前提下，通过 Google Cloud AlphaEvolve 调度 Gemini 大模型驱动代码重构与演化，最小化真实 GPU 硬件耗时，实现自动化性能极致压榨。

> 📘 **架构设计与理论推导**：
> - 完整系统设计方案、多 Pass 渲染拓扑与多目标适应度仲裁数学模型详见 [PLAN_CN.md](PLAN_CN.md)（英文版请见 [PLAN.md](PLAN.md)）。

---

## 1. 目录规范与文件清单

```text
shader-optim-test/
├── Makefile                     # 自动化命令入口 (setup, auth, baseline, run, report, profile, test, mask)
├── config.yaml                  # 🌟 唯一全局配置文件 (可见、自解释、单一真实源)
├── requirements.txt             # 项目核心依赖清单
├── PLAN.md                      # 项目完整设计架构与多目标适应度仲裁推导 (English)
├── PLAN_CN.md                   # 项目完整设计架构与多目标适应度仲裁推导 (简体中文)
├── README.md                    # 项目完整使用说明与操作指南 (English)
├── README_CN.md                 # 项目完整使用说明与操作指南 (简体中文)
├── alpha_evolve/                # Google Cloud AlphaEvolve 官方核心代码 (只读)
├── scripts/                     # 运维与工程化交付脚本
│   └── mask_credentials.py     # 🔒 自动化项目交付脱敏工具 (无硬编码敏感信息，纯标准库)
├── inputs/                      # 待优化的着色器项目输入目录 <== 用户从这里导入shader代码
│   ├── 01/                      # 单 Pass 项目 (含雨夜东京 Shader)
│   ├── 02_unmarked/             # 单 Pass 项目 (无标记，用于测试自动瓶颈挖掘)
│   └── 03/                      # 多 Pass 复杂项目 (Buffer A -> Buffer B -> Image，带 6 面 Cubemap)
├── src/                         # 本项目核心实现
│   ├── bottleneck.py            # 瓶颈分析、标记提取与代码重组器
│   ├── browser_worker.py        # Playwright Chromium WebGL2 本地工作进程
│   ├── config.py                # config.yaml 解析加载器与动态 sys.path 注入
│   ├── evaluator.py             # 多目标评估器与自适应画质门控
│   ├── evaluator_web/           # WebGL2 前端基准测试 Harness 页面与着色器兼容层
│   ├── models.py                # Pydantic 遥测数据与配置模型
│   ├── pipeline.py              # 🌟 多 Pass 管线拓扑解析、基线开销剖析与级联预算调度
│   ├── quality.py               # NVIDIA FLIP、SSIM、PSNR 画质核算模块
│   ├── report.py                # HTML 演化报告渲染引擎 (支持 Pipeline Breakdown)
│   └── run_evolution.py         # Google Cloud AlphaEvolve 演化主控制器 CLI
├── artifacts/                   # 演化产物输出目录 (按项目 ID 分离)
│   └── 03/                      # 示例项目03的产物目录 (多通道管线)
│       ├── baseline_frames/     # 黄金基准帧快照 (各 Pass 子目录)
│       ├── baseline_profile.json # 全管线各 Pass 性能开销剖析文件
│       ├── champion_buffer_a.glsl # 各 Pass 优化后的代码
│       ├── champion_optimized.glsl # 最终优化后的主 Shader 代码 (已剔除标记)
│       ├── evaluations.jsonl    # 历代评估记录全量 JSONL
│       ├── metrics.json         # 性能摘要与管线分解元数据
│       └── report.html          # 全自包含交互式 HTML 报告
└── tests/                       # 自动化单元测试套件 (72 项测试)
```

---

## 2. 前置准备与环境设置

### 2.1 操作系统与基础软件要求
- **操作系统**: macOS (Apple Silicon / Intel) 或 Linux (具备 GPU 硬件加速及 Chrome 运行环境)。
- **Python**: Python 3.11+。
- **Playwright 浏览器驱动**: 需安装 Playwright Chromium，支持 WebGL 2.0 硬件渲染管线与 `EXT_disjoint_timer_query_webgl2` 扩展（执行物理 GPU 微秒级纳秒级计时）。
- **GNU Make**: 自动化工作流工具 (`make --version`)。
- **Google Cloud SDK**: `gcloud` CLI（用于 GCP 凭证 ADC 鉴权与 API 交互）。

### 2.2 创建 Python 虚拟环境与安装依赖 (首次运行必须执行)
> [!IMPORTANT]
> **交付前置说明**：为避免依赖冲突与体积冗余，本项目交付时不包含 `venv/` 虚拟环境目录。在您首次运行任何演化任务或测试前，**必须先在项目根目录下创建虚拟环境并安装依赖**！
>
> 提供了以下两种方式（任选其一即可）：
>
> **方式一：通过 Makefile 一键自动化初始化（强烈推荐）**
> ```bash
> make setup
> ```
> 该命令会自动检测并在当前根目录下创建 `venv` 虚拟环境、升级 pip、安装 `requirements.txt` 中的全部依赖包、自动安装 Playwright Chromium 浏览器内核并校验 `config.yaml`。
>
> **方式二：手动命令行分步执行**
> ```bash
> # 1. 确保使用 Python 3.11 或以上版本创建虚拟环境
> python3.11 -m venv venv
>
> # 2. 激活虚拟环境
> source venv/bin/activate
>
> # 3. 升级 pip 并安装项目核心依赖
> pip install --upgrade pip
> pip install -r requirements.txt
>
> # 4. 安装 Playwright 专用的无头 Chromium 浏览器驱动
> playwright install chromium
> ```

### 2.3 GCP 账号与 Gemini Enterprise APP 设置
1. **获取 Google Cloud 项目权限**：
   - 准备一个已开通结算账号的 Google Cloud Project（记下您的 `PROJECT_ID`）。
2. **启用 Discovery Engine API**：
   ```bash
   gcloud services enable discoveryengine.googleapis.com --project=<YOUR_GCP_PROJECT_ID>
   ```
3. **获取 Gemini Enterprise APP ID**：
   - 在 Google Cloud Console 的 Gemini Enterprise 控制台中创建或查看应用，获取 Engine / App ID（记下您的 `GE_APP_ID`）。
4. **IAM 权限配置**：
   - 运行账号需具备 **Discovery Engine Editor** (`roles/discoveryengine.editor`) 或管理员角色。
   - 官方权限设置指导可参考：[AlphaEvolve 环境与 API 访问设置文档](https://docs.cloud.google.com/gemini/enterprise/docs/alphaevolve/developer-guide/environment-and-api-access-setup?hl=zh-cn)。
5. **本地凭据鉴权 (ADC)**：
   ```bash
   make auth
   # 或手动运行：gcloud auth application-default login
   ```

---

## 3. 全局配置文件说明 (`config.yaml`)

项目所有设置统一在根目录 `config.yaml` 中管理，无隐藏配置文件。首次运行时请在 `config.yaml` 中填入您自己的 GCP 凭据：

```yaml
# 1. Google Cloud & Gemini Enterprise 凭据与服务配置
gcp:
  project_id: "<YOUR_GCP_PROJECT_ID>" # Enter your Google Cloud Project ID here
  location: "global"
  collection: "default_collection"
  ge_app_id: "<YOUR_GE_APP_ID>"       # Enter your Gemini Enterprise App/Engine ID here
  assistant: "default_assistant"
  base_url: "discoveryengine.googleapis.com"
  alpha_evolve_path: "./alpha_evolve"   # 可改为更新后的alpha_evolve库路径

# 2. 演化控制与超参数设置 (串行 GPU 评测)
evolution:
  max_programs_generated: 50    # 需按自己的预算设置
  max_programs_evaluated: 50    # 需按自己的预算设置
  concurrency: 1                # 采样并发数
  worker_concurrency: 1         # 评估并发数 (物理 GPU 必须为 1，杜绝多任务竞争与抖动)
  parallel_evaluation: false    # 串行化硬件评测
  idle_timeout_s: 120

# 3. Gemini 大模型生成权重混合配比
models:
  - name: "gemini-3.5-flash"
    weight: 0.70
  - name: "gemini-3.1-pro-preview"
    weight: 0.30

# 4. 感知画质门控阈值
quality:
  flip_initial_threshold: 0.980    # NVIDIA FLIP 初始画质门限 (≥ 98%)
  flip_relaxed_threshold: 0.950    # 自适应放宽后的最低画质门限 (≥ 95%)
  relaxation_patience: 10          # 连续多少代无达标变体时触发自适应放宽
  min_ssim_threshold: 0.950        # SSIM 最低辅助门槛

# 5. WebGL 2.0 本地硬件基准测试 Harness 设置
benchmark:
  port: 8099                       # 本地评估静态服务端口
  headless: true                   # 是否以无头模式运行 Playwright Chromium
  resolution: [1280, 720]          # 测速画布基准分辨率 [宽, 高]
  sample_times: [0.0, 1.5, 3.0, 4.5, 6.0]  # 采样的着色器运行时间戳序列 (秒)
  warmup_frames: 30                # GPU 预热渲染帧数 (避开管线编译开销)
  timed_samples: 12                # 每次取样的硬件 GPU 计时样本数 (取中位数)
  playwright_channel: "chrome"     # 浏览器通道 (chrome / chromium)
```

---

## 4. 快速上手与 Makefile 核心工作流

### 4.1 常用 Makefile 命令参考

| 命令 | 说明 | 示例 |
| :--- | :--- | :--- |
| **`make setup`** | 初始化 Python venv、安装依赖包与 Playwright 浏览器，校验 `config.yaml`（首次必须执行） | `make setup` |
| **`make auth`** | 调起浏览器执行 Google Cloud ADC 认证 (`gcloud auth application-default login`) | `make auth` |
| **`make baseline`** | **全管线性能剖析**：对项目下所有 Pass 执行 GPU 硬件测速，输出耗时占比清单与核心瓶颈 | `make baseline PROJECT=03` |
| **`make baseline` (单着色器)** | 仅针对指定单一 shader 文件捕获基准帧与 GPU 耗时 | `make baseline PROJECT=03 SHADER=shaders/buffer_a.glsl` |
| **`make run`** | 连接 Google Cloud AlphaEvolve 执行闭环演化优化（支持方案 2 级联多 Pass 拓扑演化） | `make run PROJECT=03 PROGRAMS=50` |
| **`make run` (指定着色器)** | 仅针对多通道项目中的某一特定 Pass 执行优化演化 | `make run PROJECT=03 SHADER=shaders/buffer_a.glsl PROGRAMS=50` |
| **`make profile`** | 静态/AST 分析着色器代码性能瓶颈，输出建议优化的代码区间 | `make profile PROJECT=03` |
| **`make report`** | 生成并查看自包含交互式 HTML 优化报告（含管线 Breakdown） | `make report PROJECT=03` |
| **`make test`** | 执行全量自动化单元与集成测试套件 (包含 72 个测试项) | `make test` |
| **`make mask`** | **项目交付脱敏**：一键将全项目配置文件、文档中的个人 `project_id`、`ge_app_id` 脱敏遮盖为占位符 | `make mask` |
| **`make mask-dry`** | **脱敏预览**：预览脱敏匹配的文件与出现频次（Dry-run），不实际修改文件 | `make mask-dry` |
| **`make clean`** | 清除 Python 字节码缓存和测试缓存 | `make clean` |

### 4.2 典型执行流程示例

```bash
# 1. 环境初始化与云端认证
make setup
make auth

# 2. 全管线基准测试：评估项目所有 Pass 耗时并确定核心瓶颈
make baseline PROJECT=03

# 3. 运行演化优化
# 场景 A: 级联演化——对多 Pass 项目执行全管线拓扑级联优化（自动按开销分配预算、前序 Champion 固化传递）
make run PROJECT=03 PROGRAMS=50

# 场景 B: 单 Shader 演化——仅指定优化某一特定 Pass
make run PROJECT=03 SHADER=shaders/buffer_a.glsl PROGRAMS=50

# 场景 C: 单 Pass 项目演化（如 01）
make run PROJECT=01 PROGRAMS=50

# 4. 生成与查看全自包含 HTML 报告
make report PROJECT=03
```

---

## 5. 🌟 核心特性与架构亮点

1. **真实硬件级微秒计时 (Hardware GPU Timing)**: （可换成自己的测速工具）
   - 基于 Playwright 驱动的独立 Chromium 实例，通过 WebGL 2.0 扩展 `EXT_disjoint_timer_query_webgl2` 执行纳秒/微秒级硬件时间戳轮询；
   - 彻底避免传统 CPU 端 `performance.now()` 因驱动排队与管线缓冲造成的测量误差。

2. **串行化硬件基准测速 (Serialized GPU Benchmarking)**:
   - 本地 GPU 测速采用串行单任务模式（`concurrency: 1`, `worker_concurrency: 1`, `parallel_evaluation: false`）；
   - 杜绝多浏览器页面并发争抢物理 GPU 命令队列和上下文切换带来的抖动，保证每次测量的加速比精准可复现。

3. **多目标适应度仲裁与感知画质门控 (Multi-Objective Fitness & NVIDIA FLIP Gate)**:
   - 集成 NVIDIA HPG 2020 官方 FLIP 算法，结合 Wang et al. 2004 结构相似度（SSIM）与峰值信噪比（PSNR）；
   - 引入平滑 Sigmoid 门控函数 $`G(q) = \frac{1}{1 + \exp(-50(q - \tau))}`$，综合适应度 $`\text{Fitness} = G(q) \times \text{Speedup}`$，在保障画质的前提下最大化提速；
   - **严格单调提速准则（No Performance Regression）**：仅当候选变体通过画质门控且 $`\text{Speedup} > 1.0`$ 时方可入选新 Champion，杜绝性能倒退；
   - **四级分级防御与诊断反馈**：编译失败（-200 分）与画质劣化（-100 分）自动提取编译器诊断与视觉差异作为 Diagnostic Insights 回传大模型，指导下一代精准自我修正；
   - **自适应动态松弛（Adaptive Relaxation）**：若连续 10 代无变体满足 98% 门槛，自动自适应放宽至 95% 门槛。

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

## 6. 🔒 项目交付脱敏与隐私安全防护 (Delivery Sanitization)

为了防止在将项目打包交付或开源共享时泄漏个人 Google Cloud 凭据（`project_id`、`ge_app_id`、GCP 项目编号等），本项目内置了专业的自动化脱敏工具：

### 6.1 一键脱敏工作流
在向客户交付或提交开源代码前，推荐按以下两步快速操作：

1. **执行脱敏脚本**（自动将 `config.yaml`、说明文档与配置文件中的敏感凭据替换为 `<YOUR_GCP_PROJECT_ID>` 和 `<YOUR_GE_APP_ID>`）：
   ```bash
   make mask
   # 若仅预览将被替换的文件和频次（Dry-run），可运行：
   make mask-dry
   ```
   > 💡 **安全设计**：脱敏脚本 [`scripts/mask_credentials.py`](scripts/mask_credentials.py) 本身**绝无任何硬编码敏感信息**，采用动态上下文探测，且仅依赖 Python 3 原生标准库，即使未激活或已删除虚拟环境亦可直接执行。并在 `config.yaml` 中为客户补充了友好的填入指引注释。

2. **恢复/注入自定义凭据（可选）**：
   若需为新环境快速批量注入新凭据，可运行恢复模式：
   ```bash
   python3 scripts/mask_credentials.py --restore --project-id <NEW_PROJECT_ID> --app-id <NEW_GE_APP_ID>
   ```

3. **清理本地虚拟环境目录**：
   ```bash
   rm -rf venv/
   ```
   接收方获取项目后，仅需依照本文档 2.2 节运行 `make setup` 即可一键恢复虚拟环境、安装依赖与浏览器驱动。
