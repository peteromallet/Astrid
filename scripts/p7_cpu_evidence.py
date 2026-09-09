"""Read-only, deterministic P7 CPU evidence scanning.

This scanner is deliberately an evidence instrument, not a closure gate.  It
accepts explicitly named repository roots, scans production-looking source
files for the P7 forbidden authorities, and reports facts as ``implemented``,
``blocked``, or ``unknown``.  It never deletes, imports, executes, or mutates
the scanned repositories.

Usage::

    python -m scripts.p7_cpu_evidence \
        --repo astrid=/path/to/Astrid \
        --repo reigh-worker=/path/to/reigh-worker
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "astrid.p7_cpu_evidence.v1"

# These are intentionally scoped to source text.  Tests and documentation may
# name retired paths to prove their absence and must be reported separately.
SOURCE_DIRS = frozenset(
    {
        "app",
        "astrid",
        "backend",
        "backends",
        "bin",
        "lib",
        "packages",
        "reigh",
        "src",
        "worker",
    }
)
EXCLUDED_DIRS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".tox",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "site-packages",
        "venv",
        ".venv",
    }
)
TEXT_SUFFIXES = frozenset(
    {".c", ".cc", ".cpp", ".go", ".js", ".jsx", ".json", ".py", ".rs", ".ts", ".tsx", ".yaml", ".yml"}
)
STAGE1_SUFFIXES = TEXT_SUFFIXES | {".md"}


@dataclass(frozen=True)
class Marker:
    fact_id: str
    label: str
    pattern: re.Pattern[str]


MARKERS = (
    Marker("forbidden.inpaint_frames", "inpaint_frames", re.compile(r"\binpaint_frames\b")),
    Marker("forbidden.qwen_image_hires", "qwen_image_hires", re.compile(r"\bqwen_image_hires\b")),
    Marker(
        "forbidden.supabase_task_authority",
        "Supabase task lifecycle/materialization",
        re.compile(r"(?:supabase|materializ(?:e|ation|ed)|task[_ -]?(?:claim|lifecycle|status|retry|settle))", re.IGNORECASE),
    ),
    Marker(
        "forbidden.legacy_selector",
        "legacy selectors",
        re.compile(r"(?:legacy[_ -]?selector|selector[_ -]?legacy|legacy[_ -]?route|TASK_TYPE_TO_MODEL)", re.IGNORECASE),
    ),
    Marker(
        "forbidden.direct_engine",
        "direct-engine entrypoints",
        re.compile(r"(?:direct[_ -]?engine|run[_ -]?direct|native[_ -]?worker|backend[_ -]?warm)", re.IGNORECASE),
    ),
)


def _is_text_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in TEXT_SUFFIXES


def _is_production_path(root: Path, path: Path) -> bool:
    relative = path.relative_to(root)
    if any(part in EXCLUDED_DIRS for part in relative.parts):
        return False
    if any(part in {"tests", "test", "docs", "doc", "scripts", "fixtures", "examples"} for part in relative.parts[:-1]):
        return False
    # A root-level source file is a valid source surface; otherwise require a
    # conventional production directory so README/config text is not scanned.
    return len(relative.parts) == 1 or relative.parts[0] in SOURCE_DIRS


def _iter_files(root: Path) -> tuple[Path, ...]:
    paths = (path for path in root.rglob("*") if _is_text_file(path))
    return tuple(sorted((path for path in paths if _is_production_path(root, path)), key=lambda p: p.relative_to(root).as_posix()))


def _stage1_paths(root: Path) -> tuple[str, ...]:
    stage1 = root / "tests" / "stage1"
    if not stage1.is_dir():
        return ()
    return tuple(
        sorted(
            path.relative_to(root).as_posix()
            for path in stage1.rglob("*")
            if path.is_file() and path.suffix.lower() in STAGE1_SUFFIXES
        )
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _matches(root: Path, files: Iterable[Path]) -> dict[str, list[dict[str, Any]]]:
    found: dict[str, list[dict[str, Any]]] = {marker.fact_id: [] for marker in MARKERS}
    for path in files:
        relative = path.relative_to(root).as_posix()
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except (OSError, UnicodeDecodeError):
            continue
        for line_number, line in enumerate(lines, start=1):
            for marker in MARKERS:
                if marker.pattern.search(line):
                    found[marker.fact_id].append(
                        {"path": relative, "line": line_number, "text": line.strip()[:240]}
                    )
    return found


def _fact(marker: Marker, matches: list[dict[str, Any]], scanned_files: int) -> dict[str, Any]:
    if not scanned_files:
        status = "unknown"
        reason = "no production source files were discoverable under the explicit root"
    elif matches:
        status = "blocked"
        reason = f"{len(matches)} production-source marker(s) observed"
    else:
        status = "implemented"
        reason = "deterministic production-source scan found no configured marker"
    return {
        "id": marker.fact_id,
        "label": marker.label,
        "status": status,
        "reason": reason,
        "matches": matches,
    }


def scan_repo(name: str, root: str | Path) -> dict[str, Any]:
    """Scan one explicit repository root without changing it."""
    resolved = Path(root).expanduser().resolve()
    if not resolved.is_dir():
        return {
            "name": name,
            "root": str(resolved),
            "facts": {
                "implemented": [],
                "blocked": [],
                "unknown": [{"id": "repository.root", "status": "unknown", "reason": "explicit root is not a directory"}],
            },
            "scanned_files": [],
            "stage1_paths": [],
        }

    files = _iter_files(resolved)
    matches = _matches(resolved, files)
    facts = [_fact(marker, matches[marker.fact_id], len(files)) for marker in MARKERS]
    stage1_paths = _stage1_paths(resolved)
    stage1_fact = {
        "id": "stage1.paths_preserved",
        "status": "implemented" if stage1_paths else "unknown",
        "reason": "Stage1 paths are inventoried separately from forbidden production scans"
        if stage1_paths
        else "tests/stage1 contains no discoverable text paths",
        "count": len(stage1_paths),
        "paths_sha256": _sha256_list(resolved, stage1_paths),
    }
    facts.append(stage1_fact)
    grouped = {"implemented": [], "blocked": [], "unknown": []}
    for fact in facts:
        grouped[fact["status"]].append(fact)
    return {
        "name": name,
        "root": str(resolved),
        "scanned_files": [path.relative_to(resolved).as_posix() for path in files],
        "stage1_paths": list(stage1_paths),
        "facts": grouped,
    }


def _sha256_list(root: Path, paths: Iterable[str]) -> str | None:
    entries = []
    for relative in paths:
        path = root / relative
        try:
            entries.append((relative, _sha256(path)))
        except OSError:
            return None
    if not entries:
        return None
    payload = json.dumps(entries, separators=(",", ":"), sort_keys=True).encode("utf-8")
    return "sha256:" + hashlib.sha256(payload).hexdigest()


def scan_repositories(repositories: Iterable[tuple[str, str | Path]]) -> dict[str, Any]:
    """Return stable machine-readable evidence for explicit repository roots."""
    ordered = sorted(((str(name), root) for name, root in repositories), key=lambda item: item[0])
    if len({name for name, _ in ordered}) != len(ordered):
        raise ValueError("repository names must be unique")
    results = [scan_repo(name, root) for name, root in ordered]
    return {"schema": SCHEMA, "read_only": True, "repos": results}


def _parse_repo(value: str) -> tuple[str, str]:
    name, separator, root = value.partition("=")
    if not separator or not name.strip() or not root.strip():
        raise argparse.ArgumentTypeError("--repo must be NAME=PATH")
    return name.strip(), root.strip()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", action="append", required=True, type=_parse_repo, metavar="NAME=PATH")
    parser.add_argument("--pretty", action="store_true", help="indent JSON output")
    args = parser.parse_args(argv)
    try:
        payload = scan_repositories(args.repo)
    except ValueError as exc:
        parser.error(str(exc))
    print(json.dumps(payload, indent=2 if args.pretty else None, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
