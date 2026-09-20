"""H3 AV generation with an explicit endpoint keyframe guide.

This is a derived recipe, not a replacement for the custody-locked imported
workflow in ``seitanism_h3_av_extension_verified``.  It adds one LoadImage and
one MiniMaxH3CustomKeyframes node after loading the canonical graph, then
redirects the active extension guider to the endpoint-conditioned output.
"""
from __future__ import annotations

import os
from pathlib import Path

from vibecomfy.cli_loader import load_bundle
from vibecomfy.handles import Handle
from vibecomfy.security.provenance import Provenance
from vibecomfy.workflow import VibeWorkflow


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

# MiniMaxH3CustomKeyframes uses one-based target positions, so this is the
# final generated frame rather than the seam frame.
END_FRAME_POSITION = TARGET_FRAMES
H3_PACK = "ComfyUI-H3-Motion-Context-MultiRef"
H3_PACK_COMMIT = "361624fb406b63eb6694442eac6c895fc1533a70"


def _input_reference(path: Path) -> str:
    """Return a Comfy input filename when the runner staged the asset."""
    return path.name if REMOTE_INPUT_NAMES else str(path)


def _native_ports(node: object) -> dict[str, object]:
    """Carry the canonical node's retained port contract into the edit."""
    return {
        name: getattr(node, name)
        for name in (
            "native_input_names",
            "native_output_names",
            "native_input_types",
            "native_output_types",
            "native_input_optional",
            "native_input_asset_kinds",
            "native_output_slots",
        )
    }


def build() -> VibeWorkflow:
    """Build the endpoint-controlled continuation candidate."""
    if not END_FRAME.is_file():
        raise FileNotFoundError(f"end frame is missing: {END_FRAME}")
    if not REFERENCE_IMAGE.is_file():
        raise FileNotFoundError(f"reference image is missing: {REFERENCE_IMAGE}")

    bundle = load_bundle(
        CANONICAL_WORKFLOW,
        trust=Provenance.USER_CONFIRMED,
        allow_unresolved=True,
    )
    workflow = bundle.workflow.copy()

    # The imported graph predates the current VibeComfy lock reconciliation
    # and carries this pack as an unresolved ``missing_nodes`` hint. Promote
    # the already-installed local pack to an explicit, pinned dependency so a
    # run can validate its identity without querying the live registry.
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

    # A runner may stage the source video under a machine-local input path.
    # Leave the custody-locked loader untouched when no override is supplied.
    if SOURCE_VIDEO:
        source_video = Path(SOURCE_VIDEO)
        if not source_video.is_file():
            raise FileNotFoundError(f"source video is missing: {source_video}")
        workflow.nodes["99"].inputs["video"] = _input_reference(source_video)

    workflow.nodes["102"].inputs["values.a"] = EXTENSION_SECONDS

    # Replace the imported placeholder with a concrete first-principles action
    # description. The audiovisual mask still supplies the source context; the
    # prompt describes the intended shot rather than saying "continue directly".
    workflow.nodes["110"].inputs["prompt"] = ACTION_PROMPT

    # The imported graph keeps two legacy reference loaders enabled.  Empty
    # filenames are not inert on the current ComfyUI runtime, so carry the
    # source-tail reference that the prior working H3 recipe used.
    reference_image = _input_reference(REFERENCE_IMAGE)
    for node_id in ("1020", "1021"):
        workflow.nodes[node_id].inputs["image"] = reference_image

    # Reuse the retained native port contracts from existing nodes instead of
    # asking a live registry for schemas while constructing this derived edit.
    endpoint_image = workflow.node(
        "LoadImage",
        image=_input_reference(END_FRAME),
        _native_ports=_native_ports(workflow.nodes["1020"]),
    )
    endpoint_conditioning = workflow.node(
        "MiniMaxH3CustomKeyframes",
        keyframe_state=f'{{"count":1,"positions":[{END_FRAME_POSITION}]}}',
        indexing="1-based",
        crop="disabled",
        conditioning=Handle(node_id="110", output_slot=0, name="positive"),
        keyframe_image_1=endpoint_image.out("IMAGE"),
        latent=Handle(node_id="110", output_slot=1, name="LATENT"),
        vae=Handle(node_id="3", output_slot=0, name="VAE"),
        pass_raw=True,
        _native_ports=_native_ports(workflow.nodes["1022"]),
    )

    # Node 121 is the guider for the active generated continuation branch
    # (node 124 is extension_1; later extension branches are bypassed).
    # The existing StartMaskedContext → sampler latent path is untouched.
    workflow.replace_edge("121.conditioning", endpoint_conditioning.out("conditioning"))

    # Keep the endpoint as a first-class media input so a remote runner can
    # stage/override it instead of treating the local path as hidden metadata.
    workflow.register_input(
        "end_frame",
        endpoint_image.id,
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
            "node": "MiniMaxH3CustomKeyframes",
            "position": END_FRAME_POSITION,
            "extension_seconds": EXTENSION_SECONDS,
            "target_frames": TARGET_FRAMES,
            "indexing": "1-based",
            "image": str(END_FRAME),
            "semantics": "soft final-frame conditioning; seam remains owned by StartMaskedContext",
            "prompt": ACTION_PROMPT,
        }
    )
    return workflow
