"""Shader code analyzer, EVOLVE-BLOCK parser, and automatic bottleneck detector."""

import re
from typing import Dict, Optional, Tuple, Any

EVOLVE_START_PATTERN = re.compile(r'^[ \t]*(?:#|//|/\*)[ \t]*EVOLVE-BLOCK-START[ \t]*(?:\*/)?', re.MULTILINE)
EVOLVE_END_PATTERN = re.compile(r'^[ \t]*(?:#|//|/\*)[ \t]*EVOLVE-BLOCK-END[ \t]*(?:\*/)?', re.MULTILINE)


def has_evolve_block(shader_code: str) -> bool:
    """Checks whether the shader code contains EVOLVE-BLOCK markers."""
    return bool(EVOLVE_START_PATTERN.search(shader_code) and EVOLVE_END_PATTERN.search(shader_code))


def extract_evolve_block(shader_code: str) -> Tuple[str, str, str]:
    """
    Extracts the mutable region between EVOLVE-BLOCK markers.
    Returns (prefix, evolve_block_code, suffix).
    If no markers found, returns ("", shader_code, "").
    """
    start_match = EVOLVE_START_PATTERN.search(shader_code)
    end_match = EVOLVE_END_PATTERN.search(shader_code)

    if not start_match or not end_match or start_match.start() >= end_match.start():
        return "", shader_code, ""

    # End of the START marker line
    start_line_end = shader_code.find('\n', start_match.end())
    if start_line_end == -1:
        start_line_end = start_match.end()
    else:
        start_line_end += 1

    # Start of the END marker line
    end_line_start = shader_code.rfind('\n', 0, end_match.start())
    if end_line_start == -1:
        end_line_start = end_match.start()
    else:
        end_line_start += 1

    prefix = shader_code[:start_line_end]
    evolve_block = shader_code[start_line_end:end_line_start]
    suffix = shader_code[end_line_start:]

    return prefix, evolve_block, suffix


def reconstruct_shader(full_seed_code: str, candidate_code: str) -> str:
    """
    Splices candidate evolved code into the full shader.
    Handles candidates that are either:
    1. Full shader text containing markers
    2. Full shader text without markers
    3. Isolated evolve-block snippet
    """
    if not has_evolve_block(full_seed_code):
        return candidate_code

    if has_evolve_block(candidate_code):
        return candidate_code

    prefix, original_block, suffix = extract_evolve_block(full_seed_code)

    # If the candidate looks like a full shader (contains main or mainImage), return it
    if "mainImage(" in candidate_code or "void main(" in candidate_code:
        if len(candidate_code) > len(prefix) + len(suffix):
            return candidate_code

    # Otherwise splice into the EVOLVE-BLOCK
    return prefix + candidate_code.rstrip('\n') + '\n' + suffix


def strip_evolve_markers(shader_code: str) -> str:
    """Strips all EVOLVE-BLOCK comment markers from the final shader code."""
    cleaned = EVOLVE_START_PATTERN.sub('', shader_code)
    cleaned = EVOLVE_END_PATTERN.sub('', cleaned)
    # Remove any empty lines created by stripping marker comments
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
    return cleaned


