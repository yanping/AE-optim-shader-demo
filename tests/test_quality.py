import numpy as np
import pytest
from src.quality import (
    compute_flip_sim,
    compute_ssim_aligned,
    compute_psnr_db,
    correctness_gate
)

def test_identical_images():
    img1 = np.full((64, 64, 3), 128, dtype=np.uint8)
    img2 = np.full((64, 64, 3), 128, dtype=np.uint8)

    flip_score = compute_flip_sim(img1, img2)
    assert flip_score >= 0.999

    ssim_score = compute_ssim_aligned(img1, img2)
    assert ssim_score >= 0.999

    psnr_score = compute_psnr_db(img1, img2)
    assert psnr_score >= 99.0


def test_different_images():
    img1 = np.zeros((64, 64, 3), dtype=np.uint8)
    img2 = np.full((64, 64, 3), 255, dtype=np.uint8)

    flip_score = compute_flip_sim(img1, img2)
    assert 0.0 <= flip_score < 0.5


def test_correctness_gate():
    # Pass threshold
    high_score = correctness_gate(0.99, threshold=0.98, k=50.0)
    assert high_score > 0.60

    # Well below threshold
    low_score = correctness_gate(0.85, threshold=0.98, k=50.0)
    assert low_score < 0.01
