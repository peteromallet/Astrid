from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from evals.timeline.public_package import (
    PUBLIC_PACKAGE_KIND,
    PublicPackageError,
    stage_public_package,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_public_package_is_bounded_content_addressed_and_importable(tmp_path: Path) -> None:
    receipt = stage_public_package(REPO_ROOT, tmp_path / "packages")
    package_root = Path(receipt.root)
    manifest = json.loads(Path(receipt.manifest_path).read_text(encoding="utf-8"))

    assert receipt.kind == PUBLIC_PACKAGE_KIND
    assert receipt.tree_sha256 == "sha256:" + manifest["tree_sha256"]
    assert receipt.file_count == manifest["file_count"]
    assert package_root.name == manifest["tree_sha256"]
    assert Path(receipt.skill_path).is_file()

    relative_paths = {row["path"] for row in manifest["files"]}
    assert "astrid/__main__.py" in relative_paths
    assert "astrid/sdk/__init__.py" in relative_paths
    assert "astrid/packs/rendering/skill/SKILL.md" in relative_paths
    assert not any(
        forbidden in Path(path).parts
        for path in relative_paths
        for forbidden in ("evals", "tests", "golden", "__pycache__", ".astrid", ".otto")
    )
    assert not any(path.endswith((".pyc", ".pyo", ".DS_Store")) for path in relative_paths)
    assert not any(path.is_symlink() for path in package_root.rglob("*"))

    environment = {
        "PATH": os.environ.get("PATH", ""),
        "PYTHONPATH": str(package_root),
        "PYTHONNOUSERSITE": "1",
    }
    help_result = subprocess.run(
        [sys.executable, "-m", "astrid", "--help"],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert help_result.returncode == 0, help_result.stderr
    assert "usage:" in help_result.stdout.lower()

    import_result = subprocess.run(
        [sys.executable, "-c", "import astrid.sdk; print(astrid.sdk.__file__)"],
        env=environment,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    assert import_result.returncode == 0, import_result.stderr
    assert Path(import_result.stdout.strip()).is_relative_to(package_root)


def test_public_package_reuses_identical_content_address(tmp_path: Path) -> None:
    first = stage_public_package(REPO_ROOT, tmp_path / "packages")
    second = stage_public_package(REPO_ROOT, tmp_path / "packages")
    assert second == first


def test_public_package_reuse_rejects_tampered_read_only_tree(tmp_path: Path) -> None:
    first = stage_public_package(REPO_ROOT, tmp_path / "packages")
    module = Path(first.root) / "astrid/__init__.py"
    module.chmod(0o644)
    module.write_text("# tampered\n", encoding="utf-8")

    with pytest.raises(PublicPackageError, match="digest mismatch"):
        stage_public_package(REPO_ROOT, tmp_path / "packages")
