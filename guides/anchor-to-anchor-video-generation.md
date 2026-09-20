# Astrid: anchor-to-anchor video generation for any timeline

Use this guide to animate reference-image sections in any Astrid timeline one segment at a time through VibeComfy, select canonical results, and assemble them with the timeline's existing compositing, audio, and overlays. The concrete workflow below is the pinned Seitanism MiniMax H3 AV Extension; the queue, timing, approval, and provenance rules apply regardless of the project or timeline.

When using a different generation workflow, retain the interval, gap, approval, provenance, and assembly procedure and replace only the workflow-specific preparation and frame-grid rules in section 4 and section 6.

This is an operating procedure, not a claim that every project has already
succeeded. The worked Astrid Intro execution produced a technically successful
render, but subsequent frame comparison exposed destructive cleanup and an
assembly-induced camera drift. Its earlier visual pass is superseded; do not
copy those repairs. Updated 18 September 2026.

## Non-negotiable: fix the layer that is wrong

**Do not rescue a failed generation with cosmetic transformations.** Wrong
backgrounds, unwanted camera moves, changed anatomy, missing detail, or broken
lettering are rejection reasons. Revise the generation inputs/workflow and
regenerate within the authorized budget. If that cannot produce an acceptable
take, retain the original still or present a clearly labelled failed candidate
and ask for direction. Do not quietly widen the finishing scope.

| Where the defect first appears | Required response |
| --- | --- |
| Anchor itself | Correct or replace the anchor with the user's direction before generation. |
| Raw generated frames | Reject the take; change generation, not downstream pixels. |
| Finished derivative only | Remove the destructive processing and re-review the raw take. |
| Timeline composite only | Inspect crop, scale, placement, and double-applied transforms; fix the composition without inventing camera movement. |

Permitted technical conform includes removing measured context, mapping to the
editorial frame grid, encoding, and reviewed resolution conversion. It must not
conceal a content failure. Creative pans, crops, recoloring, masking, heading
replacement, or stabilization require an explicitly intended editorial purpose
and before/after approval—not merely a desire to make a bad take usable.

Before selecting any take, compare **anchor → raw → derivative → composite** at
the same content moment, including small identity details at native size. Check
the first usable frame after context removal, the endpoint, and every seam in
motion. A successful decode or attractive contact sheet is not visual acceptance.

### Check repeated signs before generation

When neighboring anchors repeat a heading, frame, or label, compare its pixel
position and dimensions before treating it as stationary. In the Astrid Intro
v04/v05 anchors, `TWO IDEAS` moves from roughly y=107 to y=97, and the two
label frames move upward about 9–11 pixels with slight width differences.
The old `finish_anchor_matte.sh` replaced the top 350 pixels and crossfaded
these mismatched anchor crops over native frames 120–168. The selected s02
derivative consequently shows doubled/soft sign edges around 10.5–12.5 seconds
of the parent timeline while the separately processed lower content remains
stable. This is baked-in finishing behavior, not a CUDA fault or a parent
timeline heading animation.

At native frame 144, the historical raw s02 has a single sharp heading over
the unwanted document background; its selected processed derivative has
vertically doubled heading edges. The root directly inspected both. The raw
source already moves the heading toward the offset endpoint, but the visible
ghosting is introduced by the replacement/crossfade.

Do not recreate that header-only repair. Establish whether the repeated sign
is intended to remain fixed, resolve inconsistent anchor geometry with the
user's direction, and then regenerate and review the raw transition. Matching
anchor geometry does not by itself prove the generated typography stays sharp.

For GPU setup, operation, custody, and verified teardown, use the separate
[RunPod lifecycle guide](runpod-lifecycle.md). Documentation work alone never
authorizes launching a paid machine.

## Operator-first H3 admission gates

Before staging the creative chain, apply the lifecycle guide's H3 preflight as
a hard gate:

- Resolve a provider host compatible with the pinned CUDA 13 Torch/
  `comfy-kitchen`/ComfyUI backend. Use RunPod's real
  `allowedCudaVersions` (or `minCudaVersion`) placement input; an image tag is
  not a host-driver guarantee. The current lifecycle 0.3 launcher does not
  expose that input, so use only an authorized direct-provider fallback or a
  tested substrate extension—never an invented CLI flag. The current
  CUDA-filtered relaunch and its still-pending driver verification are tracked
  in the [CUDA 13 relaunch record](astrid-intro-cuda13-relaunch-20260918.md).
- Verify the live driver, `torch.version.cuda`, kitchen revision, and active
  attention/VAE backend before admitting generation. An unexpected fallback is
  a stop condition. If the host is wrong, reprovision; do not begin a chain of
  CUDA/math patches to make an incompatible machine appear canonical.
