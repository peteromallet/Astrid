"""Trusted, no-model integration gate for the disposable A01 workflow.

The gate exercises the same public ``replace-parent-media`` operation exposed
to an evaluated worker, but it runs in a trusted preparation container.  It
creates three independent targets:

* a positive target that must publish and survive exact committed readback;
* a negative target where the same operation deliberately edits a sibling
  shot and the A01 verifier must reject the result; and
* a final untouched target that is the only target exported for model use.

Canonical source access is deliberately not required here.  Source denial is
proved by the worker boundary.  The receipt therefore records source safety as
unavailable instead of manufacturing a same-container source proof.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .a01_smoke import derive_a01_old_video_baseline, load_baseline
from .fixture import Baseline, idempotency_key, public_target_receipt, seed_case
from .fixture_contracts import action_target_contract, validate_action_target_receipt
from .independent_readback import (
    ACTIVE_MEDIA_REPLACEMENT,
    CaseReadbackResult,
    ReadbackContract,
    ReadbackObservation,
    observe_case_before,
    verify_case_after,
)
from .runtime_adapter import RuntimeFixtureAdapter
from .source_export import _canonical


GATE_KIND = "astrid.timeline-eval.a01-integration-gate.v1"
EXAMPLES_KIND = "astrid.timeline-eval.a01-integration-examples.v1"


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_bytes(_canonical(value) + b"\n")
    os.replace(temporary, path)


def _plain(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return _plain(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): _plain(child) for key, child in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(child) for child in value]
    return value


def _publication(adapter: RuntimeFixtureAdapter, value: Any) -> Mapping[str, Any]:
    plain = adapter._plain(value)
    data = plain.get("data", plain) if isinstance(plain, Mapping) else None
    if not isinstance(data, Mapping):
        raise RuntimeError("replace-parent-media returned no publication record")
    publication = data.get("publication", data)
    if not isinstance(publication, Mapping):
        raise RuntimeError("replace-parent-media returned an invalid publication record")
    return publication


def _replacement_digest(disclosure: Mapping[str, Any]) -> str:
    value = disclosure.get("admitted_new_charcoal_image_digest")
    if not isinstance(value, str) or not value:
        raise RuntimeError("A01 derivative omitted the admitted replacement digest")
    return value if value.startswith("sha256:") else "sha256:" + value


def _seed_target(
    adapter: RuntimeFixtureAdapter,
    baseline: Baseline,
    *,
    media_root: Path,
    attempt_id: str,
) -> tuple[Mapping[str, Any], dict[str, Any]]:
    seeded = seed_case(
        adapter, baseline, attempt_id=attempt_id, case_id="A01", media_root=media_root,
    )
    target = public_target_receipt(seeded)
    errors = validate_action_target_receipt(target, action_target_contract({"id": "A01"}))
    if errors:
        raise RuntimeError("seeded A01 target violates its public contract: " + "; ".join(errors))
    return seeded, target


def _replace(
    adapter: RuntimeFixtureAdapter,
    *,
    target: Mapping[str, Any],
    occurrence_id: str,
    clip_id: str,
    source_object_id: str,
    operation: str,
    attempt_id: str,
) -> Mapping[str, Any]:
    result = adapter.workspace.replace_parent_composition_media(
        str(target["project_id"]),
        str(target["timeline_id"]),
        occurrence_id=occurrence_id,
        clip_id=clip_id,
        source_object_id=source_object_id,
        expected_head=str(target["head_revision_id"]),
        idempotency_key=idempotency_key(
            attempt_id=attempt_id,
            case_id="A01",
            operation=operation,
            request={
                "project_id": target["project_id"],
                "timeline_id": target["timeline_id"],
                "occurrence_id": occurrence_id,
                "clip_id": clip_id,
                "source_object_id": source_object_id,
                "expected_head": target["head_revision_id"],
            },
        ),
        timing="preserve-duration",
    )
    return _publication(adapter, result)


def _wrong_shot_locator(
    adapter: RuntimeFixtureAdapter, target: Mapping[str, Any],
) -> tuple[str, str]:
    """Find a real, uniquely pinned sibling picture clip in the exact closure."""
    closure = adapter.read_current_closure(
        str(target["project_id"]), str(target["timeline_id"]),
        head=str(target["head_revision_id"]),
    )
    parent = closure.get("parent_revision")
    payload = parent.get("payload") if isinstance(parent, Mapping) else None
    occurrences = payload.get("occurrences") if isinstance(payload, Mapping) else None
    if not isinstance(occurrences, list):
        raise RuntimeError("A01 wrong-shot gate cannot read parent occurrences")
    target_occurrence = target.get("target_locator", {}).get("occurrence_id")
    counts: dict[str, int] = {}
    for occurrence in occurrences:
        if isinstance(occurrence, Mapping) and isinstance(occurrence.get("shot_revision_id"), str):
            revision = str(occurrence["shot_revision_id"])
            counts[revision] = counts.get(revision, 0) + 1
    shots = {
        (row.get("shot_id"), row.get("revision_id")): row
        for row in closure.get("shot_revisions", ()) if isinstance(row, Mapping)
    }
    internals = {
        row.get("revision_id"): row
        for row in closure.get("internal_timeline_revisions", ()) if isinstance(row, Mapping)
    }
    for occurrence in occurrences:
        if not isinstance(occurrence, Mapping) or occurrence.get("occurrence_id") == target_occurrence:
            continue
        revision = occurrence.get("shot_revision_id")
        if not isinstance(revision, str) or counts.get(revision) != 1:
            continue
        shot = shots.get((occurrence.get("shot_id"), revision))
        if not isinstance(shot, Mapping):
            continue
        internal_id = shot.get("internal_timeline_revision_id")
        if not isinstance(internal_id, str):
            shot_payload = shot.get("payload")
            internal_id = shot_payload.get("internal_timeline_revision_id") if isinstance(shot_payload, Mapping) else None
        internal = internals.get(internal_id)
        internal_payload = internal.get("payload") if isinstance(internal, Mapping) else None
        clips = internal_payload.get("clips") if isinstance(internal_payload, Mapping) else None
        if not isinstance(clips, list):
            continue
        clip = next((
            row for row in clips
            if isinstance(row, Mapping)
            and isinstance(row.get("id"), str)
            and row.get("track") in {"picture", "video", "visual"}
        ), None)
        if isinstance(clip, Mapping):
            return str(occurrence["occurrence_id"]), str(clip["id"])
    raise RuntimeError("A01 wrong-shot gate found no uniquely pinned sibling picture clip")


def _positive_is_sound(result: CaseReadbackResult) -> bool:
    allowed = {"canonical source fingerprint proof is unavailable"}
    return (
        result.status in {"pass", "unavailable"}
        and result.media_digest_evidence.get("matched") is True
        and result.safety.get("test_target_only") is True
        and result.safety.get("source_unchanged") is None
        and set(result.reasons).issubset(allowed)
    )


def _launch_is_fresh(
    before: ReadbackObservation, target: Mapping[str, Any], *, old_digest: str, new_digest: str,
) -> bool:
    return (
        before.head_revision_id == target.get("head_revision_id")
        and before.target.get("active_media_digest") == old_digest
        and before.target.get("active_media_digest") != new_digest
        and before.sibling_timeline_fingerprints is not None
    )


def run_a01_gate_examples(
    adapter: RuntimeFixtureAdapter,
    baseline: Baseline,
    *,
    media_root: Path,
    attempt_id: str,
) -> dict[str, Any]:
    """Exercise the positive and wrong-shot cases in an examples-only realm."""
    if not attempt_id:
        raise ValueError("A01 integration gate requires a non-empty attempt_id")
    derived, disclosure = derive_a01_old_video_baseline(baseline)
    new_digest = _replacement_digest(disclosure)
    old_digest = str(disclosure["selected_old_video_digest"])
    contract = ReadbackContract(
        case_id="A01", projection=ACTIVE_MEDIA_REPLACEMENT,
        expected_media_digest=new_digest,
    )

    positive_seed, positive_target = _seed_target(
        adapter, derived, media_root=media_root, attempt_id=attempt_id + "-positive",
    )
    positive_before = observe_case_before(adapter, positive_target, contract)
    positive_locator = positive_target["target_locator"]
    replacement_object = positive_seed["owned_media"].get(new_digest)
    if not isinstance(replacement_object, str) or not replacement_object:
        raise RuntimeError("positive A01 target does not own the expected replacement object")
    positive_publication = _replace(
        adapter,
        target=positive_target,
        occurrence_id=str(positive_locator["occurrence_id"]),
        clip_id=str(positive_locator["selector_clip_id"]),
        source_object_id=replacement_object,
        operation="integration-positive-replace-parent-media",
        attempt_id=attempt_id,
    )
    positive_result = verify_case_after(
        adapter, positive_target, contract, positive_before, positive_publication,
    )
    if not _positive_is_sound(positive_result):
        raise RuntimeError(
            "A01 positive publication failed independent target readback: "
            + json.dumps(positive_result.as_dict(), sort_keys=True)
        )

    negative_seed, negative_target = _seed_target(
        adapter, derived, media_root=media_root, attempt_id=attempt_id + "-negative",
    )
    negative_before = observe_case_before(adapter, negative_target, contract)
    wrong_occurrence, wrong_clip = _wrong_shot_locator(adapter, negative_target)
    negative_object = negative_seed["owned_media"].get(new_digest)
    if not isinstance(negative_object, str) or not negative_object:
        raise RuntimeError("negative A01 target does not own the expected replacement object")
    negative_publication = _replace(
        adapter,
        target=negative_target,
        occurrence_id=wrong_occurrence,
        clip_id=wrong_clip,
        source_object_id=negative_object,
        operation="integration-negative-wrong-shot-replace-parent-media",
        attempt_id=attempt_id,
    )
    negative_result = verify_case_after(
        adapter, negative_target, contract, negative_before, negative_publication,
    )
    if negative_result.status != "fail" or negative_result.safety.get("test_target_only") is not False:
        raise RuntimeError(
            "A01 wrong-shot publication was not rejected by independent readback: "
            + json.dumps(negative_result.as_dict(), sort_keys=True)
        )

    return {
        "kind": EXAMPLES_KIND,
        "status": "pass",
        "attempt_id": attempt_id,
        "examples_realm_id": adapter.proof.realm_id,
        "source_safety": {
            "status": "outside_gate_boundary",
            "reason": (
                "the target-only gate does not connect to or read the canonical source "
                "closure; worker boundary denial and coordinator source readback remain "
                "separate admission evidence"
            ),
        },
        "derivative": disclosure,
        "positive": {
            "target_identity": {
                key: positive_target[key]
                for key in ("project_id", "timeline_id", "head_revision_id")
            },
            "publication": dict(positive_publication),
            "readback": positive_result.as_dict(),
        },
        "wrong_shot_negative": {
            "edited_occurrence_id": wrong_occurrence,
            "edited_clip_id": wrong_clip,
            "publication": dict(negative_publication),
            "readback": negative_result.as_dict(),
            "rejected": True,
        },
    }


def prepare_a01_launch_target(
    adapter: RuntimeFixtureAdapter,
    baseline: Baseline,
    examples_receipt: Mapping[str, Any],
    *,
    media_root: Path,
    attempt_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Seed only an untouched target in a realm that has no solved examples."""
    if examples_receipt.get("kind") != EXAMPLES_KIND or examples_receipt.get("status") != "pass":
        raise RuntimeError("A01 launch preparation requires a passed examples receipt")
    examples_realm_id = examples_receipt.get("examples_realm_id")
    launch_realm_id = adapter.proof.realm_id
    if not isinstance(examples_realm_id, str) or not examples_realm_id:
        raise RuntimeError("A01 examples receipt omitted its server-observed realm ID")
    if examples_realm_id == launch_realm_id:
        raise RuntimeError(
            "A01 solved examples and model launch target must use distinct Runtime realms"
        )
    derived, disclosure = derive_a01_old_video_baseline(baseline)
    if examples_receipt.get("derivative") != disclosure:
        raise RuntimeError("A01 launch fixture differs from the examples fixture")
    new_digest = _replacement_digest(disclosure)
    old_digest = str(disclosure["selected_old_video_digest"])
    contract = ReadbackContract(
        case_id="A01", projection=ACTIVE_MEDIA_REPLACEMENT,
        expected_media_digest=new_digest,
    )
    _launch_seed, launch_target = _seed_target(
        adapter, derived, media_root=media_root, attempt_id=attempt_id + "-launch",
    )
    launch_before = observe_case_before(adapter, launch_target, contract)
    if not _launch_is_fresh(
        launch_before, launch_target, old_digest=old_digest, new_digest=new_digest,
    ):
        raise RuntimeError("A01 exported launch target is not a fresh OLD-video target")

    receipt = {
        "kind": GATE_KIND,
        "status": "pass",
        "attempt_id": attempt_id,
        # Compatibility identity: all subsequent worker admission binds the
        # launch realm, never the now-inaccessible examples realm.
        "realm_id": launch_realm_id,
        "examples_realm_id": examples_realm_id,
        "launch_realm_id": launch_realm_id,
        "realm_separation": {
            "status": "pass",
            "distinct": True,
            "examples_available_to_worker": False,
        },
        "source_safety": dict(examples_receipt["source_safety"]),
        "derivative": disclosure,
        "positive": dict(examples_receipt["positive"]),
        "wrong_shot_negative": dict(examples_receipt["wrong_shot_negative"]),
        "launch": {
            "target_identity": {
                key: launch_target[key]
                for key in ("project_id", "timeline_id", "head_revision_id")
            },
            "before": _plain(launch_before),
            "untouched": True,
        },
    }
    return receipt, launch_target


