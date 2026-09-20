"""H3 AV generation with the end frame used only as a reference image.

This is a derived recipe, not a replacement for the custody-locked imported
workflow in ``seitanism_h3_av_extension_verified``.  It keeps the canonical
latent and audiovisual graph unchanged, replaces one of its two legacy
reference images with the supplied end frame, and does not add or enable a
``MiniMaxH3CustomKeyframes`` node.
"""
from __future__ import annotations

import os
from pathlib import Path

from vibecomfy.cli_loader import load_bundle
from vibecomfy.security.provenance import Provenance
from vibecomfy.workflow import NodeMode, VibeWorkflow


ASTRID_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CANONICAL_WORKFLOW = ASTRID_ROOT / "workflows" / "seitanism_h3_av_extension_verified"
CANONICAL_WORKFLOW = Path(
    os.environ.get("ASTRID_H3_CANONICAL_WORKFLOW", str(DEFAULT_CANONICAL_WORKFLOW))
)
DEFAULT_END_FRAME = (
    ASTRID_ROOT.parent
    / "runs"
    / "minkhole-keyframes-20260910"
    / "ending"
    / "neo_mink_run"
    / "20260910-223930-create-one-full-frame-cinematic-16-9-key.png"
)
END_FRAME = Path(os.environ.get("ASTRID_H3_END_FRAME", str(DEFAULT_END_FRAME)))
SOURCE_VIDEO = os.environ.get("ASTRID_H3_SOURCE_VIDEO")
DEFAULT_REFERENCE_IMAGE = (
    ASTRID_ROOT
    / "runs"
    / "matrix-minkhole"
    / "h3-continuation-20260917"
    / "r4i"
    / "input"
    / "source_tail_r4i.png"
)
REFERENCE_IMAGE = Path(
    os.environ.get("ASTRID_H3_REFERENCE_IMAGE", str(DEFAULT_REFERENCE_IMAGE))
)
REMOTE_INPUT_NAMES = os.environ.get("ASTRID_H3_REMOTE_INPUT_NAMES") == "1"
H3_PACK = "ComfyUI-H3-Motion-Context-MultiRef"
H3_PACK_COMMIT = "361624fb406b63eb6694442eac6c895fc1533a70"

# The comparison recipes default to a short test extension. Set this to 5 for
# the full D14-sized extension; H3 quantizes the requested frame count to its
# valid temporal block size.
EXTENSION_SECONDS = float(os.environ.get("ASTRID_H3_EXTENSION_SECONDS", "3"))


def _target_frames(seconds: float) -> int:
    raw_frames = max(5, round(seconds * 24))
    return raw_frames + (5 - (raw_frames % 17)) % 17


TARGET_FRAMES = _target_frames(EXTENSION_SECONDS)

ACTION_PROMPT = (
    "A single continuous cinematic shot begins in a black graphic Matrix world "
    "with green digital code, orange vector graphics, and a reflective floor. A "
    "small orange pixelated mink is in the foreground holding simple tools. The "
    "mink turns around, throws the tools aside, and runs quickly to the right. "
    "As the mink runs, its orange pixelated body visibly transforms into a "
    "realistic mink with detailed fur and natural movement. The stylized world "
    "transforms into a realistic cinematic Matrix environment with green code "
    "rain, reflective surfaces, atmospheric depth, and natural lighting. Neo, a "
    "recognizable human man with short dark hair and a black coat, runs in behind "
    "the mink and keeps pace beside it. A side-tracking camera follows Neo and "
    "the realistic mink as they run together toward a glowing doorway. Preserve "
    "Neo's recognizable face, black coat, and silhouette, and preserve the mink's "
    "identity through the transformation. Show the transformation clearly while "
    "maintaining coherent motion, scale, lighting, and direction. No cut, no "
    "unrelated scene, no random woman, no duplicate characters, no static pose, "
    "no frozen frame, and no reset."
)


def _input_reference(path: Path) -> str:
    return path.name if REMOTE_INPUT_NAMES else str(path)


def build() -> VibeWorkflow:
    """Build the reference-only endpoint candidate."""
    if not END_FRAME.is_file():
        raise FileNotFoundError(f"end frame is missing: {END_FRAME}")
    if not REFERENCE_IMAGE.is_file():
        raise FileNotFoundError(f"source-tail reference is missing: {REFERENCE_IMAGE}")

    bundle = load_bundle(
        CANONICAL_WORKFLOW,
        trust=Provenance.USER_CONFIRMED,
        allow_unresolved=True,
    )
    workflow = bundle.workflow.copy()

    if H3_PACK not in workflow.requirements.custom_nodes:
        workflow.requirements.custom_nodes.append(H3_PACK)
    workflow.requirements.custom_nodes.sort()
    requirements = workflow.metadata.setdefault("requirements", {})
    requirements["custom_nodes"] = list(workflow.requirements.custom_nodes)
    requirements["custom_node_refs"] = [
        {
            "slug": H3_PACK,
            "name": H3_PACK,
            "source": "git",
            "commit": H3_PACK_COMMIT,
            "url": "https://github.com/seitanism/ComfyUI-H3-Motion-Context-MultiRef.git",
        }
    ]

    if SOURCE_VIDEO:
        source_video = Path(SOURCE_VIDEO)
        if not source_video.is_file():
            raise FileNotFoundError(f"source video is missing: {source_video}")
        workflow.nodes["99"].inputs["video"] = _input_reference(source_video)

    workflow.nodes["102"].inputs["values.a"] = EXTENSION_SECONDS

    # Keep the source-tail image as the first appearance reference and use the
    # end frame as the second appearance reference. No keyframe conditioning is
    # added, so the image is not injected at a target frame.
    workflow.nodes["1020"].inputs["image"] = _input_reference(REFERENCE_IMAGE)
    workflow.nodes["1021"].inputs["image"] = _input_reference(END_FRAME)
    workflow.nodes["110"].inputs["prompt"] = ACTION_PROMPT
    workflow.nodes["1022"].mode = NodeMode.BYPASSED

    workflow.register_input(
        "end_frame",
        "1021",
        "image",
        value=_input_reference(END_FRAME),
        type=None,
        default=_input_reference(END_FRAME),
        required=True,
        aliases=("image_end_ref",),
        media_semantics="image",
    )
    workflow.metadata.setdefault("endpoint_guidance", {})
    workflow.metadata["endpoint_guidance"].update(
        {
            "node": "MiniMaxH3ReferenceToVideo",
            "reference_node": "1021",
            "image": str(END_FRAME),
            "semantics": "appearance/reference guidance only; no injected keyframe",
            "extension_seconds": EXTENSION_SECONDS,
            "target_frames": TARGET_FRAMES,
            "prompt": ACTION_PROMPT,
        }
    )
    return workflow
