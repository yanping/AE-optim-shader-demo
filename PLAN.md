# 📋 AlphaEvolve Shader Optimization Tool - 项目实施规划方案 (PLAN.md)

本规划文档依据 [`TASK_SPEC.md`](TASK_SPEC.md) 的要求制定，旨在基于原项目（`~/Projects/shader-optim/`）中积累的 Shader 优化技术，参考 Google Cloud AlphaEvolve 官方样例（[https://github.com/Google-Cloud-AI/alphaevolve-on-googlecloud/tree/main/examples](https://github.com/Google-Cloud-AI/alphaevolve-on-googlecloud/tree/main/examples)）的工程架构与规范，抽取出核心算法与系统模块，构建一个面向**任意输入 Shader 项目**（包含复杂单 Pass 与多 Pass 渲染流水线）的自动化闭环演化优化工具集。

---

## 1. 🎯 项目定位与核心目标

1. **核心逻辑解耦与工具化**：
   从针对单一演示场景的旧工程中，解耦并抽取出通用的 Shader 演化闭环模块：
   - **本地设备硬件评估器**：基于 Playwright + WebGL 2.0（利用 `EXT_disjoint_timer_query_webgl2` 硬件定时器）实现微秒/纳秒级精准测速，杜绝 CPU 调度抖动。
   - **全管线渲染剖析与级联演化（Cascaded Multi-pass）**：深度支持跨通道 FBO 渲染流水线（如 `Buffer A -> Buffer B -> Image`），自动解析拓扑依赖图（DAG），提供全管线 GPU 耗时占比清单（Breakdown）与核心瓶颈定位；依开销自动加权分配搜索预算，级联向前传递 Champion 接口契约，实现全管线联合提速。
   - **权威画质门控协议**：基于 NVIDIA FLIP (ACM TOG / HPG 2020) 算法作为第一指标，结合 Wang 2004 SSIM 与 PSNR，建立自适应动态放宽门控（初始 98% → 动态降级 95%）。
   - **多目标适应度仲裁体系**：平衡硬件加速比（Speedup Ratio）与平滑画质门控乘子，严厉惩罚编译失败、语法错误及画面崩溃，严格遵循单调提速准则（ $`\text{Speedup} > 1.0`$ ）以确保无性能回退。
   - **云端原生闭环演化与反馈学习**：纯粹直连 Google Cloud AlphaEvolve（基于 Gemini 3.5 Flash / 3.1 Pro 混合大模型推理），并在评估器中生成精准的 Diagnostic Insights 结构化诊断建议，指导大模型下一代自我修正。
   - **自动瓶颈识别与标定**：支持用户显式使用 `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` 标注待优化代码块；若未标注，系统自动运行 AST 静态语法与热点分析，精准定位计算瓶颈（如 Raymarching 主步进循环、重度 FBM 噪声、高频超越函数等）并自动包裹标注。
   - **候选变体择优与成果导出**：自动筛选 Pareto 最优解与最高综合得分冠军代码（Champion），导出管线各 Pass 及核心瓶颈代码。

2. **标准化工程交付标准**：
   - 仿照 `alphaevolve-on-googlecloud/examples` 体系结构，以根目录对应样例工程，提供标准统一的 `Makefile`（`setup`、`auth`、`run`、`report`、`baseline`、`profile` 等目标）。
   - 统一单一配置源：所有 GCP 凭证、模型混合权重、演化超参数与 WebGL 硬件测试参数统一收敛于显式可见的 [`config.yaml`](config.yaml)。
   - 提供可视化 HTML 报告生成命令 `make report`，生成包含多通道管线性能分解表、演化收敛轨迹曲线、代码 Diff、技术改进点中文摘要、黄金参考帧 vs 冠军帧比对的一体化独立报告。
   - 严格保护外部官方库 `alpha_evolve/`，不修改任何文件，并通过配置项自由配置路径。

---

## 2. 🏗️ 系统整体架构与数据流图

```text
+---------------------------------------------------------------------------------+
| 1. 输入层 (inputs/<project_id>/)                                                 |
|    - 着色器源码 (shaders/*.glsl)                                                 |
|    - manifest.json: 定义多 Pass (Buffer A, Buffer B, Image) 与通道贴图 (2D/Cubemap) |
+---------------------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
| 2. 管线拓扑与瓶颈分析模块 (src/pipeline.py & src/bottleneck.py)                   |
|    - 拓扑依赖解算: 解析跨 Buffer 依赖，构建有向无环图 (DAG)                     |
|    - 瓶颈识别与标定: 检查/注入 # EVOLVE-BLOCK (Raymarching / 重度计算热点)        |
|    - 全量基准剖析 (make baseline): 测速各 Pass，输出开销清单与 CORE BOTTLENECK    |
+---------------------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
| 3. 云端演化引擎: Google Cloud AlphaEvolve (src/run_evolution.py)                |
|    - 连接 Google Cloud Gemini Enterprise App & Discovery Engine                 |
|    - 预算动态调度: 根据各 Pass 耗时权重分摊演化代数 (allocate_pass_budget)      |
|    - 方案 2 级联演化: 按拓扑序演化，前序 Champion 固化并向前传递接口契约       |
+---------------------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
| 4. 本地硬件评估闭环 (src/evaluator.py + src/browser_worker.py)                   |
|    - Playwright Chromium WebGL 2.0 (Headless Metal/ANGLE 原生硬件渲染)          |
|    - EXT_disjoint_timer_query 硬件时间戳纳秒/微秒级精确测速                     |
|    - 权威画质评估: NVIDIA FLIP (HPG 2020) + SSIM + PSNR                         |
|    - 多目标适应度仲裁 (Speedup x Sigmoid Gate, 严格单调性保证)                  |
|    - 结构化反馈诊断生成 (Diagnostic Insights 反馈至 Gemini 大模型指导迭代)       |
+---------------------------------------------------------------------------------+
                                      |
                                      v
+---------------------------------------------------------------------------------+
| 5. 交付物与产物导出 (artifacts/<project_id>/)                                    |
|    - 阶段与主冠军代码 (champion_<pass>.glsl & champion_optimized.glsl)          |
|    - 管线基线剖析报告 (baseline_profile.json) 与逐 Pass 参考帧                  |
|    - 全量演化评估日志 (evaluations.jsonl) 与综合量化指标 (metrics.json)          |
|    - 多通道交互式 HTML 报告 (report.html，集成 Multi-Pass Pipeline Breakdown)     |
+---------------------------------------------------------------------------------+
```

---

## 3. 📂 交付目录结构与模块划分

```text
shader-optim-test/
├── PLAN.md                     # 📋 本规划方案文档 (含多目标适应度仲裁算法推导)
├── TASK_SPEC.md                # 📝 原始任务需求说明文档
├── Makefile                    # ⚙️ 统一操作入口 (setup, auth, run, report, profile, baseline, test, clean)
├── requirements.txt            # 📦 项目 Python 依赖清单
├── config.yaml                 # 🌟 唯一全局可见配置文件 (单真实源，无隐藏 .env)
├── README.md                   # 📖 用户使用指南与架构说明文档
├── venv/                       # 🐍 Python 3.11 独立虚拟环境
├── alpha_evolve/               # 🔒 Google Cloud 官方 AlphaEvolve 客户端库 (严禁修改)
├── tests/                      # 🧪 自动化测试套件 (包含 71 项单元测试，100% 通过)
│   ├── test_pipeline.py        # 管线拓扑、通道识别、级联预算与剖析测试
│   ├── test_evaluator.py       # 评估器、单调提速判定与项目解析测试
│   ├── test_bottleneck.py      # AST 瓶颈挖掘与标记注入测试
│   ├── test_quality.py         # NVIDIA FLIP、SSIM 与 PSNR 画质测试
│   ├── test_report.py          # HTML 演化报告渲染测试
│   └── ...
├── inputs/                     # 📥 待优化着色器项目集
│   ├── 01/                     # 单 Pass 项目 (含 EVOLVE-BLOCK 标签，雨夜东京 Shader)
│   ├── 02_unmarked/            # 单 Pass 项目 (无标记，用于验证自动瓶颈分析)
│   └── 03/                     # 多 Pass 复杂项目 (Buffer A -> Buffer B -> Image，带 6 面 Cubemap)
│       ├── manifest.json       # 项目元数据、跨 Buffer 依赖与通道贴图定义
│       └── shaders/
│           ├── buffer_a.glsl   # 地形 Raymarching 核心计算 Pass
│           ├── buffer_b.glsl   # 模糊后处理 Pass
│           └── image.glsl      # 最终合成输出 Pass
├── artifacts/                  # 📤 优化成果与进化产物目录 (按项目 ID 分离)
│   └── 03/                     # 示例项目 03 产物目录
│       ├── baseline_profile.json # 全管线各 Pass 耗时占比与瓶颈剖析元数据
│       ├── baseline_frames/    # 各 Pass 黄金参考帧图像快照
│       │   ├── buffer_a/
│       │   ├── buffer_b/
│       │   └── image/
│       ├── champion_buffer_a.glsl # Buffer A 优化后的 Champion 代码
│       ├── champion_optimized.glsl # 整帧主瓶颈 Champion 代码 (已剔除标记)
│       ├── evaluations.jsonl   # 历代评估记录全量 JSONL
│       ├── metrics.json        # 性能摘要与管线分解元数据 (pipeline_breakdown)
│       └── report.html         # 全自包含交互式 HTML 综合优化报告
└── src/                        # 💻 核心逻辑源代码目录
    ├── __init__.py
    ├── config.py               # config.yaml 统一配置解析器
    ├── models.py               # Pydantic 数据模型 (候选指标、评估记录、管线元数据)
    ├── bottleneck.py           # 智能瓶颈分析器、EVOLVE-BLOCK 解析与代码重组器
    ├── quality.py              # NVIDIA FLIP、SSIM、PSNR 画质门控与 Sigmoid 抑制函数
    ├── browser_worker.py       # Playwright 浏览器进程控制与本地 HTTP 静态服务
    ├── evaluator_web/          # WebGL 2.0 评估前端 Harness
    │   ├── index.html          # WebGL 画布承载页
    │   ├── evaluator.js        # WebGL2 上下文初始化、动态贴图绑定 (2D & 6面 Cubemap)
    │   ├── gpuTimer.js         # EXT_disjoint_timer_query 异步查询封装
    │   └── shadertoyCompat.js  # Shadertoy Uniforms 注入、动态 Preamble 与预编译包装
    ├── pipeline.py             # 🌟 多 Pass 管线拓扑解析、基线开销剖析与级联预算调度
    ├── evaluator.py            # 多目标适应度评估器、自适应画质门控与诊断生成
    ├── report.py               # 可视化 HTML 报告渲染引擎 (支持 Pipeline Breakdown)
    └── run_evolution.py        # Google Cloud AlphaEvolve 演化主控制器入口
```

---

## 4. 🧩 核心功能模块详细设计

### 4.1 智能瓶颈识别与代码块解析 (`src/bottleneck.py`)
- **标记支持**：兼容 `# EVOLVE-BLOCK-START` / `# EVOLVE-BLOCK-END` 以及 C/GLSL 风格注释 `// EVOLVE-BLOCK-START` / `// EVOLVE-BLOCK-END`。
- **自动瓶颈检测算法**：
  若输入代码未包含标记，则激活分析引擎：
  1. **语法与 AST 扫描**：扫描所有函数体及主渲染函数（`mainImage` / `main`）。
  2. **启发式热点权重计算**：
     - Raymarching 循环权重（检测 `for`/`while` 内部调用 SDF 场景函数 `map()` / `scene()` / `castRay()`）：权重 +50。
     - 嵌套循环与高步长循环（`for (... < 64 ...)` / `< 128`）：权重 +30。
     - 超越函数与高开销数学运算密集体（`sin`, `cos`, `pow`, `exp`, `atan`, `reflect`, `refract`）：权重 +20。
     - 分形噪声与 FBM 函数（迭代累加噪声）：权重 +25。
  3. **自动包裹标注**：选取得分最高的核心计算块，自动注入 `# EVOLVE-BLOCK-START` 与 `# EVOLVE-BLOCK-END`，生成供 AlphaEvolve 优化的可演化种子代码，并将瓶颈分析原因注入提示词 context 中。

### 4.2 本地 WebGL 2.0 硬件测速与多类型纹理支持 (`src/evaluator_web/` & `src/browser_worker.py`)
- **硬件级 GPU 定时器**：使用 Chrome/Chromium Metal/ANGLE 后端的 `EXT_disjoint_timer_query_webgl2` 扩展，执行预热（30 帧）后进行 12 次独立纳秒级查询，取中位数（Median GPU Time），彻底消除 CPU 调度抖动。
- **全通道纹理资产绑定 (2D & 6 面 Cubemap)**：
  - 自动解析 `manifest.json` 各通道绑定类型。当检测到通道为 `cubemap` 时，动态创建 WebGL `TEXTURE_CUBE_MAP`，并为 6 个面（`TEXTURE_CUBE_MAP_POSITIVE_X` ~ `NEGATIVE_Z`）填充对应无缝立方体纹理数据；
  - 动态在 Shader 头部注入重载兼容宏，支持 `samplerCube iChannelN`，彻底解决 `texture(iChannel3, reflect(...))` 在 WebGL2 环境下签名不匹配的报错。
- **动态 Shadertoy 兼容垫片**：自动注入 `iResolution`, `iTime`, `iTimeDelta`, `iFrame`, `iMouse`, `iChannel0~3`。
- **多时间点快照捕获**：在固定时间序列采样（ $`t = [0.0, 1.5, 3.0, 4.5, 6.0]`$ 秒），导出高质量图像 DataURL，用于多帧全局对比。

### 4.3 多目标适应度仲裁方法详细设计 (`src/evaluator.py` & `src/quality.py`)

在着色器自动化优化任务中，核心挑战在于**“计算性能提升”与“视觉感知保真度”之间的双目标权衡（Bi-Objective Trade-off）**。单纯追求速度极易导致模型偷工减料（如直接清空画面、跳过复杂光影），而死板的硬阈值截断又会导致演化过程因梯度缺失而停滞。为此，本项目设计了一套兼具**平滑连续导引**、**分级防御硬截断**与**严格单调性保证**的多目标适应度仲裁体系。

#### 1. 双目标优化数学建模
设待优化着色器变体为 $`P`$，其在真实 GPU 硬件上的运行耗时为 $`T(P)`$（毫秒），基准代码耗时为 $`T_{\text{baseline}}`$。其加速比（Speedup）定义为：

```math
\text{Speedup}(P) = \frac{T_{\text{baseline}}}{T(P)}
```

视觉保真度基于 NVIDIA FLIP 算法核算。在时间序列采样集合 $`\mathcal{T} = \{t_1, t_2, \dots, t_N\}`$ 下，变体渲染帧与黄金基准帧的平均感知相似度为：

```math
q(P) = 1.0 - \frac{1}{\lvert \mathcal{T} \rvert} \sum_{t \in \mathcal{T}} \text{FLIP}_{\text{error}}\left(I_{\text{cand}}(t), I_{\text{base}}(t)\right)
```

同时辅助计算结构相似度 $`\text{SSIM}(P)`$ 与峰值信噪比 $`\text{PSNR}(P)`$。

#### 2. 平滑 Sigmoid 画质门控函数 (Smooth Correctness Gate)
为了避免传统阶跃函数在阈值边缘造成的适应度震荡，定义平滑非线性门控函数 $`G(q)`$：

```math
G(q) = \frac{1}{1 + \exp\left(-k \cdot (q - \tau)\right)}
```

其中：
- $`\tau`$ 为当前画质门限，默认初始值为 $`\tau = 0.980`$（即 98% FLIP 相似度）；
- $`k`$ 为陡度因子，取 $`k = 50.0`$。
- **特性分析**：
  - 当 $`q \ge \tau`$ 时，$`G(q) \in [0.5, 1.0]`$，且迅速逼近 $`1.0`$；
  - 当 $`q < \tau`$ 时，$`G(q)`$ 发生剧烈但平滑的指数级衰减；当 $`q < \tau - 0.05`$ 时，$`G(q) < 0.08`$。

#### 3. 综合适应度评分公式 (Composite Fitness Score)
对于通过基础编译与初步画质检查的有效候选变体，其综合适应度得分定义为：

```math
\text{Fitness}(P) = G(q(P)) \times \text{Speedup}(P)
```

- **优化导向**：在画质满足要求（ $`q \ge \tau`$ ）时，$`G(q) \approx 1.0`$，适应度直接正比于硬件加速比，驱动 AlphaEvolve 最大化压榨 GPU 耗时；
- **破损惩罚**：一旦变体改动破坏了几何轮廓或光照方程导致 $`q`$ 轻微下降，门控乘子 $`G(q)`$ 会迅速缩水，哪怕该变体拥有极高加速比，其最终得分也会大幅低于画质合格的变体。

#### 4. 四级分级仲裁与硬截断防御机制 (Hierarchical Arbitration)
系统设立四层仲裁防御链，严密过滤各类异常变体：

| 等级 | 变体状态 | 判定准则 | 适应度得分 $`\text{Score}`$ | 处置动作与反馈 (Diagnostic Insights) |
| :---: | :--- | :--- | :---: | :--- |
| **Tier 1** | **编译与链接失败** | WebGL `compileOk == False` | $`\mathbf{-200.0}`$ | **直接硬拒绝**。提取并清洗底层 GLSL 编译器具体错误行号与堆栈原因，格式化为带有具体修改建议的诊断信息反馈给 Gemini 大模型。 |
| **Tier 2** | **严重画质劣化** | $`q < \tau`$ 或 $`G(q) < 0.1`$ | $`\mathbf{-100.0 - 100 \times (1 - q)}`$ | **直接硬拒绝**。不更新 Champion。向大模型反馈当前 FLIP、SSIM、PSNR 数值，并指出几何轮廓或颜色失真，提示模型收敛变异幅度。 |
| **Tier 3** | **无实际修改** | 代码与 Baseline 散列一致 | $`\mathbf{1.0}`$ | 赋予基准中性得分，不污染 Champion 池。 |
| **Tier 4** | **有效优化变体** | `compileOk` 且 $`q \ge \tau`$ | $`G(q) \times \text{Speedup}`$ | **采纳并入库**。记录详细帧快照、硬件时间戳与各项画质指标，进入 Champion 择优池。 |

#### 5. 自适应动态阈值放宽策略 (Adaptive Threshold Relaxation)
针对场景极其复杂、初始 98% 门槛极难跨越的特种 Shader，系统维护连续拒绝计数器 $`C_{\text{fail}}`$：
- 若连续 $`N_{\text{patience}} = 10`$ 次候选变体均因 FLIP 处于 $`[0.950, 0.980)`$ 之间被拒，系统自动将阈值 $`\tau`$ 动态下调至 $`\tau_{\text{relaxed}} = 0.950`$（即 95%）；
- 该机制有效防止了高难度着色器搜索陷入僵局，同时牢牢守住 95% 的底线感知质量。

#### 6. Pareto 冠军遴选与严格单调提速准则 (Monotonic Pareto Champion Rule)
为了确保演化优化过程的**严格单调性（No Performance Regression）**：
- **准入充要条件**：一个候选变体被遴选为新一代 Champion（或覆写阶段产物）必须**同时满足**：

```math
\text{Candidate Accepted} \quad \land \quad \text{Speedup}(P) > 1.0
```

- **反退化保护**：如果某一候选变体画质极佳（例如 $`\text{FLIP} = 0.9998`$），但由于大模型增加了分支或计算导致实际耗时增加（例如 $`\text{Speedup} = 0.594\times`$），系统虽然在日志中记录其有效性，但**绝对不将其推举为 Champion**，基线代码始终保持 Champion 地位，确保交付产物 100% 优于或等于原始基线。
- **Pareto 优中选优**：在所有 $`\text{Speedup} > 1.0`$ 的候选变体中，选取 $`\text{Fitness}`$ 得分最高的个体作为最终交付代码。

---

### 4.4 多 Pass 管线拓扑与方案 2 级联演化设计 (`src/pipeline.py`)

#### 1. 跨通道渲染流水线数据结构
针对 Shadertoy / WebGL 常见的多通道渲染管线（如 `Buffer A` 渲染地形 → `Buffer B` 径向模糊 → `Image` 屏幕输出），定义统一抽象：
- **`PassInfo`**：封装单个 Pass 的名称、文件路径、代码、4 个通道的输入类型（2D 或 Cubemap）、依赖的上游 Buffer 列表、基线耗时、Champion 耗时与加速比。
- **`Pipeline`**：封装整帧管线，提供基于入度的 Kahn 算法求解有向无环图拓扑序列（`get_topological_order()`），自动切断 Ping-Pong 自依赖历史环路。

#### 2. 全量基准性能剖析 (`make baseline`)
- 启动本地硬件 WebGL2 评估容器，依次独立测量各 Pass 的精确 GPU 毫秒数 $`T_i`$；
- 计算整帧管线总耗时：$`T_{\text{frame}} = \sum_{i=1}^{M} T_i`$ 以及整帧帧率 $`\text{FPS} = \frac{1000}{T_{\text{frame}}}`$；
- 计算各 Pass 耗时占比：$`W_i = \frac{T_i}{T_{\text{frame}}} \times 100\%`$；
- 自动标定 $`\max(T_i)`$ 为核心瓶颈（`CORE BOTTLENECK`），并导出 `artifacts/<project>/baseline_profile.json`。

#### 3. 方案 2：依赖感知多文件级联演化 (Cascaded Multi-pass Evolution)
- **按需加权预算分配 (`allocate_pass_budget`)**：
  若总演化预算为 $`B`$，对于开销极小的轻量 Pass（ $`W_i < 5\%`$ ），不浪费大模型预算；将预算按各 Pass 耗时权重 $`W_i`$ 比例动态划分（若 $`B \le 2`$，100% 预算倾斜给核心瓶颈 Pass）。
- **拓扑级联向前传递**：
  按照拓扑序依次对各 Pass 启动 AlphaEvolve 优化会话。当上游 Pass（如 Buffer A）优化完成并产生 Champion 后，系统将前序代码与接口契约作为 Context 注入后序 Pass（如 Buffer B、Image）的提示词中，指导大模型在知晓输入源特性的前提下进行下游联合优化。
- **整帧全管线加速比核算**：

```math
\text{Pipeline Speedup} = \frac{\sum_{i=1}^M T_{\text{baseline}, i}}{\sum_{i=1}^M T_{\text{champion}, i}}
```

```math
\text{Energy Reduction} = \max\left(0, \left(1.0 - \frac{\sum_{i=1}^M T_{\text{champion}, i}}{\sum_{i=1}^M T_{\text{baseline}, i}}\right)\right) \times 100\%
```

---

### 4.5 可视化演化报告生成器 (`src/report.py`)
执行 `make report` 时自动生成独立 HTML 文件（`artifacts/<project_id>/report.html`）：
1. **指标看板 (Executive Scorecard)**：展示 Baseline GPU 耗时、Optimized GPU 耗时、加速比（Speedup）、FLIP 相似度得分、节省功耗百分比。
2. **多通道渲染管线分解表 (Multi-Pass Pipeline Breakdown)**：以可视化卡片展示各 Pass 的文件路径、行数、基线耗时、耗时占比、优化后耗时及单 Pass 加速比。
3. **种子 vs 冠军代码 Diff 审查**：集成直观的代码比对高亮视图，标出删除与新增指令。
4. **技术改进点摘要**：中文提炼关键优化手法（如步长裁剪、超越函数近似、无分化展开等）。
5. **收敛历史轨迹图表**：绘制 Best-So-Far 峰值加速折线与全体候选散点分布。
6. **画质检验画廊**：多采样帧的原版 vs 冠军渲染图并排或滑块对比。

---

### 4.6 Makefile 目标体系

| 目标命令 | 参数选项 | 核心功能说明 | 典型执行示例 |
| :--- | :--- | :--- | :--- |
| `make setup` | 无 | 自动创建 `venv` 独立环境，安装 Python 依赖库与 Chromium 浏览器内核，校验 `config.yaml` | `make setup` |
| `make auth` | 无 | 执行 Google Cloud ADC 认证 (`gcloud auth application-default login`) | `make auth` |
| `make baseline` | `PROJECT`, `SHADER` | **全管线性能剖析**：测量管线所有 Pass 耗时，输出开销占比、瓶颈标定与 `baseline_profile.json`；若传入 `SHADER=` 则测速单一着色器 | `make baseline PROJECT=03`<br>`make baseline PROJECT=03 SHADER=shaders/buffer_b.glsl` |
| `make run` | `PROJECT`, `PROGRAMS`, `SHADER` | **启动闭环演化优化**：多 Pass 项目默认采用方案 2 级联演化；若传入 `SHADER=` 则演化指定单一着色器 | `make run PROJECT=03 PROGRAMS=50`<br>`make run PROJECT=01 PROGRAMS=50` |
| `make report` | `PROJECT` | 编译并导出自包含交互式 HTML 优化报告，输出可点击的本地文件链接 | `make report PROJECT=03` |
| `make profile` | `PROJECT` | 运行 AST 静态瓶颈分析器，打印各 Pass 的瓶颈代码行区间与热点评分 | `make profile PROJECT=03` |
| `make test` | 无 | 运行自动化单元测试套件（覆盖管线、评估器、画质、瓶颈、报告各模块，共 71 项测试） | `make test` |
| `make clean` | 无 | 清理 Python 字节码缓存与临时文件 | `make clean` |

---

## 5. 🗓️ 实施与交付状态回顾

| 阶段 | 核心任务 | 完成内容与状态 | 核心产物 |
| :--- | :--- | :--- | :--- |
| **Phase 1** | 环境与配置统一化 | 建立 Python 3.11 虚拟环境，构建单真实源 `config.yaml`。 | `config.yaml`, `venv/` |
| **Phase 2** | 评估底座与纹理拓展 | WebGL2 纳秒级硬件计时、6 面 Cubemap 立方体纹理绑定与动态 Preamble 兼容层开发。 | `src/evaluator_web/`, `browser_worker.py` |
| **Phase 3** | 画质门控与多目标仲裁 | NVIDIA FLIP 算法集成、Sigmoid 平滑门控函数、四级分级防御、严格单调提速准则。 | `src/quality.py`, `src/evaluator.py` |
| **Phase 4** | 多 Pass 管线拓扑与级联演化 | `src/pipeline.py` 拓扑依赖解析、`make baseline` 全量剖析升级、方案 2 级联演化闭环落地。 | `src/pipeline.py`, `src/run_evolution.py` |
| **Phase 5** | 报告增强与全量测试 | HTML 报告集成多通道 Breakdown 卡片；71 项自动化测试 100% 通过；实机云端闭环验证。 | `src/report.py`, `tests/test_pipeline.py` |

---

## 6. 验证与验收准则

1. **环境与依赖**：`make setup` 一键就绪，Playwright 能够正常驱动本地 Chromium 调用 Metal/ANGLE WebGL2 原生硬件加速。
2. **GCP 与 AlphaEvolve 兼容**：使用 `config.yaml` 凭证与端点配置，无缝连接 Google Cloud Gemini Enterprise 官方 AlphaEvolve 运行时。
3. **多 Pass 与通道支持**：
   - 能正确加载并渲染包含 2D 纹理与 6 面 Cubemap 的多通道着色器（如 Project 03 ValleyRace）。
   - `make baseline PROJECT=03` 输出清晰的各 Pass 耗时占比清单与核心瓶颈提示。
4. **方案 2 级联优化有效性**：
   - 自动按各 Pass 基线开销分配演化预算，按拓扑序逐级演化，前序 Champion 契约向前传递。
   - 严格保证单调性：只有 $`\text{Speedup} > 1.0`$ 的合格变体才允许当选 Champion，杜绝性能倒退。
5. **自动化测试**：全量执行 `make test`，72 项单元测试全部通过。
6. **报告质量**：`make report` 生成的 HTML 报告具备交互式管线分解表、代码 Diff 与量化指标展示，可直接单文件在浏览器中离线打开浏览。
