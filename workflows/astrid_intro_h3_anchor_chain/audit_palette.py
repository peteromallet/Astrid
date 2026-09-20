"""Read-only diagnostic for unwanted gray scenery in orange-on-black takes.

This measures sampled decoded pixels, not visual acceptance. Bright low-chroma
pixels occupying >5% of a sampled frame flag a take for manual review. It does
not modify media or claim that a low score proves continuity or image quality.
"""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def audit(path: Path) -> dict:
    width, height, rate = 160, 90, 4
    frame_bytes = width * height * 3
    decoded = subprocess.run(
        ["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(path),
         "-an", "-vf", f"fps={rate},scale={width}:{height}",
         "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
        check=True, capture_output=True,
    ).stdout
    if not decoded or len(decoded) % frame_bytes:
        raise ValueError("No complete decoded diagnostic frames")
    samples = []
    for index, start in enumerate(range(0, len(decoded), frame_bytes)):
        frame = decoded[start:start + frame_bytes]
        gray = 0
        for pixel in range(0, frame_bytes, 3):
            channels = frame[pixel:pixel + 3]
            high, low = max(channels), min(channels)
            gray += high >= 32 and (high - low) / high < 0.20
        samples.append({"time_seconds": index / rate,
                        "bright_low_chroma_fraction": gray / (width * height)})
    flagged = [sample for sample in samples if sample["bright_low_chroma_fraction"] > 0.05]
    return {
        "path": str(path.resolve()),
        "diagnostic_only": True,
        "visual_acceptance": "not_established",
        "sample_fps": rate,
        "sample_dimensions": [width, height],
        "thresholds": {"brightness_min": 32, "chroma_max": 0.20,
                       "flag_frame_fraction": 0.05},
        "sample_count": len(samples),
        "max_bright_low_chroma_fraction": max(s["bright_low_chroma_fraction"] for s in samples),
        "flagged_samples": flagged,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("videos", type=Path, nargs="+")
    args = parser.parse_args()
    print(json.dumps([audit(path) for path in args.videos], indent=2))
