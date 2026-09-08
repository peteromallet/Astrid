"""Build the writable skill view consumed by agent harnesses.

The package checkout (and an installed wheel) is an input, never a generated
output location.  A view contains a real root ``SKILL.md``, a small real core
directory skeleton, and symlinked pack skill directories.
"""

from __future__ import annotations

import shutil
from dataclasses import replace
from pathlib import Path

from astrid.core.contracts.errors import AstridError

from .discovery import SkillDescriptor
from .harnesses.base import PlannedStep, ensure_symlink


_ROOT_ROUTE_REWRITES = {
    "../../rendering/skill/SKILL.md": "packs/rendering/SKILL.md",
    "../../references/skill/SKILL.md": "packs/references/SKILL.md",
    "../../hivemind/skill/SKILL.md": "packs/hivemind/SKILL.md",
}
_CREATIVE_ROUTE_REWRITES = {
    "../../../generation/skill/SKILL.md": "../packs/generation/SKILL.md",
    "../../../vibecomfy/skill/SKILL.md": "../packs/vibecomfy/SKILL.md",
    "../../../understanding/skill/SKILL.md": "../packs/understanding/SKILL.md",
    "../../../editorial/skill/SKILL.md": "../packs/editorial/SKILL.md",
    "../../../media/skill/SKILL.md": "../packs/media/SKILL.md",
    "../../../video_editing/skill/SKILL.md": "../packs/video_editing/SKILL.md",
    "../../../rendering/skill/SKILL.md": "../packs/rendering/SKILL.md",
    "../../../iteration/skill/SKILL.md": "../packs/iteration/SKILL.md",
    "../../../fal/skill/SKILL.md": "../packs/fal/SKILL.md",
    "../../../foley/skill/SKILL.md": "../packs/foley/SKILL.md",
    "../../../stream_content/skill/SKILL.md": "../packs/stream_content/SKILL.md",
    "../../../training/skill/SKILL.md": "../packs/training/SKILL.md",
    "../../../blender/skill/SKILL.md": "../packs/blender/SKILL.md",
    "../../../moirae/skill/SKILL.md": "../packs/moirae/SKILL.md",
    "../../../youtube/skill/SKILL.md": "../packs/youtube/SKILL.md",
    "../pack-builder/SKILL.md": "../pack-builder/SKILL.md",
}
_PACK_BUILDER_DOC_PREFIX = "https://github.com/peteromallet/Astrid/blob/main/"
_PACK_BUILDER_VIEW_REWRITES = {
    "../../../rendering/skill/SKILL.md": "../packs/rendering/SKILL.md",
    "../../../references/skill/SKILL.md": "../packs/references/SKILL.md",
}


def _rewrite(text: str, replacements: dict[str, str]) -> str:
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


def _safe_link(target: Path, source: Path) -> None:
    if target.exists() or target.is_symlink():
        if target.is_symlink() and target.resolve() == source.resolve():
            return
        if not target.is_symlink():
            raise AstridError(
                f"Astrid skill view target is occupied: {target}",
                recovery_command="remove the foreign entry or choose another profile",
            )
    ensure_symlink(target, source)


def view_descriptors(root: Path, packs: list[SkillDescriptor]) -> list[SkillDescriptor]:
    """Return descriptors addressed through the generated view."""
    return [
        replace(
            descriptor,
            skill_dir=root / "packs" / descriptor.pack_id,
            skill_md=root / "packs" / descriptor.pack_id / "SKILL.md",
        )
        for descriptor in packs
    ]


def compose_view(
    root: Path,
    core: SkillDescriptor,
    packs: list[SkillDescriptor],
    *,
    dry_run: bool = False,
) -> tuple[SkillDescriptor, list[PlannedStep]]:
    """Compose one harness view and return a descriptor for its gateway.

    Pack links are keyed by pack id and are therefore safe to reconcile without
    touching unrelated user files.  The returned gateway descriptor points at
    the writable view, so registry writes cannot follow a symlink into source.
    """
    steps: list[PlannedStep] = []
    core_source = core.skill_dir
    if not dry_run:
        root.mkdir(parents=True, exist_ok=True)

        root_text = _rewrite(core.skill_md.read_text(encoding="utf-8"), _ROOT_ROUTE_REWRITES)
        (root / "SKILL.md").write_text(root_text, encoding="utf-8")

        # Keep source-owned guidance read-only while making the generated
        # registry file a regular file in the view.
        for relative in ("pack-builder/SKILL.md", "references/capabilities.md"):
            source = core_source / relative
            if source.exists():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                if relative == "pack-builder/SKILL.md":
                    # The authoring guides live outside the Python package and
                    # therefore are not present in a clean wheel.  Keep the
                    # composed skill navigable by resolving those links to the
                    # canonical public docs; package-owned skill routes remain
                    # source-relative and continue to work offline.
                    text = source.read_text(encoding="utf-8")
                    text = text.replace(
                        "../../../../../docs/",
                        _PACK_BUILDER_DOC_PREFIX + "docs/",
                    ).replace(
                        "../../../../../scripts/",
                        _PACK_BUILDER_DOC_PREFIX + "scripts/",
                    )
                    text = _rewrite(text, _PACK_BUILDER_VIEW_REWRITES)
                    # A previous composition may have left this managed
                    # entry as a symlink. Unlink it before writing the
                    # rewritten view copy so the source checkout remains
                    # read-only and untouched.
                    if target.is_symlink():
                        target.unlink()
                    target.write_text(text, encoding="utf-8")
                else:
                    _safe_link(target, source)
        creative_source = core_source / "creative-work"
        creative_target = root / "creative-work"
        creative_target.mkdir(parents=True, exist_ok=True)
        creative_skill = creative_source / "SKILL.md"
        if creative_skill.exists():
            (creative_target / "SKILL.md").write_text(
                _rewrite(creative_skill.read_text(encoding="utf-8"), _CREATIVE_ROUTE_REWRITES),
                encoding="utf-8",
            )
        references = creative_target / "references"
        references.mkdir(parents=True, exist_ok=True)
        source_packs = creative_source / "references" / "packs.md"
        if source_packs.exists() and not (references / "packs.md").exists():
            shutil.copyfile(source_packs, references / "packs.md")

    view_packs = view_descriptors(root, packs)
    enabled_ids = {descriptor.pack_id for descriptor in view_packs}
    marker = root / ".astrid-managed-packs"
    previous_ids = set()
    if marker.is_file():
        previous_ids = {line.strip() for line in marker.read_text(encoding="utf-8").splitlines() if line.strip()}
    for pack_id in sorted(previous_ids - enabled_ids):
        target = root / "packs" / pack_id
        if target.is_symlink():
            steps.append(PlannedStep(f"prune disabled pack {target}", target=target))
            if not dry_run:
                target.unlink()

    for descriptor in view_packs:
        target = root / "packs" / descriptor.pack_id
        source = next(item.skill_dir for item in packs if item.pack_id == descriptor.pack_id)
        steps.append(PlannedStep(f"link {target} -> {source}", target=target))
        if not dry_run:
            _safe_link(target, source)
    if not dry_run:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("\n".join(sorted(enabled_ids)) + "\n", encoding="utf-8")
    gateway = replace(
        core,
        skill_dir=root,
        skill_md=root / "SKILL.md",
    )
    return gateway, steps, view_packs


__all__ = ["compose_view", "view_descriptors"]
