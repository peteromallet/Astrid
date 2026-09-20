"""Read-only QA for ordered native H3 outputs.

Usage:
  python3 workflows/astrid_intro_h3_anchor_chain/review.py s01.mp4 ... s05.mp4
  python3 workflows/astrid_intro_h3_anchor_chain/review.py --output-dir /tmp/qa s01.mp4

The default output directory is a new temporary folder. This script never
imports media or mutates Astrid timelines.
"""
from __future__ import annotations

import argparse
import json
from fractions import Fraction
import subprocess
import tempfile
from pathlib import Path

EXPECTED = ((175, 1920, 1088), (260, 1920, 1088), (175, 1920, 1088),
            (175, 1920, 1088), (294, 1920, 1088))
def ffprobe(path: Path) -> dict:
    raw = subprocess.check_output([
        "ffprobe", "-v", "error", "-count_frames",
        "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames:format_tags",
        "-of", "json", str(path),
    ])
    return json.loads(raw)
def select_expr(indices: list[int]) -> str:
    return "+".join(f"eq(n\\,{n})" for n in indices)
def run_ffmpeg(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-y", *args],
                          text=True, capture_output=True)
def contact(path: Path, out: Path, index: int, count: int) -> bool:
    indices = [round(i * (count - 1) / 7) for i in range(8)]
    vf = (f"drawtext=fontcolor=white:fontsize=90:box=1:boxcolor=black@0.75:"
          f"text='s{index:02} source=%{{n}}',select='{select_expr(indices)}',"
          "setpts=N/(24*TB),scale=480:-2:flags=neighbor,"
          "tile=4x2")
    result = run_ffmpeg(["-i", str(path), "-vf", vf, "-frames:v", "1", str(out)])
    if result.returncode:
        print(f"CONTACT s{index:02}: FAILED {result.stderr.strip()}")
        return False
    print(f"CONTACT s{index:02}: {out}")
    return True
def seam(prev: Path, nxt: Path, out: Path, pi: int, ni: int, prev_count: int) -> bool:
    left = list(range(max(0, prev_count - 12), prev_count))
    right = list(range(30, 55))
    a = select_expr(left)
    b = select_expr(right)
    filt = (
        f"[0:v]drawtext=fontcolor=white:fontsize=72:box=1:boxcolor=black@0.75:"
        f"text='prev s{pi:02} source=%{{n}}',select='{a}',setpts=N/(24*TB),"
        f"scale=320:-2:flags=neighbor[a];"
        f"[1:v]drawtext=fontcolor=white:fontsize=72:box=1:boxcolor=black@0.75:"
        f"text='next s{ni:02} source=%{{n}} (first-new=39)',select='{b}',"
        f"setpts=N/(24*TB),scale=320:-2:flags=neighbor[b];"
        f"[a][b]concat=n=2:v=1:a=0,tile=6x7"
    )
    result = run_ffmpeg(["-i", str(prev), "-i", str(nxt), "-filter_complex", filt,
                         "-frames:v", "1", str(out)])
    if result.returncode:
        print(f"SEAM s{pi:02}->s{ni:02}: FAILED {result.stderr.strip()}")
        return False
    print(f"SEAM s{pi:02}->s{ni:02}: {out}")
    return True
def black_report(path: Path, index: int) -> tuple[bool, bool]:
    result = subprocess.run([
        "ffmpeg", "-nostdin", "-v", "info", "-i", str(path), "-an",
        "-vf", "blackdetect=d=0.25:pix_th=0.001", "-f", "null", "-",
    ], text=True, capture_output=True)
    if result.returncode:
        print(f"BLACK s{index:02}: UNVERIFIED (ffmpeg failed: {result.stderr.strip()})")
        return True, True
    hits = [line.strip() for line in result.stderr.splitlines() if "black_start" in line]
    if hits:
        print(f"BLACK s{index:02}: UNEXPECTED full-black interval(s): {' | '.join(hits)}")
        return True, False
    print(f"BLACK s{index:02}: none detected (threshold 0.001, duration 0.25s)")
    return False, False
