"""Materialize the reproducible offline derivatives used by navigation evals."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

try:
    from .fixture import derive_invalid_authoring_candidate
    from .fixture_manifest import DEFAULT_FIXTURE_ROOT
except ImportError:  # pragma: no cover - direct script invocation
    from fixture import derive_invalid_authoring_candidate
    from fixture_manifest import DEFAULT_FIXTURE_ROOT


def materialize_l06(fixture_root: Path) -> tuple[Path, str]:
    manifest_path = fixture_root / "informational" / "fixture.json"
    manifest: dict[str, Any] = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = manifest.get("source", {})
    baseline_path = (manifest_path.parent / str(source.get("baseline", ""))).resolve()
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    result = derive_invalid_authoring_candidate(baseline)
    output = manifest_path.parent / "L06-stale-invalid-candidate.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    digest = "sha256:" + hashlib.sha256(output.read_bytes()).hexdigest()
    return output, digest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-root", type=Path, default=DEFAULT_FIXTURE_ROOT)
    args = parser.parse_args()
    path, digest = materialize_l06(args.fixture_root.expanduser().absolute())
    print(json.dumps({"l06_invalid_candidate": str(path), "sha256": digest}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
