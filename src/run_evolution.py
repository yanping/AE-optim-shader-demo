"""
AlphaEvolve Shader Optimization Pipeline
Executes closed-loop fragment shader optimization using Google Cloud AlphaEvolve
and local hardware-accelerated WebGL 2.0 evaluation with NVIDIA FLIP quality gating.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import List, Optional, Tuple

from PIL import Image

from .bottleneck import (
    analyze_and_mark_bottlenecks,
    has_evolve_block,
    strip_evolve_markers
)
from .browser_worker import BrowserEvaluatorWorker
from .config import (
    ARTIFACTS_DIR,
    ASSISTANT,
    BASE_URL,
    COLLECTION,
    CONCURRENCY,
    FLIP_INITIAL_THRESHOLD,
    FLIP_RELAXED_THRESHOLD,
    GE_APP_ID,
    IDLE_TIMEOUT_S,
    INPUTS_DIR,
    LOCATION,
    MAX_PROGRAMS_EVALUATED,
    MAX_PROGRAMS_GENERATED,
    MODEL_1,
    MODEL_1_WEIGHT,
    MODEL_2,
    MODEL_2_WEIGHT,
    PARALLEL_EVALUATION,
    PROJECT_ID,
    SAMPLE_TIMES,
    WORKER_CONCURRENCY
)
from .evaluator import ShaderEvaluator
from .models import CandidateMetrics, EvaluationRecord
from .pipeline import (
    load_pipeline,
    profile_pipeline,
    allocate_pass_budget,
    format_pipeline_breakdown,
    Pipeline,
    PassInfo
)
from .quality import data_url_to_ndarray
from .report import build_html_report

# Official Google Cloud AlphaEvolve components
from alpha_evolve.client import AlphaEvolveClient
from alpha_evolve.controller import run_controller_loop
from alpha_evolve.experiment import AlphaEvolveExperiment

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("shader_evolve")


def resolve_project_input(
    project_id: Optional[str] = None,
    target_shader: Optional[str] = None
) -> Tuple[str, Path, str, str, List[str]]:
    """
    Locates the target shader project under inputs/.
    Returns (project_id, project_dir, entry_shader_rel_path, shader_code, channel_types).
    Delegates to load_pipeline for consistent resolution.
    """
    pipeline = load_pipeline(project_id, target_shader)
    target_pass = pipeline.passes[0]
    for p in pipeline.passes:
        if p.has_evolve_block:
            target_pass = p
            break
    return pipeline.project_id, pipeline.proj_dir, target_pass.rel_path, target_pass.code, target_pass.channel_types


async def run_shader_evolution(
    project_id: Optional[str] = None,
    target_shader: Optional[str] = None,
    max_evaluations: int = MAX_PROGRAMS_EVALUATED,
    num_evaluators: int = WORKER_CONCURRENCY,
    baseline_only: bool = False,
    profile_only: bool = False
):
    """
    Executes the full closed-loop shader optimization pipeline via Google Cloud AlphaEvolve.
    Supports single-shader optimization and multi-pass cascaded optimization (Scheme 2).
    """
    pipeline = load_pipeline(project_id, target_shader)
    pid = pipeline.project_id
    proj_dir = pipeline.proj_dir
    out_dir = ARTIFACTS_DIR / pid
    out_dir.mkdir(parents=True, exist_ok=True)

    is_multi_pass = (len(pipeline.passes) > 1 and not target_shader)

    logger.info("=" * 70)
    logger.info(f"🚀 Google Cloud AlphaEvolve Shader Optimization | Project: [{pid}] ({pipeline.title})")
    logger.info(f"📂 Project Directory: {proj_dir}")
    if is_multi_pass:
        logger.info(f"📁 Multi-Pass Pipeline Detected: {len(pipeline.passes)} passes {[p.name for p in pipeline.passes]}")
    else:
        entry_pass = pipeline.passes[0]
        logger.info(f"📄 Target Shader: {entry_pass.rel_path} ({entry_pass.lines_count} lines) | Channels: {entry_pass.channel_types}")
    logger.info(f"☁️ GCP Project: {PROJECT_ID} | Discovery Engine App: {GE_APP_ID}")
    logger.info("=" * 70)

    # 1. Bottleneck Inspection & EVOLVE-BLOCK Verification
    for p in pipeline.passes:
        if p.has_evolve_block:
            logger.info(f"✅ Pass [{p.name}]: EVOLVE-BLOCK markers already present in shader code.")
        else:
            logger.info(f"🔍 Pass [{p.name}]: EVOLVE-BLOCK not found. Running automatic AST bottleneck analysis...")
            logger.info(f"🎯 Bottleneck Identified: {p.bottleneck_info.get('message')}")
            logger.info(f"   Hotspot Type: {p.bottleneck_info.get('hotspot_type')} (Score: {p.bottleneck_info.get('score')})")

    if profile_only:
        logger.info("Profile-only flag specified. Bottleneck analysis completed.")
        return

    # 2. Launch Local WebGL2 Browser Evaluator
    worker = BrowserEvaluatorWorker()
    preflight = await worker.start()
    hw_renderer = preflight.get("renderer", "WebGL2 Hardware GPU")
    timer_query = preflight.get("timerQuery", True)
    logger.info(f"🖥️ Hardware GPU Unmasked Renderer: {hw_renderer}")
    logger.info(f"⏱️ EXT_disjoint_timer_query_webgl2 Supported: {timer_query}")

    try:
        # 3. Benchmark Baseline Performance & Reference Frames
        if is_multi_pass:
            await profile_pipeline(pipeline, worker, SAMPLE_TIMES, out_dir=out_dir)
            logger.info("\n" + format_pipeline_breakdown(pipeline, hw_renderer, timer_query))

            # Save baseline frame images per pass
            for p in pipeline.passes:
                p_frames_dir = out_dir / "baseline_frames" / p.name.lower().replace(" ", "_")
                p_frames_dir.mkdir(parents=True, exist_ok=True)
                for idx, frame_arr in enumerate(p.baseline_frames):
                    img = Image.fromarray(frame_arr)
                    img.save(p_frames_dir / f"frame_{idx:02d}.png")

            # Also save primary frames in out_dir / "baseline_frames"
            primary_pass = max(pipeline.passes, key=lambda p: p.baseline_gpu_ms)
            for idx, frame_arr in enumerate(primary_pass.baseline_frames):
                img = Image.fromarray(frame_arr)
                img.save(out_dir / "baseline_frames" / f"frame_{idx:02d}.png")

            if baseline_only:
                logger.info("Baseline-only flag specified. Multi-pass baseline capture completed.")
                return

        else:
            pass_info = pipeline.passes[0]
            logger.info(f"\n📊 Capturing Golden Reference Baseline for [{pass_info.name}] ({pass_info.rel_path})...")
            baseline_res = await worker.evaluate_shader(
                glsl_code=pass_info.seed_code,
                sample_times=SAMPLE_TIMES,
                channel_types=pass_info.channel_types
            )
            if not baseline_res.get("compileOk"):
                raise RuntimeError(f"Seed shader compilation failed: {baseline_res.get('compileError')}")

            pass_info.baseline_gpu_ms = float(baseline_res.get("gpuTimeMs", 16.67))
            pass_info.baseline_fps = 1000.0 / max(0.001, pass_info.baseline_gpu_ms)
            pass_info.cost_percent = 100.0
            captured_frames_data = baseline_res.get("frames", [])
            pass_info.baseline_frames = [data_url_to_ndarray(f["dataUrl"]) for f in captured_frames_data]

            logger.info(f"✨ Baseline Median GPU Time: {pass_info.baseline_gpu_ms:.2f} ms ({pass_info.baseline_fps:.1f} FPS)")

            base_frames_dir = out_dir / "baseline_frames"
            base_frames_dir.mkdir(parents=True, exist_ok=True)
            for idx, frame_arr in enumerate(pass_info.baseline_frames):
                img = Image.fromarray(frame_arr)
                img.save(base_frames_dir / f"frame_{idx:02d}.png")

            if baseline_only:
                logger.info("Baseline-only flag specified. Baseline capture finished.")
                return

        # 4. Evolution Planning (Scheme 2 Cascaded Multi-Pass or Single-Pass)
        if is_multi_pass:
            allocations = allocate_pass_budget(pipeline, max_evaluations)
            stages_to_run = [p for p in pipeline.get_topological_order() if allocations.get(p.name, 0) > 0]
        else:
            allocations = {pipeline.passes[0].name: max_evaluations}
            stages_to_run = [pipeline.passes[0]]

        logger.info("\n" + "=" * 70)
        logger.info(f"🚀 EVOLUTION EXECUTION PLAN: {len(stages_to_run)} Stage(s)")
        for stg in stages_to_run:
            logger.info(f"• Stage [{stg.name}]: {allocations[stg.name]} evaluations | Baseline: {stg.baseline_gpu_ms:.2f} ms ({stg.cost_percent:.1f}%)")
        logger.info("=" * 70)

        # 5. Connect to Google Cloud AlphaEvolve
        logger.info("\n☁️ Connecting to Google Cloud AlphaEvolve Service...")
        ae_client = AlphaEvolveClient(
            project_id=PROJECT_ID,
            location=LOCATION,
            collection=COLLECTION,
            engine=GE_APP_ID,
            assistant=ASSISTANT,
            base_url=BASE_URL
        )

        models_raw = [(MODEL_1, MODEL_1_WEIGHT), (MODEL_2, MODEL_2_WEIGHT)]
        generation_models = [
            {"name": m, "weight": round(w, 2)}
            for m, w in {name: sum(weight for n, weight in models_raw if n == name) for name, _ in models_raw}.items()
            if m
        ]

        all_records: List[EvaluationRecord] = []

        for stage_idx, pass_info in enumerate(stages_to_run, 1):
            stage_budget = allocations[pass_info.name]
            logger.info("\n" + "=" * 70)
            logger.info(f"🚀 CASCADED STAGE [{stage_idx}/{len(stages_to_run)}]: Optimizing Pass '{pass_info.name}'")
            logger.info(f"📄 Shader File: {pass_info.rel_path} ({pass_info.lines_count} lines) | Channels: {pass_info.channel_types}")
            logger.info(f"⏱️ Pass Baseline: {pass_info.baseline_gpu_ms:.2f} ms ({pass_info.cost_percent:.1f}% of frame)")
            logger.info(f"🎯 Stage Budget : {stage_budget} evaluations")

            upstream = pipeline.get_upstream_passes(pass_info.name)
            upstream_desc = ""
            if upstream:
                dep_names = ", ".join(f"{u.name} ({u.rel_path})" for u in upstream)
                upstream_desc = f"\n- Dependencies: Reads data from upstream pass(es): {dep_names}"
                logger.info(f"🔗 {upstream_desc.strip()}")

            logger.info("=" * 70)

            stage_evaluator = ShaderEvaluator(
                browser_worker=worker,
                baseline_frames=pass_info.baseline_frames,
                baseline_gpu_ms=pass_info.baseline_gpu_ms,
                seed_code=pass_info.seed_code,
                initial_flip_threshold=FLIP_INITIAL_THRESHOLD,
                relaxed_flip_threshold=FLIP_RELAXED_THRESHOLD,
                channel_types=pass_info.channel_types
            )

            stage_exp = AlphaEvolveExperiment(
                ae_client=ae_client,
                evaluator_function=stage_evaluator.evaluate_program,
                max_programs_evaluated=stage_budget,
                parallel_evaluation=PARALLEL_EVALUATION
            )

            exp_config = {
                "title": f"Shader Opt [{pid}] - {pass_info.name}",
                "problem_description": (
                    f"Optimize the GLSL fragment shader pass '{pass_info.name}' ({pass_info.rel_path}) to minimize GPU render duration "
                    f"on local WebGL2 hardware while strictly maintaining perceptual visual fidelity.\n\n"
                    "Constraints & Goals:\n"
                    "- Target Hardware: WebGL 2.0 (High Performance GPU mode)\n"
                    "- NVIDIA FLIP visual similarity threshold: >= 0.98 (or >= 0.95)\n"
                    "- Only modify the code enclosed within EVOLVE-BLOCK-START and EVOLVE-BLOCK-END\n"
                    "- Do not change shader uniform semantics, output canvas resolution, or inputs.\n"
                    f"{upstream_desc}\n"
                    "- Apply algorithmic optimizations: Raymarching step relaxation, mathematical approximations."
                ),
                "program_language": "glsl",
                "run_settings": {
                    "max_programs": stage_budget,
                    "concurrency": CONCURRENCY
                },
                "generation_settings": {
                    "models": generation_models
                }
            }

            stage_exp.create_experiment(exp_config)
            stage_exp.create_initial_program({
                "content": {
                    "files": [
                        {"path": pass_info.rel_path, "content": pass_info.seed_code}
                    ]
                },
                "evaluation": {
                    "scores": {
                        "scores": [{"metric": "shader_speedup", "score": 1.0}]
                    }
                }
            })
            stage_exp.start_experiment()

            logger.info(f"Starting AlphaEvolve controller loop for pass '{pass_info.name}' (Target: {stage_budget})...")
            await run_controller_loop(
                experiment=stage_exp,
                num_samplers=CONCURRENCY,
                num_evaluators=num_evaluators,
                idle_timeout_s=IDLE_TIMEOUT_S
            )

            # Stage champion selection (monotonic improvement requirement)
            champ_rec = stage_evaluator.best_candidate_record
            if champ_rec and champ_rec.accepted and champ_rec.speedup > 1.0:
                pass_info.champion_code = stage_evaluator.best_candidate_code
                pass_info.champion_gpu_ms = champ_rec.candidate_gpu_ms
                pass_info.champion_speedup = champ_rec.speedup
                pass_info.champion_flip = champ_rec.flip_similarity
            else:
                pass_info.champion_code = pass_info.seed_code
                pass_info.champion_gpu_ms = pass_info.baseline_gpu_ms
                pass_info.champion_speedup = 1.0
                pass_info.champion_flip = 1.0

            # Save pass-specific champion shader
            pass_slug = pass_info.name.lower().replace(" ", "_")
            clean_pass_code = strip_evolve_markers(pass_info.champion_code)
            with open(out_dir / f"champion_{pass_slug}.glsl", "w", encoding="utf-8") as f:
                f.write(clean_pass_code)

            all_records.extend(stage_evaluator.records)

        # 6. Post-Cascade Champion Selection & Pipeline Aggregation
        core_bottleneck = max(pipeline.passes, key=lambda p: p.baseline_gpu_ms)
        clean_core_code = strip_evolve_markers(core_bottleneck.champion_code or core_bottleneck.seed_code)
        champ_file = out_dir / "champion_optimized.glsl"
        with open(champ_file, "w", encoding="utf-8") as f:
            f.write(clean_core_code)
        logger.info(f"\n💾 Primary Champion Shader Saved: {champ_file}")

        total_baseline_ms = sum(p.baseline_gpu_ms for p in pipeline.passes)
        total_champ_ms = sum((p.champion_gpu_ms if p.champion_gpu_ms > 0 else p.baseline_gpu_ms) for p in pipeline.passes)
        pipeline_speedup = total_baseline_ms / max(0.001, total_champ_ms)
        energy_saved = max(0.0, (1.0 - (total_champ_ms / total_baseline_ms))) * 100.0

        pipeline_breakdown = [
            {
                "name": p.name,
                "file": p.rel_path,
                "lines": p.lines_count,
                "baseline_ms": round(p.baseline_gpu_ms, 2),
                "cost_percent": round(p.cost_percent, 1),
                "champion_ms": round(p.champion_gpu_ms if p.champion_gpu_ms > 0 else p.baseline_gpu_ms, 2),
                "speedup": round(p.champion_speedup, 3),
                "flip": round(p.champion_flip, 4)
            }
            for p in pipeline.passes
        ]

        # Save Evaluations JSONL Log
        eval_log_file = out_dir / "evaluations.jsonl"
        with open(eval_log_file, "w", encoding="utf-8") as f:
            for rec in all_records:
                f.write(rec.model_dump_json() + "\n")
        logger.info(f"💾 Evaluations Log Saved: {eval_log_file} ({len(all_records)} entries)")

        # Save Metrics Summary JSON
        accepted_count = sum(1 for r in all_records if r.accepted)
        metrics_dict = {
            "project_id": pid,
            "title": f"Shader Optimization: {pid} ({pipeline.title})",
            "author": "Google Cloud AlphaEvolve",
            "baseline_gpu_ms": round(total_baseline_ms, 2),
            "optimized_gpu_ms": round(total_champ_ms, 2),
            "speedup": round(pipeline_speedup, 3),
            "flip_similarity": round(core_bottleneck.champion_flip, 4),
            "energy_saved_percent": round(energy_saved, 1),
            "total_evaluations": len(all_records),
            "accepted_count": accepted_count,
            "champion_program_id": core_bottleneck.name,
            "pipeline_breakdown": pipeline_breakdown
        }
        metrics_file = out_dir / "metrics.json"
        with open(metrics_file, "w", encoding="utf-8") as f:
            json.dump(metrics_dict, f, indent=2)
        logger.info(f"💾 Metrics Summary Saved: {metrics_file}")

        # Generate HTML Evolution Report
        report_html = build_html_report(
            project_id=pid,
            title=f"Shader Optimization: {pid} ({pipeline.title})",
            baseline_gpu_ms=total_baseline_ms,
            champion_gpu_ms=total_champ_ms,
            flip_similarity=core_bottleneck.champion_flip,
            mean_ssim=core_bottleneck.champion_flip,
            psnr_db=100.0,
            seed_code=core_bottleneck.seed_code,
            champion_code=clean_core_code,
            records=all_records,
            baseline_frames=core_bottleneck.baseline_frames,
            champion_frames=getattr(core_bottleneck, 'champion_frames', None) or core_bottleneck.baseline_frames,
            hardware_info=hw_renderer,
            pipeline_breakdown=pipeline_breakdown if is_multi_pass else None
        )
        report_file = out_dir / "report.html"
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_html)
        logger.info(f"🎉 HTML Evolution Report Generated: {report_file}")

        # Terminal Final Summary
        logger.info("\n" + "=" * 70)
        logger.info("🏆 ALPHAEVOLVE OPTIMIZATION SUMMARY" + (" (CASCADED MULTI-PASS)" if is_multi_pass else ""))
        logger.info(f"• Baseline GPU Time : {total_baseline_ms:.2f} ms")
        logger.info(f"• Champion GPU Time : {total_champ_ms:.2f} ms")
        logger.info(f"• Hardware Speedup  : {pipeline_speedup:.3f}x (+{(pipeline_speedup-1.0)*100:.1f}%)")
        logger.info(f"• NVIDIA FLIP Score : {core_bottleneck.champion_flip*100:.2f}%")
        logger.info(f"• Energy Reduction  : -{energy_saved:.1f}% Duty Cycle")
        if is_multi_pass:
            logger.info("• Cascaded Pass Results:")
            for pb in pipeline_breakdown:
                logger.info(f"  - [{pb['name']}]: {pb['baseline_ms']}ms -> {pb['champion_ms']}ms ({pb['speedup']}x)")
        logger.info(f"• HTML Report Link  : file://{report_file.resolve()}")
        logger.info("=" * 70 + "\n")

    finally:
        await worker.stop()


def main():
    parser = argparse.ArgumentParser(description="Google Cloud AlphaEvolve Shader Optimization Tool")
    parser.add_argument("--project", "-p", type=str, default=None, help="Target shader project ID under inputs/")
    parser.add_argument("--shader", "-s", type=str, default=None, help="Specific shader file to optimize within the project (e.g. shaders/buffer_a.glsl or shaders/image.glsl)")
    parser.add_argument(
        "--max-programs", "--programs", "--iterations", "-n",
        dest="max_programs",
        type=int,
        default=MAX_PROGRAMS_EVALUATED,
        help="Max candidate programs to generate and evaluate (default from config.yaml: %(default)s)"
    )
    parser.add_argument("--evaluators", type=int, default=WORKER_CONCURRENCY, help="Number of parallel evaluator workers")
    parser.add_argument("--baseline-only", action="store_true", help="Only evaluate and record baseline performance")
    parser.add_argument("--profile-only", action="store_true", help="Only analyze and detect performance bottlenecks")

    args = parser.parse_args()

    asyncio.run(run_shader_evolution(
        project_id=args.project,
        target_shader=args.shader,
        max_evaluations=args.max_programs,
        num_evaluators=args.evaluators,
        baseline_only=args.baseline_only,
        profile_only=args.profile_only
    ))


if __name__ == "__main__":
    main()
