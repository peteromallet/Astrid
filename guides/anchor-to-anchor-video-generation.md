# Astrid: anchor-to-anchor video generation for any timeline

Use this guide to animate reference-image sections in any Astrid timeline one segment at a time through VibeComfy, select canonical results, and assemble them with the timeline's existing compositing, audio, and overlays. The concrete workflow below is the pinned Seitanism MiniMax H3 AV Extension; the queue, timing, approval, and provenance rules apply regardless of the project or timeline.

When using a different generation workflow, retain the interval, gap, approval, provenance, and assembly procedure and replace only the workflow-specific preparation and frame-grid rules in section 4 and section 6.

This is an operating procedure, not an implemented queue or a claim that generation has already succeeded. Updated 15 September 2026.

## 1. Establish scope and approval policy

Before admitting generation for a project, ask:

> Do you want to approve each generated segment before I continue, or should I run through the eligible picture intervals automatically and bring you a combined review?

Record the answer with the project/run evidence. Recommend per-segment approval for the first pass. In automatic mode, retain technical checks and stop on failures or material uncertainty; automatic generation does not imply approval of a final export.

Agree on the runtime, spending limit, and generation scope before GPU admission. Writing this guide or preparing the queue does not authorize generation.

Discover current state through Astrid, not checkout filenames:

```bash
python3 -m astrid timelines list --project <project-slug> --json
python3 -m astrid timelines show <timeline-id-or-slug> --project <project-slug> --json
```

Inspect every referenced child timeline and its current registry. Pin parent and child versions, exact managed input identities, and the approval policy. Reinspect before saving changes.

## 2. Separate references, generated picture, and overlays

Keep three concepts distinct:

- **Canonical reference:** the original managed anchor image. Keep it available and unchanged even when video replaces its on-screen hold.
- **Canonical playback selection:** the currently selected still or accepted generated-video take for a particular picture interval.
- **Overlay composition:** existing compositor layers, graphics, footage, framing, and narration. These remain separate from H3's picture generation.

Use the clean reference image as generation input, not a rendered screenshot containing overlays. Preserve the authored crop and placement; avoid baking a transform into the video and then applying it again in the timeline.

The canonical switch is an editorial contract: select the still or a specific managed video take by changing the owning picture clip through the supported timeline API. This guide does **not** assume that a dedicated `canonical_switch` field or UI already exists. Never invent a runtime field or maintain a competing authoritative JSON database.

Keep both media objects registered. Record the original clip configuration, selected take digest/run, selection decision, and resulting timeline version in managed project/run evidence. Switching back restores the original still clip without deleting generated attempts. The saved timeline determines playback; a recent successful generation alone does not make a take canonical.

## 3. Inventory picture intervals and editorial gaps

Read the chosen timeline and its child timelines from the runtime. Build candidate intervals from actual picture coverage and image changes, not merely from shot names or narration boundaries. A single shot may contain several picture intervals, and a repeated image does not require a transition.

For each eligible interval, record:

- its exact start and end on the owning timeline;
- the clean managed start and end anchors, if present;
- whether it is an independent start, a continuation from the previous accepted take, or a cut/new chain;
- overlays, preserved footage, audio, or compositing that must remain outside the generated picture; and
- any interval that must remain still, be held, or receive a separately authored anchor.

Do not infer continuous coverage from asset names alone. Do not force a morph between unrelated compositions. If a section has no valid endpoint or anchor, stop that chain and use an explicit hold, cut, or newly authored reference. A black or compositor-only interval is not automatically an end-frame target.

### Duration is determined by the gap

The editorial gap between the interval's start and end boundaries is the target **usable new-picture duration**. In other words, the generated picture that replaces that interval must fill the gap exactly, subject to the master timeline's frame grid. Record that gap before choosing the H3 frame count.

