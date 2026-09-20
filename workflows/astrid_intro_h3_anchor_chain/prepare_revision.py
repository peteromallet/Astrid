"""Stage exact managed inputs and reviewed prompts for the 2026-09-18 revision.

No generation or timeline selection. --bind publishes prompt text and evidence.
Temporary files are transport material; managed IDs remain authoritative.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

from astrid.sdk import AstridClient

PROJECT = "astrid-intro"
ROOT = Path(__file__).resolve().parents[2]
SHOTS = [
    ["5024db66-8472-5eeb-8fba-bd05bac13337"],
    ["b1b0ab58-e2b1-58c7-a6d2-c64c2d93bcf0", "ed3bcb9f-d0ed-56b0-8383-e55fbb74f151"],
    ["b9a999b8-d3e1-5c94-8b6e-b5d53dc6af27"],
    ["9286b9f3-d466-5029-b467-e6cfe6a96f25"],
    ["4417bd8f-754e-5c48-965c-721a9eb37389"],
    ["4417bd8f-754e-5c48-965c-721a9eb37389"],
]
TYPING = (
    "Flat orange 2D pixel animation on the supplied black canvas. Keep the exact "
    "small lower-right seated mink, narrow desk with two straight legs, upright "
    "black monitor, orange swivel chair and broad tail pointing right. Continue "
    "the incoming seated motion into a contained typing cycle: alternate the two "
    "paws at the keyboard, dip the head slightly, then return to the same pose. "
    "The round black eye retains its tiny orange center; the inner ear, bent "
    "elbow, knee outline and individual toes stay crisp and distinct. The chair, "
    "desk and monitor stay fixed at the reference size and location. Give the "
    "tail one small two-step swish. The entire left side and upper half remain "
    "empty black. The monitor remains black without letters. Finish seated and "
    "ready to turn toward the right for the next action. Locked full-frame "
    "composition, no zoom, reframing, room, texture, gray panels, lighting change, "
    "extra minks or props. Preserve hard square edges and the reference palette."
)
EXIT = (
    "Continue the supplied small lower-right typing vignette in flat orange "
    "pixel art on black, at exactly its current scale. First the mink completes "
    "one paw tap, lifts both paws from the keyboard, turns its pointed snout "
    "toward screen right, plants its feet and springs off the chair. It runs "
    "rightward with two clear alternating strides; its long tail follows and "
    "passes completely beyond the right frame edge. The animal exits by "
    "traveling out of frame with an intact silhouette. Its black eye, ears, "
    "paws and tail remain recognizable throughout. The chair rolls right after "
    "it. Then the desk and monitor slide together as one rigid pixel-art prop "
    "to the right and fully cross the same frame edge. Keep their straight "
    "edges and proportions intact while they travel. By the final beat every "
    "orange subject and prop is offscreen, leaving the supplied empty black "
    "picture endpoint. Keep the camera fixed and the upper and left black "
    "negative space empty throughout. No dissolving bodies, morphing furniture, "
    "shrinking, particle breakup, opacity fades, gray collage, new scenery or "
    "generated terminal text. The terminal overlay is a separate editorial layer."
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bind", action="store_true")
    args = parser.parse_args()
    draft = json.loads((ROOT / "workflows/astrid_intro_h3_revision_prompts.json").read_text())
    stage = Path(tempfile.mkdtemp(prefix="astrid-intro-revision-20260918-"))
    frames = [175, 260, 175, 175, 209, 124]
    rows = draft["revisions"][:4] + [
        {"anchors": {"start": "terminal_v1_background", "end": "terminal_v1_background"}, "prompt": TYPING},
        {"anchors": {"start": "terminal_v1_background", "end": "black_frame"}, "prompt": EXIT},
    ]
    segments = []
    for i, row in enumerate(rows):
        prompt = row["prompt"].replace("TOOLS & STRUCTURES", "1 TOOLS & STRUCTURES").replace("COLLECTIVE KNOWLEDGE", "2 COLLECTIVE KNOWLEDGE")
        segments.append({"frames": frames[i], "start": row["anchors"]["start"] + ".png",
                         "end": row["anchors"]["end"] + ".png", "prompt": prompt,
                         "seed": 2026091801 + i})
    (stage / "segments.json").write_text(json.dumps(segments, indent=2) + "\n")
    evidence = {"project": PROJECT, "policy": "automatic execution and review authorized; not user-approved",
                "segments": segments, "inputs": {}, "bindings": []}
    with AstridClient.open_from_launcher(start_pack_host=False) as client:
        for name, anchor in draft["anchors"].items():
            data = client.media.read_bytes(anchor["media_id"])
            digest = "sha256:" + hashlib.sha256(data).hexdigest()
            if digest != anchor["media_id"]:
                raise RuntimeError(f"Anchor digest mismatch: {name}")
            path = stage / (name + ".png")
            path.write_bytes(data)
            evidence["inputs"][name] = {"media_id": digest, "path": str(path)}
        for i, segment in enumerate(segments):
            (stage / f"s{i+1:02}-prompt.txt").write_text(segment["prompt"])
        if args.bind:
            # Use the canonical CLI for versioned shot text writes; each revision
            # has a new stable slot, so existing run prompt identities stay intact.
            import subprocess
            for i, shot_ids in enumerate(SHOTS):
                for shot_id in shot_ids:
                    result = subprocess.run([
                        "python3", "-m", "astrid", "timelines", "shots", "text", "set", shot_id,
                        "--project", PROJECT, "--kind", "prompt", "--slot", f"h3-revision-20260918-{i+1:02}",
                        "--text-file", str(stage / f"s{i+1:02}-prompt.txt"), "--expected-head", "0", "--json",
                    ], check=True, text=True, capture_output=True)
                    evidence["bindings"].append(json.loads(result.stdout))
            evidence_path = stage / "preparation.json"
            evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
            imported = client.media.import_file(project=PROJECT, path=evidence_path)
            if not imported.ok:
                raise RuntimeError(str(imported.error))
            print(json.dumps({"staging": str(stage), "managed_evidence": imported.data}, indent=2))
        else:
            (stage / "preparation.json").write_text(json.dumps(evidence, indent=2) + "\n")
            print(json.dumps({"staging": str(stage), "status": "prepared-only"}))


if __name__ == "__main__":
    main()
