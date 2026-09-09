# Audio and speech in the unified timeline inspector

Status: implemented in the current checkout; the waveform/rhythm viewer under `runs/matrix-minkhole/audio-v11/` remains a diagnostic prototype and is not the shipped inspector implementation.

## Outcome

Extend the existing `--view filmstrip` inspector with synchronized picture, speech and waveform rows. Do not introduce a third visualizer, separate navigation model, runtime store or capability. Keep `--view structure` compatible. The user should be able to see what is said, what is shown, and where a pause occurs, then play or inspect that exact interval.

## Concrete motivating case and completed edit

In Matrix v11, measured near-silence runs from 21.790812 to 24.259042 seconds: 2.468229 seconds before “And see just how deep the minkhole goes.” This was measured from the rendered audio using FFmpeg silence detection at −40 dB for intervals of at least 0.25 seconds; it is not inferred from empty transcript space.

The closing shot and its audio were moved 50 frames earlier at 24 fps. Its parent placement is now 21.916667 seconds, and the preceding picture is shortened to match without trimming the spoken line. Parent version 10 and creature child version 5 retain the edit. Expected residual pause is approximately 0.385 seconds. The final v12 review render succeeded as `8829c7209bff4b569a10d9a1b47aadd0`, video SHA-256 `24190c7cdfd3be3bca111e554a5027fbc3a0b4604ee80c1757ad17b5fe9764ee`. Final rendered-audio verification measured 21.790812–22.176042 seconds, a 0.385229-second pause. The downloaded video was hash-verified and opened; total timeline duration is 29.541667 seconds. Local delivery: `runs/matrix-minkhole/minkhole-review-v12.mp4`.

## Experience

- One time ruler, viewport, playhead, selection and detail panel for all rows.
- A compact “Speech and audio” disclosure adds phrase blocks and the waveform beneath the picture row. Remember its state within the viewer.
- Show actual rendered mix by default. Expand declared audio tracks for placements; only display per-track waveforms when an actual corresponding stem exists. Never repeat the mix waveform and imply isolation.
- Phrase blocks show readable canonical wording with timing provenance in details. Recognized text remains available when it differs. Zoomed-out blocks may shorten labels; selection always reveals the full text.
- Highlight measured quiet intervals with duration labels. Call them “Quiet gap” and expose the measurement threshold. Keep “No speech annotation” distinct: missing words can coexist with audible sound, music or effects.
- Clicking a phrase, gap, waveform point, cut or frame goes through the same select/seek action. A selected gap plays with a short context handle on either side; loop is optional. Previous/next phrase or gap is available alongside existing frame navigation.
- During playback the playhead follows real media time, even between captured images. Do not snap playback to the nearest filmstrip sample.
- Existing range, shot, asset and search filters apply coherently. Keep the ruler in absolute render time; filtered material is dimmed or explicitly omitted, never time-compressed.
- Use existing typography, colors, focus styling and spacing. Labels and patterns supplement color. Keyboard controls must not intercept text entry; screen-reader labels include text, start, end and duration.

## Data and authority

Extend the frame index additively with an `audio` section and versioned, digest-verified sidecars. All annotations belong to the exact successful render and its frozen snapshot, including when the current edit has changed.

1. **Waveform:** render/video digest, selected audio stream, presentation-time origin, sample rate, channels, decoder and analysis version; streamed integer-sample bins containing min/max or peak plus RMS. Store multiple bounded resolutions for zooming. Use a fixed amplitude scale; document downmix policy and preserve channel information to avoid cancellation hiding sound.
2. **Speech:** separate canonical wording from recognized wording; source audio digest, immutable transcript/annotation digest, source sample bounds, timing method, uncertainty and correction version. Map through the frozen occurrence, trims, speed and placement into render time. Repeated clips remain distinct occurrences. Unsupported time warps must be marked unavailable, not approximated silently.
3. **Gaps:** distinguish `low_amplitude` measurement from `no_phrase_annotation`. Record threshold, minimum duration, channel aggregation and analysis digest. Speech absence is not acoustic silence; waveform amplitude is not semantic speech detection.
4. **Coverage:** record unavailable streams, partial transcript coverage, missing/uncertain words and analysis failures explicitly. Missing transcription does not prevent waveform inspection.
5. **Time:** sample indices remain authoritative for audio; canonical integer frames remain authoritative for picture. Conversion uses rational rates and the actual stream time origin. Define half-open intervals and deterministic rounding; never progressively accumulate float offsets.

