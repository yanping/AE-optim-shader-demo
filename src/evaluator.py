"""Multi-objective shader evaluator adapter for AlphaEvolve controller loop."""

import asyncio
import datetime
import logging
from typing import Any, Dict, List, Optional
import nest_asyncio
import numpy as np

nest_asyncio.apply()

from .bottleneck import reconstruct_shader
from .browser_worker import BrowserEvaluatorWorker
from .config import FLIP_INITIAL_THRESHOLD, FLIP_RELAXED_THRESHOLD, SAMPLE_TIMES
from .models import EvaluationRecord
from .quality import correctness_gate, data_url_to_ndarray, full_report_frames

logger = logging.getLogger(__name__)


class ShaderEvaluator:
    """Evaluates candidate shaders via WebGL2 and applies adaptive FLIP visual gating."""

    def __init__(
        self,
        browser_worker: BrowserEvaluatorWorker,
        baseline_frames: List[np.ndarray],
        baseline_gpu_ms: float,
        seed_code: str,
        initial_flip_threshold: float = FLIP_INITIAL_THRESHOLD,
        relaxed_flip_threshold: float = FLIP_RELAXED_THRESHOLD,
        channel_types: Optional[List[str]] = None
    ):
        nest_asyncio.apply()
        self.worker = browser_worker
        self.baseline_frames = baseline_frames
        self.baseline_gpu_ms = max(0.1, float(baseline_gpu_ms))
        self.seed_code = seed_code
        self.flip_threshold = initial_flip_threshold
        self.relaxed_threshold = relaxed_flip_threshold
        self.channel_types = channel_types or ["2d", "2d", "2d", "2d"]

        self.evaluation_counter = 0
        self.passed_count = 0
        self.records: List[EvaluationRecord] = []
        self.best_candidate_record: Optional[EvaluationRecord] = None
        self.best_candidate_code: str = seed_code
        self.best_candidate_frames: List[np.ndarray] = baseline_frames

    def evaluate_program(self, program_candidate: Dict[str, Any]) -> Dict[str, Any]:
        """
        AlphaEvolve evaluator callback entrypoint.
        Processes candidate AST/code, measures GPU render duration, tests FLIP perceptual quality,
        and constructs multi-objective fitness scores and feedback insights.
        """
        self.evaluation_counter += 1
        eval_idx = self.evaluation_counter

        program_id = program_candidate.get("name") or f"candidate_{eval_idx:03d}"
        parent_id = program_candidate.get("parent_program_id") or program_candidate.get("parent")

        files = program_candidate.get("content", {}).get("files", [])
        if not files:
            record = self._build_record(
                eval_idx, program_id, parent_id, False, False, 0.0, 0.0, 0.0, 0.0, 0.0, -1000.0, False,
                "Candidate payload contains no files."
            )
            return self._format_response(score=-1000.0, insight="Rejected: Empty file payload.", record=record)

        raw_code = files[0].get("content", "")
        if not raw_code.strip():
            record = self._build_record(
                eval_idx, program_id, parent_id, False, False, 0.0, 0.0, 0.0, 0.0, 0.0, -1000.0, False,
                "Candidate GLSL source code is empty."
            )
            return self._format_response(score=-1000.0, insight="Rejected: Empty GLSL source code.", record=record)

        # Reconstruct complete GLSL shader by merging candidate code with seed boilerplate
        full_glsl = reconstruct_shader(self.seed_code, raw_code)

        # Adaptive Threshold Check: If after 10 candidates 0 have passed at 98%, relax threshold to 95%
        if self.flip_threshold > self.relaxed_threshold and self.evaluation_counter >= 10 and self.passed_count == 0:
            old_t = self.flip_threshold
            self.flip_threshold = self.relaxed_threshold
            logger.info(f"⚡ [ADAPTIVE GATE RELAXATION] 0 candidates accepted after {self.evaluation_counter} evaluations. Relaxing FLIP gate from {old_t:.2f} down to {self.flip_threshold:.2f}")

        # Execute candidate evaluation inside browser worker
        loop = asyncio.get_event_loop()
        worker_res = loop.run_until_complete(
            self.worker.evaluate_shader(
                glsl_code=full_glsl,
                sample_times=SAMPLE_TIMES,
                channel_types=self.channel_types
            )
        )

        # 1. Gate: Shader Compilation Check
        if not worker_res.get("compileOk"):
            err = worker_res.get("compileError", "GLSL compilation error")
            logger.info(f"[eval {eval_idx:03d}] compile=FAILED | {err[:80]}")
            record = self._build_record(
                eval_idx, program_id, parent_id, False, False, 0.0, 0.0, 0.0, 0.0, 0.0, -1000.0, False,
                f"Compile error: {err[:120]}"
            )
            return self._format_response(
                score=-1000.0,
                insight=f"GLSL Compilation Error:\n{err[:240]}\nPlease ensure valid GLSL ES 3.0 syntax and matching variable types.",
                record=record
            )

        captured_frames = worker_res.get("frames", [])
        if len(captured_frames) != len(self.baseline_frames):
            record = self._build_record(
                eval_idx, program_id, parent_id, True, False, 0.0, 0.0, 0.0, 0.0, 0.0, -500.0, False,
                "Frame count mismatch during render capture."
            )
            return self._format_response(score=-500.0, insight="Runtime error: Frame count mismatch.", record=record)

        cand_ndarrays = [data_url_to_ndarray(f["dataUrl"]) for f in captured_frames]

        # 2. Gate: Visual Quality Assessment (NVIDIA FLIP / SSIM / PSNR)
        quality_rep = full_report_frames(cand_ndarrays, self.baseline_frames)
        flip_sim = quality_rep["flip_sim"]
        mean_ssim = quality_rep["mean_ssim"]
        worst_ssim = quality_rep["worst_ssim"]
        psnr_db = quality_rep["psnr_db"]

        gate_multiplier = correctness_gate(flip_sim, threshold=self.flip_threshold, k=50.0)

        # Check visual gate satisfaction
        if flip_sim < self.flip_threshold or gate_multiplier < 0.1:
            rej_reason = f"Perceptual FLIP similarity {flip_sim:.4f} < threshold {self.flip_threshold:.2f} (SSIM {mean_ssim:.4f})"
            penalty_score = -100.0 - (1.0 - flip_sim) * 100.0
            logger.info(f"[eval {eval_idx:03d}] compile=OK FLIP={flip_sim:.4f} < {self.flip_threshold:.2f} -> REJECTED")

            record = self._build_record(
                eval_idx, program_id, parent_id, True, True, flip_sim, mean_ssim, worst_ssim, psnr_db, 0.0,
                penalty_score, False, rej_reason
            )
            insight_msg = (
                f"Visual Quality Rejection: FLIP similarity {flip_sim:.4f} is below the threshold of {self.flip_threshold:.2f}.\n"
                f"Wang 2004 SSIM: {mean_ssim:.4f}, PSNR: {psnr_db:.2f} dB.\n"
                f"Recommendation: Ensure geometric shapes, lighting, and colors match the reference image closely."
            )
            return self._format_response(score=penalty_score, insight=insight_msg, record=record)

        # 3. Candidate Passed Gates: GPU Speedup Calculation
        self.passed_count += 1
        candidate_gpu_ms = float(worker_res.get("gpuTimeMs", 16.67))
        candidate_gpu_ms = max(0.1, candidate_gpu_ms)
        speedup = self.baseline_gpu_ms / candidate_gpu_ms

        # Multi-objective fitness score: Speedup scaled by the smooth visual gate multiplier
        fitness_score = gate_multiplier * speedup

        logger.info(f"[eval {eval_idx:03d}] compile=OK FLIP={flip_sim:.4f} baseline={self.baseline_gpu_ms:.2f}ms candidate={candidate_gpu_ms:.2f}ms speedup={speedup:.3f}x score={fitness_score:.4f} ACCEPTED ✅")

        record = self._build_record(
            eval_idx, program_id, parent_id, True, True, flip_sim, mean_ssim, worst_ssim, psnr_db,
            candidate_gpu_ms, fitness_score, True, None
        )

        # Update Champion Candidate if Pareto improvement over baseline (speedup > 1.0)
        is_better = False
        if self.best_candidate_record is None:
            if speedup > 1.0:
                is_better = True
        elif fitness_score > self.best_candidate_record.score and speedup > 1.0:
            is_better = True

        if is_better:
            self.best_candidate_record = record
            self.best_candidate_code = full_glsl
            self.best_candidate_frames = cand_ndarrays
            logger.info(f"🏆 NEW CHAMPION: {program_id} with Speedup={speedup:.3f}x, FLIP={flip_sim:.4f}")

        insight_text = (
            f"Evaluation SUCCESS:\n"
            f"- Perceptual FLIP Similarity: {flip_sim:.4f} (Gate >= {self.flip_threshold:.2f})\n"
            f"- Structural SSIM: {mean_ssim:.4f} (Worst SSIM: {worst_ssim:.4f})\n"
            f"- PSNR: {psnr_db:.2f} dB\n"
            f"- GPU Render Time: {candidate_gpu_ms:.2f} ms (Baseline: {self.baseline_gpu_ms:.2f} ms)\n"
            f"- Real Hardware Speedup: {speedup:.3f}x\n"
            f"- Fitness Score: {fitness_score:.4f}"
        )

        return self._format_response(score=fitness_score, insight=insight_text, record=record)

    def _build_record(
        self,
        eval_idx: int,
        program_id: str,
        parent_id: Optional[str],
        compile_ok: bool,
        runtime_ok: bool,
        flip_sim: float,
        mean_ssim: float,
        worst_ssim: float,
        psnr_db: float,
        candidate_gpu_ms: float,
        score: float,
        accepted: bool,
        rejection_reason: Optional[str]
    ) -> EvaluationRecord:
        speedup = self.baseline_gpu_ms / candidate_gpu_ms if candidate_gpu_ms > 0 else 1.0
        rec = EvaluationRecord(
            evaluation_index=eval_idx,
            program_id=str(program_id),
            parent_program_id=str(parent_id) if parent_id else None,
            compile_ok=compile_ok,
            runtime_ok=runtime_ok,
            flip_similarity=round(flip_sim, 4),
            mean_ssim=round(mean_ssim, 4),
            worst_ssim=round(worst_ssim, 4),
            psnr_db=round(psnr_db, 2),
            baseline_gpu_ms=round(self.baseline_gpu_ms, 2),
            candidate_gpu_ms=round(candidate_gpu_ms, 2),
            speedup=round(speedup, 3),
            score=round(score, 4),
            accepted=accepted,
            rejection_reason=rejection_reason,
            timestamp=datetime.datetime.now().isoformat()
        )
        self.records.append(rec)
        return rec

    def _format_response(self, score: float, insight: str, record: EvaluationRecord) -> Dict[str, Any]:
        return {
            "scores": {
                "scores": [
                    {"metric": "shader_speedup", "score": float(score)}
                ]
            },
            "insights": {
                "insights": [
                    {"label": "Evaluation Detail", "text": str(insight)}
                ]
            },
            "record": record
        }
