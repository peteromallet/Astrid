"""Canonical executor entrypoint for H3 candidate verification."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from astrid.core.pack.entrypoint import guard_canonical_entrypoint, run_pack_main

from astrid.packs.h3_av.src.verify import verify_candidate


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify an H3 audiovisual candidate.")
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--composition", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    preparation = json.loads(args.preparation.read_text(encoding="utf-8"))
    composition = json.loads(args.composition.read_text(encoding="utf-8"))
    report = verify_candidate(preparation=preparation, composition=composition, source=args.source, candidate=args.candidate)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"h3_av.verify: wrote {args.out}")
    return 0


if __name__ == "__main__":
    guard_canonical_entrypoint("h3_av.verify")
    raise SystemExit(run_pack_main("h3_av.verify", lambda: main()))