Prefer an existing immutable transcript tied to the admitted source audio. If transcription is absent, offer an explicit analysis action through the existing editorial capability and report missing provider readiness. Do not make opening an inspector silently start paid transcription. Local diagnostic ASR is not automatically canonical transcript authority.

## Navigation and playback contract

Extend `inspector_navigation.py` with render-scoped phrase and gap targets. Include analysis/annotation identity so a corrected transcript cannot silently change an old target. Reuse the existing pinned-render range commands; introduce a narrow additive selector only if required. Preserve old frame, clip, track and shot target behavior and keep the structural legacy target grammar separate until its existing adapter work is done.

The inspector state owns selected target, visible range, playback time and loop interval. Every row consumes that state. Use the HTML media clock with `requestVideoFrameCallback` when available and a `timeupdate` fallback. Selection can remain a phrase or gap while the playhead advances. Escape authored and recognized text. Bundle a relative digest-verified video file for offline playback rather than embedding a large base64 video; make playback inclusion explicit because it changes artifact size.

## Implementation packages

| Package | Existing owner/seam | Deliverable |
| --- | --- | --- |
| Measured audio | `timeline_visualize/filmstrip_execution.py`, new focused analysis helper | Decode exact admitted render; bounded waveform pyramid, measured gap sidecar, clear stream absence/errors |
| Speech projection | SDK `timeline_filmstrip.py`, new focused projection helper | Retrieve immutable transcript through runtime; project through frozen clip occurrences; expose coverage and provenance |
| Index and targets | `filmstrip_cards.py`, `inspector_navigation.py` | Additive audio schema, stable phrase/gap identities and pinned navigation |
| Viewer | `inspector_viewer.py`, `inspector_assets/inspector.js` and `.css` | Shared audio rows, playback/seek/loop, unified selection and accessible controls |
| Delivery | Existing filmstrip bundle/manifest and SDK rehydration | Hashed waveform/transcript/media artifacts; bounded extraction and cache reuse |
| Documentation | Rendering skill, timeline cookbook, visualize STAGE, CLI help | Accurate capability boundaries and examples; retire prototype-only instructions after parity |

Keep analysis pure and testable; runtime admission, media lookup and publication stay in their existing SDK/executor owners. Do not invoke executor modules directly or read runtime stores. Reuse existing bundled-artifact verification and limits.

## Delivery sequence

1. Ship waveform and measured gap rows from exact render audio, using existing selection/range navigation. Preserve useful operation without transcription.
2. Add immutable speech timing projection and text search, with explicit unavailable/partial states.
3. Add synchronized media playback, context audition and loops to the same viewer state; retain PNG evidence export.
4. Add per-track stems only where real stems are available. Do not block the useful full-mix inspector on stem rendering.
5. Update skill and CLI documentation and run the actual Matrix regression before calling the integration complete.

Waveform density follows zoom and should not reuse the picture sampling interval. Limit decoded duration, samples, sidecar bytes and annotation count; stream long media and cache by immutable input plus analysis settings. Empty audio, no speech, muted clips and missing transcripts are normal states.

## Acceptance and verification

- Matrix v11 visibly exposes the measured 2.47-second gap; the corrected render exposes roughly 0.4 seconds using the same settings.
- Clicking either gap auditions the correct interval and shows matching picture frames. Phrase and frame selection, keyboard navigation, filters, deep links and playback all share state.
- Test leading/trailing silence, quiet speech, music under narration, stereo/channel cancellation, overlapping audio, muted clips, fades, empty tracks and a render with no audio stream.
- Test trimmed and retimed clips, repeated occurrences, fractional-frame audio onsets, stream PTS offsets, missing transcript spans, uncertain ASR and corrected annotation identities.
- Frozen render evidence never mixes with a newer script or newer timeline. Changing analysis settings or a transcript correction changes analysis identity, not the original render.
- Validate bounded memory and artifact size for a long render; corruption/path traversal checks still cover every new bundle member.
- Run focused analysis/projection/navigation tests, existing inspector/CLI regressions, and media-backed playback/seek tests. Visually inspect exported evidence and report the limits of browser testing honestly.
- Existing structural view and old filmstrip consumers remain compatible. Opening the viewer does not make an unrequested provider call.

