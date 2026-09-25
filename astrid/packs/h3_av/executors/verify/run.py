"""Canonical executor entrypoint for H3 candidate verification."""

from __future__ import annotations

import argparse
import json
import hashlib
import shutil
from pathlib import Path

from astrid.core.pack.entrypoint import guard_canonical_entrypoint, run_pack_main

from astrid.packs.h3_av.src.verify import verify_candidate
from astrid.packs.h3_av.src.input_bundle import resolve_preparation_assets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Verify an H3 audiovisual candidate.")
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--composition", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--input-bundle", type=Path)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    preparation = json.loads(args.preparation.read_text(encoding="utf-8"))
    composition = json.loads(args.composition.read_text(encoding="utf-8"))
    output_root = args.out
    if output_root.suffix.lower() == ".json":
        # Keep direct legacy invocations usable while the managed definition
        # always supplies the host-owned output directory.
        output_root = output_root.parent
    output_root = output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    stale_manifest = output_root / "manifest.json"
    if stale_manifest.exists():
        if stale_manifest.is_symlink():
            raise ValueError("verify result manifest is a symlink")
        stale_manifest.unlink()
    if args.input_bundle:
        preparation = resolve_preparation_assets(
            preparation,
            args.input_bundle,
            output_root / ".input-assets",
        )
        if args.source is None:
            request = preparation.get("request", {})
            source_spec = request.get("source") if isinstance(request, dict) else None
            source_asset = source_spec.get("asset") if isinstance(source_spec, dict) else None
            if source_asset is None and isinstance(request, dict):
                for item in request.get("media", []):
                    if isinstance(item, dict) and item.get("role") == "timeline" and item.get("modality") == "video":
                        source_asset = item.get("asset")
                        break
            for asset in preparation.get("assets", []):
                if isinstance(asset, dict) and asset.get("asset") == source_asset:
                    args.source = Path(str(asset["path"]))
                    break
    candidate = args.candidate.expanduser()
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("managed candidate is not a regular file")
    candidate = candidate.resolve(strict=True)
    staged_candidate = output_root / "verified-candidate.mkv"
    if staged_candidate.exists() and staged_candidate.is_symlink():
        raise ValueError("verified candidate output is a symlink")
    shutil.copyfile(candidate, staged_candidate)
    report = verify_candidate(
        preparation=preparation,
        composition=composition,
        candidate=staged_candidate,
        source=args.source,
    )
    expected_digest = "sha256:" + hashlib.sha256(staged_candidate.read_bytes()).hexdigest()
    candidate_info = composition.get("candidate")
    if not isinstance(candidate_info, dict) or candidate_info.get("sha256") != expected_digest.removeprefix("sha256:"):
        raise ValueError("verified candidate changed after exact verification")
    verification_path = output_root / "verification.json"
    verification_path.write_text(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "kind": "h3_av_verify_result",
        "created": "h3_av.verify.v2",
        "inputs": {
            "candidate_sha256": expected_digest,
            "composition_sha256": "sha256:" + hashlib.sha256(args.composition.read_bytes()).hexdigest(),
        },
        "warnings": [],
        "outputs": [
            {
                "name": "verified_candidate",
                "path": staged_candidate.name,
                "ordinal": 0,
                "content_hash": expected_digest,
                "bytes": staged_candidate.stat().st_size,
                "media_type": "video/x-matroska",
                "output_port": "verified_candidate",
                "group_key": "main",
                "variant_key": "original",
                "selector": {"group_key": "main", "variant_key": "original"},
                "role": "result",
                "is_primary": True,
            },
            {
                "name": "verification",
                "path": verification_path.name,
                "ordinal": 1,
                "content_hash": "sha256:" + hashlib.sha256(verification_path.read_bytes()).hexdigest(),
                "bytes": verification_path.stat().st_size,
                "media_type": "application/json",
                "role": "auxiliary",
                "is_primary": False,
            },
        ],
    }
    manifest_path = output_root / "manifest.json"
    temporary = output_root / ".manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(manifest_path)
    print(f"h3_av.verify: wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    guard_canonical_entrypoint("h3_av.verify")
    raise SystemExit(run_pack_main("h3_av.verify", lambda: main()))