The raw H3 output is not necessarily the same length as the gap: it includes retained context/overlap needed for continuity. Choose a supported full generation length containing the required context plus enough new material, then assemble only the usable new-picture portion into the gap. Never treat context as additional editorial duration, and never silently stretch or trim an endpoint to hide a frame-grid mismatch. If the supported frame grid cannot produce an acceptable conform, split the interval or regenerate with a better target.

For the current Astrid Intro inventory and its Remotion-only exception, see the [worked example](astrid-intro-anchor-video-generation.md). That example is evidence for one project at one inspection time, not a rule for other timelines.

## 4. Use the selected Seitanism workflow

Start from the corrected imported bundle:

- [Editable workflow](../workflows/seitanism_h3_av_extension_fixed/workflow.py)
- [Companion JSON](../workflows/seitanism_h3_av_extension_fixed/workflow.vibe.json)
- [Original source](../workflows/seitanism_h3_av_extension_fixed/source.json)
- [Import and reproducibility audit](../workflows/seitanism_h3_import_audit.md)

It uses `minimax_h3_ref2va_pruned_int8_convrot.safetensors`, the enabled `minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` LoRA at 0.95, and **8 effective sampling steps**. Keep these as the baseline rather than silently swapping workflows or models.

**Preparation is still required:** this imported AV-extension graph is not already an endpoint-controlled production queue. Follow the VibeComfy edit and run skills to create a separate candidate derived from it, wire custom end-keyframe conditioning, resolve custom nodes/models, and validate against the actual runtime. Preserve the imported baseline and its source provenance.

For the first segment, guide from anchor A toward anchor B. For a same-scene continuation, carry the previous selected clip's tail and guide toward the next anchor. Begin with 39 frames of context. Use compatible 39/90/141/... context lengths only when longer context is warranted.

Seitanism's Custom Keyframes provides soft image conditioning; Custom Keyframes (Masked) protects encoded latent steps. Neither guarantees identical decoded endpoint pixels. If combining preserved video context with masked anchors, apply the context preparation first, then non-overlapping masked anchors. Verify the exact node contract and output assembly for the edited graph.

