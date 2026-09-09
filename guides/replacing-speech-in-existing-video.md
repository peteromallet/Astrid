# Replacing speech in an existing video

A reusable workflow for an agent working with someone directing an edit: use existing footage, write new dialogue, assemble a timing preview, review it together, then finish speech and visual effects. Based on the [Matrix editing session](matrix-minkhole-workflow.md); the final lip-sync and moving-object replacement steps are still future work in that example.

## Current supported workflow and references

### ComfyUI workflow selected for the next experiment

The starting graph identified in our earlier research was **LanPaint’s MiniMax H3 audio/video inpainting workflow**: [`MiniMax_H3_AV_EncodeDecode_Inpaint.json`](https://github.com/scraed/LanPaint/blob/master/example_workflows/MiniMax_H3_AV_EncodeDecode_Inpaint.json). This choice is recorded in the original [edit plan, “Later generation passes”](../runs/matrix-minkhole/planning/edit-plan.md#later-generation-passes). That document’s old script and timings are superseded; this is its workflow reference.

The planned experiment is to take one short source passage with its original audio, preserve adjacent original voice as context, and replace the selected dialogue interval while permitting the required face/mouth changes. Check the generated wording, voice continuity, lip synchronization and surrounding frames before extending it to other passages. The original context audio is an input to that experiment; the temporary narration is the timing reference. Choose the retained output interval after reviewing the result, rather than assuming all context belongs in the final edit.

For the reusable source provenance → Python candidate → inspection/edit → validation path, see the [VibeComfy workflow onboarding guide](</Users/peteromalley/Documents/reigh-workspace/vibecomfy/.otto/worktrees/canonical-workflow-source-20260903/docs/guides/workflow-onboarding.md>).

This graph **has not yet been validated or run on our footage/runtime**. Inspect its actual inputs, nodes and model requirements before execution; these are planned steps, not a proven recipe. Treat object replacement and glasses reflections as a separate tracked-mask/compositing pass unless testing demonstrates a suitable combined workflow.

### Python review candidate

The [editable H3 Python builder](/Users/peteromalley/Documents/reigh-workspace/vibecomfy/.otto/worktrees/canonical-workflow-source-20260903/comfy-inspection/MiniMax_H3_AV_EncodeDecode_Inpaint.py) is available in the selected VibeComfy worktree. Its `build()` function exposes the prompt, model, source video, video-mask keyframes, audio intervals, duration, seed and step controls. The defaults still describe the upstream demo; select our source passage and replacement dialogue before generation.

This is a review candidate: native subgraph expansion and builder loading have been checked, but current H3 core-schema coverage and runtime requirements remain unresolved. Calling `build()` constructs the graph; it does not generate video. See [inspection and verification](../runs/matrix-minkhole/planning/comfy-inspection/verification.md) for evidence.

### Astrid assembly and review

Use **Astrid timeline editing → render → integrated filmstrip inspection → version-checked edit → re-render** for this work. The integrated inspector is the current review tool; the project-specific sentence/waveform scripts are historical diagnostics, not required workflow steps.

| Operation | Authoritative reference |
| --- | --- |
| Discover the project, inspect and save timelines, render and open results | [Astrid timeline workflow skill](../astrid/packs/rendering/skill/SKILL.md) |
| Work with clip placement, trims, speed and timeline composition | [Timeline cookbook](../astrid/packs/rendering/skill/references/timeline-cookbook.md) |
| Sample rendered frames; inspect tracks, audio, speech and pinned targets | [Timeline visualization contract](../astrid/packs/rendering/executors/timeline_visualize/STAGE.md) |
| Obtain transcription through the supported capability | [Editorial skill](../astrid/packs/editorial/skill/SKILL.md) and [transcription contract](../astrid/packs/editorial/executors/transcribe/STAGE.md) |
| Find the capability for generating replacement speech or edited media | [Creative-work routing skill](../astrid/packs/_core/skill/creative-work/SKILL.md) |

Start with the timeline skill and current CLI help. Save through the public CLI/SDK, render successfully, then inspect that exact run with `--view filmstrip --include-media`. Expand **Speech and audio** for waveform, measured gaps and available speech annotations; use **Show tracks** to trace placements. Inspect, edit and repeat using the same time references.

Transcription and generation are explicit operations with their own input and provider requirements. Do not assume transcription output is automatically admitted as inspector speech annotations; follow the current visualization contract and check reported coverage. If speech annotations are unavailable, waveform and video review remain usable. The [audio integration record](../docs/plans/timeline-inspector-audio-integration.md) documents implementation evidence and remaining verification limits; the skill and capability contracts above are the operational references.

## 1. Establish the idea and inspect the source

Get the replacement script, the intended visual joke or story, and the source footage. Establish whether the result needs narration over existing shots or a character visibly speaking the new words. A narration preview can establish timing before a lip-sync workflow is selected.

Inspect the source before choosing cuts. Make a contact sheet and record useful source ranges: speaking faces, reactions, gestures, object reveals and completed actions. Include the surrounding frames; a thumbnail can hide an opening hand, an early reflection or an unfinished pickup.

Keep **source time** and **edited timeline time** distinct. Record the source asset, trims, speed and placement so a review comment can be traced back to the editable clip.

## 2. Turn the script into a spoken timing draft

Break the script into meaningful phrases and pair each with the intended picture. For example: introduction → closed hands; choice → reveal; explanation → face; closing line → completed action. Phrase boundaries and picture cuts need not coincide.

Generate or record temporary speech and listen to the complete delivery. Generate connected sentences together where possible; separately generated fragments can produce unnatural pauses or changes in delivery. If audio crosses child-shot boundaries, keep it continuous or split it at exact samples without introducing padding or dropping sound.

For replaced lines, mute the original dialogue in the preview so it does not compete with the new voice. Decide separately which original dialogue, ambience, music and effects should remain. If they are mixed together, obtaining or separating suitable background audio is an additional finishing task; replacing narration alone does not solve it.

Keep the intended wording separate from recognized text. Use transcription/alignment to estimate when phrases occur, then listen and inspect the waveform near important words. Record the audio version and timing method. Changing the recording invalidates its old alignment; moving a picture cut alone should not move the speech.

## 3. Assemble a rough cut before finishing effects

Put the source clips and temporary speech on the Astrid timeline. Use reaction shots and inserts where they suit the line. Trim or carefully retime picture to support the delivery, and let actions finish. Keep planned object replacements visible as clearly identified placeholders until timing works.

Render this draft early. A playable edit makes feedback such as “stay on the hand until ‘who knows’” much more precise than discussing the script alone.

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