def analyze_and_mark_bottlenecks(shader_code: str) -> Tuple[str, Dict[str, Any]]:
    """
    Analyzes GLSL shader source code for performance bottlenecks.
    If no EVOLVE-BLOCK markers exist, identifies high-cost blocks (Raymarching loops,
    FBM octave loops, complex SDF functions) and automatically injects markers.
    """
    if has_evolve_block(shader_code):
        return shader_code, {
            "auto_detected": False,
            "message": "Existing EVOLVE-BLOCK markers detected in source code."
        }

    lines = shader_code.splitlines()

    # 1. Look for Raymarching March / Trace Loops
    # Pattern: for (int i = 0; i < MARCHSTEPS / N; i++) or while(...) with map / dist / scene / step
    raymarch_patterns = [
        re.compile(r'for\s*\([^;]+;\s*[^;]+<[ \t]*(?:\d+|MARCHSTEPS|MAX_STEPS|STEPS)[^;]*;\s*[^)]+\)', re.IGNORECASE),
        re.compile(r'for\s*\(float\s+t\s*=\s*0\.[0-9]*;\s*t\s*<[^;]+;\s*[^)]+\)'),
        re.compile(r'for\s*\([^)]+\b(?:map|scene|sdf|dist|getDist|world)\b[^)]*\)')
    ]

    best_match_start = -1
    best_match_end = -1
    detection_type = "unknown"
    highest_score = -1

    for i, line in enumerate(lines):
        line_score = 0
        is_loop = "for" in line or "while" in line
        if not is_loop:
            continue

        # Check loop boundary iteration count
        match_steps = re.search(r'<\s*(\d+)', line)
        if match_steps:
            steps = int(match_steps.group(1))
            line_score += steps // 2

        # Lookahead 25 lines for raymarching indicators
        block_chunk = "\n".join(lines[i:min(len(lines), i + 35)])
        if re.search(r'\b(map|scene|sdf|dist|getDist|castRay|trace)\(', block_chunk, re.IGNORECASE):
            line_score += 80
        if re.search(r'\b(t\s*\+=|d\s*=|h\s*=)', block_chunk):
            line_score += 40
        if "MARCH" in block_chunk or "STEPS" in block_chunk:
            line_score += 50
        if "fbm(" in block_chunk or "noise(" in block_chunk:
            line_score += 30

        if line_score > highest_score:
            highest_score = line_score
            best_match_start = i
            detection_type = "Raymarching Core March Loop" if "map" in block_chunk or "castRay" in block_chunk else "Heavy Computational Loop"

    # If a hotspot loop is found, locate its enclosing block
    if best_match_start >= 0 and highest_score > 30:
        # Find closing brace of loop
        brace_count = 0
        found_open = False
        loop_end = best_match_start

        for j in range(best_match_start, min(len(lines), best_match_start + 60)):
            for char in lines[j]:
                if char == '{':
                    brace_count += 1
                    found_open = True
                elif char == '}':
                    brace_count -= 1
                    if found_open and brace_count == 0:
                        loop_end = j
                        break
            if found_open and brace_count == 0:
                break

        if loop_end == best_match_start:
            loop_end = min(len(lines) - 1, best_match_start + 15)

        annotated_lines = []
        annotated_lines.extend(lines[:best_match_start])
        annotated_lines.append("# EVOLVE-BLOCK-START")
        annotated_lines.extend(lines[best_match_start:loop_end + 1])
        annotated_lines.append("# EVOLVE-BLOCK-END")
        annotated_lines.extend(lines[loop_end + 1:])

        annotated_code = "\n".join(annotated_lines)
        return annotated_code, {
            "auto_detected": True,
            "hotspot_type": detection_type,
            "score": highest_score,
            "start_line": best_match_start + 1,
            "end_line": loop_end + 1,
            "message": f"Automatically identified performance bottleneck: {detection_type} at lines {best_match_start+1}-{loop_end+1}."
        }

    # Fallback: Locate mainImage or main and wrap its inner computation
    for i, line in enumerate(lines):
        if "void mainImage" in line or "void main(" in line:
            # Wrap after variable setup
            start_idx = min(len(lines) - 1, i + 3)
            end_idx = max(start_idx, len(lines) - 4)
            annotated_lines = []
            annotated_lines.extend(lines[:start_idx])
            annotated_lines.append("# EVOLVE-BLOCK-START")
            annotated_lines.extend(lines[start_idx:end_idx])
            annotated_lines.append("# EVOLVE-BLOCK-END")
            annotated_lines.extend(lines[end_idx:])
            return "\n".join(annotated_lines), {
                "auto_detected": True,
                "hotspot_type": "Main Image Rendering Pipeline",
                "score": 20,
                "start_line": start_idx + 1,
                "end_line": end_idx,
                "message": f"Wrapped main rendering body at lines {start_idx+1}-{end_idx} as default optimization target."
            }

    # If completely undetermined, wrap the middle half of the shader
    mid = len(lines) // 2
    s_idx = max(0, mid - 20)
    e_idx = min(len(lines), mid + 20)
    annotated_lines = []
    annotated_lines.extend(lines[:s_idx])
    annotated_lines.append("# EVOLVE-BLOCK-START")
    annotated_lines.extend(lines[s_idx:e_idx])
    annotated_lines.append("# EVOLVE-BLOCK-END")
    annotated_lines.extend(lines[e_idx:])
    return "\n".join(annotated_lines), {
        "auto_detected": True,
        "hotspot_type": "Generic Midpoint Section",
        "score": 10,
        "start_line": s_idx + 1,
        "end_line": e_idx,
        "message": "Wrapped central shader code section."
    }