Reference: [Seitanism keyframes and inserts guide](https://github.com/seitanism/ComfyUI-H3-Motion-Context-MultiRef/blob/main/KEYFRAMES_AND_INSERTS.md). Source workflow revision investigated: `0a9619766d40c83dbfa313172601fe8f364e6589`; imported pack pin: `361624fb406b63eb6694442eac6c895fc1533a70`. Preserve exact resolved runtime pins as well as source-reported versions: the latter contain conflicts and do not alone define a reproducible environment.

The import passed structural checks, not a GPU generation test. Missing custom-node schemas/dependencies must be resolved before claiming execution readiness.

## 5. Prepare the segment queue

### Store generation prompts on the owning shot

Before generating each section, save its actual H3 prompt in the registered shot's canonical `prompt` text binding. The workflow consumes that text; it must not be the only place the prompt is saved. Keep prompts separate from `voiceover_script`.

```bash
python3 -m astrid timelines shots text list --project <project-slug> \
  --kind prompt --shot <shot-id> --json
python3 -m astrid timelines shots text set <shot-id> --project <project-slug> \
  --kind prompt --slot h3_segment_01 --text-file <reviewed-prompt.txt> \
  --expected-head 0 --json
```

Use a stable lowercase slot per segment, such as `h3_segment_01`. A shot with several picture intervals needs several slots, not one overwritten prompt. For an existing binding, use its observed current head instead of zero. Preserve previous revisions; pin the exact binding identity/head and text digest in each generation's evidence. Changing a prompt must not relabel an old generated take as if it used the new revision.

Draft prompts only after inspecting that interval's actual anchors and the predecessor's motion. Store the incoming action followed by the intended transition, not just the narration or an asset filename. Mark draft versus reviewed status in run/project evidence. Do not populate still-only or compositor-only sections with invented H3 prompts.

For each segment, retain these fields in supported managed run inputs/evidence (these are requirements, not a new runtime schema):

- Stable segment identity, owning timeline/clip, observed versions, and chain identity.
- Start/end timeline times and clean managed anchor identities.
- Start mode: independent anchors or continuation; exact predecessor output/context identity.
- Target new-picture duration, context length, generated frame count, overlap removal, and conform plan.
- Workflow revision/hash, prompt, seed, sampler settings, model identities, and resolved runtime/node versions.
- Attempt/run identity, output digest, validation evidence, approval decision, and playback selection.

Run sequentially by default, as requested:

1. Resolve the segment's inputs from pinned anchors and its selected predecessor.
2. Generate through the supported VibeComfy execution route and collect real output evidence.
3. Publish/register the output through Astrid's managed media boundary before using it in a timeline.
4. Validate and present a review candidate.
5. If per-segment approval is enabled, wait for explicit approval or revision instructions.
6. Select the accepted take through the canonical timeline save path, then admit the next dependent segment.

Do not start a continuation from a take still awaiting approval. In automatic mode, technically accepted takes can feed the chain under the recorded policy; label them as automatically selected, not user-approved.

Use the workspace runtime's supported task/dependency mechanism for durable execution. Do not implement a pack-local scheduler or pretend an in-memory loop is a durable queue. If a required approval/dependency feature is unavailable, perform the sequence explicitly through supported admissions and report that limitation.

Retries create new attempts and preserve old outputs. A failed job blocks its descendants; it does not discard completed work. Changing an upstream take makes downstream context-dependent results stale: regenerate or explicitly review them before reuse. Resume from verified managed outputs, not the latest filename or task status alone.

## 6. Preserve timing and audio

Read the chosen timeline's editorial frame rate from the runtime. This H3 workflow operates at 24 fps and full generation lengths of `5 + 17*k` frames; those are generation constraints, not assumptions about the timeline.

Keep separate clocks for generated frames, retained overlap, and final timeline duration. Context is overlap, not extra footage added to the edit. Choose a supported full target length that includes the necessary context and new material; use the graph's actual overlap outputs/assembly policy rather than blindly subtracting a constant from every file.

Extract subsequent context from the native 24-fps generation before editorial retiming. Conform the usable new-picture interval to its exact authored duration, preserving the endpoint. Convert to the 30-fps timeline without moving narration or accumulating rounding drift. Record any retiming; if it noticeably distorts motion, regenerate with a better duration or split the interval instead.

Do not simply trim off an endpoint to make a clip fit. At shared anchors, check for duplicate-frame holds, jumps, or a slowdown. Quantize placement consistently to the master timeline's frame grid and check the final boundaries.

Preserve the timeline's existing voiceover and soundtrack. Do not mix H3-generated audio into the final edit by default; mute generated picture clips in assembly unless the project explicitly calls for the generated audio. Audio used internally by the AV workflow is distinct from the final soundtrack.

## 7. Review and switch each segment

Technical acceptance requires a decodable video, expected dimensions/frame count/duration, valid managed identity, and no missing or unexpected black frames. Also inspect motion, character/style consistency, text deformation, endpoint likeness, and the join to the preceding clip. A successful task status is insufficient.

For user approval, show a labeled video with the segment name/time range and enough neighboring picture to judge the seam. Prefer an in-context preview with the existing overlays and narration. Keep candidates separate from canonical playback until accepted; do not replace the canonical timeline merely to obtain a preview.

On acceptance, freshly read the owning child timeline, replace only the intended picture interval, retain audio/other clips and registry entries, and save the complete document with its observed `expected_version`. Handle version conflicts by rereading and reconciling, never overwriting concurrent edits. Preserve parent-level effects spanning several shots.

The selection must remain reversible to the original still. Do not delete anchors or unselected takes as part of promotion.

## 8. Assemble and verify the whole video

Once all intended picture intervals are selected, render the existing parent timeline with its original compositor. Do not flatten generated segments into a replacement movie that loses overlays, narration timing, or compositor-only sections.

```bash
python3 -m astrid timelines render <timeline-id-or-slug> --project <project-slug> \
  --expected-version <fresh-parent-version> --review \
  --output-name <project>-animated-review.mp4 --json
python3 -m astrid runs open <exact-successful-render-run-id> --project <project-slug>
```

Use the rendering skill and current CLI help for execution. Review mode should visibly label shots/timecodes; its default low-resolution export is for feedback, not the final master.

Check every generated seam, every handoff into/out of still or compositor-only sections, overlay placement, unchanged narration timing, overall duration, and the final ending. Deliver the exact managed render/run and identify any intervals still using their original stills. A clean final export follows the user's acceptance; generation completion alone is not final editorial approval.

## Thread-informed practices

The following were found in untruncated messages from Seitanism's thread on 15 September 2026. They are community guidance, not GPU validation of a particular project.

- **Prompt the incoming motion before the new action.** The first context window carries existing motion; describe its continuation, then its change toward the next anchor. Avoid demanding an immediate reversal at the seam. For example: “The camera continues its slow rightward move, eases to a stop, then tracks toward the next composition.” [3 September advice](https://discord.com/channels/1076117621407223829/1533923760984555875/1545199805058252820).
- **Wire keyframes into every extension that needs an endpoint.** Starter keyframes do not automatically control later samplers. Verify each extension's conditioning path after the custom-keyframe node. [Author clarification](https://discord.com/channels/1076117621407223829/1533923760984555875/1538664864002609243).
- **Prove the base chain before adding latent upscaling.** A community report traced combined upscale/keyframe failures to the conditioning supplied to the sampler. Treat refinement as its own tested stage, not an arbitrary upscaler spliced into the base graph. [31 August report](https://discord.com/channels/1076117621407223829/1533923760984555875/1544116827205144717).

## Upscaling the generated picture

Keep the native 24-fps output as the continuation source. Upscaling is a derived finishing take; do not silently substitute it into subsequent context inputs.

For pixel-art or deliberately hard-edged artwork, first compare the native output with an integer nearest-neighbor enlargement. This is the conservative baseline: it does not invent texture or smooth the pixel edges. For other artwork, compare an appropriate high-quality scaler as well. Choose a factor that fits the intended presentation; do not assume every source resolution scales exactly to the timeline's master dimensions. Review framing and any final non-integer conform explicitly.

If that is too coarse, test the animation-video model `realesr-animevideov3` from [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN), optionally through [Video2X](https://github.com/k4yt3x/video2x). Treat it as a candidate, not a proven improvement for our artwork: inspect palette changes, invented detail, thin-line instability, and temporal shimmer. Keep frame interpolation disabled during this comparison; conform frame rate separately under the timing policy above.

Pilot on a short moving interval and both sides of a segment seam. Compare native, nearest-neighbor, and learned upscale at the final display size. Record tool/model versions and exact settings. Keep original and derived media identities, and require the selected approval policy before switching playback to the upscale.

Upscale only the clean generated picture. Render compositor text, graphics, and framing at master resolution afterwards; retain the existing audio. Do not upscale a flattened low-resolution review render containing labels and overlays.

H3 two-pass latent upscaling is a separate graph change, not the default finishing step. The thread describes stage-matched context (pass 1 to pass 1, pass 2 to pass 2); wiring keyframes into a refinement pass also needs deliberate conditioning handling. Test this separately if the conservative finishing routes are inadequate. Do not mix a different latent-upscaler implementation into the pinned workflow without inspecting its own model, conditioning, memory, and continuity requirements.

## Execution references

- [Astrid timeline editing/rendering](../astrid/packs/rendering/skill/SKILL.md)
- Use the installed `edit-comfy-workflow` skill for endpoint wiring and `run-comfy-workflow` for runtime execution.
- Use Astrid's creative-work route and the selected capability's current contract for managed VibeComfy invocation/publication. Do not invent CLI verbs or write directly into runtime storage.