def metadata_report(tags: dict, canonical: dict, index: int, path: Path) -> bool:
    raw = tags.get("prompt") if isinstance(tags, dict) else None
    if not raw:
        print(f"METADATA s{index:02}: UNVERIFIED (no format.tags.prompt)")
        return False
    try:
        compiled = json.loads(raw)
        node = compiled[f"s{index:02}_target"]
        actual = node["inputs"]["prompt"]
        expected = canonical["segments"][index - 1]["prompt"]
        movie = compiled[f"s{index:02}_movie"]["inputs"]
        prefix = movie.get("filename_prefix", "")
    except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        print(f"METADATA s{index:02}: UNVERIFIED ({exc})")
        return False
    prompt_ok = actual == expected
    association_ok = bool(prefix.endswith(f"/s{index:02}") and path.stem.startswith(f"s{index:02}"))
    state = "verified" if prompt_ok and association_ok else "UNVERIFIED"
    details = f"prompt={'match' if prompt_ok else 'MISMATCH'}, output_prefix={prefix!r}"
    if not association_ok:
        details += ", file association mismatch"
    print(f"METADATA s{index:02}: {state} ({details})")
    return prompt_ok and association_ok
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("clips", nargs="+", type=Path, help="ordered native s01..s05 MP4s")
    parser.add_argument("--output-dir", type=Path, help="contact/seam output folder")
    parser.add_argument("--prompts", type=Path,
                        default=Path(__file__).resolve().parents[1] / "astrid_intro_h3_prompts.json")
    args = parser.parse_args()
    if not 1 <= len(args.clips) <= 5:
        parser.error("supply 1 to 5 ordered native clips")
    out = args.output_dir or Path(tempfile.mkdtemp(prefix="astrid-intro-h3-review-"))
    out.mkdir(parents=True, exist_ok=True)
    canonical = json.loads(args.prompts.read_text())
    print(f"OUTPUT_DIR: {out}")
    review_required = False
    hard_failure = False
    for index, path in enumerate(args.clips, 1):
        path = path.resolve(strict=True)
        data = ffprobe(path)
        stream = (data.get("streams") or [{}])[0]
        actual = (int(stream.get("nb_read_frames", -1)), int(stream.get("width", -1)),
                  int(stream.get("height", -1)), stream.get("avg_frame_rate"))
        expected = EXPECTED[index - 1]
        try:
            fps_ok = Fraction(actual[3]) == 24
        except (TypeError, ValueError, ZeroDivisionError):
            fps_ok = False
        shape_ok = actual[:3] == (*expected,)
        print(f"PROBE s{index:02}: frames={actual[0]} size={actual[1]}x{actual[2]} "
              f"fps={actual[3]} {'OK' if shape_ok and fps_ok else 'MISMATCH'}")
        if not shape_ok or not fps_ok:
            review_required = hard_failure = True
        tags = (data.get("format") or {}).get("tags") or {}
        if not metadata_report(tags, canonical, index, path):
            review_required = True
        if not contact(path, out / f"s{index:02}_contact.png", index, actual[0]):
            review_required = hard_failure = True
        black_issue, black_hard = black_report(path, index)
        if black_issue:
            review_required = True
        if black_hard:
            hard_failure = True
        if index > 1:
            previous = args.clips[index - 2].resolve(strict=True)
            previous_count = int(ffprobe(previous)["streams"][0]["nb_read_frames"])
            if not seam(previous, path, out / f"seam_s{index-1:02}_s{index:02}.png",
                        index - 1, index, previous_count):
                review_required = hard_failure = True
    print("SUMMARY:", "PASS" if not review_required else "REVIEW REQUIRED")
    return 1 if hard_failure else 0


if __name__ == "__main__":
    raise SystemExit(main())
