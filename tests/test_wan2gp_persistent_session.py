from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest

from astrid.packs.wan2gp.src.persistent import (
    PersistentSessionError,
    PersistentSessionUncertain,
    PersistentWan2GPSession,
)


def _settings(model: str, prompt: str, **extra: object) -> dict[str, object]:
    return {
        "model": model,
        "model_artifact_digest": f"sha256:{model}",
        "prompt": prompt,
        **extra,
    }


@dataclass
class _JobResult:
    generated_files: tuple[str, ...]
    success: bool = True
    errors: tuple[str, ...] = ()


class _Job:
    def __init__(self, output: Path) -> None:
        self.output = output
        self.cancelled = False

    def result(self, timeout: float | None = None) -> _JobResult:
        del timeout
        self.output.write_text("cpu-substitute\n", encoding="utf-8")
        return _JobResult((str(self.output),))

    def cancel(self) -> dict[str, bool]:
        self.cancelled = True
        return {"ok": True, "done": True}


class _Session:
    def __init__(self, key: str, created: list["_Session"]) -> None:
        self.key = key
        self.created = created
        self.output_dir: Path | None = None
        self.closed = False
        self.jobs = 0
        created.append(self)

    def rebind_output_dir(self, output_dir: Path) -> bool:
        if self.closed:
            return False
        self.output_dir = Path(output_dir).resolve()
        return True

    def observe_output_dir(self) -> str | None:
        return str(self.output_dir) if self.output_dir is not None else None

    def submit_task(self, settings: dict[str, object]) -> _Job:
        del settings
        assert self.output_dir is not None
        self.jobs += 1
        return _Job(self.output_dir / f"result-{self.jobs}.txt")

    def close(self) -> None:
        self.closed = True

    def observe_closed(self) -> bool:
        return self.closed


def test_two_tasks_reuse_one_owner_and_rebind_distinct_spools(tmp_path: Path) -> None:
    created: list[_Session] = []
    owner = PersistentWan2GPSession(lambda key: _Session(key, created))
    settings = _settings("wan-2.2", "first", seed=1)

    first = owner.run(settings, attempt_root=tmp_path / "one")
    second = owner.run({**settings, "prompt": "second", "seed": 2}, attempt_root=tmp_path / "two")

    assert first.status == "succeeded"
    assert second.status == "succeeded"
    assert second.reused is True
    assert len(created) == 1
    assert owner.CAPABILITY.warm_reuse_expected is False
    assert created[0].jobs == 2
    assert Path(first.generated_files[0]).parent == (tmp_path / "one").resolve()
    assert Path(second.generated_files[0]).parent == (tmp_path / "two").resolve()
    owner.close()
    assert created[0].closed is True


def test_resident_change_fences_old_incarnation_before_replacement(tmp_path: Path) -> None:
    created: list[_Session] = []
    owner = PersistentWan2GPSession(lambda key: _Session(key, created))

    owner.run(_settings("a", "one"), attempt_root=tmp_path / "one")
    owner.run(
        _settings("b", "two"),
        attempt_root=tmp_path / "two",
    )

    assert len(created) == 2
    assert created[0].closed is True
    assert created[1].closed is False


def test_missing_explicit_rebind_protocol_is_rejected() -> None:
    class Unsupported:
        pass

    owner = PersistentWan2GPSession(lambda _key: Unsupported())
    with pytest.raises(PersistentSessionError, match="rebind_output_dir"):
        owner.run(_settings("a", "one"), attempt_root="/tmp/astrid-cpu")


def test_residency_without_content_attestation_is_rejected(tmp_path: Path) -> None:
    owner = PersistentWan2GPSession(lambda key: _Session(key, []))
    with pytest.raises(PersistentSessionError, match="content digest"):
        owner.run({"model": "a", "prompt": "one"}, attempt_root=tmp_path / "one")


def test_output_escape_fences_and_releases_session(tmp_path: Path) -> None:
    created: list[_Session] = []

    class Escaping(_Session):
        def submit_task(self, settings: dict[str, object]) -> _Job:
            del settings
            assert self.output_dir is not None
            return _Job(self.output_dir.parent / "escape.txt")

    owner = PersistentWan2GPSession(lambda key: Escaping(key, created))
    result = owner.run(_settings("a", "one"), attempt_root=tmp_path / "one")
    assert result.status == "failed"
    assert "containment" in result.errors[0]
    assert created[0].closed is True


def test_ambiguous_rebind_acknowledgement_blocks_submission(tmp_path: Path) -> None:
    created: list[_Session] = []

    class Ambiguous(_Session):
        def rebind_output_dir(self, output_dir: Path) -> None:
            super().rebind_output_dir(output_dir)
            return None

    owner = PersistentWan2GPSession(lambda key: Ambiguous(key, created))
    result = owner.run(_settings("a", "one"), attempt_root=tmp_path / "one")
    assert result.status == "failed"
    assert "rebind" in result.errors[0]
    assert created[0].jobs == 0
    assert created[0].closed is True


def test_cancellation_retires_incarnation_before_next_task(tmp_path: Path) -> None:
    created: list[_Session] = []
    owner = PersistentWan2GPSession(lambda key: _Session(key, created))
    checks = iter((False, True))
    first = owner.run(
        _settings("a", "one"),
        attempt_root=tmp_path / "one",
        cancel=lambda: next(checks),
    )
    assert first.status == "cancelled"
    assert created[0].closed is True
    second = owner.run(_settings("a", "two"), attempt_root=tmp_path / "two")
    assert second.status == "succeeded"
    assert len(created) == 2


def test_unverified_release_blocks_future_admission(tmp_path: Path) -> None:
    created: list[_Session] = []

    class Uncertain(_Session):
        def observe_closed(self) -> bool:
            return False

    owner = PersistentWan2GPSession(lambda key: Uncertain(key, created))
    owner.run(_settings("a", "one"), attempt_root=tmp_path / "one")
    with pytest.raises(PersistentSessionUncertain):
        owner.run(_settings("b", "two"), attempt_root=tmp_path / "two")
