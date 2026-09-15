# Matrix minkhole: editing and review workflow

For the reusable method, including collaboration and agent checks, start with [Replacing speech in an existing video](replacing-speech-in-existing-video.md). This document records the project-specific example and handoff.

Updated 11 September 2026. Project: `matrix-minkhole`. Timeline: `rough-cut`.

## Current result

The latest delivered reference-keyframe preview is **v23**, canonical render `a5f7624d22eb4e85bfc9a40aba81f76a`, digest `sha256:29f72b5caa8349afa6c6731dc6a2347264aa527737b670250bd0fa1c8eba2dcd`, approximately **43.492667 seconds** at 720p/24 fps. Parent timeline version: **21**; the final reflection child is version **16**. It was rendered through the Astrid task runtime with `review: true`, opened from the exact successful run, and checked as a reference-keyframe preview. The v23 picture updates preserve the accepted four-limb correction while matching the mink scale and the amazed pixel-Neo expression; this remains a still-based visual draft rather than finished animation or lip-sync.

```bash
python3 -m astrid runs open a5f7624d22eb4e85bfc9a40aba81f76a --project matrix-minkhole
```

The first five seconds introduce the canonical mink-on-ASTRID logo, melting pixels and a Matrix-style pullback. The final part of that pullback uses actual Morpheus speaking footage and continues into the original “You have two options” opening. The full dialogue remains present.

The current six-shot cut is: **00:00–00:05** ASTRID through the glasses; **00:05–00:08** “Two options”; **00:08–00:19** blue-pill manual tools; **00:19–00:22** red pill; **00:22–00:26.916667** creature reveal in the glasses; and **00:26.916667–00:43.492667** the reflection close-up. The separate frontal smiling Neo still remains removed. The final shot keeps the two reflections distinct: only the touching, screen-left Neo changes, while the screen-right blue-pill Neo remains human. The mink then examines its hands, says “Let’s go!”, and runs through the pixel world before the canonical Astrid logo and slogan ending.

## Current production shot approach

Treat the v23 cut as the timing and continuity reference for the next generation pass. Start with one short, representative speaking-face passage, using the actual source shot and its surrounding original audio. Resolve the replacement line, source interval, retained context and spatial mask before processing the longer reflection sequence. Keep the hand/object reveal and the two-reflection transformation as a separate pilot: it needs tracked spatial masks, matched before/after contact frames and explicit protection for the unaffected screen-right character.

The practical order is: lock the Astrid timeline and phrase timing; test one H3 audio/video inpainting passage; inspect the generated line and both audio boundaries; then test the hand/object or reflection replacement separately. Combine them only after each pass is visually stable. A still-based reference-keyframe preview can establish design and timing, but it cannot prove temporal consistency, lip-sync, identity preservation or reflection continuity.

## Lessons from the reference-keyframe revisions

- **Review mode is the default during feedback.** Use `--review` on every revision and inspect the actual exported labels. The filmstrip complements the video; it does not replace those labels.
- **Review exports are lightweight by design.** Remotion uses its backend `--scale` option to fit the authored canvas inside 640x360 while preserving aspect ratio. The canonical canvas and authored positions stay unchanged, the output profile matches the dimensions actually emitted, and the video carries `Low Res Render` at top left. Explicit profiles and clean exports keep their existing resolution.
- **Find the real character in the referenced timeline.** The useful Astrid-intro references were later registered anchors, not its first opening image or the initially empty saved-reference list. `anchor_shot_v02.png` established the mink-on-logo design, `anchor_shot_v03.png` the upright mink and slogan, and `anchor_shot_v06.png` the side profile. These names describe the inspected exports; recover the managed media through the source timeline rather than treating a filename as identity.
- **Use those images as generation inputs every time.** The mink is flat orange pixel art with a long low body, short legs and dark pixel details. Earlier furry, rounded or glowing-outline substitutes did not match. Reflections must preserve the same character design.
- **Track the two reflections separately.** Screen-left is the mink interaction and transformation; screen-right retains the human blue-pill character. Keep matched before/after contact frames and preserve the unaffected figure.
- **Preserve speech while changing picture.** Removing the smiling still meant extending the preceding reflection picture, not shortening its dialogue. Adding the intro must not lose “You have two options.” Compare decoded audio when an edit is picture-only.
- **A zoom into a speaking shot needs the real shot.** The opening zoom was corrected to use advancing source footage, with matching source time across the following cut. Check adjacent rendered frames for continuity.

## Historical timing preview (v13)

The remainder records the earlier 9 September timing pass and its evidence. Its render IDs, timestamps and future-work list are historical, not instructions to restore that edit. v13 (`e3aaf311c17b450198d1c2d6f1582887`) lasted about 29.54 seconds and still used the original red-pill footage. MiniMax/H3 was investigated but was not used for these delivered revisions.

## Script and picture

| Narration | Intended picture |
| --- | --- |
| “You have two options.” | Morpheus leaning forward with both fists closed. |
| “You take the blue pill.” | Blue hand opening. |
| “You keep running tools one by one, tuning workflows by hand, searching through GitHub issues for answers.” | Neo looking nervous, then Morpheus speaking; preserve blue-only pill reflections. |
| “Or you get this cute little pixely creature,” | Hand reveal; eventually replace the red pill with the creature. |
| “who knows how to do everything in the open-source AI art space.” | Cut back to Morpheus’s face at the audible start of “who knows.” |
| “And see just how deep the minkhole goes.” | Continue through Neo picking it up; stop before the hand-to-mouth action. |

“Creature” introduces the helper without repeating “mink” before “minkhole.”

## What we used