## Not included in this plan

Automatic silence deletion or an unreviewed ripple-edit action. Inspection can suggest an interval and expose owning editable clips; actual edits still use canonical timeline saves with fresh versions. Also excluded: replacing the Matrix pill with an animated creature, which is a separate visual-effects task.

## Prototype and environment handoff

The diagnostic currently loads whole PCM into memory, uses mono downmix and its own playback controller. These are prototype limitations, not production architecture to copy. Reuse its evidence and interaction lessons; implement bounded analysis and one shared inspector state.

A concurrent checkout/runtime update interrupted delivery tooling. The completed render was retrieved with a schema-matched runtime client and compatibility checks intact. The current Astrid host checkout still needs a matching runtime schema before future renders; resolve this prerequisite through normal runtime tooling without weakening health or identity checks. The delivered implementation is limited to the local, render-admitted filmstrip path and its focused compatibility coverage; Matrix/browser-backed proof remains an environment-dependent follow-up recorded in the run status.

## Implementation evidence (2026-09-09)

Implemented in the current checkout at main SHA `82736138dd8b44a6dbaa7d229f38ef5c065bc79a`.

- Focused integration command: `python3 -m pytest -q tests/packs/rendering/test_audio_analysis.py tests/packs/rendering/test_speech_projection.py tests/packs/rendering/test_inspector_navigation.py tests/packs/rendering/test_timeline_inspector_viewer.py tests/packs/rendering/test_timeline_filmstrip_cards.py tests/packs/rendering/test_timeline_filmstrip_execution.py tests/sdk/test_timeline_filmstrip.py tests/sdk/test_timeline_filmstrip_invocation.py` — 42 passed.
- Affected timeline command: `python3 -m pytest -q tests/packs/rendering/test_timeline_visualize_*.py tests/packs/rendering/test_timeline_filmstrip_cards.py tests/packs/rendering/test_timeline_filmstrip_execution.py tests/packs/rendering/test_inspector_navigation.py tests/packs/rendering/test_timeline_inspector_viewer.py tests/sdk/test_timeline_filmstrip*.py tests/core/timeline/test_timeline_visualize_*.py tests/core/test_timeline_visualize_view_context.py tests/core/rendering/test_cli.py tests/core/rendering/test_cli_contract.py` — 251 passed, 71 skipped.
- Static checks passed: `python3 -m compileall -q astrid/packs/rendering/executors/timeline_visualize astrid/sdk`, `node --check astrid/packs/rendering/executors/timeline_visualize/inspector_assets/inspector.js`, and `git diff --check`.

Limitations remain unchanged: Matrix/browser-backed playback proof was not locally available, and future renders on this host require a matching runtime schema. The shipped proof is the local render-admitted filmstrip path and focused compatibility coverage; no provider call is made when the inspector opens.

## Final Megado completion audit — 2026-09-09

The current dirty `main` checkout was re-audited at Astrid `HEAD`
`82736138dd8b44a6dbaa7d229f38ef5c065bc79a`. The audit corrected the documented
`--include-media` CLI/parser gap and added a direct help-surface assertion.

- Focused audio/speech/inspector/SDK gate: **42 passed**.
- Exact affected timeline gate: **251 passed, 71 skipped**.
- Timeline CLI visualize help regression: **4 passed, 83 deselected**.
- Compileall, Node syntax, and `git diff --check`: **passed**.
- Shared managed setup/offline/discovery/skill/runtime evidence is recorded in
  the default-packs plan and its `.otto` acceptance ledger. The Hivemind pin is
  locally validated; upstream publication remains explicitly unauthorized.

Final local verdict: **complete locally with the recorded browser/runtime
limitations**. Matrix/browser-backed playback was not available in this
environment, and three unrelated-to-audio integration fixtures remain blocked
by the deliberate runtime schema identity mismatch (`sha256:64f9c5ff...` daemon
versus `sha256:4be7e530...` generated client). No health or identity check was
weakened. The independent current-candidate verdict is recorded in the run
ledger.
