"""Canonical executor entrypoint for H3 request compilation."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from astrid.core._shared.result_manifest import build_manifest, write_manifest
from astrid.core.pack.entrypoint import guard_canonical_entrypoint, run_pack_main
from astrid.packs.h3_av.src.compile import compile_preparation


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile a prepared H3 request.")
    parser.add_argument("--preparation", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    args.out = args.out.expanduser().resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    result_manifest_path = args.out / "manifest.json"
    if result_manifest_path.exists():
        if result_manifest_path.is_symlink():
            raise ValueError("compile result manifest is a symlink")
        result_manifest_path.unlink()
    preparation = json.loads(args.preparation.read_text(encoding="utf-8"))
    if not isinstance(preparation, dict):
        raise ValueError("preparation must be a JSON object")
    result = compile_preparation(preparation, out_dir=args.out)
    if "workflow" not in result:
        # The generalized v2 boundary emits one shared graph manifest rather
        # than selecting a workflow-per-fixture trio.  The graph binding and
        # managed asset archive are the complete compile-stage outputs.
        output_paths = {
            "compilation": Path(result["manifest_path"]),
            "managed_assets": Path(result["managed_assets"]["path"]),
            "graph_binding": Path(result["graph_binding"]["path"]),
            "graph": Path(result["graph_binding"]["path"]).with_name("graph.vibe.json"),
        }
        if "prepared_artifact" in result:
            output_paths["prepared_artifact"] = Path(result["prepared_artifact"]["path"])
    else:
        # The paths recorded in compilation.json are attempt-local details.
        # Publish the selected canonical bundle as declared executor outputs
        # so Runtime settles each member as a managed object.
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
        output_paths = {
            "compilation": Path(result["manifest_path"]),
            "managed_assets": Path(result["managed_assets"]["path"]),
            "python": args.out / "workflow.py",
            "companion": args.out / "workflow.vibe.json",
            "source": args.out / "source.json",
        }

    outputs = []
    for ordinal, (name, path) in enumerate(output_paths.items()):
        if not path.is_file():
            raise RuntimeError(f"compiled output {name!r} is missing: {path}")
        outputs.append({
            "name": name,
            "path": path.name,
            "output_port": name,
            "ordinal": ordinal,
            "role": "result" if ordinal == 0 else "auxiliary",
            "is_primary": ordinal == 0,
        })
    write_manifest(
        result_manifest_path,
        build_manifest(
            kind="h3_av_compile_result",
            inputs={"preparation": str(args.preparation.expanduser().resolve())},
            outputs=outputs,
            created="h3_av.compile.v1",
        ),
    )
    print(json.dumps({name: str(path) for name, path in output_paths.items()}, sort_keys=True))
    return 0


if __name__ == "__main__":
    guard_canonical_entrypoint("h3_av.compile")
    raise SystemExit(run_pack_main("h3_av.compile", lambda: main()))
