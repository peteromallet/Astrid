# Matrix minkhole: editing and review workflow

For the reusable method, including collaboration and agent checks, start with [Replacing speech in an existing video](replacing-speech-in-existing-video.md). This document records the project-specific example and handoff.

Updated 9 September 2026. Project: `matrix-minkhole`. Timeline: `rough-cut`.

## Current result

We built a timing preview using the original Matrix pill scene, replacement narration and revised picture cuts. The latest delivered preview is [v13](../runs/matrix-minkhole/minkhole-review-v13.mp4), render `e3aaf311c17b450198d1c2d6f1582887`, lasting approximately 29.54 seconds.

The original red pill is still visible in the moving footage. The [pixely creature image](../runs/matrix-minkhole/planning/pixely-creature-concept.png) is a concept still; the moving replacement and matching reflections remain to be made. MiniMax/H3 was investigated as a possible route, but was not used to produce this edit.

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

1. Render a concrete edit and pin review evidence to that exact run.
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

## Next steps

1. **Review v13 in the integrated inspector.** Confirm runtime/client compatibility, generate the pinned filmstrip with media, and check waveform, phrase coverage, seeking and cut navigation against the actual video. Admit verified speech annotations if phrase rows are missing.
2. **Finish the picture timing before effects.** Use phrase boundaries and cut-neighbor frames to review the reveal, face return and pickup. Keep any new changes tied to a new render and its own evidence.
3. **Test the creature replacement on the short hand reveal.** Select and validate a video-editing workflow using the source shot and concept still. Match lighting, palm contact, scale and motion before processing other shots.
4. **Carry the creature consistently through reflections and pickup.** Nothing should appear before the reveal. Preserve the blue pill and end before any eating action.
5. **Finish dialogue and sound.** The current voice is temporary narration. If on-camera speech must match the new words, test a dialogue/lip-sync pass after timing is settled; then review final sound and picture together.
6. **Render and repeat the same evidence loop.** Check every cut, sentence transition, measured gap and effect boundary, then open the finished video for review.

Local media links above are workspace deliverables, not portable source assets. Astrid’s managed run and digest-verified artifacts remain the durable render evidence. See the [rendering skill](../astrid/packs/rendering/skill/SKILL.md) for the supported editing and visualization contract.
