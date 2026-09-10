"""Pydantic data models for evaluation records, candidate metrics, and project manifests."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class EvaluationRecord(BaseModel):
    """Detailed telemetry record for a single evaluated shader program candidate."""
    evaluation_index: int = Field(..., description="1-based evaluation sequence index")
    program_id: str = Field(..., description="Unique program candidate identifier")
    parent_program_id: Optional[str] = Field(None, description="Parent program ID in evolution tree")
    compile_ok: bool = Field(..., description="Whether GLSL compiled without errors")
    runtime_ok: bool = Field(..., description="Whether WebGL2 execution succeeded")
    flip_similarity: float = Field(0.0, description="NVIDIA FLIP perceptual similarity (1.0 - mean_err)")
    mean_ssim: float = Field(0.0, description="Wang 2004 aligned SSIM score")
    worst_ssim: float = Field(0.0, description="Worst SSIM across all sampled frames")
    psnr_db: float = Field(0.0, description="PSNR in decibels")
    baseline_gpu_ms: float = Field(0.0, description="Baseline median GPU execution time in ms")
    candidate_gpu_ms: float = Field(0.0, description="Candidate median GPU execution time in ms")
    speedup: float = Field(1.0, description="Speedup ratio: baseline_gpu_ms / candidate_gpu_ms")
    score: float = Field(0.0, description="Multi-objective fitness score")
    accepted: bool = Field(False, description="Whether candidate met all gate thresholds")
    rejection_reason: Optional[str] = Field(None, description="Detailed reason if rejected")
    timestamp: Optional[str] = Field(None, description="ISO timestamp of evaluation")


class ShaderPassConfig(BaseModel):
    """Configuration for an individual rendering pass in a multi-pass pipeline."""
    name: str = "Image"
    file: str = "shaders/image.glsl"
    output: str = "screen"
    channels: Dict[str, Any] = Field(default_factory=dict)


class ShaderProjectManifest(BaseModel):
    """Descriptor for a shader project in inputs/ directory."""
    id: str
    title: str = ""
    author: Optional[str] = "Unknown"
    description: Optional[str] = ""
    passes: List[ShaderPassConfig] = Field(default_factory=list)


class CandidateMetrics(BaseModel):
    """Aggregated optimization summary metrics for final reporting."""
    project_id: str
    title: str
    author: str
    baseline_gpu_ms: float
    optimized_gpu_ms: float
    speedup: float
    flip_similarity: float
    energy_saved_percent: float
    total_evaluations: int
    accepted_count: int
    champion_program_id: str
