"""
Shader Project Pipeline and Multi-Pass Dependency Management
Analyzes project manifests, GLSL passes, texture bindings, and dependency graphs
for multi-pass shader rendering and cascaded optimization.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from .bottleneck import analyze_and_mark_bottlenecks, has_evolve_block
from .config import INPUTS_DIR
from .quality import data_url_to_ndarray

logger = logging.getLogger("shader_evolve.pipeline")


@dataclass
class PassInfo:
    """Metadata and source representation of an individual render pass."""
    name: str
    rel_path: str
    abs_path: Path
    code: str
    channel_types: List[str] = field(default_factory=lambda: ["2d", "2d", "2d", "2d"])
    dependencies: List[str] = field(default_factory=list)
    output_type: str = "buffer"  # "buffer" or "screen"
    lines_count: int = 0
    has_evolve_block: bool = False
    seed_code: str = ""
    bottleneck_info: Dict[str, Any] = field(default_factory=dict)
    baseline_gpu_ms: float = 0.0
    baseline_fps: float = 0.0
    cost_percent: float = 0.0
    baseline_frames: List[Any] = field(default_factory=list)
    champion_code: str = ""
    champion_gpu_ms: float = 0.0
    champion_speedup: float = 1.0
    champion_flip: float = 1.0

    def __post_init__(self):
        if not self.lines_count:
            self.lines_count = len(self.code.splitlines())
        self.has_evolve_block = has_evolve_block(self.code)
        if self.has_evolve_block:
            self.seed_code = self.code
        else:
            marked, info = analyze_and_mark_bottlenecks(self.code)
            self.seed_code = marked
            self.bottleneck_info = info


@dataclass
class Pipeline:
    """Represents a complete multi-pass shader rendering project."""
    project_id: str
    proj_dir: Path
    title: str
    passes: List[PassInfo]
    manifest_data: Dict[str, Any] = field(default_factory=dict)

    def get_pass(self, name_or_file: str) -> Optional[PassInfo]:
        """Finds a pass by exact name, relative path, or filename."""
        name_or_file_lower = name_or_file.lower().replace("\\", "/")
        for p in self.passes:
            if (p.name.lower() == name_or_file_lower or
                p.rel_path.lower().replace("\\", "/") == name_or_file_lower or
                p.abs_path.name.lower() == Path(name_or_file).name.lower()):
                return p
        return None

    def get_topological_order(self) -> List[PassInfo]:
        """
        Returns passes in topological dependency order (upstream passes first).
        If cyclic (e.g. ping-pong buffer with previous frame), falls back to manifest pass order.
        """
        name_to_pass = {p.name: p for p in self.passes}
        visited: Set[str] = set()
        order: List[PassInfo] = []

        def visit(p_name: str, path_stack: Set[str]):
            if p_name in visited or p_name not in name_to_pass:
                return
            if p_name in path_stack:
                # Cycle detected (e.g. history buffer self-reference)
                return
            path_stack.add(p_name)
            current_pass = name_to_pass[p_name]
            for dep in current_pass.dependencies:
                if dep != p_name and dep in name_to_pass:
                    visit(dep, path_stack)
            path_stack.remove(p_name)
            visited.add(p_name)
            order.append(current_pass)

        for p in self.passes:
            visit(p.name, set())

        # Ensure any unvisited passes are included in original manifest order
        for p in self.passes:
            if p not in order:
                order.append(p)

        return order

    def get_upstream_passes(self, pass_name: str) -> List[PassInfo]:
        """Returns all passes that the specified pass depends on."""
        target = self.get_pass(pass_name)
        if not target:
            return []
        upstream = []
        for dep_name in target.dependencies:
            p = self.get_pass(dep_name)
            if p and p not in upstream:
                upstream.append(p)
        return upstream


def load_pipeline(
    project_id: Optional[str] = None,
    target_shader: Optional[str] = None
) -> Pipeline:
    """
    Discovers project directory and constructs a Pipeline representation.
    Extracts multi-pass definitions, channels, textures, and dependencies.
    """
    if not INPUTS_DIR.exists():
        INPUTS_DIR.mkdir(parents=True, exist_ok=True)

    if not project_id:
        subdirs = [d.name for d in INPUTS_DIR.iterdir() if d.is_dir() and not d.name.startswith(".")]
        if subdirs:
            project_id = sorted(subdirs)[0]
        else:
            project_id = "01"

    proj_dir = INPUTS_DIR / project_id
    if not proj_dir.exists():
        raise FileNotFoundError(f"Input project directory does not exist: {proj_dir}")

    manifest_path = proj_dir / "manifest.json"
    manifest_data: Dict[str, Any] = {}
    title = project_id

    if manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest_data = json.load(f)
                title = manifest_data.get("title", project_id)
        except Exception as e:
            logger.warning(f"Failed to read manifest {manifest_path}: {e}")

    passes: List[PassInfo] = []
    textures = manifest_data.get("textures", {})

    # 1. Manifest-driven discovery
    if manifest_data and "passes" in manifest_data and manifest_data["passes"]:
        for p_info in manifest_data["passes"]:
            pass_file_rel = p_info.get("file")
            pass_name = p_info.get("name", Path(pass_file_rel).stem)
            pass_abs = proj_dir / pass_file_rel

            if not pass_abs.exists():
                logger.warning(f"Pass file declared in manifest not found: {pass_abs}")
                continue

            try:
                code = pass_abs.read_text(encoding="utf-8")
            except Exception as e:
                logger.error(f"Failed to read shader file {pass_abs}: {e}")
                continue

            # Determine channel_types and dependencies
            channel_types = ["2d", "2d", "2d", "2d"]
            dependencies: List[str] = []
            channels = p_info.get("channels", {})

            for slot_str, ch_info in channels.items():
                try:
                    slot_idx = int(slot_str)
                    if 0 <= slot_idx < 4:
                        ch_type = ch_info.get("type")
                        if ch_type == "buffer":
                            channel_types[slot_idx] = "2d"
                            dep_pass = ch_info.get("pass")
                            if dep_pass and dep_pass not in dependencies:
                                dependencies.append(dep_pass)
                        elif ch_type == "cubemap":
                            channel_types[slot_idx] = "cubemap"
                        elif ch_type == "texture":
                            tex_name = ch_info.get("texture")
                            if tex_name in textures and textures[tex_name].get("type") == "cubemap":
                                channel_types[slot_idx] = "cubemap"
                            else:
                                channel_types[slot_idx] = "2d"
                except (ValueError, TypeError):
                    pass

            # Fallback heuristic for cubemap sampling
            for i in range(4):
                if channel_types[i] != "cubemap":
                    cube_pattern = rf"texture\s*\(\s*iChannel{i}\s*,\s*(?:reflect\s*\(|vec3\s*\(|(?:rd|rayDir|viewDir|eyeDir)\s*[,\\)])"
                    if re.search(cube_pattern, code):
                        channel_types[i] = "cubemap"

            output_type = p_info.get("output", "buffer")
            passes.append(PassInfo(
                name=pass_name,
                rel_path=pass_file_rel,
                abs_path=pass_abs,
                code=code,
                channel_types=channel_types,
                dependencies=dependencies,
                output_type=output_type
            ))

    # 2. Filesystem fallback discovery (if no manifest or empty passes)
    if not passes:
        all_shaders = [
            f for f in sorted(list(proj_dir.glob("**/*.glsl")) + list(proj_dir.glob("**/*.frag")))
            if not any(part.startswith(".") or part.startswith("backup") for part in f.relative_to(proj_dir).parts)
        ]
        if not all_shaders:
            raise FileNotFoundError(f"No GLSL shader files found in {proj_dir}")

        for s_file in all_shaders:
            rel_path = str(s_file.relative_to(proj_dir))
            code = s_file.read_text(encoding="utf-8")
            channel_types = ["2d", "2d", "2d", "2d"]
            for i in range(4):
                cube_pattern = rf"texture\s*\(\s*iChannel{i}\s*,\s*(?:reflect\s*\(|vec3\s*\(|(?:rd|rayDir|viewDir|eyeDir)\s*[,\\)])"
                if re.search(cube_pattern, code):
                    channel_types[i] = "cubemap"

            name = s_file.stem
            passes.append(PassInfo(
                name=name,
                rel_path=rel_path,
                abs_path=s_file,
                code=code,
                channel_types=channel_types,
                dependencies=[],
                output_type="screen" if "image" in rel_path.lower() else "buffer"
            ))

    pipeline = Pipeline(
        project_id=project_id,
        proj_dir=proj_dir,
        title=title,
        passes=passes,
        manifest_data=manifest_data
    )

    # Filter to specific target shader if explicitly requested
    if target_shader:
        matched = pipeline.get_pass(target_shader)
        if matched:
            pipeline.passes = [matched]
        else:
            logger.warning(f"Requested target shader '{target_shader}' not matched; using full pipeline.")

    return pipeline


async def profile_pipeline(
    pipeline: Pipeline,
    worker: Any,
    sample_times: List[float],
    out_dir: Optional[Path] = None
) -> Dict[str, Any]:
    """
    Executes baseline GPU time profiling and reference frame capture for all passes
    in the pipeline in topological order.
    Calculates execution cost breakdown and identifies the core bottleneck pass.
    """
    logger.info("=" * 70)
    logger.info(f"📊 Capturing Golden Baseline for Pipeline: [{pipeline.project_id}] ({pipeline.title})")
    logger.info(f"📁 Passes to benchmark: {len(pipeline.passes)}")
    logger.info("=" * 70)

    for pass_info in pipeline.get_topological_order():
        logger.info(f"⏳ Benchmarking pass [{pass_info.name}] ({pass_info.rel_path}, {pass_info.lines_count} lines)...")
        res = await worker.evaluate_shader(
            glsl_code=pass_info.seed_code,
            sample_times=sample_times,
            channel_types=pass_info.channel_types
        )
        if not res.get("compileOk"):
            err_msg = res.get("compileError") or res.get("runtimeError") or "Unknown compile error"
            raise RuntimeError(f"Pass '{pass_info.name}' ({pass_info.rel_path}) baseline failed to compile: {err_msg}")

        pass_info.baseline_gpu_ms = float(res.get("gpuTimeMs", 16.67))
        pass_info.baseline_fps = 1000.0 / max(0.001, pass_info.baseline_gpu_ms)
        captured_frames_data = res.get("frames", [])
        pass_info.baseline_frames = [data_url_to_ndarray(f["dataUrl"]) for f in captured_frames_data]
        logger.info(f"   -> GPU Time: {pass_info.baseline_gpu_ms:.2f} ms ({pass_info.baseline_fps:.1f} FPS)")

    total_pipeline_gpu_ms = sum(p.baseline_gpu_ms for p in pipeline.passes)
    bottleneck_pass = max(pipeline.passes, key=lambda p: p.baseline_gpu_ms)

    for p in pipeline.passes:
        p.cost_percent = (p.baseline_gpu_ms / max(0.001, total_pipeline_gpu_ms)) * 100.0

    breakdown = {
        "project_id": pipeline.project_id,
        "title": pipeline.title,
        "total_pipeline_gpu_ms": round(total_pipeline_gpu_ms, 2),
        "total_pipeline_fps": round(1000.0 / max(0.001, total_pipeline_gpu_ms), 1),
        "bottleneck_pass": bottleneck_pass.name,
        "bottleneck_file": bottleneck_pass.rel_path,
        "passes": [
            {
                "name": p.name,
                "file": p.rel_path,
                "lines": p.lines_count,
                "gpu_ms": round(p.baseline_gpu_ms, 2),
                "fps": round(p.baseline_fps, 1),
                "cost_percent": round(p.cost_percent, 1),
                "channels": p.channel_types,
                "dependencies": p.dependencies,
                "is_bottleneck": (p.name == bottleneck_pass.name),
                "hotspot_type": p.bottleneck_info.get("hotspot_type", "Standard GLSL Pipeline")
            }
            for p in pipeline.passes
        ]
    }

    if out_dir:
        out_dir.mkdir(parents=True, exist_ok=True)
        profile_file = out_dir / "baseline_profile.json"
        with open(profile_file, "w", encoding="utf-8") as f:
            json.dump(breakdown, f, indent=2)
        logger.info(f"💾 Multi-Pass Baseline Profile Saved: {profile_file}")

    return breakdown


def allocate_pass_budget(pipeline: Pipeline, total_budget: int) -> Dict[str, int]:
    """
    Allocates candidate evolution budget across passes based on their relative GPU cost.
    For small budgets (<= 2), allocates entirely to the core bottleneck pass.
    For larger budgets, allocates proportionally to all passes with >= 5% cost share.
    """
    if not pipeline.passes:
        return {}

    bottleneck = max(pipeline.passes, key=lambda p: p.baseline_gpu_ms)

    if total_budget <= 2 or len(pipeline.passes) == 1:
        return {bottleneck.name: total_budget}

    # Filter passes with >= 5% of total pipeline GPU cost
    eligible = [p for p in pipeline.passes if p.cost_percent >= 5.0]
    if not eligible:
        eligible = [bottleneck]

    if len(eligible) == 1:
        return {eligible[0].name: total_budget}

    total_eligible_cost = sum(p.baseline_gpu_ms for p in eligible)
    allocations: Dict[str, int] = {}
    remaining = total_budget

    # Allocate proportionally, minimum 1 per eligible pass
    for p in eligible[:-1]:
        ratio = p.baseline_gpu_ms / max(0.001, total_eligible_cost)
        share = max(1, int(round(total_budget * ratio)))
        share = min(share, remaining - (len(eligible) - len(allocations) - 1))
        allocations[p.name] = share
        remaining -= share

    allocations[eligible[-1].name] = max(1, remaining)
    return allocations


def format_pipeline_breakdown(
    pipeline: Pipeline,
    hw_renderer: str = "WebGL2 GPU",
    timer_query: bool = True
) -> str:
    """Formats a beautiful terminal ASCII report of the multi-pass baseline profiling."""
    total_gpu_ms = sum(p.baseline_gpu_ms for p in pipeline.passes)
    total_fps = 1000.0 / max(0.001, total_gpu_ms)
    bottleneck = max(pipeline.passes, key=lambda p: p.baseline_gpu_ms)

    lines = [
        "=" * 70,
        f"📊 MULTI-PASS BASELINE PERFORMANCE BREAKDOWN | Project: [{pipeline.project_id}] ({pipeline.title})",
        f"📂 Project Directory: {pipeline.proj_dir}",
        f"🖥️ Hardware GPU Renderer: {hw_renderer}",
        f"⏱️ EXT_disjoint_timer_query_webgl2 Supported: {timer_query}",
        "=" * 70,
    ]

    for idx, p in enumerate(pipeline.passes):
        is_bn = (p.name == bottleneck.name)
        tag = " 🚨 [CORE BOTTLENECK]" if is_bn else ""
        lines.append(f"• [Pass {idx}] {p.name} ({p.rel_path} | {p.lines_count} lines):")
        lines.append(f"  ⏱️ GPU Time : {p.baseline_gpu_ms:.2f} ms ({p.cost_percent:.1f}%) | {p.baseline_fps:.1f} FPS{tag}")
        dep_str = f" (Depends on: {', '.join(p.dependencies)})" if p.dependencies else ""
        lines.append(f"  🔗 Channels : {p.channel_types}{dep_str}")
        hs = p.bottleneck_info.get("hotspot_type")
        sc = p.bottleneck_info.get("score")
        if hs:
            lines.append(f"  🎯 Hotspot  : {hs} (Score: {sc})")

    lines.append("-" * 70)
    lines.append(f"🏆 TOTAL PIPELINE FRAME GPU TIME : {total_gpu_ms:.2f} ms ({total_fps:.1f} FPS)")
    lines.append(f"🎯 PRIMARY OPTIMIZATION TARGET   : {bottleneck.name} ({bottleneck.rel_path})")
    lines.append("=" * 70)

    return "\n".join(lines)
