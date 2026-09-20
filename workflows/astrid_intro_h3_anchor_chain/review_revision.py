"""Create bounded raw-frame evidence for one exact revision segment.

Technical checks do not constitute visual acceptance. No source pixels are
modified, no media are selected, and the review files live in temporary staging.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path

from review import contact, ffprobe, seam

EXPECTED = (175, 260, 175, 175, 209, 124)


def video_stream(data: dict) -> dict:
    # The shared probe includes audio streams but requests video dimensions.
    # Do not assume a muxer writes its video stream first.
    return next(stream for stream in data["streams"] if "width" in stream and "height" in stream)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--index", required=True, type=int, choices=range(1, 7))
    parser.add_argument("--segments", required=True, type=Path)
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    source = args.source.resolve(strict=True)
    out = Path(tempfile.mkdtemp(prefix=f"astrid-revision-s{args.index:02}-qa-"))
    data = ffprobe(source)
    stream = video_stream(data)
    count = int(stream["nb_read_frames"])
    if (count, stream["width"], stream["height"], stream["avg_frame_rate"]) != (EXPECTED[args.index-1], 1920, 1088, "24/1"):
        raise RuntimeError(f"Unexpected native shape: {stream}")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(source), "-f", "null", "-"], check=True)
    specs = json.loads(args.segments.read_text())
    graph = json.loads(data.get("format", {}).get("tags", {}).get("prompt", "{}"))
    prefix = f"s{args.index:02}"
    actual = graph.get(prefix + "_target", {}).get("inputs", {}).get("prompt")
    if actual != specs[args.index-1]["prompt"]:
        raise RuntimeError("Embedded generation prompt does not match bound revision prompt")
    if not contact(source, out / "contact.png", args.index, count):
        raise RuntimeError("Contact extraction failed")
    context_ssim = None
    if args.previous:
        previous_count = int(video_stream(ffprobe(args.previous))["nb_read_frames"])
        if not seam(args.previous, source, out / "seam.png", args.index-1, args.index, previous_count):
            raise RuntimeError("Seam extraction failed")
        comparison = subprocess.run([
            "ffmpeg", "-nostdin", "-v", "info", "-i", str(args.previous), "-i", str(source),
            "-filter_complex", f"[0:v]trim=start_frame={previous_count-39},setpts=PTS-STARTPTS[a];"
            "[1:v]trim=end_frame=39,setpts=PTS-STARTPTS[b];[a][b]ssim",
            "-an", "-f", "null", "-",
        ], check=True, text=True, capture_output=True)
        match = re.search(r"All:([0-9.]+)", comparison.stderr)
        context_ssim = float(match.group(1)) if match else None
        (out / "context-ssim.log").write_text(comparison.stderr)
    frames = sorted(set([0, count-1] + ([38, 39, 40, 48, 60] if args.index > 1 else [24, 48, 96])))
    for frame in frames:
        subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-i", str(source),
                        "-vf", f"select=eq(n\\,{frame})", "-frames:v", "1",
                        str(out / f"frame-{frame:04}.png")], check=True)
    report = {"source": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
              "index": args.index, "probe": stream, "full_decode": "pass", "prompt": "exact-match",
              "protected_context_ssim": context_ssim,
              "visual_verdict": "pending human/agent frame and motion review", "frames": frames,
              "evidence_directory": str(out)}
    (out / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