- Run one exact **1920x1088, 260-native-frame, one-step** production-shape
  diagnostic through the real graph and decode it. This proves only backend/
  capacity readiness; it is not visual acceptance and does not replace the
  raw visual/seam review required for every segment. A matched CUDA stack can
  still have an independent memory-capacity failure.
- Confirm the continuation graph retains **39 native context frames** from the
  raw latent edge. Never decode/re-encode an MP4 as descendant context. Record
  the context edge and first unprotected frames before queuing the next
  segment.

## 1. Establish scope and approval policy

Before admitting generation for a project, establish the review policy. If the
user has already requested unattended end-to-end execution, record that as
automatic mode and proceed within the authorized scope. Otherwise ask:

> Do you want to approve each generated segment before I continue, or should I run through the eligible picture intervals automatically and bring you a combined review?

Record the answer with the project/run evidence. Recommend per-segment approval for the first pass. In automatic mode, retain technical checks and stop on failures or material uncertainty; automatic generation does not imply approval of a final export.

Establish the authorized runtime and generation scope before GPU admission,
and honor any supplied spending limit. An explicit request to use an existing
pod for the scoped generation authorizes that work; it does not require another
approval round. Writing this guide or preparing a queue alone does not authorize
generation.

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

For the current Astrid Intro chain, use the pinned Seitanism MiniMax H3 AV
workflow and its direct latent continuation graph:

- [Canonical imported workflow](../workflows/seitanism_h3_av_extension_verified/workflow.py)
- [Canonical source JSON](../workflows/seitanism_h3_av_extension_verified/source.json)
- [Astrid Intro chain workflow](../workflows/astrid_intro_h3_anchor_chain/workflow.py)
- [Astrid Intro chain notes](../workflows/astrid_intro_h3_anchor_chain/README.md)

The measured Astrid Intro target is **1920x1088 at 24 fps**. The historical
five-stage chain used 175, 260, 175, 175, and 294 frames. The 18 September
revision instead plans six stages: **175, 260, 175, 175, 209, 124**, separating
the typing hold from an explicit physical run-away exit to black. These are
project-specific frame contracts, not universal workflow defaults; see the
[revision execution record](astrid-intro-regeneration-20260918.md) for acceptance
status and the exact timeline conform. Each continuation
uses a direct 39-frame edge from the preceding sampler's generated nested
audio/video latent. This is not equivalent to decoding an MP4 and re-encoding
it as context; the raw latent chain must remain available for descendants.

The starter injects both clean anchors in one `MiniMaxH3CustomKeyframes` call at
positions 1 and 175. Each continuation injects its destination image as an
endpoint constraint at its final one-based target frame. An additional
`ref_images.ref_image_0` appearance reference is a separate conditioning role:
it may be changed for motion/style experiments without changing the endpoint
keyframe. The output picture is silent for the edit; H3's internal audio latent
is not the project's final soundtrack.

The retry-3 experiment is a failure lesson, not a finishing recipe. Its extra
destination appearance reference improved running motion but introduced a gray
document collage. Broad gray removal damaged valid eye and line details; heading
replacement also cropped rising heads in an earlier pass. The terminal take's
unwanted zoom was treated with HSV extraction and bounding-box stabilization.
These are rejected repair strategies for this workflow: regenerate defective
content instead. Preserve the raw outputs and historical derivative lineage as
evidence, not as recommended defaults. Never feed a finished/decoded MP4 back
into the native AV context path.

To reproduce the clip-11 length, set `ASTRID_H3_EXTENSION_SECONDS=3`. For the
full D14-sized extension, set it to `5`, which quantizes to 124 H3 target
frames. When running remotely, stage the source video, source-tail image, and
end-frame image in the Comfy input directory, set the corresponding
`ASTRID_H3_*` path variables, and use `ASTRID_H3_REMOTE_INPUT_NAMES=1`.

The recipe uses `minimax_h3_ref2va_pruned_int8_convrot.safetensors`, the enabled
`minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors` LoRA at 0.95, and
**8 effective sampling steps**. Keep these as the baseline rather than silently
swapping workflows or models. Validate the Python recipe against the actual
runtime before queueing; do not edit the companion JSON by hand.

For each segment, inspect both clean anchors and the predecessor's last motion
before writing its prompt. Describe the exact subject silhouette, pose and
placement, props, lettering, icon/panel state, palette, negative space, and
destination arrangement. Turn those observations into a few ordered physical
beats—continue the incoming motion, make the transition, settle into the
endpoint—and state the flat pixel medium and hard-edged orange-on-black
prohibitions. This is vivid, anchor-specific direction, not a generic
megaprompt or an asset filename substituted for visual analysis. Store the
reviewed prompt on the owning shot's canonical binding.

