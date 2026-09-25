from __future__ import annotations

from copy import deepcopy

from astrid.packs.h3_av.workflows.native_h3_continuation import workflow as continuation
from astrid.packs.h3_av.workflows.native_h3_continuation_refs import workflow as continuation_refs
from vibecomfy.runtime import drift
from vibecomfy.workflow import VibeWorkflow


PINNED_COMFY_COMMIT = "ee71d5c4993f29086b27fde1629a945ae48425bf"
PINNED_CUSTOM_NODE_PACKS = {
    "ComfyUI-H3-Motion-Context-MultiRef",
    "ComfyUI-VideoHelperSuite",
}


def test_h3_continuation_workflow_build_reload_exposes_dependency_attestation() -> None:
    for template in (continuation, continuation_refs):
        workflow = template.build()
        envelope = deepcopy(workflow.to_envelope())
        # Runtime pins are retained in the template metadata witness; the
        # public envelope's normalized requirements carries models and packs.
        envelope["requirements"]["models"] = [
            model["name"] for model in envelope["requirements"]["models"]
        ]
        reloaded = VibeWorkflow.from_envelope(envelope)

        assert reloaded.metadata["comfy_commit"] == PINNED_COMFY_COMMIT
        assert reloaded.metadata["requirements"]["runtime"]["comfy_commit"] == PINNED_COMFY_COMMIT
        assert PINNED_CUSTOM_NODE_PACKS <= set(reloaded.requirements.custom_nodes)
        assert reloaded.metadata["custom_node_packs"].keys() >= PINNED_CUSTOM_NODE_PACKS


def test_h3_workflow_comfy_commit_drift_rejects_mismatched_identity(monkeypatch) -> None:
    workflow = continuation_refs.build()
    monkeypatch.setattr(drift, "_comfyui_git_head", lambda: "different-comfy-commit")

    pinned: dict[str, object] = {}
    actual: dict[str, object] = {}
    mismatches: list[str] = []
    drift._collect_comfy_commit_drift(workflow, pinned, actual, mismatches)

    assert pinned["comfy_commit"] == PINNED_COMFY_COMMIT
    assert actual["comfy_commit"] == "different-comfy-commit"
    assert any("does not match pinned" in mismatch for mismatch in mismatches)
