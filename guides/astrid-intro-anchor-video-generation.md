# Astrid Intro: anchor-to-anchor video generation

Use this guide to animate the existing reference-image sections one segment at a time through VibeComfy, select canonical results, and assemble them with the existing Remotion layers and narration.

This is an operating procedure, not an implemented queue or a claim that generation has already succeeded. Updated 15 September 2026.

## 1. Establish scope and approval policy

Before admitting generation, ask:

> Do you want to approve each generated segment before I continue, or should I run through the image-backed sections automatically and bring you a combined review?

Record the answer with the project/run evidence. Recommend per-segment approval for the first pass. In automatic mode, retain technical checks and stop on failures or material uncertainty; automatic generation does not imply approval of a final export.

Agree on the runtime, spending limit, and generation scope before GPU admission. Writing this guide or preparing the queue does not authorize generation.

Discover current state through Astrid, not checkout filenames:

```bash
python3 -m astrid timelines list --project astrid-intro --json
python3 -m astrid timelines show main-final-blackend2 --project astrid-intro --json
```

Inspect every referenced child timeline and its current registry. Pin parent and child versions, exact managed input identities, and the approval policy. Reinspect before saving changes.

## 2. Separate references, generated picture, and overlays

Keep three concepts distinct:

- **Canonical reference:** the original managed anchor image. Keep it available and unchanged even when video replaces its on-screen hold.
- **Canonical playback selection:** the currently selected still or accepted generated-video take for a particular picture interval.
- **Overlay composition:** existing Remotion elements, terminal footage, framing, and narration. These remain separate from H3's picture generation.

Use the clean reference image as generation input, not a rendered screenshot containing overlays. Preserve the authored crop and placement; avoid baking a transform into the video and then applying it again in the timeline.

The canonical switch is an editorial contract: select the still or a specific managed video take by changing the owning picture clip through the supported timeline API. This guide does **not** assume that a dedicated `canonical_switch` field or UI already exists. Never invent a runtime field or maintain a competing authoritative JSON database.

Keep both media objects registered. Record the original clip configuration, selected take digest/run, selection decision, and resulting timeline version in managed project/run evidence. Switching back restores the original still clip without deleting generated attempts. The saved timeline determines playback; a recent successful generation alone does not make a take canonical.

## 3. Inventory the real picture intervals

The inspected timeline had this structure; reread it before execution because timings and assets can change:

| Timeline interval | Picture policy |
| --- | --- |
| 0–27.892 s | Image-backed opening; candidate for animation |
| 27.892–38.280 s | Background image plus terminal content; inspect carefully before animating behind the terminal |
| 38.280–64.592 s | No child-shot background anchor wired in; retain Remotion/process sequence and terminal layers |
| 64.592–117.072 s | Image-backed ending sections, with overlays where authored |

Do not treat the black base as an end-frame target. End the opening generation chain at the editorial boundary and start a new chain when image-backed picture resumes. Creating backgrounds for the Remotion-only interval is a separate creative decision requiring new anchors.

Build intervals from actual image changes, not merely shot or narration boundaries:

- The image at 7.076 s is reused at 10.264 s; that does not require a transition.
- The guidance image at 64.592 s continues into the next shot.
- That next shot changes image internally at 74.652 s (72.492 + 2.160), so one shot can contain multiple picture intervals.

Check all source clip bounds and actual rendered coverage. Do not infer continuous coverage solely from a list of asset names. Do not force a morph between unrelated compositions: mark those boundaries as cuts/new chains. At the end of a chain with no next anchor, use an explicitly chosen hold/end composition rather than borrowing an anchor from across a gap.

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
python3 -m astrid timelines shots text list --project astrid-intro \
  --kind prompt --shot <shot-id> --json
python3 -m astrid timelines shots text set <shot-id> --project astrid-intro \
  --kind prompt --slot h3_segment_01 --text-file <reviewed-prompt.txt> \
  --expected-head 0 --json
