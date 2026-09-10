"""Image quality assessment module supporting NVIDIA FLIP (HPG 2020), SSIM, and PSNR."""

import base64
import io
import math
from typing import Any, Dict, List, Tuple
import numpy as np
from PIL import Image
from skimage.metrics import peak_signal_noise_ratio as psnr
from skimage.metrics import structural_similarity as ssim

_HAS_FLIP = False
try:
    import flip as _flip
    _HAS_FLIP = True
except Exception:
    _HAS_FLIP = False


def data_url_to_ndarray(data_url: str) -> np.ndarray:
    """Decodes a base64 PNG data URL into an RGB numpy ndarray (H, W, 3) uint8."""
    if "," in data_url:
        data_url = data_url.split(",", 1)[1]
    image_bytes = base64.b64decode(data_url)
    with Image.open(io.BytesIO(image_bytes)) as img:
        rgb = img.convert("RGB")
        return np.array(rgb, dtype=np.uint8)


def image_file_to_ndarray(file_path: str) -> np.ndarray:
    """Loads an image file into an RGB numpy ndarray."""
    with Image.open(file_path) as img:
        return np.array(img.convert("RGB"), dtype=np.uint8)


def _to_gray(img: np.ndarray) -> np.ndarray:
    """Converts HxWx3 uint8 or float32 image to 2D grayscale."""
    if img.ndim == 2:
        return img
    img_float = img.astype(np.float32) / 255.0 if img.dtype == np.uint8 else img.astype(np.float32)
    return img_float @ np.array([0.299, 0.587, 0.114], dtype=np.float32)


def compute_ssim_aligned(base: np.ndarray, cand: np.ndarray) -> float:
    """Computes SSIM aligned with Wang et al. 2004 (gaussian_weights=True, sigma=1.5)."""
    bg, cg = _to_gray(base), _to_gray(cand)
    score = ssim(
        bg, cg,
        data_range=1.0,
        gaussian_weights=True,
        sigma=1.5,
        use_sample_covariance=False
    )
    return float(max(0.0, score))


def compute_flip_sim(base: np.ndarray, cand: np.ndarray) -> float:
    """
    Computes NVIDIA FLIP similarity score = 1.0 - mean_flip_error.
    Higher is better, 1.0 is identical perceptual visual quality.
    """
    if not _HAS_FLIP:
        return compute_ssim_aligned(base, cand)

    b_float = base.astype(np.float32) / 255.0 if base.dtype == np.uint8 else base.astype(np.float32)
    c_float = cand.astype(np.float32) / 255.0 if cand.dtype == np.uint8 else cand.astype(np.float32)

    try:
        if hasattr(_flip, "evaluate"):
            _, mean_err, _ = _flip.evaluate(b_float, c_float, "LDR", inputsRGB=True, applyMagma=False)
            return float(max(0.0, 1.0 - mean_err))
        else:
            return compute_ssim_aligned(base, cand)
    except Exception:
        return compute_ssim_aligned(base, cand)


def compute_psnr_db(base: np.ndarray, cand: np.ndarray) -> float:
    """Computes PSNR in dB between two images."""
    b_float = base.astype(np.float32) / 255.0 if base.dtype == np.uint8 else base.astype(np.float32)
    c_float = cand.astype(np.float32) / 255.0 if cand.dtype == np.uint8 else cand.astype(np.float32)

    mse = float(np.mean((b_float - c_float) ** 2))
    if mse <= 1e-12:
        return 100.0
    return float(psnr(b_float, c_float, data_range=1.0))


def correctness_gate(sim: float, threshold: float = 0.980, k: float = 50.0) -> float:
    """
    Smooth Sigmoid Gate:
      multiplier = 1 / (1 + exp(-k * (sim - threshold)))
    Returns ~1.0 for sim >= threshold, rapidly decays towards 0.0 when sim falls below threshold.
    """
    if sim < 0.0:
        return 0.0
    x = k * (sim - threshold)
    x = max(-20.0, min(20.0, x))
    return float(1.0 / (1.0 + math.exp(-x)))


def full_report_frames(candidate_frames: List[np.ndarray], baseline_frames: List[np.ndarray]) -> Dict[str, Any]:
    """Evaluates FLIP, SSIM, and PSNR across all captured time-sampled frames."""
    flip_sims = []
    ssim_sims = []
    psnr_dbs = []

    for c_img, b_img in zip(candidate_frames, baseline_frames):
        flip_sims.append(compute_flip_sim(b_img, c_img))
        ssim_sims.append(compute_ssim_aligned(b_img, c_img))
        psnr_dbs.append(compute_psnr_db(b_img, c_img))

    mean_flip = float(np.mean(flip_sims)) if flip_sims else 0.0
    worst_flip = float(np.min(flip_sims)) if flip_sims else 0.0
    mean_ssim = float(np.mean(ssim_sims)) if ssim_sims else 0.0
    worst_ssim = float(np.min(ssim_sims)) if ssim_sims else 0.0
    mean_psnr = float(np.mean(psnr_dbs)) if psnr_dbs else 0.0

    return {
        "has_flip": _HAS_FLIP,
        "primary_metric": "flip",
        "flip_sim": round(mean_flip, 4),
        "worst_flip_sim": round(worst_flip, 4),
        "mean_ssim": round(mean_ssim, 4),
        "worst_ssim": round(worst_ssim, 4),
        "psnr_db": round(mean_psnr, 2)
    }
