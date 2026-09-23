import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EVAL_ROOT = REPO_ROOT / "Astrid" / "evals" / "timeline"
SUITE_PATH = EVAL_ROOT / "suite.json"
BRIEFS_PATH = EVAL_ROOT / "cases" / "agent_briefs.json"
HISTORICAL_BRIEF_PATH = (
    REPO_ROOT
    / ".otto"
    / "runs"
    / "timeline-text-inspection-20260922"
    / "evidence"
    / "luna-benchmark-brief-20260923.json"
)


ACTION_PROMPTS = {
    "A01": "In {opening shot}, replace the old mink video with the charcoal pixel-mink image. Keep its timing, voiceover, and frame overlay. Show me the preview, then save it to this test timeline.",
    "A02": "Remove {redundant shot}, including its own voiceover, and close the space it leaves. Keep the other shots intact and keep the continuous music bed at its original source position.",
    "A03": "Move {closing shot} to immediately before {middle shot}. Move its image, voiceover, and caption together. Keep all shot lengths and the total running time the same.",
    "A04": "Make a second version of {feature shot} right after it, change the copy to {alternate image}, and name it ‘Feature alternate’. Keep the original untouched, including its voiceover and title.",
    "A05": "Tighten the intro by ending each spoken shot six frames after its last voice clip ends, then bring the next shot up. Don't cut any voice audio or change words, playback speed, or the order. Leave shots with no voice alone; keep the music continuous from its original start.",
    "A06": "Change the on-screen title in {title shot} to ‘A more curious internet’. Keep the voiceover script and spoken audio exactly as they are, and keep the title's style and screen time.",
    "A07": "Make the background music six decibels quieter throughout this excerpt. Leave the voiceover at the same level and keep everything in sync.",
    "A08": "In {demonstration shot}, use source seconds 2 through 4 of the terminal video and start it on the supplied cue at {cue time}. Keep the voiceover fixed and fill the rest with the existing still image.",
    "A09": "Make a four-quadrant montage from these four supplied images in {montage shot}. Start with one in each quadrant, then rotate them clockwise at each supplied music cue. Keep the music and voice untouched.",
    "A10": "Add a new 20-second montage after {last shot}: use the 200 images in this supplied collection from darkest to brightest, each for 0.1 seconds. Use every image exactly once, break brightness ties by media ID, and leave the existing intro unchanged.",
}


def _read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_has_exactly_twenty_unique_versioned_cases():
    suite = _read_json(SUITE_PATH)
    cases = suite["cases"]

    assert suite["suite_version"] == "2.0.0"
    assert suite["status"] == "manifest_only_not_executed"
    assert len(cases) == 20
    assert [case["id"] for case in cases] == [
        *(f"L{i:02d}" for i in range(1, 11)),
        *(f"A{i:02d}" for i in range(1, 11)),
    ]
    assert len({case["id"] for case in cases}) == 20
    assert all(case["version"] == suite["suite_version"] for case in cases)


def test_original_luna_prompt_objects_are_preserved_exactly():
    suite = _read_json(SUITE_PATH)
    original = _read_json(HISTORICAL_BRIEF_PATH)
    expected = {query["id"]: query for query in original["queries"]}
    source_sessions = {
        item["id"]: item["path"] for item in original["transcript_sources"]
    }

    assert suite["historical_sessions"] == source_sessions

    for case in suite["cases"]:
        if case["id"].startswith("L"):
            old = expected[case["id"]]
            assert case["prompt"] == {
                "agent_task": old["agent_task"],
                "focus": old["focus"],
                "questions": old["questions"],
            }
            assert case["historical_prompt_source"].endswith(
                f"#/queries/{case['id']}"
            )


def test_action_prompts_match_astra_design_and_public_briefs():
    suite = _read_json(SUITE_PATH)
    briefs = _read_json(BRIEFS_PATH)
    suite_actions = {
        case["id"]: case["prompt"]
        for case in suite["cases"]
        if case["id"].startswith("A")
    }
    public_actions = {
        case["id"]: case["prompt"]
        for case in briefs["cases"]
        if case["id"].startswith("A")
    }

    assert suite_actions == ACTION_PROMPTS
    assert public_actions == ACTION_PROMPTS


def test_case_records_have_machine_readable_contract_and_valid_units():
    suite = _read_json(SUITE_PATH)
    required = {
        "id",
        "version",
        "kind",
        "prompt",
        "preconditions",
        "allowed_target",
        "invariants",
        "success_checks",
        "required_artifacts",
        "timeout",
        "render_windows",
    }

    for case in suite["cases"]:
        assert required <= case.keys(), case["id"]
        assert case["kind"] in {"navigation", "action"}
        assert isinstance(case["preconditions"], list)
        assert isinstance(case["invariants"], list)
        assert isinstance(case["success_checks"], list)
        assert isinstance(case["required_artifacts"], list)
        assert case["required_artifacts"]
        assert case["timeout"]["unit"] == "seconds"
        assert isinstance(case["timeout"]["value"], int)
        assert case["timeout"]["value"] > 0
        for window in case["render_windows"]:
            assert set(window) == {"start_ms", "end_ms", "purpose"}
            assert isinstance(window["start_ms"], int)
            assert isinstance(window["end_ms"], int)
            assert 0 <= window["start_ms"] < window["end_ms"]
            assert isinstance(window["purpose"], str) and window["purpose"]


def test_agent_briefs_exclude_verifier_only_fields_and_match_suite_prompts():
    suite = _read_json(SUITE_PATH)
    briefs = _read_json(BRIEFS_PATH)
    full_by_id = {case["id"]: case for case in suite["cases"]}
    public_cases = briefs["cases"]

    assert [case["id"] for case in public_cases] == [case["id"] for case in suite["cases"]]
    forbidden = {
        "preconditions",
        "allowed_target",
        "invariants",
        "success_checks",
        "required_artifacts",
        "timeout",
        "render_windows",
        "fixture",
    }
    for public in public_cases:
        full = full_by_id[public["id"]]
        assert forbidden.isdisjoint(public)
        assert public["version"] == full["version"]
        assert public["prompt"] == full["prompt"]
        if public["id"].startswith("L"):
            assert public["operational_addendum"] == full["operational_addendum"]
        else:
            assert public.keys() == {"id", "version", "task", "prompt"}


def test_manifest_renders_stable_json_and_has_no_executed_case_claims():
    raw = SUITE_PATH.read_text(encoding="utf-8")
    parsed = json.loads(raw)
    assert raw.endswith("\n")
    canonical = json.dumps(parsed, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert canonical == json.dumps(
        json.loads(canonical), ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    assert all("result.json" in case["required_artifacts"] for case in parsed["cases"])
