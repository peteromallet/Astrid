# Replacing speech in an existing video

A reusable workflow for an agent working with someone directing an edit: use existing footage, write new dialogue, assemble a timing preview, review it together, then finish speech and visual effects. Based on the [Matrix editing session](matrix-minkhole-workflow.md); the final lip-sync and moving-object replacement steps are still future work in that example.

## Current supported workflow and references

### ComfyUI workflow selected for the next experiment

The starting graph identified in our earlier research was **LanPaint’s MiniMax H3 audio/video inpainting workflow**: [`MiniMax_H3_AV_EncodeDecode_Inpaint.json`](https://github.com/scraed/LanPaint/blob/master/example_workflows/MiniMax_H3_AV_EncodeDecode_Inpaint.json). This choice is recorded in the original [edit plan, “Later generation passes”](../runs/matrix-minkhole/planning/edit-plan.md#later-generation-passes). That document’s old script and timings are superseded; this is its workflow reference.

The planned experiment is to take one short source passage with its original audio, preserve adjacent original voice as context, and replace the selected dialogue interval while permitting the required face/mouth changes. Check the generated wording, voice continuity, lip synchronization and surrounding frames before extending it to other passages. The original context audio is an input to that experiment; the temporary narration is the timing reference. Choose the retained output interval after reviewing the result, rather than assuming all context belongs in the final edit.

For the reusable source provenance → Python candidate → inspection/edit → validation path, see the [VibeComfy workflow onboarding guide](</Users/peteromalley/Documents/reigh-workspace/vibecomfy/.otto/worktrees/canonical-workflow-source-20260903/docs/guides/workflow-onboarding.md>).

This graph **has not yet been validated or run on our footage/runtime**. The local read-only inspection is recorded in [`report.md`](../runs/matrix-minkhole/planning/comfy-inspection/report.md), against the upstream LanPaint graph at commit `32cf848e93971da380d868936e007f5611218bee`; the checked-in graph is [`MiniMax_H3_AV_EncodeDecode_Inpaint.json`](../runs/matrix-minkhole/planning/comfy-inspection/MiniMax_H3_AV_EncodeDecode_Inpaint.json), SHA-256 `2dd64fe26c42281962e434841c458cc935b1d1858e83093b882bbaeb02dc3121`. This provenance is for the original LanPaint reference graph; the intro script's Xenodorf attribution or any derivative graph remains unresolved and should not be treated as established provenance. The native-boundary import failure was resolved in the checked candidate; schema coverage, model availability and executable runtime readiness remain outstanding, and no GPU generation was performed. Inspect its actual inputs, nodes and model requirements before execution; these are planned steps, not a proven recipe. Treat object replacement and glasses reflections as a separate tracked-mask/compositing pass unless testing demonstrates a suitable combined workflow.

### What the graph actually controls

This is a **MiniMax H3 audio/video inpainting graph**, not a standalone TTS or guaranteed lip-sync graph. `LanPaint_VideoMaskEditor` supplies the source video, a per-frame spatial video mask and a temporal audio mask. The nested H3 graph encodes the source AV, samples a new latent with the prompt, then decodes and merges generated content only where the masks permit it.

- The video mask is spatial and temporal: value **1 regenerates** that region/frame and value **0 preserves** the source. Paint the speaker mouth/face only for a dialogue pilot; protect adjacent faces, hands, reflections and background.
- The audio mask is temporal: its JSON intervals are seconds, converted to frame coverage from `floor(start × fps)` through `ceil(end × fps)`. Mask only the replacement line and leave adjacent speech unmasked so the original voice remains available as context.
- The decoder merges generated video inside the video mask and generated audio inside the audio interval, with boundary blending/crossfade controlled by the LanPaint decode node. The source fps is preserved by the wrapper; the H3 duration input is separately rounded to a 24 fps `17k+5` frame grid, so verify the actual output duration and boundary alignment rather than assuming the two time bases are identical.
- The graph does not promise identity-preserving voice cloning. Context preservation comes from retaining unmasked original audio; generated voice quality, speaker continuity and lip synchronization must be judged from the result.

The graph's public controls are source video, video mask keyframes, audio intervals, prompt, duration, seed, resolution, four model selections and LanPaint steps. The upstream demo's media, masks, prompt and model widgets are examples. In this graph the outer subgraph instance overrides inner loader defaults, and the serialized outer/inner model names differ; preserve the effective outer values or report the conflict explicitly rather than silently selecting the nested defaults. The boundary mapping and model-selection evidence is tabulated in [`review.md`](../runs/matrix-minkhole/planning/comfy-inspection/review.md).

The checked builder/source records these **graph defaults**, which are provenance facts rather than recommended best settings: 16:9 at 0.4 megapixels (`864×480` in the source selector), duration 5 seconds, H3 duration quantization at 24fps, LanPaint sampler steps 5, `euler` sampler, decode blend overlap 7 and audio crossfade 0.02. The effective serialized outer model names are `minimax_h3_fl2va_pruned_fp8_scaled.safetensors`, `qwen3vl_32b_minimax_h3_int8_convrot.safetensors`, `minimax_h3_video_vae_fp16.safetensors`, and `minimax_h3_audio_vae_fp32.safetensors`; verify availability and compatibility before using them.

### Recommended common workflow

1. **Lock the edit first.** Use the canonical Astrid timeline to settle the script, source trims and phrase intervals. Render a review timing cut and keep the original source audio available.
2. **Pilot dialogue in one short speaking passage.** Extract the exact source interval, retain a little unmasked speech before and after it, paint only the mouth/face area across the affected frames, and describe the intended line plus unchanged scene in the H3 prompt. Start with a short passage so voice continuity and facial motion can be judged cheaply.
3. **Inspect both domains.** Compare the generated wording and decoded audio at each boundary; watch mouth motion, identity, lighting, hands and neighboring frames; measure any gap or overlap. Keep the result only after listening with context.
4. **Pilot object or reflection changes separately.** Use a tracked spatial mask with matched contact frames for the hand/object reveal. For glasses, maintain separate masks for screen-left and screen-right reflections and explicitly protect the unaffected character. H3 may help with a local temporal inpaint, but it does not replace tracking, compositing or reflection-specific validation.
5. **Assemble through Astrid.** Import the accepted generated media, place it on the canonical child timeline, preserve original ambience/effects deliberately, render with `--review`, and inspect the exact run around every mask boundary and phrase transition.
6. **Scale only after the pilot passes.** Extend the mask and audio interval to the next passage, retaining a new source snapshot, prompt, mask provenance, model names, seed, duration and output digest for each attempt.

### Continuation and longer passages

For **new motion after a clip ends**, the same masking principle is a useful experiment: preserve an overlapping prefix and regenerate a later full-frame region. However, this selected AV inpainting graph merges into an existing source canvas; it is not a verified append-video workflow. A proposed test would first prepare a longer canvas, preserve the original prefix, and mask the placeholder suffix in video and, if new sound is wanted, audio. Canvas preparation, duration handling and mask alignment must be validated before this can be called supported. Alternatively, select a dedicated continuation workflow. Judge motion direction and speed, camera movement, identity and sound across the join; a matching boundary frame alone does not prove a smooth continuation.

For a longer dialogue passage, split only at audible phrase boundaries or clean shot boundaries after the short pilot passes. Keep a small unmasked context window around each replacement so the original voice and room tone can bridge the edit, then inspect every join for a change in timbre, loudness, ambience or lip motion. If the passage crosses a reflection or object interaction, finish the dialogue pilot first and carry the accepted audio into a separate tracked visual pass. Do not infer that a successful short inpaint will remain stable across a full scene; extend one passage at a time and retain independent provenance and review evidence.

### Python review candidate

The [editable H3 Python builder](/Users/peteromalley/Documents/reigh-workspace/vibecomfy/.otto/worktrees/canonical-workflow-source-20260903/comfy-inspection/MiniMax_H3_AV_EncodeDecode_Inpaint.py) is available in the selected VibeComfy worktree. Its `build()` function exposes the prompt, model, source video, video-mask keyframes, audio intervals, duration, seed and step controls. The defaults still describe the upstream demo; select our source passage and replacement dialogue before generation.

This is a review candidate: native subgraph expansion and builder loading have been checked, but current H3 core-schema coverage and runtime requirements remain unresolved. Calling `build()` constructs the graph; it does not generate video. See [inspection and verification](../runs/matrix-minkhole/planning/comfy-inspection/verification.md) for evidence.

The current short Morpheus pilot is preparation-only and remains **blocked before queueing**. Its mask/keyframe and duration checks are recorded in [`prep-checks-v2.json`](../runs/matrix-minkhole/h3-pilot-20260911/prep-checks-v2.json): the canonical managed source has now been extracted at 24 fps as 226 frames/9.416 seconds for 52.000–61.416667 seconds, with its original audio interval retained. H3 quantizes the requested 9-second duration to that same 226-frame grid, but core schema/object-info resolution, runtime authorization and GPU/weight availability remain unresolved; a successful `build()` or `load_bundle()` does not establish queue readiness.

### Astrid assembly and review

Use **Astrid timeline editing → review-mode render → integrated filmstrip inspection → version-checked edit → review-mode re-render** for this work. The integrated inspector is the current review tool; the project-specific sentence/waveform scripts are historical diagnostics, not required workflow steps.

| Operation | Authoritative reference |
| --- | --- |
| Discover the project, inspect and save timelines, render and open results | [Astrid timeline workflow skill](../astrid/packs/rendering/skill/SKILL.md) |
| Work with clip placement, trims, speed and timeline composition | [Timeline cookbook](../astrid/packs/rendering/skill/references/timeline-cookbook.md) |
| Sample rendered frames; inspect tracks, audio, speech and pinned targets | [Timeline visualization contract](../astrid/packs/rendering/executors/timeline_visualize/STAGE.md) |
| Obtain transcription through the supported capability | [Editorial skill](../astrid/packs/editorial/skill/SKILL.md) and [transcription contract](../astrid/packs/editorial/executors/transcribe/STAGE.md) |
| Find the capability for generating replacement speech or edited media | [Creative-work routing skill](../astrid/packs/_core/skill/creative-work/SKILL.md) |

During editorial feedback, render with `--review` (SDK input `review: true`) by default and retain it through subsequent revisions unless the user asks for a clean export. Give registered shots meaningful names, and verify that shot names and timecodes are readable in the actual exported video. A labeled filmstrip alone does not let someone identify a frame while watching the video. When a shot contains several reference poses, use the shot name plus timecode to distinguish them.
The default Remotion review artifact is scaled by the backend with `--scale` to
fit inside 640x360, preserving the authored aspect ratio and canvas coordinates.
Its probed profile records the emitted size and the video marks it with the
exact `Low Res Render` label at top left; shot name and timecode remain at top
right. Use an explicit profile or omit review for the existing full-resolution
behavior.

Render through the canonical Astrid timeline/runtime, then open the successful run. Generated assets must be imported and placed on that timeline before rendering; a separately assembled movie is not a substitute. Diagnostic frame extraction or audio analysis can use external tools without changing this ownership.

Start with the timeline skill and current CLI help. Save through the public CLI/SDK, render successfully, then inspect that exact run with `--view filmstrip --include-media`. Expand **Speech and audio** for waveform, measured gaps and available speech annotations; use **Show tracks** to trace placements. Inspect, edit and repeat using the same time references.

Transcription and generation are explicit operations with their own input and provider requirements. Do not assume transcription output is automatically admitted as inspector speech annotations; follow the current visualization contract and check reported coverage. If speech annotations are unavailable, waveform and video review remain usable. The [audio integration record](../docs/plans/timeline-inspector-audio-integration.md) documents implementation evidence and remaining verification limits; the skill and capability contracts above are the operational references.

## 1. Establish the idea and inspect the source

Get the replacement script, the intended visual joke or story, and the source footage. Establish whether the result needs narration over existing shots or a character visibly speaking the new words. A narration preview can establish timing before a lip-sync workflow is selected.

Inspect the source before choosing cuts. Make a contact sheet and record useful source ranges: speaking faces, reactions, gestures, object reveals and completed actions. Include the surrounding frames; a thumbnail can hide an opening hand, an early reflection or an unfinished pickup.

Keep **source time** and **edited timeline time** distinct. Record the source asset, trims, speed and placement so a review comment can be traced back to the editable clip.

### Establish the actual visual references

When the user points to another project or timeline, inspect its registered media and later shots as well as its opening and saved reference list. An empty reference list does not mean the character reference is absent. Inspect the actual images; filenames and a similar-looking generated concept are insufficient. Record the source project, timeline/shot and managed media identity, and supply the selected images as inputs to every relevant generation or edit.

Define the continuity constraints before generating: silhouette, proportions, palette, pixel size and shading style. For reflections and transformations, record each character's screen side, gaze, prop and transformation state. Generate distinct before-contact and after-contact frames from matching composition: change the touching character while preserving the other character's appearance unless directed otherwise. Check the result against the references before placing it on the timeline.

## 2. Turn the script into a spoken timing draft

Break the script into meaningful phrases and pair each with the intended picture. For example: introduction → closed hands; choice → reveal; explanation → face; closing line → completed action. Phrase boundaries and picture cuts need not coincide.

Generate or record temporary speech and listen to the complete delivery. Generate connected sentences together where possible; separately generated fragments can produce unnatural pauses or changes in delivery. If audio crosses child-shot boundaries, keep it continuous or split it at exact samples without introducing padding or dropping sound.

For replaced lines, mute the original dialogue in the preview so it does not compete with the new voice. Decide separately which original dialogue, ambience, music and effects should remain. If they are mixed together, obtaining or separating suitable background audio is an additional finishing task; replacing narration alone does not solve it.

Keep the intended wording separate from recognized text. Use transcription/alignment to estimate when phrases occur, then listen and inspect the waveform near important words. Record the audio version and timing method. Changing the recording invalidates its old alignment; moving a picture cut alone should not move the speech.

## 3. Assemble a rough cut before finishing effects

Put the source clips and temporary speech on the Astrid timeline. Use reaction shots and inserts where they suit the line. Trim or carefully retime picture to support the delivery, and let actions finish. Keep planned object replacements visible as clearly identified placeholders until timing works.

When adding an introduction, preserve the complete opening line and the rest of the approved script. When removing a reference still, adjust the remaining picture coverage without deleting the speech underneath it. If a zoom must reveal the speaking shot, end on the actual source footage and verify source-time continuity into the next clip; a generated likeness does not establish that continuity.

Render this draft early in review mode. A playable edit makes feedback such as “stay on the hand until ‘who knows’” much more precise than discussing the script alone.

## 4. Review picture, words and sound together

Use complementary views of the same exact render:

| Review question | Evidence to inspect |
| --- | --- |
| Does the sequence make visual sense? | Regularly sampled filmstrip with time labels. |
| Is there a flash or discontinuity? | Frames immediately before and after every cut. |
| Does the picture support the delivery? | Phrase start/end times, corresponding frames, and playback across the transition. |
| Is a pause too long? | Actual waveform, measured quiet intervals and listening with context. |
| Which edit controls this moment? | Frozen clip/track details, then the current canonical timeline. |

One frame per authored shot is insufficient for continuity checks. Missing transcript text is not proof of silence. A waveform shows amplitude, not whether dialogue makes sense. Still images cannot establish the rhythm of playback.

Astrid’s rendered inspector provides frame sampling, track details, measured audio and optional playback. Speech rows require admitted timing annotations; opening the view does not transcribe automatically. Use the returned pinned focus commands to inspect a specific interval.

```bash
# Replace the placeholders; run from a compatible Astrid checkout/runtime.
python3 -m astrid timelines render <timeline> --project <project> \
  --expected-version <current-version> --review --output-name <name>-review.mp4 --json

# Use the successful render ID returned above.
python3 -m astrid timelines visualize <timeline> --project <project> \
  --view filmstrip --render-run <exact-run-id> \
  --every 0.5 --include-media --json

python3 -m astrid timelines visualize <timeline> --project <project> \
  --view filmstrip --render-run <exact-run-id> \
  --sample cuts --include-media --json
```

Use `--at <seconds> --context 2 --every-frames 1` for a bounded frame-by-frame inspection. The HTML supports interactive review; the PNG sheet gives a shareable overview. `--view structure` explains arrangement across tracks. Its navigation targets are separate from rendered-inspector targets.

## 5. Run the back-and-forth as concrete editorial changes

The person directing supplies intent and judges how the edit feels. The agent translates that into an edit, checks it independently and presents evidence. Do not make the person discover every technical error.

For each note:

1. **Locate it in the shared version.** Use the exact render, quoted words and time reference. If “there” is ambiguous, inspect the nearby passage before asking for clarification.
2. **State the intended relationship.** Translate “hold it longer” into “keep the reveal until the next clause begins.” A named spoken cue is often more useful than a loosely estimated duration.
3. **Choose what changes.** Is the problem picture timing, a pause in the recording, audio placement, script wording or unfinished effects? Avoid moving all of them together by default.
4. **Make the edit through Astrid.** Read fresh timeline versions and save through the CLI/SDK. Shot boundaries may need changing; preserve continuous speech across them.
5. **Check the new render yourself.** Verify the affected moment and its neighboring cuts, then play the passage with context. Confirm that previously accepted timing remains intact.
6. **Show the result.** Open the requested video or actual contact-sheet image. Report what changed, its exact time and any remaining placeholder. Ask for creative judgment only where it is still needed.

Keep a short revision record: render ID, user note, edit made, checks performed and unresolved work. Old contact sheets and transcripts must remain labeled with their old versions.

## 6. Agent checks before presenting a revision

- **Picture:** no accidental single-frame inserts, premature reveals or inconsistent reflections; hands, props and actions progress coherently; the ending completes the intended action.
- **Speech:** correct wording, no missing or duplicated words, no unintended overlap with original dialogue, and no added gap at an audio split.
- **Synchronization:** reveals land on the intended phrase; face returns match the audible cue. Check actual sound rather than trusting an ASR timestamp alone.
- **Rhythm:** listen through pauses and watch transitions at normal speed. Measure suspicious quiet intervals with stated settings; do not remove every natural pause.
- **Regression:** compare the changed area and adjacent transitions with the previous render. For picture-only edits, decoded-audio comparison can establish that the sound stayed identical.
- **Evidence:** confirm successful rendering and verified media delivery. State which checks were visual, auditory or automated, and disclose anything not inspected.

In our session, FFmpeg measurements exposed a long closing pause, adjacent frames verified a corrected face cut, and decoded-audio hashes confirmed that the picture change preserved the narration. These checks complement creative review; they do not replace it.

## 7. Finish and hand off

Once the timing is settled, choose the final voice and test any needed lip-sync or video-editing method on a short representative shot. If the final performance changes timing, realign the speech and revisit the picture before processing the full sequence. Research provider-specific workflows at this stage; do not assume a model can perform every required edit.

Apply visual replacements across all affected shots, including reflections and interaction. Finish background sound and dialogue transitions. Re-render and repeat the same cut, phrase and waveform review on the final output.

Deliver the video, exact render identity, current script, timing evidence and a short statement of remaining work. The [rendering skill](../astrid/packs/rendering/skill/SKILL.md) documents supported Astrid operations; the [audio integration document](../docs/plans/timeline-inspector-audio-integration.md) records implementation status and verification limits.
