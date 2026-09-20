#!/usr/bin/env python3
"""Matte s05 to orange-on-black and stabilize its orange cluster.

The H3 source contains a transient camera zoom. This pass detects saturated
orange pixels, removes the grayscale field, and applies a smoothed uniform
scale/translation so the complete desk+mink cluster stays in the terminal's
small lower-right picture region. It never changes aspect ratio or frame count.

Usage:
  finish_s05_orange_stabilize.py SOURCE OUTPUT.mp4 [frames] [fps]
      [target_x target_y target_w target_h smoothing_radius]
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    source, output = Path(sys.argv[1]), Path(sys.argv[2])
    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise RuntimeError(f"cannot open source: {source}")
    source_fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    frames = int(sys.argv[3]) if len(sys.argv) > 3 else int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fps = float(sys.argv[4]) if len(sys.argv) > 4 else 24.0
    target = tuple(float(sys.argv[i]) for i in range(5, 9)) if len(sys.argv) > 8 else (1323.0, 537.0, 468.0, 306.0)
    radius = int(sys.argv[9]) if len(sys.argv) > 9 else 4
    if frames <= 0 or fps <= 0 or radius < 0:
        raise ValueError("frames/fps must be positive and smoothing radius nonnegative")

    images: list[np.ndarray] = []
    boxes: list[tuple[float, float, float, float] | None] = []
    for _ in range(frames):
        ok, image = cap.read()
        if not ok:
            raise RuntimeError(f"source ended before requested frame count {frames}")
        hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
        # Saturated orange is the authored pixel palette; the gray collage has
        # low saturation and is therefore omitted without a soft halo.
        mask = ((hsv[:, :, 0] >= 3) & (hsv[:, :, 0] <= 28) &
                (hsv[:, :, 1] >= 100) & (hsv[:, :, 2] >= 80))
        ys, xs = np.where(mask)
        if len(xs):
            boxes.append((float(xs.min()), float(ys.min()),
                          float(xs.max() + 1), float(ys.max() + 1)))
        else:
            boxes.append(None)
        images.append(np.where(mask[:, :, None], image, 0).astype(np.uint8))
    cap.release()

    # Fill an absent detection from the nearest valid frame, then smooth the
    # affine parameters symmetrically. A uniform scale preserves pixel-art
    # geometry while the target box pins the terminal cluster lower-right.
    valid = [i for i, box in enumerate(boxes) if box is not None]
    if not valid:
        raise RuntimeError("no saturated orange foreground detected")
    for i in range(frames):
        if boxes[i] is None:
            j = min(valid, key=lambda k: abs(k - i))
            boxes[i] = boxes[j]
    tx, ty, tw, th = target
    target_cx, target_cy = tx + tw / 2.0, ty + th / 2.0
    params = []
    for x1, y1, x2, y2 in boxes:  # type: ignore[misc]
        scale = min(tw / (x2 - x1), th / (y2 - y1))
        cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
        params.append((scale, target_cx - scale * cx, target_cy - scale * cy))
    smoothed = []
    for i in range(frames):
        lo, hi = max(0, i - radius), min(frames, i + radius + 1)
        smoothed.append(tuple(np.mean(params[lo:hi], axis=0)))

    output.parent.mkdir(parents=True, exist_ok=True)
    width, height = images[0].shape[1], images[0].shape[0]
    duration = frames / fps
    cmd = ["ffmpeg", "-y", "-nostdin", "-hide_banner", "-loglevel", "error",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{width}x{height}",
           "-r", str(fps), "-i", "-", "-frames:v", str(frames), "-t", f"{duration:.6f}",
           "-an", "-c:v", "libx264", "-preset", "fast", "-crf", "16",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(output)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for image, (scale, dx, dy) in zip(images, smoothed):
            matrix = np.array([[scale, 0.0, dx], [0.0, scale, dy]], dtype=np.float32)
            stabilized = cv2.warpAffine(image, matrix, (width, height),
                                         flags=cv2.INTER_NEAREST,
                                         borderMode=cv2.BORDER_CONSTANT,
                                         borderValue=(0, 0, 0))
            proc.stdin.write(stabilized.tobytes())
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg encode failed")
    print(f"wrote {output} ({frames} frames at {fps:g} fps; target bbox {target})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