- **Astrid CLI/SDK:** inspect canonical timelines, save version-checked edits, render, inspect run evidence and retrieve verified media. The parent timeline arranges child shots; child clips control source trims, speed and audio placement.
- **Timeline visualizer:** rendered filmstrips and contact sheets show actual output at regular intervals and around cuts. Structural views explain track and clip arrangement.
- **macOS Daniel voice, rate 135:** temporary narration. The creature sentence was generated as one continuous WAV and split at an exact audio sample across child shots, preserving its delivery.
- **Local faster-whisper:** estimated phrase/word timing, checked against the intended script and actual audio. These diagnostic estimates were not treated as canonical transcripts. The public transcription route lacked provider readiness at the time.
- **FFmpeg:** source-frame inspection, rendered-audio analysis, silence measurement and adjacent-frame verification.
- **Diagnostic sentence/waveform viewer:** placed text, picture and measured audio on a common time axis to expose pauses and cuts. This project prototype informed the integrated inspector.
- **Image generation:** produced the creature-in-hand concept still from a source frame.

## The review loop

1. Render a concrete edit with `--review`, verify visible shot names/timecodes in the video, and pin review evidence to that exact run.
2. Scan a contact sheet for picture continuity. Sample more densely around a suspicious cut; inspect the frames immediately before and after it.
3. Compare each phrase’s beginning and end with the picture. Use the waveform to distinguish an actual quiet interval from missing transcript annotations.
4. Listen around the proposed edit. ASR gives a starting point; the audible onset determines the final cut.
5. Map the render time back to its owning child clip. Adjust picture trims, speed or placement; move audio only when the spoken timing itself needs changing.
6. Save through Astrid, re-render, and compare the affected interval. Open the actual video or image for review and report exact time references.

This caught early red-pill reflections, unwanted flashes at cuts, incorrect opening footage, a short pickup ending and excess silence before the closing line. It also showed why a single image per authored shot is insufficient: a shot can contain several visual changes or span a sentence boundary.

Two verified fixes:

- **Closing pause:** v11 had 2.468 seconds of measured near-silence. Moving the closing shot and audio 50 frames earlier at 24 fps reduced it to **0.385 seconds**. Measurement used FFmpeg at −40 dB with a minimum interval of 0.25 seconds.
- **Creature reveal:** v13 holds the hand until **17.583 seconds**, then cuts to Morpheus on “who knows.” Frame 421 shows the hand; frame 422 shows his face. Decoded audio is identical to v12, preserving the tightened pause.

## Using the timeline visualizer

Run from the Astrid checkout with a compatible workspace runtime. For a broad review of the delivered edit:

```bash
python3 -m astrid timelines visualize rough-cut --project matrix-minkhole \
  --view filmstrip --render-run e3aaf311c17b450198d1c2d6f1582887 \
  --every 0.5 --columns 5 --page-size 50 --include-media --json
```

For closer inspection around the creature-to-face cut:

```bash
python3 -m astrid timelines visualize rough-cut --project matrix-minkhole \
  --view filmstrip --render-run e3aaf311c17b450198d1c2d6f1582887 \
  --at 17.583333 --context 2 --every-frames 6 --include-media --json
```

Use `--sample cuts` for cut boundaries, `--sample clips` for picture clips, or `--sample shots` for authored story beats. Interval sampling also retains adjacent cut frames. Use `--range 14..20` to restrict a review. Density controls hide/show captured samples; rerun at a finer interval to obtain additional frames.

The inspector shares an absolute time ruler across picture and declared tracks. Select a frame or interval to inspect details and copy its time, target or pinned focus command. `--include-media` bundles verified video for playback. Open the returned HTML for interactive inspection or the PNG contact sheet for a single-image overview.

Use `--view structure` when the question is how clips and tracks are arranged. Its legacy navigation targets differ from rendered-inspector targets; use the commands supplied by each view.

## Audio visualization status

The [audio integration document](../docs/plans/timeline-inspector-audio-integration.md) now records implementation and focused test evidence in the current checkout. It adds waveform, measured quiet gaps, explicitly admitted speech annotations and optional playback to the existing filmstrip inspector. Missing transcription does not block waveform inspection, and opening a view does not start a transcription provider call.

The earlier [audio-v11 diagnostic](../runs/matrix-minkhole/audio-v11/sentence-review.html) and [waveform sheet](../runs/matrix-minkhole/audio-v11/auditory-timeline.png) show the **old v11 edit**, including the long pause. They are reference evidence, not current v13 views. Integrated playback still needs a fresh Matrix/browser-backed check; implementation tests do not replace that review.

## Historical next steps after v13

1. **Review v13 in the integrated inspector.** Confirm runtime/client compatibility, generate the pinned filmstrip with media, and check waveform, phrase coverage, seeking and cut navigation against the actual video. Admit verified speech annotations if phrase rows are missing.
2. **Finish the picture timing before effects.** Use phrase boundaries and cut-neighbor frames to review the reveal, face return and pickup. Keep any new changes tied to a new render and its own evidence.
3. **Test the creature replacement on the short hand reveal.** Select and validate a video-editing workflow using the source shot and concept still. Match lighting, palm contact, scale and motion before processing other shots.
4. **Carry the creature consistently through reflections and pickup.** Nothing should appear before the reveal. Preserve the blue pill and end before any eating action.
5. **Finish dialogue and sound.** The current voice is temporary narration. If on-camera speech must match the new words, test a dialogue/lip-sync pass after timing is settled; then review final sound and picture together.
6. **Render and repeat the same evidence loop.** Check every cut, sentence transition, measured gap and effect boundary, then open the finished video for review.

Local media links above are workspace deliverables, not portable source assets. Astrid’s managed run and digest-verified artifacts remain the durable render evidence. See the [rendering skill](../astrid/packs/rendering/skill/SKILL.md) for the supported editing and visualization contract.