def run_a01_integration_gate(
    examples_adapter: RuntimeFixtureAdapter,
    launch_adapter: RuntimeFixtureAdapter,
    baseline: Baseline,
    *,
    media_root: Path,
    attempt_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Exercise examples, then prepare launch in a distinct Runtime realm."""
    if examples_adapter.proof.realm_id == launch_adapter.proof.realm_id:
        raise RuntimeError(
            "A01 solved examples and model launch target must use distinct Runtime realms"
        )
    examples = run_a01_gate_examples(
        examples_adapter, baseline, media_root=media_root, attempt_id=attempt_id,
    )
    return prepare_a01_launch_target(
        launch_adapter, baseline, examples, media_root=media_root, attempt_id=attempt_id,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the trusted no-model A01 integration gate")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--credential-file", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--media-root", type=Path, required=True)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--phase", choices=("examples", "launch"), required=True)
    parser.add_argument("--examples-receipt", type=Path)
    parser.add_argument("--target-output", type=Path)
    parser.add_argument("--receipt-output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    adapter = RuntimeFixtureAdapter.connect(
        endpoint=args.endpoint,
        credential_file=args.credential_file,
        contract_path=args.contract,
    )
    baseline = load_baseline(args.baseline)
    if args.phase == "examples":
        if args.examples_receipt is not None or args.target_output is not None:
            raise SystemExit("examples phase does not accept launch output/input arguments")
        receipt = run_a01_gate_examples(
            adapter, baseline, media_root=args.media_root, attempt_id=args.attempt_id,
        )
        target_output = None
    else:
        if args.examples_receipt is None or args.target_output is None:
            raise SystemExit("launch phase requires --examples-receipt and --target-output")
        raw_examples = json.loads(args.examples_receipt.read_text(encoding="utf-8"))
        if not isinstance(raw_examples, Mapping):
            raise SystemExit("examples receipt must be a JSON object")
        receipt, target = prepare_a01_launch_target(
            adapter, baseline, raw_examples,
            media_root=args.media_root, attempt_id=args.attempt_id,
        )
        _write_json(args.target_output, target)
        target_output = str(args.target_output)
    _write_json(args.receipt_output, receipt)
    print(json.dumps({
        "status": receipt["status"],
        "realm_id": receipt.get("realm_id", receipt.get("examples_realm_id")),
        "phase": args.phase,
        "target_output": target_output,
        "receipt_output": str(args.receipt_output),
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
