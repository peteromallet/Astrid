# Unified timeline inspector

## Outcome
Extend the existing rendered filmstrip into one inspector: final composited frames, expandable multi-track lanes, one shared selection/time window, and a persistent detail panel. Keep the existing structural evidence view compatible. No third public mode, new runtime store, or separate capability. Existing `--view filmstrip` produces the unified inspector; `--view structure` remains available for structural evidence.

## Experience
- Header: project/timeline, pinned render/version, clear frozen-versus-current provenance.
- Primary content: composited rendered frames and human shot/script captions.
- Expandable "Show tracks" section: every declared visual/audio track as a lane on a shared time ruler, clips at canonical integer frame bounds; show empty tracks too. Audio clips are placements, not fabricated waveforms.
- One selected frame/time and optional clip/shot identity. Selecting a frame highlights all active clips; selecting a clip highlights/selects a captured frame in its interval and opens details. If no captured frame falls in it, indicate that honestly and provide exact focus command rather than choosing an unrelated frame.
- One shared range/search/shot scope. Track lanes and frame grid explain what is filtered; no silent mutation of the source render or isolation of a composited track.
- Detail panel: larger selected frame, time/frame, script, active clip/track/source identities, copy stable target and exact rerun command. Previous/next captured frame controls and keyboard navigation, visible selection/focus, responsive layout.
- Density controls use human time/frame values; retain cut-neighbor option semantics and clearly state capture floor. Technical IDs live in details.
- Consistent colors, typography, selection styling, spacing across lanes/grid/details; visually distinguish audio from visual tracks without color as sole cue.

## Navigation contract
Define one additive navigation model for frame, clip, shot/occurrence, range and track references, scoped to canonical project/timeline/render/video digest. Shared integer frame bounds use canonical compositor timing. UI actions and agent copy commands derive from this model, not ad-hoc strings. Existing frame-index consumers remain compatible. Reuse current selectors and pinned --render-run where sufficient; add only a narrow typed focus grammar if needed. Clearly distinguish structural legacy `--from-view` references from new inspector targets until an explicit safe adapter exists; do not claim incompatible schemas are unified.

The frame grid and track lanes MUST consume the same navigation targets/selection, not maintain separate modes. A stale source render must never be annotated with current tracks/scripts.

## Work packages / ownership
1. Navigation/data (edit_plan): new shared navigation module + tests; frozen snapshot tracks/occurrences; schema consumed by UI and frame-index; command generation and SDK/CLI additions only if required. Coordinate exact interface before UI integration. Preserve immutable runtime admission.
2. Inspector UI (filmstrip_ui): new offline HTML viewer module/assets, filmstrip_cards integration; synchronized track lanes/grid/details, responsive aesthetic and keyboard accessibility; DOM/Node interaction regressions. Own viewer and cards, not SDK.
3. Review/docs (h3_research): inspect current shared architecture and this spec; write concrete acceptance/review checklist; update timeline skill/cookbook/STAGE to accurate final behavior after agents finish; review navigation+UI against spec and report defects. Do not edit implementation.
4. Coordinator: resolve interfaces, integration tests, pack validation, actual matrix-minkhole runtime smoke; inspect images, deliver output artifact and concrete completion report.

## Acceptance
- Multi-track fixture with overlapping visual/audio, empty track, repeated shot, fractional start times, script gaps and unsampled clips.
- Frame selection and clip selection synchronize with deterministic frame targets; repeated placements not collapsed.
- Range/filter and density changes preserve or explicitly clear selection; stable deep-link round-trip, next/previous behavior, keyboard input doesn't hijack text fields.
- Viewer remains self-contained/offline and escapes all authored strings; no global CSS affecting unrelated pages.
- Existing structural selectors/navigation remain working and documented; new output distinguishes rendered composition from editable track layout.
- Managed run publishes digest-verified bundle/HTML/manifest, SDK returns openable paths.
- Existing feature/CLI tests + focused new tests, static rendering pack validation, live full timeline and focus smoke.

## Constraints
Repository is heavily dirty: preserve unrelated changes, no reset/revert/commit. Use existing runtime APIs only. Browser automation previously rejected file URLs; do not bypass this policy via a server/alternate browser. Inspect PNGs and run deterministic viewer tests; report browser inspection limitation honestly.

## Live editorial exercise (Matrix)
The user steered implementation validation toward fixing the actual film. V5 already obeyed red reveal at 16s and glasses at 17s, but closed-hand footage at 14s reset a gesture after the blue palm opened;7–11s reused the opening performance. Applied canonical child timeline edits: blue child 5→6, red child 3→4; unused opening continuation then Neo, then the blue opening, continuous Neo reaction from 11.458–16s split seamlessly at 14s, existing red reveal at 16s and glasses at 17s. Parent remains version 6. Audio/scripts/registries preserved. Before/after evidence: runs/matrix-minkhole/planning/continuity-v6-*.json.

Native --sample cuts successfully produced 23 cards, 2 tracks and shared navigation. Labelled one-second motion windows around 8 authored boundaries were produced as runs/matrix-minkhole/cuts-before.mp4 using a diagnostic FFmpeg script; there is no single native cut-motion-reel command. Authored clip boundaries differ from actual visual cuts (the continuous Neo reaction spans an authored boundary at14).

Editing data are sufficient but locating the owning child timeline still takes an extra runtime lookup; copied focus commands inspect, they do not directly open the editable child. Keep this as a concrete follow-up UX gap rather than guessing source ownership from clip IDs.

130 feature/CLI tests passed; rendering pack validates. Renderer admission temporarily unavailable because -I Python probe excluded user-site jsonschema. Installed same existing versions into interpreter site-packages, verified isolated import, confirmed no active tasks, then normal launcher restart refreshed readiness. V6 review render in progress. No timeline authority/integrity checks disabled.

## Completed live verification
Review render `268db6be93a6475e826303060869708a` completed and opened via `runs open`; video digest `sha256:37be9b44ec999aa83e0c94818571a4390d1c13e313160ae46e18fe777d9caef9`. New native inspector run `17ddf90fd26b44a9bf0fc7f7ac7bf02c` produced 62 cards and 2 tracks; copied to `runs/matrix-minkhole/continuity-v6-inspector`. Rendered PNG inspected: continuous Neo through 14s, red hand reveal at 16s, glasses at 17s. Labelled diagnostic `cuts-after.mp4` has 8 windows around authored boundaries `[72,175,233,275,336,384,408,504]` at 24fps. 14s remains a clip/shot boundary but is intentionally not a visual cut. Simple scene detection threshold 0.2 found only 17s, so it is insufficient as an oracle for this dark footage.