For the first segment, guide from anchor A toward anchor B. For a same-scene
continuation, carry the previous accepted native latent and guide toward the
next anchor. Begin with 39 frames of context; use longer compatible windows only
when the graph and memory budget justify them. Delegate a separate Luna review
pass to inspect all anchors, challenge prompt/action drift, and review dense
seams and endpoints independently of the generation operator. Automatic
selection is a recorded policy, not user approval.

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
  --kind prompt --slot h3-segment-01 --text-file <reviewed-prompt.txt> \
  --expected-head 0 --json
```

Use a stable lowercase hyphenated slot per segment, such as `h3-segment-01`.
The current runtime rejects underscores in slot slugs. A shot with several picture intervals needs several slots, not one overwritten prompt. For an existing binding, use its observed current head instead of zero. Preserve previous revisions; pin the exact binding identity/head and text digest in each generation's evidence. Changing a prompt must not relabel an old generated take as if it used the new revision.

Draft prompts only after inspecting both actual anchors for the interval and the predecessor's motion. First inventory the exact composition and identity in each image: subject silhouette, screen position and scale, pose, props, icon states, readable typography, negative space, and the destination's specific arrangement. Turn that inventory into a few temporal beats scaled to the usable interval: preserve the incoming motion, perform the transition, then settle into the destination. Store those concrete actions rather than narration, an asset filename, or generic adjective filler. Keep overlays and compositor-only content separate: reserve their required negative space and do not ask H3 to invent terminal text or other external graphics. Mark draft versus reviewed status in run/project evidence. Do not populate still-only or compositor-only sections with invented H3 prompts.

### Treat style as a continuation constraint

The 39-frame Seitanism overlap protects incoming audiovisual motion and timing; it does not, by itself, lock the model to the source medium. A flat illustration can remain identity-consistent while drifting into a photorealistic or materially different scene immediately after the protected prefix. Treat style and composition as explicit prompt constraints, not as a property guaranteed by the overlap.

For graphic, pixel-art, or deliberately flat source material, put a short style guide before the action description. The Hivemind-tested shape is:

```text
For the target video, at 0.00 seconds into the target video, <Picture 1> (from [Shot 1]) is fully referenced.
integrated_multimodal_description: [palette, medium, line/shading treatment, background treatment, subject identity, and the exact action that continues from the incoming frame]
```

Then describe the transition in temporal order: continue the motion already in progress, specify the next action, and state the destination or compositional change. For a flat source, name the medium and its prohibitions explicitly (for example, “flat 2D graphic, limited palette, hard-edged shapes; no photorealism, CGI rendering, volumetric texture, or live-action landscape”). Reference images should reinforce identity, not be expected to preserve the whole style. Match detail to the interval rather than treating length as a target: the 200–300 words used for the five Astrid Intro prompts are an example, not a mandate. Prefer vivid, concrete physical detail over adjective density; if actions become contradictory or overloaded, reduce them to a few staged beats that protect the destination pose, text, and medium. Keep this prompt per-shot in the canonical prompt binding; do not bake a project-specific style into the reusable workflow default.

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

Do not start a continuation from a take still awaiting approval. In automatic mode, only takes that pass both technical and raw visual gates can feed the chain under the recorded policy; label them as automatically selected, not user-approved. Technical success alone never admits a descendant.

Use the workspace runtime's supported task/dependency mechanism for durable execution. Do not implement a pack-local scheduler or pretend an in-memory loop is a durable queue. If a required approval/dependency feature is unavailable, perform the sequence explicitly through supported admissions and report that limitation.

Retries create new attempts and preserve old outputs. A failed job blocks its descendants; it does not discard completed work. Changing an upstream take makes downstream context-dependent results stale: regenerate or explicitly review them before reuse. Resume from verified managed outputs, not the latest filename or task status alone.

## 6. Preserve timing and audio

Read the chosen timeline's editorial frame rate from the runtime. In the
Astrid Intro H3 chain, native generation is **1920x1088 at 24 fps** with source
counts `175/260/175/175/294`; the corresponding 30-fps conformed counts are
`212/279/177/169/311`. Treat these as this recipe's measured lengths, not as
assumptions about every H3 workflow or timeline.

Keep separate clocks for generated frames, retained overlap, and final timeline duration. Context is overlap, not extra footage added to the edit. Choose a supported full target length that includes the necessary context and new material; use the graph's actual overlap outputs/assembly policy rather than blindly subtracting a constant from every file.

Extract subsequent context from the native 24-fps generation's direct 39-frame
AV latent edge before editorial retiming. Do not decode an MP4 and re-encode it
as continuation context. Conform the usable new-picture interval to its exact
authored duration, preserving the endpoint. Convert to the 30-fps timeline
without moving narration or accumulating rounding drift. Record any retiming;
if it noticeably distorts motion, regenerate with a better duration or split
the interval instead.

Do not simply trim off an endpoint to make a clip fit. At shared anchors, check for duplicate-frame holds, jumps, or a slowdown. Quantize placement consistently to the master timeline's frame grid and check the final boundaries.

Preserve the timeline's existing voiceover and soundtrack. Do not mix H3-generated audio into the final edit by default; mute generated picture clips in assembly unless the project explicitly calls for the generated audio. Audio used internally by the AV workflow is distinct from the final soundtrack.

## 7. Review and switch each segment

Technical acceptance requires a decodable video, expected dimensions/frame count/duration, valid managed identity, and no missing or unexpected black frames. Also inspect motion, character/style consistency, text deformation, endpoint likeness, and the join to the preceding clip. A successful task status is insufficient.

Use this gate for **every** segment, before it feeds a descendant:

- [ ] Inspect the unmodified raw video in motion, not only extracted endpoints.
- [ ] For a subject that must remain visible, inspect every frame around pose
  changes and position changes. A sparse contact sheet can miss a brief
  dissolve between a running body and a newly appearing standing body. Track
  one opaque silhouette through deceleration, planted feet, turn, and rise;
  require a physically connected path rather than two correct endpoint poses.
  For short takes, numbered all-frame contact pages complement motion review.
- [ ] Compare anchor and raw identity details at native size: eyes, outline,
  hands/props, lettering, palette, and background.
- [ ] Confirm requested action, camera behavior, and destination composition.
- [ ] Compare any technical conform against raw at matching content frames;
  context removal must not hide a sudden processing change.
- [ ] Review the outgoing final second, cut, and incoming first second in the
  actual composition. Verify static placement, crop, and scale explicitly.
- [ ] Have an independent Luna reviewer report concrete defects and compared
  frame identities. Missing evidence is an incomplete review, not a pass.
- [ ] Record separate technical, raw visual, derivative, and composite verdicts
  plus automatic-selection versus user-approval status.

Any failed box blocks selection and dependent generation. Retry with a stated
hypothesis and a bounded attempt/spend limit, preserving the old take. When the
limit is reached, report the unresolved defect; do not switch to unrequested
masking, warping, stabilization, or heading replacement. If the defect is found
after selection, mark that verdict superseded and review dependent results.

### Diagnose the seam at the correct layer

A detailed anchor description can still produce a nearly static subject. In
the Astrid Intro run, an otherwise valid continuation preserved the tool-holding
mink for most of the interval and introduced soft vertical orange streaks.
The 39-frame overlap had SSIM 0.998832 against the source tail and the runtime
mask protected only those frames, so this was a motion/style failure rather
than an overlap failure. The corrective trial moved the action earlier in the
prompt, assigned explicit early beats to releasing props and beginning the run,
and prohibited the observed streak artifact. Judge the retry on actual output;
more prompt words alone do not establish better animation.

Review the last preserved frame, the first generated frame, and the next 10–20 generated frames as a dense seam inspection. If the preserved prefix matches exactly, the 39-frame overlap and source-frame path are functioning; changing frame counts or re-encoding the source is unlikely to fix a style or composition drift. Retry first with a stronger style/action guide or a new destination anchor. If the subject changes identity, inspect reference wiring and keyframes separately.

When chaining one H3 generation into another, pass the prior H3 latent through the generated-context path where the workflow supports it. Do not decode that latent to images and re-encode it merely to create the next context: that loses motion information. A first continuation from an ordinary source MP4 is different—the initial source encode is expected. In both cases, verify the actual context node logs and the first unprotected frames rather than inferring continuity from a successful queue status.

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

Check every generated seam, every handoff into/out of still or compositor-only sections, overlay placement, unchanged narration timing, overall duration, and the final ending. Deliver the exact managed render/run and identify any intervals still using their original stills. A clean final export follows the user's acceptance unless the user already requested an unattended finished export. Keep automatic technical/editorial selection distinct from user approval in either case.

For the completed Astrid Intro instance, the six child picture replacements were
applied to parent `main-final-blackend2` version 52. The successful technical
render is run `4c1671f288c043ea8ddc18fb4e8249ab`; its managed video is
`sha256:e2f550a7d6d7cc8152f41e1476f6e82b0a0246570fb902edefb7a2cbb6c6a632`.
The audit verified 1920x1080 at 30 fps for 117.066667 s, clean full decode, and
decoded PCM byte-identical to the prior render; the render pod was terminated
after completion. The earlier overall visual pass was incorrect and is
superseded: gray chromakey removed eye detail that survived in both the anchor
and raw generation, and an assembly bridge introduced a 37.5-pixel downward
move before the first cut. Heading glyph scatter also remains. This render is
technical evidence, not an approved visual-quality example. See the
[corrected execution record](astrid-intro-animation-execution.md).

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
