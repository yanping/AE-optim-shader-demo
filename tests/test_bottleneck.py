import pytest
from src.bottleneck import (
    analyze_and_mark_bottlenecks,
    extract_evolve_block,
    has_evolve_block,
    reconstruct_shader,
    strip_evolve_markers
)

SAMPLE_MARKED_GLSL = """
void boilerplate_before() {}

// EVOLVE-BLOCK-START
float compute_march(vec3 ro, vec3 rd) {
    float t = 0.0;
    for (int i=0; i<64; i++) {
        t += 0.1;
    }
    return t;
}
// EVOLVE-BLOCK-END

void mainImage(out vec4 col, in vec2 uv) {
    col = vec4(1.0);
}
"""

SAMPLE_UNMARKED_GLSL = """
float map(vec3 p) {
    return length(p) - 1.0;
}

float raymarch(vec3 ro, vec3 rd) {
    float t = 0.0;
    for (int i = 0; i < 96; i++) {
        vec3 p = ro + rd * t;
        float d = map(p);
        if (d < 0.001) return t;
        t += d;
    }
    return -1.0;
}

void mainImage(out vec4 col, in vec2 uv) {
    col = vec4(1.0);
}
"""

def test_has_evolve_block():
    assert has_evolve_block(SAMPLE_MARKED_GLSL) is True
    assert has_evolve_block(SAMPLE_UNMARKED_GLSL) is False


def test_extract_and_reconstruct():
    prefix, target, suffix = extract_evolve_block(SAMPLE_MARKED_GLSL)
    assert "compute_march" in target
    assert "boilerplate_before" in prefix
    assert "mainImage" in suffix

    mutated_target = target.replace("64", "48")
    reconstructed = reconstruct_shader(SAMPLE_MARKED_GLSL, mutated_target)
    assert "48" in reconstructed
    assert "boilerplate_before" in reconstructed
    assert "mainImage" in reconstructed


def test_strip_evolve_markers():
    clean = strip_evolve_markers(SAMPLE_MARKED_GLSL)
    assert "EVOLVE-BLOCK-START" not in clean
    assert "EVOLVE-BLOCK-END" not in clean
    assert "compute_march" in clean


def test_analyze_and_mark_bottlenecks():
    marked_code, info = analyze_and_mark_bottlenecks(SAMPLE_UNMARKED_GLSL)
    assert has_evolve_block(marked_code) is True
    assert info["auto_detected"] is True
    assert "Raymarching" in info["hotspot_type"]
    assert "raymarch" in marked_code
