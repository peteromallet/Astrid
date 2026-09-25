"""Canonical executor entrypoint for H3 request preparation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from astrid.core._shared.result_manifest import build_manifest, write_manifest
from astrid.core.pack.entrypoint import guard_canonical_entrypoint, run_pack_main

from astrid.packs.h3_av.src.prepare import prepare_request, write_preparation
from astrid.packs.h3_av.src.request import load_request
from astrid.packs.h3_av.src.input_bundle import bundle_digest, materialize_input_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare an H3 audiovisual request.")
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--asset-map", type=Path)
    parser.add_argument("--input-bundle", type=Path)
    parser.add_argument("--fps", type=float, default=24.0)
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=576)
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--target-model-dimensions", type=Path)
    parser.add_argument("--channel-layout", default="stereo")
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.out = args.out.expanduser().resolve()
    result_manifest_path = args.out.parent / "manifest.json"
    if result_manifest_path.exists():
        if result_manifest_path.is_symlink():
            raise ValueError("prepare result manifest is a symlink")
        result_manifest_path.unlink()
    request = load_request(args.request)
    asset_map = None
    if args.asset_map:
        raw = json.loads(args.asset_map.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or not all(isinstance(key, str) and isinstance(value, str) for key, value in raw.items()):
            raise ValueError("asset map must be a JSON object of string ids to string paths")
        asset_map = raw
    if args.input_bundle:
        asset_map, identities = materialize_input_bundle(
            request, args.input_bundle, args.out.parent / ".input-assets"
        )
    else:
        asset_map = None
        identities = None
    manifest = prepare_request(
        request,
        asset_map=asset_map,
        fps=args.fps,
        width=args.width,
        height=args.height,
        sample_rate=args.sample_rate,
        target_model_dimensions=(json.loads(args.target_model_dimensions.read_text(encoding="utf-8")) if args.target_model_dimensions else None),
        channel_layout=args.channel_layout,
    )
    if identities is not None:
        manifest["input_bundle_sha256"] = bundle_digest(args.input_bundle)
    write_preparation(args.out, manifest)
    write_manifest(
        result_manifest_path,
        build_manifest(
            kind="h3_av_prepare_result",
            inputs={"request": str(args.request.expanduser().resolve())},
            outputs=[
                {
                    "name": "preparation",
                    "path": args.out.name,
                    "output_port": "preparation",
                    "role": "result",
                    "is_primary": True,
                }
            ],
            created="h3_av.prepare.v1",
        ),
    )
    print(f"h3_av.prepare: wrote {args.out}")
    return 0


if __name__ == "__main__":
    guard_canonical_entrypoint("h3_av.prepare")
    raise SystemExit(run_pack_main("h3_av.prepare", lambda: main()))