```

Use a stable lowercase slot per segment, such as `h3_segment_01`. A shot with several picture intervals needs several slots, not one overwritten prompt. For an existing binding, use its observed current head instead of zero. Preserve previous revisions; pin the exact binding identity/head and text digest in each generation's evidence. Changing a prompt must not relabel an old generated take as if it used the new revision.

Draft prompts only after inspecting that interval's actual anchors and the predecessor's motion. Store the incoming action followed by the intended transition, not just the narration or an asset filename. Mark draft versus reviewed status in run/project evidence. Do not populate Remotion-only sections with invented H3 prompts. At inspection on 15 September, this project's prompt-binding list was empty; this guide does not claim prompts have already been authored.

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

The inspected intro is 30 fps. This H3 workflow operates at 24 fps and full generation lengths of `5 + 17*k` frames.

Keep separate clocks for generated frames, retained overlap, and final timeline duration. Context is overlap, not extra footage added to the edit. Choose a supported full target length that includes the necessary context and new material; use the graph's actual overlap outputs/assembly policy rather than blindly subtracting a constant from every file.

Extract subsequent context from the native 24-fps generation before editorial retiming. Conform the usable new-picture interval to its exact authored duration, preserving the endpoint. Convert to the 30-fps timeline without moving narration or accumulating rounding drift. Record any retiming; if it noticeably distorts motion, regenerate with a better duration or split the interval instead.

Do not simply trim off an endpoint to make a clip fit. At shared anchors, check for duplicate-frame holds, jumps, or a slowdown. Quantize placement consistently to the master timeline's frame grid and check the final boundaries.

Preserve the existing voiceover and soundtrack. Do not mix H3-generated audio into the intro by default; mute generated picture clips in assembly. Audio used internally by the AV workflow is distinct from the final soundtrack.

## 7. Review and switch each segment

Technical acceptance requires a decodable video, expected dimensions/frame count/duration, valid managed identity, and no missing or unexpected black frames. Also inspect motion, character/style consistency, text deformation, endpoint likeness, and the join to the preceding clip. A successful task status is insufficient.

For user approval, show a labeled video with the segment name/time range and enough neighboring picture to judge the seam. Prefer an in-context preview with the existing overlays and narration. Keep candidates separate from canonical playback until accepted; do not replace the canonical timeline merely to obtain a preview.

On acceptance, freshly read the owning child timeline, replace only the intended picture interval, retain audio/other clips and registry entries, and save the complete document with its observed `expected_version`. Handle version conflicts by rereading and reconciling, never overwriting concurrent edits. Preserve parent-level effects spanning several shots.

The selection must remain reversible to the original still. Do not delete anchors or unselected takes as part of promotion.

## 8. Assemble and verify the whole video

Once all intended picture intervals are selected, render the existing parent timeline with the original Remotion composition. Do not flatten generated segments into a replacement movie that loses overlays, narration timing, or the Remotion-only middle section.

```bash
python3 -m astrid timelines render main-final-blackend2 --project astrid-intro \
  --expected-version <fresh-parent-version> --review \
  --output-name astrid-intro-animated-review.mp4 --json
python3 -m astrid runs open <exact-successful-render-run-id> --project astrid-intro
```

Use the rendering skill and current CLI help for execution. Review mode should visibly label shots/timecodes; its default low-resolution export is for feedback, not the final master.

Check every generated seam, the handoff into/out of the Remotion-only section, overlay placement, unchanged narration timing, overall duration, and the final ending. Deliver the exact managed render/run and identify any intervals still using their original stills. A clean final export follows the user's acceptance; generation completion alone is not final editorial approval.

## Thread-informed practices

The following were found in untruncated messages from Seitanism's thread on 15 September 2026. They are community guidance, not GPU validation of this particular intro.

- **Prompt the incoming motion before the new action.** The first context window carries existing motion; describe its continuation, then its change toward the next anchor. Avoid demanding an immediate reversal at the seam. For example: “The camera continues its slow rightward move, eases to a stop, then tracks toward the next composition.” [3 September advice](https://discord.com/channels/1076117621407223829/1533923760984555875/1545199805058252820).
- **Wire keyframes into every extension that needs an endpoint.** Starter keyframes do not automatically control later samplers. Verify each extension's conditioning path after the custom-keyframe node. [Author clarification](https://discord.com/channels/1076117621407223829/1533923760984555875/1538664864002609243).
- **Prove the base chain before adding latent upscaling.** A community report traced combined upscale/keyframe failures to the conditioning supplied to the sampler. Treat refinement as its own tested stage, not an arbitrary upscaler spliced into the base graph. [31 August report](https://discord.com/channels/1076117621407223829/1533923760984555875/1544116827205144717).

## Upscaling the generated picture

Keep the native 24-fps output as the continuation source. Upscaling is a derived finishing take; do not silently substitute it into subsequent context inputs.

For this pixel-art intro, first compare the native output with an integer nearest-neighbor enlargement. This is the conservative baseline: it does not invent texture or smooth the pixel edges. Choose an integer factor that fits the intended presentation; do not assume every source resolution scales exactly to 1920×1080. Review framing and any final non-integer conform explicitly.

If that is too coarse, test the animation-video model `realesr-animevideov3` from [Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN), optionally through [Video2X](https://github.com/k4yt3x/video2x). Treat it as a candidate, not a proven improvement for our artwork: inspect palette changes, invented detail, thin-line instability, and temporal shimmer. Keep frame interpolation disabled during this comparison; conform frame rate separately under the timing policy above.

Pilot on a short moving interval and both sides of a segment seam. Compare native, nearest-neighbor, and learned upscale at the final display size. Record tool/model versions and exact settings. Keep original and derived media identities, and require the selected approval policy before switching playback to the upscale.

Upscale only the clean generated picture. Render Remotion text, graphics, and framing at master resolution afterwards; retain the existing audio. Do not upscale a flattened low-resolution review render containing labels and overlays.

H3 two-pass latent upscaling is a separate graph change, not the default finishing step. The thread describes stage-matched context (pass 1 to pass 1, pass 2 to pass 2); wiring keyframes into a refinement pass also needs deliberate conditioning handling. Test this separately if the conservative finishing routes are inadequate. Do not mix a different latent-upscaler implementation into the pinned workflow without inspecting its own model, conditioning, memory, and continuity requirements.

## Execution references

- [Astrid timeline editing/rendering](../astrid/packs/rendering/skill/SKILL.md)
- Use the installed `edit-comfy-workflow` skill for endpoint wiring and `run-comfy-workflow` for runtime execution.
- Use Astrid's creative-work route and the selected capability's current contract for managed VibeComfy invocation/publication. Do not invent CLI verbs or write directly into runtime storage.
