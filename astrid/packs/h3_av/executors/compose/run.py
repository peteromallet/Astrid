"""Canonical executor entrypoint for H3 candidate composition."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from astrid.core.pack.entrypoint import guard_canonical_entrypoint, run_pack_main

from astrid.packs.h3_av.src.compose import compose_candidate
from astrid.packs.h3_av.src.input_bundle import resolve_preparation_assets


def _portable_evidence(value: object) -> object:
    """Remove attempt-local locators from durable composition evidence."""

    if isinstance(value, dict):
        return {
            key: _portable_evidence(item)
            for key, item in value.items()
            if key not in {"path", "local_path", "manifest_path", "relative_path"}
        }
    if isinstance(value, list):
        return [_portable_evidence(item) for item in value]
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compose an H3 audiovisual candidate.")
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--generated", type=Path, required=True)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--input-bundle", type=Path)
    parser.add_argument("--preservation-evidence", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.out = args.out.expanduser().resolve()
    stale_manifest = args.out / "manifest.json"
    if stale_manifest.exists():
        if stale_manifest.is_symlink():
            raise ValueError("compose result manifest is a symlink")
        stale_manifest.unlink()
    preparation = json.loads(args.preparation.read_text(encoding="utf-8"))
    if args.input_bundle:
        preparation = resolve_preparation_assets(
            preparation,
            args.input_bundle,
            args.out / ".input-assets",
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
    evidence = None
    if args.preservation_evidence:
        evidence = json.loads(args.preservation_evidence.read_text(encoding="utf-8"))
    report = compose_candidate(
        preparation=preparation,
        generated=args.generated,
        source=args.source,
        out_dir=args.out,
        preservation_evidence=evidence,
    )
    candidate_info = report.get("candidate")
    if not isinstance(candidate_info, dict):
        raise ValueError("composition did not emit candidate identity")
    candidate_path = Path(str(candidate_info.get("path", ""))).expanduser().resolve()
    composition_path = args.out / "composition-manifest.json"
    if not candidate_path.is_file() or not composition_path.is_file():
        raise ValueError("composition did not emit its declared candidate and evidence")
    # Keep local compatibility in the function return, but make the managed
    # composition object path-free. Verify receives the candidate explicitly.
    durable_report = _portable_evidence(report)
    composition_path.write_text(
        json.dumps(durable_report, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    candidate_bytes = candidate_path.read_bytes()
    composition_bytes = composition_path.read_bytes()
    candidate_digest = "sha256:" + hashlib.sha256(candidate_bytes).hexdigest()
    if candidate_info.get("sha256") != candidate_digest.removeprefix("sha256:"):
        raise ValueError("composition candidate identity changed before harvest")
    manifest = {
        "schema_version": 1,
        "kind": "h3_av_compose_result",
        "created": "h3_av.compose.v2",
        "inputs": {"composition_sha256": "sha256:" + hashlib.sha256(composition_bytes).hexdigest()},
        "warnings": [],
        "outputs": [
            {
                "name": "candidate",
                "path": candidate_path.name,
                "ordinal": 0,
                "content_hash": candidate_digest,
                "bytes": len(candidate_bytes),
                "media_type": "video/x-matroska",
                "output_port": "candidate",
                "role": "result",
                "is_primary": True,
            },
            {
                "name": "composition",
                "path": composition_path.name,
                "ordinal": 1,
                "content_hash": "sha256:" + hashlib.sha256(composition_bytes).hexdigest(),
                "bytes": len(composition_bytes),
                "media_type": "application/json",
                "role": "auxiliary",
                "is_primary": False,
            },
        ],
    }
    temporary = args.out / ".manifest.json.tmp"
    temporary.write_text(json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    temporary.replace(args.out / "manifest.json")
    print(f"h3_av.compose: wrote {args.out / 'manifest.json'}")
    return 0


if __name__ == "__main__":
    guard_canonical_entrypoint("h3_av.compose")
    raise SystemExit(run_pack_main("h3_av.compose", lambda: main()))
