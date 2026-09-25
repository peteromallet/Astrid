"""Canonical executor entrypoint for H3 request compilation."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from astrid.core.pack.entrypoint import guard_canonical_entrypoint, run_pack_main
from astrid.packs.h3_av.src.compile import compile_preparation
from astrid.packs.h3_av.src.input_bundle import resolve_preparation_assets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile a prepared H3 request.")
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--input-bundle", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    preparation = json.loads(args.preparation.read_text(encoding="utf-8"))
    if not isinstance(preparation, dict):
        raise ValueError("preparation must be a JSON object")
    preparation = resolve_preparation_assets(
        preparation, args.input_bundle, args.out / "request-assets"
    )
    result = compile_preparation(preparation, out_dir=args.out)
    # The paths recorded in compilation.json are attempt-local implementation
    # details.  Publish the selected canonical bundle as declared executor
    # outputs so the Runtime settles each member as a managed object.
    published: dict[str, str] = {}
    for output_name, filename in (
        ("python", "workflow.py"),
        ("companion", "workflow.vibe.json"),
        ("source", "source.json"),
    ):
        source = Path(result["workflow"][filename]["path"])
        destination = args.out / filename
        if not source.is_file():
            raise RuntimeError(f"compiled workflow member {filename!r} is missing")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        expected = result["workflow"][filename]["sha256"]
        actual = hashlib.sha256(destination.read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"published workflow member {filename!r} failed hash verification")
        published[output_name] = str(destination)
    print(json.dumps({
        "compilation": result["manifest_path"],
        "managed_assets": result["managed_assets"]["path"],
        **published,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    guard_canonical_entrypoint("h3_av.compile")
    raise SystemExit(run_pack_main("h3_av.compile", lambda: main()))
