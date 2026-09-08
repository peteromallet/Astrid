# Unified timeline inspector review

This review is intentionally bounded to the interface between the frozen
render snapshot, navigation, and the offline filmstrip viewer. It does not
approve changes to the runtime timeline authority or introduce a second
timeline store.

## Architecture decision

The inspector should have one frozen presentation model per successful render.
The model must contain the composited frame cards and a complete projection of
the frozen timeline's declared tracks, including empty tracks. Each clip keeps
its canonical integer `[start_frame, end_frame)` bounds, authored id, track id,
kind, source/asset identity, and occurrence identity. Audio is represented as a
placement interval; the inspector must not manufacture a waveform or imply
that a script binding is word timing.

The UI and agent commands consume the same target union:

```text
frame   { timeline, render_run, frame }
clip    { timeline, render_run, clip_id, occurrence_id? }
shot    { timeline, render_run, shot_id, occurrence_id? }
range   { timeline, render_run, start_frame, end_frame, range_id? }
track   { timeline, render_run, track_id }
```

Every target is scoped to the canonical timeline and pinned render/video digest.
`occurrence_id` is required when repeated shot/clip placements could otherwise
collapse. A clip selection resolves to a captured frame only when a captured
frame lies in its interval; otherwise the details panel reports that no frame
was captured and exposes the exact focus command. Frame and clip actions must
round-trip through the same serializer/parser used by the viewer.

The existing frame-index card shape remains compatible. Additive fields should
carry `track_id`, `track_kind`, `occurrence_id`, `active_clip_ids`, and the
serialized target; do not rename existing `id`, `frame`, `time_rational`, or
`actions.focus_command` fields. Build the track lanes from the same frozen
snapshot that annotates cards, never from the current timeline after a render.

## Review findings against the current tree

- The current filmstrip snapshot and card planner already use integer frame
  intervals and frozen render authority, which is the right base.
- The current card model has active clips and script segments but does not yet
  expose a complete track list, empty tracks, audio/visual lane metadata, or
  occurrence-safe clip targets. The UI currently renders a card grid only.
- `navigation.py` currently allocates timeline/shot/clip/asset/range display
  ids, while its own module contract says tracks have no `TR` display code.
  Track references therefore need the additive typed target grammar above;
  do not pretend `TR` is already a valid legacy display id.
- Structural `--from-view/--focus` is a frozen manifest navigation protocol.
  Filmstrip focus commands are render/frame navigation. Keep these grammars
  visibly separate until an adapter is implemented and tested.
- The runtime authority checks in `timeline_filmstrip.py` correctly reject an
  unmanaged video and stale latest render. Preserve those checks while adding
  lanes; a lane payload must carry the same render run and video digest.

## Acceptance checklist

### Frozen data and bounds

- [x] Snapshot contains every declared visual and audio track, including empty
      tracks, in canonical track order.
- [x] Every clip has half-open integer frame bounds derived by the compositor;
      fractional starts are covered by a fixture and repeated placements retain
      separate occurrence ids.
- [x] Audio rows are interval placements with source identity; no waveform or
      inferred silence is emitted.
- [x] Lane metadata preserves frozen mute/visibility/opacity/compositing flags;
      overlap at the playhead is described as timing overlap, not proof that a
      clip is audible or visible in the final composite.
- [x] Current edits cannot alter annotations for an explicit old render run.

### Shared navigation

- [x] Frame, clip, shot/occurrence, range, and track selections serialize to
      one typed target shape containing timeline and render scope.
- [x] Selecting a frame highlights all active lanes; selecting a clip selects a
      captured frame only when one exists in that clip's interval.
- [x] Unsampled clip selection states “no captured frame” and provides the
      exact pinned focus command; it never chooses an unrelated frame.
- [x] Range/search/shot filters update grid and lanes together and preserve or
      explicitly clear selection according to a tested rule.
- [x] The dense captured-frame grid and the track time ruler share the same
      scope but remain honest about sampling: density hides captured cards and
      never implies that unsampled frames were extracted.
- [x] Deep-link/hash round-trip, previous/next captured frame, and keyboard
      navigation work without hijacking text inputs.

### Viewer and compatibility

- [x] Offline HTML escapes authored labels/scripts and has no global CSS leak.
- [x] Visual and audio lanes are distinguishable without color alone; the
      selected state is visible in the grid, lanes, and details panel.
- [x] Details expose time/frame, script status, active track/clip/source ids,
      stable target, and exact rerun/focus command.
- [x] `--view filmstrip` is the unified inspector; `--view structure` and its
      legacy `--from-view`/`--focus` object navigation remain documented and
      working.
- [x] Existing frame-index consumers and structural selectors pass unchanged.

### Verification fixture and gates

- [x] Fixture includes overlapping visual/audio clips, an empty track, a
      repeated shot, fractional starts, script gaps, and an unsampled clip.
- [x] Focused model/card/viewer tests cover target round-trip and selection
      synchronization; static pack validation checks HTML escaping and hashes.
- [x] A managed full-timeline smoke confirms digest-pinned render provenance,
      openable offline HTML, and SDK output paths. Browser file-URL inspection
      remains unavailable under the current policy; deterministic DOM/tests and
      PNG inspection are the evidence for this surface.

## Risk gates for integration

1. Do not land UI-only track inference. The snapshot builder must first expose
   frozen tracks and occurrence-safe bounds.
2. Do not reuse structural display ids as track ids. Add a typed track target
   or keep tracks as authored ids inside the render-scoped target.
3. Do not let density filtering mutate the source selection model. It may hide
   captured cards, but it cannot invent a frame or change lane intervals.
4. Do not call the inspector a synchronized timeline if the selected render
   lacks frozen timeline provenance or if current tracks are mixed into it.

## Final review evidence

The focused navigation, viewer, card, SDK, and invocation tests pass together
(`41 passed` in the final local review; the coordinator reports the broader
suite at `130 passed`). The Node-backed tests exercise target round-trips,
unsampled clips, repeated occurrences, shared filters, keyboard guards, lane
rendering, empty tracks, copy-command behavior, and offline HTML escaping.
Native inspector smoke runs `3da9...` and `17dd...` emitted the inspector with
two tracks; the coordinator also completed the full timeline render/open smoke.
