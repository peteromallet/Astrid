"""Seed and safely preflight A02-A10 in isolated disposable Runtime timelines.

Cases remain explicitly blocked unless their case-specific fixture contract is
present. This runner never infers placeholder targets, invents missing media,
or publishes a synthetic success; it emits reproducible source/seed/preflight
evidence for each case.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .a01_smoke import _target_candidate, load_baseline
from .fixture import seed_case
from .runtime_adapter import ISOLATION_MARKER_NAME, RuntimeFixtureAdapter, isolation_contract_template
from .source_export import _canonical, _data


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_bytes(_canonical(value) + b"\n")
    os.replace(temporary, path)


def _write_consolidated(root: Path, summaries: list[dict[str, Any]], realm_id: str, head_before: str, head_after: str, baseline: Any) -> None:
    a01_dir = root / "attempts" / "e05-a01-action-final2" / "A01"
    try:
        a01 = json.loads((a01_dir / "result.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        a01 = {"id": "A01", "status": "blocked", "score": 0, "blocked_reason": [f"completed A01 evidence unavailable: {exc}"]}
    cases = [{
        "id": "A01", "status": a01.get("status"), "score": a01.get("score"),
        "executor_kind": a01.get("executor_kind"), "agent_executed": a01.get("agent_executed"),
        "action_published": a01.get("action_published"), "preview_rendered": a01.get("preview_rendered"),
        "canonical_source_unchanged": a01.get("canonical_source_unchanged"),
        "evidence": str(a01_dir.relative_to(root)),
        "notes": ["Deterministic fixture action only; not a natural-language agent result.", "Frozen authoring preview exists; managed rendered preview was unavailable."],
    }]
    cases.extend({
        "id": row["id"], "status": row["status"], "score": 0,
        "executor_kind": "deterministic_fixture_action", "agent_executed": False,
        "action_published": False, "preview_rendered": False,
        "canonical_source_unchanged": row["canonical_source_unchanged"],
        "blockers": row["blockers"], "evidence": f"attempts/e05-a02-a10-batch/{row['id']}",
    } for row in summaries)
    consolidated = {
        "suite": "astrid-timeline-navigation-and-actions",
        "suite_version": "2.0.0",
        "executor_kind": "deterministic_fixture_action",
        "agent_model_evaluation": False,
        "source_project_id": baseline.source_project_id,
        "source_timeline_id": baseline.source_timeline_id,
        "source_pinned_head": baseline.source_head,
        "source_closure_digest": baseline.closure_digest,
        "source_semantic_digest": baseline.semantic_digest,
        "disposable_batch_realm_id": realm_id,
        "canonical_head_before": head_before,
        "canonical_head_after": head_after,
        "canonical_unchanged": head_before == head_after,
        "cases": cases,
    }
    _write_json(root / "action-evals-a01-a10-results.json", consolidated)
    lines = [
        "# Astrid timeline action evals — A01–A10",
        "",
        "This is a deterministic fixture-action harness run, not a natural-language agent-model evaluation. A01 executed in its own disposable realm. A02–A10 were seeded into distinct disposable timelines and blocked at fixture preflight; no edits were published for them.",
        "",
        f"Pinned source: `{baseline.source_head}` (closure `{baseline.closure_digest}`); canonical mutable head before/after batch: `{head_before}` / `{head_after}` — unchanged: **{head_before == head_after}**.",
        "",
        "| Case | Result | Published action | Key blocker / qualification | Evidence |",
        "|---|---|---:|---|---|",
    ]
    for row in cases:
        notes = row.get("notes") or row.get("blockers") or []
        detail = "; ".join(str(item).replace("|", "\\|") for item in notes)
        lines.append(f"| {row['id']} | {row['status']} | {row.get('action_published', False)} | {detail} | `{row['evidence']}` |")
    lines.extend(["", "Every A02–A10 timeline has `before.json`, `candidate.json`, `diff.json`, `validation.json`, `preview.json`, `receipt.json`, `after.json`, `result.json`, and `seed.json`. Their hidden checks record fixture preconditions, unchanged seeded target, and canonical-source immutability.", ""])
    output = "\n".join(lines)
    md_path = root / "action-evals-a01-a10-results.md"
    temporary = md_path.with_name(f".{md_path.name}.tmp")
    temporary.write_text(output, encoding="utf-8")
    os.replace(temporary, md_path)


def _preflight(case_id: str, baseline: Any) -> dict[str, Any]:
    closure = baseline.closure
    parent = closure["parent_revision"]["payload"]
    occurrences = parent.get("occurrences", [])
    clips = parent.get("clips", [])
    count = len(occurrences) if isinstance(occurrences, list) else 0
    tracks: dict[str, int] = {}
    for clip in clips if isinstance(clips, list) else []:
        if isinstance(clip, Mapping):
            track = str(clip.get("track", "<none>"))
            tracks[track] = tracks.get(track, 0) + 1
    music_clips = [clip for clip in clips if isinstance(clip, Mapping) and str(clip.get("track", "")).lower() in {"music", "bgm", "audio"}]
    internal_payloads = [row.get("payload", {}) for row in closure["internal_timeline_revisions"]]
    child_clip_count = sum(len(payload.get("clips", [])) for payload in internal_payloads if isinstance(payload, Mapping))
    child_text_items = [
        {"revision_id": row.get("revision_id"), "item_id": item.get("item_id", item.get("id")), "role": item.get("role"), "type": item.get("type")}
        for row in closure["shot_revisions"]
        for item in (row.get("payload", {}).get("items", []) if isinstance(row.get("payload", {}).get("items", []), list) else [])
        if isinstance(item, Mapping) and ("text" in str(item.get("type", "")).lower() or "text" in str(item.get("role", "")).lower())
    ]
    media_count = len(baseline.media)
    common = {
        "source_occurrence_count": count,
        "source_parent_track_counts": tracks,
        "source_parent_music_clip_count": len(music_clips),
        "source_internal_revision_count": len(internal_payloads),
        "source_internal_clip_count": child_clip_count,
        "source_closure_media_count": media_count,
        "source_candidate_text_item_count": len(child_text_items),
    }
    reasons = {
        "A02": [
            f"pinned source has {count} occurrences rather than the declared four-shot fixture",
            "case-specific redundant-shot identity/voiceover target is not supplied",
            "the pinned parent has a full-duration frame overlay, violating the fixture's no-crossing-overlay precondition",
            f"pinned parent continuous music clips detected: {len(music_clips)}; required trim window and source-position assertions are not declared",
        ],
        "A03": [
            f"pinned source has {count} occurrences rather than the declared four-shot fixture",
            "closing-shot and middle-shot target identities are unresolved prompt placeholders; no case permutation table is supplied",
        ],
        "A04": [
            "feature-shot identity and alternate-image digest are unresolved fixture placeholders",
            "the pinned closure has no declared independent duplicate identity/reference manifest; duplicate/copy-local edit cannot be safely inferred",
        ],
        "A05": [
            "no A05 derivative records frozen-frame-rate voice endpoints/trailing-hold expected table",
            "no case-specific transition/effect ambiguity adjudication is supplied",
            "renderer/audio-probe outputs required by the acceptance checks are not attached to this disposable Runtime",
        ],
        "A06": [
            "title-shot target is unresolved; no distinct title/script/transcript/audio role map is supplied",
            f"pinned candidate contains {len(child_text_items)} explicitly role/type-identifiable text items, insufficient to establish the required separated role bindings",
            "renderer required to verify visible title styling/time is not attached",
        ],
        "A07": [
            f"pinned parent supported music clips detected: {len(music_clips)}; no A07 short-excerpt track/window manifest supplied",
            "music-only and voice-only measurement windows, baseline gains, and decoder tolerance are absent",
            "decoded PCM renderer/probe is unavailable in the disposable Runtime",
        ],
        "A08": [
            "demonstration-shot target and cue-time value remain unresolved prompt placeholders",
            "no terminal source-marker manifest or still-coverage interval is supplied for this case",
            "renderer/frame-sampling path is not attached",
        ],
        "A09": [
            f"only {media_count} total unique media dependencies are in the pinned closure; no four-image A09 collection manifest or destination ownership list is supplied",
            "cue times/frame policy and supported four-rectangle target layout are not supplied as executable fixture data",
            "renderer cue-sample verification is unavailable",
        ],
        "A10": [
            f"pinned closure contains {media_count} media dependencies, not the required 200-image collection",
            "brightness definition/version, orientation/alpha policy, tie manifest, and supplied collection IDs are not present in an A10 fixture artifact",
            "200-frame membership/order and decoded sentinel render cannot be verified without the missing collection and renderer",
        ],
    }[case_id]
    return {
        "case_id": case_id,
        "ready": False,
        "evidence": common,
        "hidden_checks": [
            {"id": "case_fixture_contract_present", "passed": False, "evidence": reasons[0]},
            {"id": "target_identity_unambiguous", "passed": False, "evidence": reasons[1]},
            {"id": "canonical_source_is_pinned_and_read_only", "passed": True, "evidence": baseline.source_head},
        ],
        "blockers": reasons,
    }


def _run(args: argparse.Namespace) -> int:
    from runtime_protocol.daemon import RuntimeDaemon
    from runtime_protocol.store import RealmStore
    from astrid.sdk.workspace_client import WorkspaceClient
    from .fixture import SOURCE_PROJECT_ID, SOURCE_TIMELINE_ID

    attempt_dir = args.attempt_dir.expanduser().absolute()
    baseline = load_baseline(args.source_baseline)
    media_root = args.source_baseline.parent
    source_workspace = WorkspaceClient(args.source_endpoint, args.source_credential_file)
    canonical_before = _data(source_workspace.get_timeline(SOURCE_TIMELINE_ID, project_id=SOURCE_PROJECT_ID), "source timeline before").get("head_revision_id")
    runtime_root = attempt_dir / "disposable-runtime"
    runtime_root.mkdir(parents=True, exist_ok=True)
    if not (runtime_root / "realm.sqlite3").exists():
        RealmStore.initialize(runtime_root, display_name="Astrid A02-A10 action evals").close()
    daemon = RuntimeDaemon(runtime_root, support_root=attempt_dir / "runtime-support", display_name="Astrid A02-A10 action evals").start()
    summaries: list[dict[str, Any]] = []
    try:
        realm_id = str(daemon.service.realm["id"])
        _write_json(runtime_root / ISOLATION_MARKER_NAME, {
            "kind": "astrid.timeline-eval-isolation.v1", "purpose": "timeline-eval-disposable-realm", "realm_id": realm_id,
        })
        contract_path = attempt_dir / "isolation-contract.json"
        _write_json(contract_path, isolation_contract_template(
            endpoint=daemon.endpoint,
            realm_id=realm_id,
            credential_file=Path(daemon.credential_path),
            realm_root=runtime_root,
            canonical_endpoint=args.source_endpoint,
            canonical_realm_id=args.canonical_realm_id,
            canonical_root=args.canonical_root,
        ))
        adapter = RuntimeFixtureAdapter.connect(
            endpoint=daemon.endpoint, credential_file=Path(daemon.credential_path),
            contract_path=contract_path, client_factory=WorkspaceClient,
        )
        for case_id in (f"A{i:02}" for i in range(2, 11)):
            case_dir = attempt_dir / case_id
            seed = seed_case(adapter, baseline, attempt_id=attempt_dir.name, case_id=case_id, media_root=media_root)
            seed = {**seed, "canonical_head_before": canonical_before}
            candidate, test_head = _target_candidate(adapter, str(seed["project_id"]), str(seed["timeline_id"]))
            validation = validate_candidate(candidate)
            diff = diff_candidate(candidate)
            frozen = preview_candidate(candidate)
            after_head = adapter.current_head(str(seed["project_id"]), str(seed["timeline_id"]))
            after_semantic = adapter.read_case_semantic_digest(str(seed["project_id"]), str(seed["timeline_id"]))
            block = _preflight(case_id, baseline)
            canonical_after = _data(source_workspace.get_timeline(SOURCE_TIMELINE_ID, project_id=SOURCE_PROJECT_ID), "source timeline after case").get("head_revision_id")
            hidden = block["hidden_checks"] + [
                {"id": "test_target_unchanged_before_action", "passed": after_head == test_head and after_semantic == baseline.semantic_digest, "evidence": {"head_before": test_head, "head_after": after_head, "semantic_digest_matches_seed": after_semantic == baseline.semantic_digest}},
                {"id": "canonical_source_unchanged", "passed": canonical_after == canonical_before, "evidence": {"head_before": canonical_before, "head_after": canonical_after}},
            ]
            before = {
                "source_project_id": baseline.source_project_id, "source_timeline_id": SOURCE_TIMELINE_ID,
                "source_pinned_head": baseline.source_head, "canonical_head_before": canonical_before,
                "test_project_id": seed["project_id"], "test_timeline_id": seed["timeline_id"],
                "test_head": test_head, "test_semantic_digest": baseline.semantic_digest,
                "case_preflight": block,
            }
            candidate_record = {"status": "blocked-no-action", "executor_kind": "deterministic_fixture_action", "candidate": candidate, "reason": "Case-specific fixture/target contract is absent; no edit inferred or published."}
            preview_record = {"status": "frozen-seed-preview-not-rendered", "frozen_candidate_preview": frozen, "reason": "Blocked at fixture preflight; no action candidate/render was produced."}
            receipt = {
                "kind": "fixture-seed-receipt-only", "action_published": False,
                "project_id": seed["project_id"], "timeline_id": seed["timeline_id"],
                "new_head": test_head, "semantic_digest": after_semantic,
                "owned_media_count": len(seed["owned_media"]), "runtime_receipt": seed["receipt"],
            }
            after = {
                "test_head": after_head, "test_semantic_digest": after_semantic,
                "test_target_unchanged_since_seed": after_head == test_head and after_semantic == baseline.semantic_digest,
                "canonical_head_after": canonical_after, "canonical_timeline_unchanged": canonical_after == canonical_before,
            }
            result = {
                "id": case_id, "status": "blocked", "score": 0,
                "executor_kind": "deterministic_fixture_action", "agent_executed": False,
                "action_published": False, "blocked_at": "fixture_preflight",
                "blocked_reason": block["blockers"], "candidate_valid": validation.get("valid") is True,
                "candidate_changed": False,
                "baseline_projection_diff_count": diff.get("change_count", 0),
                "candidate_modified_by_harness": False,
                "preview_rendered": False,
                "canonical_source_unchanged": canonical_after == canonical_before,
                "test_target_unchanged_since_seed": after_head == test_head and after_semantic == baseline.semantic_digest,
                "hidden_checks": hidden,
            }
            case_seed = {key: seed[key] for key in ("endpoint_realm_id", "project_alias", "timeline_alias", "project_id", "timeline_id", "owned_media", "receipt", "canonical_head_before")}
            for filename, value in (
                ("before.json", before), ("candidate.json", candidate_record), ("diff.json", diff),
                ("validation.json", validation), ("preview.json", preview_record), ("receipt.json", receipt),
                ("after.json", after), ("result.json", result), ("seed.json", case_seed),
            ):
                _write_json(case_dir / filename, value)
            summaries.append({"id": case_id, "status": result["status"], "project_id": seed["project_id"], "timeline_id": seed["timeline_id"], "canonical_source_unchanged": result["canonical_source_unchanged"], "blocker_count": len(block["blockers"]), "blockers": block["blockers"]})
        final_head = _data(source_workspace.get_timeline(SOURCE_TIMELINE_ID, project_id=SOURCE_PROJECT_ID), "source timeline final").get("head_revision_id")
        _write_json(attempt_dir / "summary.json", {"executor_kind": "deterministic_fixture_action", "agent_executed": False, "realm_id": realm_id, "canonical_head_before": canonical_before, "canonical_head_after": final_head, "source_closure_digest": baseline.closure_digest, "source_semantic_digest": baseline.semantic_digest, "cases": summaries})
        _write_consolidated(attempt_dir.parent.parent, summaries, realm_id, canonical_before, str(final_head), baseline)
        print(json.dumps(summaries, indent=2, sort_keys=True))
        return 0
    finally:
        daemon.stop()


def validate_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    from astrid.core.timeline.authoring_bundle import validate_authoring_candidate
    return validate_authoring_candidate(candidate)


def diff_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    from astrid.core.timeline.authoring_bundle import diff_authoring_candidate
    return diff_authoring_candidate(candidate)


def preview_candidate(candidate: Mapping[str, Any]) -> dict[str, Any]:
    from astrid.core.timeline.authoring_bundle import preview_authoring_candidate
    return preview_authoring_candidate(candidate)


def _main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-endpoint", required=True)
    parser.add_argument("--source-credential-file", required=True, type=Path)
    parser.add_argument("--source-baseline", required=True, type=Path)
    parser.add_argument("--attempt-dir", required=True, type=Path)
    parser.add_argument("--canonical-realm-id", required=True)
    parser.add_argument("--canonical-root", required=True, type=Path)
    return _run(parser.parse_args())


if __name__ == "__main__":
    raise SystemExit(_main())
