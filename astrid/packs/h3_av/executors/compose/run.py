"""Canonical executor entrypoint for H3 candidate composition."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from astrid.core.pack.entrypoint import guard_canonical_entrypoint, run_pack_main

from astrid.packs.h3_av.src.compose import compose_candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compose an H3 audiovisual candidate.")
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--preservation-evidence", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    preparation = json.loads(args.preparation.read_text(encoding="utf-8"))
    evidence = None
    if args.preservation_evidence:
        evidence = json.loads(args.preservation_evidence.read_text(encoding="utf-8"))
    composition = compose_candidate(
        preparation=preparation,
        generated=args.generated,
        source=args.source,
        out_dir=args.out,
        preservation_evidence=evidence,
    )
    # Fixed declared output name, without pretending every container is MKV.
    # Decoders detect the container from bytes; preserve the original bytes.
    candidate = args.out / "candidate.media"
    original = Path(composition["candidate"]["path"])
    if original.resolve() != candidate.resolve():
        shutil.copyfile(original, candidate)
    composition["candidate"]["path"] = str(candidate.resolve())
    (args.out / "composition-manifest.json").write_text(
        json.dumps(composition, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"h3_av.compose: wrote {args.out / 'composition-manifest.json'}")
    return 0


if __name__ == "__main__":
    guard_canonical_entrypoint("h3_av.compose")
    raise SystemExit(run_pack_main("h3_av.compose", lambda: main()))
