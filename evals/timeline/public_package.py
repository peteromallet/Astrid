"""Build the bounded, read-only Astrid package exposed to eval workers.

This is intentionally a source bundle rather than a checkout mount.  Only the
two installed public Python package roots and minimal canonical version
metadata are admitted; evaluator code, repository metadata, tests, caches,
local state, virtualenvs, and golden data never enter the bundle.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import tomllib
from dataclasses import asdict, dataclass
from pathlib import Path


PUBLIC_PACKAGE_KIND = "astrid.timeline-eval.public-package.v1"
PACKAGE_ROOTS = ("astrid", "banodoco_workspace_client")
EXCLUDED_PARTS = {
    "__pycache__", "tests", "test", "evals", "golden", "build", "dist",
    ".astrid", ".git", ".megaplan", ".otto", "node_modules", "site-packages",
    "venv", "venvs", "worktrees",
}
EXCLUDED_NAMES = {".DS_Store", ".gitkeep"}


class PublicPackageError(RuntimeError):
    """The public worker package cannot be built without leaking private state."""


@dataclass(frozen=True)
class PublicPackageReceipt:
    kind: str
    root: str
    tree_sha256: str
    file_count: int
    manifest_path: str
    skill_path: str

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _admitted(relative: Path) -> bool:
    return (
        not any(part in EXCLUDED_PARTS or part.startswith(".") for part in relative.parts)
        and relative.name not in EXCLUDED_NAMES
        and not relative.name.endswith((".pyc", ".pyo"))
    )


def _tree_rows(root: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise PublicPackageError(f"public package contains a symlink: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        content = path.read_bytes()
        rows.append({
            "path": relative,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size": len(content),
        })
    return rows


def _tree_digest(rows: list[dict[str, object]]) -> str:
    return hashlib.sha256(json.dumps(
        rows, sort_keys=True, separators=(",", ":"),
    ).encode("utf-8")).hexdigest()


def _remove_tree(path: Path) -> None:
    """Remove only our exact staging directory, including after chmod hardening."""
    if not path.exists():
        return
    for child in path.rglob("*"):
        if not child.is_symlink():
            os.chmod(child, 0o755 if child.is_dir() else 0o644)
    os.chmod(path, 0o755)
    shutil.rmtree(path)


def _stage_version_metadata(source: Path, destination: Path) -> None:
    """Write only the canonical name/version fields needed by astrid.version."""
    metadata_path = source / "pyproject.toml"
    if metadata_path.is_symlink() or not metadata_path.is_file():
        raise PublicPackageError(f"Astrid project metadata is missing or unsafe: {metadata_path}")
    try:
        with metadata_path.open("rb") as stream:
            project = tomllib.load(stream).get("project", {})
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise PublicPackageError(f"Astrid project metadata is unreadable: {metadata_path}") from exc
    name = project.get("name")
    version = project.get("version")
    if name != "astrid" or not isinstance(version, str) or not version.strip():
        raise PublicPackageError("Astrid project metadata has no canonical name/version")
    destination.write_text(
        "[project]\n"
        f"name = {json.dumps(name)}\n"
        f"version = {json.dumps(version.strip())}\n",
        encoding="utf-8",
    )


def stage_public_package(source_root: Path, packages_root: Path) -> PublicPackageReceipt:
    """Materialize one content-addressed public package and return its receipt."""
    source = source_root.expanduser().absolute()
    destination_parent = packages_root.expanduser().absolute()
    if source.is_symlink() or not source.is_dir():
        raise PublicPackageError(f"Astrid source root is missing or unsafe: {source}")
    if destination_parent.is_symlink():
        raise PublicPackageError(f"public package parent is a symlink: {destination_parent}")
    destination_parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".astrid-public-", dir=destination_parent))
    try:
        for package_name in PACKAGE_ROOTS:
            package_source = source / package_name
            if package_source.is_symlink() or not package_source.is_dir():
                raise PublicPackageError(f"required public package root is missing: {package_source}")
            for path in sorted(package_source.rglob("*")):
                relative = path.relative_to(source)
                if not _admitted(relative):
                    continue
                if path.is_symlink():
                    raise PublicPackageError(f"admitted public package path is a symlink: {path}")
                if not path.is_file():
                    continue
                destination = temporary / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, destination)

        _stage_version_metadata(source, temporary / "pyproject.toml")

        required = (
            Path("pyproject.toml"),
            Path("astrid/__init__.py"),
            Path("astrid/__main__.py"),
            Path("astrid/sdk/__init__.py"),
            Path("astrid/packs/rendering/skill/SKILL.md"),
            Path("astrid/packs/rendering/skill/references/timeline-cookbook.md"),
            Path("banodoco_workspace_client/__init__.py"),
        )
        missing = [path.as_posix() for path in required if not (temporary / path).is_file()]
        if missing:
            raise PublicPackageError("public package omitted required files: " + ", ".join(missing))
        rows = _tree_rows(temporary)
        digest = _tree_digest(rows)
        final_root = destination_parent / digest
        manifest = {
            "kind": PUBLIC_PACKAGE_KIND,
            "tree_sha256": digest,
            "file_count": len(rows),
            "files": rows,
        }
        (temporary / "public-package-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8",
        )
        if final_root.exists():
            existing_manifest = final_root / "public-package-manifest.json"
            if existing_manifest.is_symlink() or not existing_manifest.is_file():
                raise PublicPackageError(f"existing public package is incomplete: {final_root}")
            existing = json.loads(existing_manifest.read_text(encoding="utf-8"))
            existing_rows = [
                row for row in _tree_rows(final_root)
                if row["path"] != "public-package-manifest.json"
            ]
            if (
                existing.get("kind") != PUBLIC_PACKAGE_KIND
                or existing.get("tree_sha256") != digest
                or existing.get("file_count") != len(rows)
                or existing.get("files") != rows
                or existing_rows != rows
            ):
                raise PublicPackageError(f"existing public package digest mismatch: {final_root}")
            _remove_tree(temporary)
        else:
            temporary.replace(final_root)
            for path in sorted(final_root.rglob("*"), reverse=True):
                os.chmod(path, 0o555 if path.is_dir() else 0o444)
            os.chmod(final_root, 0o555)
        return PublicPackageReceipt(
            kind=PUBLIC_PACKAGE_KIND,
            root=str(final_root),
            tree_sha256="sha256:" + digest,
            file_count=len(rows),
            manifest_path=str(final_root / "public-package-manifest.json"),
            skill_path=str(final_root / "astrid/packs/rendering/skill/SKILL.md"),
        )
    except Exception:
        if temporary.exists():
            _remove_tree(temporary)
        raise


__all__ = [
    "PUBLIC_PACKAGE_KIND", "PublicPackageError", "PublicPackageReceipt",
    "stage_public_package",
]
