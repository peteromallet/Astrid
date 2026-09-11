from __future__ import annotations

from pathlib import Path


def test_generation_alone_does_not_access_timeline_mutation_api(
    monkeypatch, tmp_path: Path
) -> None:
    import astrid
    import astrid.sdk as sdk
    from astrid.core.generation import GENERATION_RESULT_KEY
    from astrid.core.generation.backends.base import GenerationResult

    class NoTimelineAccessClient:
        @property
        def timelines(self):
            raise AssertionError("generation must not access timeline placement")

    def fake_invoke(capability_id: str, **_kwargs):
        return astrid.InvocationResult(
            capability_id=capability_id,
            capability_type="executor",
            native_kind="built_in",
            ok=True,
            raw_result={
                "payload": {
                    GENERATION_RESULT_KEY: GenerationResult(
                        image_paths=[tmp_path / "generated.png"],
                        model_actual="flux-dev",
                        run_dir=tmp_path,
                    ).to_dict(),
                    "returncode": 0,
                }
            },
        )

    monkeypatch.setattr(sdk, "invoke", fake_invoke)
    result = astrid.generate.image(
        model="flux-dev",
        mode="t2i",
        execution="cloud",
        project="demo",
        client=NoTimelineAccessClient(),
        out=tmp_path,
        prompt="a lantern in fog",
    )

    assert result.ok is True
    assert result.path == tmp_path / "generated.png"
