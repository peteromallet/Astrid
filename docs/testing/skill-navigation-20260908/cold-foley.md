# Cold navigation trial: Foley for an existing ten-second video

User query: “Add Foley to my existing ten-second video and give me a finished video with the sound.”

## Navigation log

1. Read `Astrid/astrid/packs/_core/skill/SKILL.md` (core orientation). It says creative requests must route through `creative-work/SKILL.md`; packs own execution contracts; live work must use the runtime/SDK.
2. Read `Astrid/astrid/packs/_core/skill/creative-work/SKILL.md`. The exact route for “Add sound to one short video clip” is `fal` followed by timeline editing/rendering: `fal.fal_foley` produces audio, then place it alongside the source video and render.
3. Read `Astrid/astrid/packs/fal/skill/SKILL.md`. Confirmed `fal.fal_foley` is the single-short-clip Foley executor, recommended for clips ≤15 seconds, and that Foley generation returns audio only rather than a muxed video. It explicitly directs the returned runtime audio artifact into the source video timeline and then to the rendering skill.
4. Attempted the inferred path `Astrid/astrid/packs/fal/capabilities/fal_foley/STAGE.md`; it did not exist. This was a path correction/backtrack, not a route failure.
5. Read-only file discovery under the fal pack located the actual stage contract at `Astrid/astrid/packs/fal/executors/fal_foley/STAGE.md`.
6. Read `Astrid/astrid/packs/fal/executors/fal_foley/STAGE.md`. Contract: invoke SDK capability `fal.fal_foley` with `kind="executor"`, explicit `project`, and inputs `clip` plus a short natural-language `prompt`; input accepts mp4/mov/webm/m4v/gif and is ≤15 seconds recommended; output is one audio file (typically WAV) plus a `.fal.json` sidecar; requires `FAL_KEY`.
7. Read `Astrid/astrid/packs/rendering/skill/SKILL.md`. Timeline edits and rendering are runtime-owned; use CLI/SDK, preserve managed media identity/digests, and render through `rendering.render` or the product timeline command.
8. Read-only file discovery under the rendering pack located `Astrid/astrid/packs/rendering/executors/render/STAGE.md` (the render stage is under `executors`, not `capabilities`).
9. Read `Astrid/astrid/packs/rendering/executors/render/STAGE.md`. Contract: SDK `astrid.sdk.invoke("rendering.render", kind="executor", project=..., inputs={"timeline_ref": ..., "expected_version": ...})`; managed timeline rendering is equivalent to `python3 -m astrid timelines render <ref> --project <project> --expected-version <version>`. Render output is a project/runtime-owned video plus provenance sidecar. `timeline_ref` is mutually exclusive with raw `timeline`; managed mode is the correct route for an existing runtime timeline.
10. Read `Astrid/astrid/packs/rendering/skill/references/timeline-cookbook.md`. Audio must be represented as an explicit audio track/clip in the complete runtime timeline document; media references in durable state must be runtime-owned object IDs with verified digests, not source paths or URLs. The render profile’s audio fields are an all-or-none trio; default MP4 output uses H.264/AAC.

## Final route and actionable contract

1. Resolve/select the runtime project and existing ten-second source video through Astrid’s project/media/timeline surfaces. The user file is expected to be missing during this cold trial; that is a data prerequisite, not a navigation failure. Do not infer state from checkout filenames.
2. Admit Foley generation through the SDK:

   ```python
   import astrid.sdk as sdk
   result = sdk.invoke(
       "fal.fal_foley",
       kind="executor",
       project="<project>",
       inputs={
           "clip": "<runtime/project-owned ten-second clip>",
           "prompt": "<short description of the sounds the video should make>",
       },
   )
   ```

   Required external credential: `FAL_KEY`. The result is an audio artifact, not a finished video.
3. Create or update the project’s managed timeline through the runtime. Keep the source video on a visual track and add the returned runtime audio artifact on an audio track at the same start/time span as the scored clip. Save the complete config and registry with the observed `config_version` using the timeline save compare-and-swap contract; do not persist raw local paths, URLs, or private CAS locators.
4. Render the saved managed timeline:

   ```bash
   python3 -m astrid timelines render <timeline-slug-or-id> \
     --project <project> \
     --expected-version <observed-config-version> \
     --output-name finished-foley.mp4 \
     --json
   ```

   SDK equivalent: `sdk.invoke("rendering.render", kind="executor", project="<project>", inputs={"timeline_ref":"<timeline>", "expected_version": <version>})`.
5. Inspect the successful runtime render/run and hand off the published runtime video artifact and provenance. The contracts support a finished rendered video artifact; Foley generation alone does not.

## Remaining docs friction

- The routing docs name “timeline editing” but do not provide a Foley-specific worked timeline JSON example or a dedicated audio-clip schema in the ten-action path.
- The exact CLI/SDK operation for importing/admitting the user’s local source video into a runtime-owned media object was not exposed by the selected links; it must be resolved from the connected runtime/media surface before execution.
- Stage locations are under `packs/<pack>/executors/<id>/STAGE.md`, while the first inferred `capabilities/<id>` path was stale.
- No execution, runtime discovery, media search, network call, or mutation beyond this requested navigation log was performed.
