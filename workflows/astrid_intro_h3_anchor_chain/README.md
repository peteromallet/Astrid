# Astrid Intro H3 anchor chain

## Current entry point: CUDA 13 relaunch

Follow the [canonical-stack relaunch record](../../guides/astrid-intro-cuda13-relaunch-20260918.md)
and the [H3 admission gates](../../guides/runpod-lifecycle.md#h3-fail-closed-preflight-before-creative-downloads).
The `workflow.py` in this directory preserves the prior CUDA 12.8 fallback
attempt; it is **not** the canonical CUDA 13 runtime recipe. Do not copy its
Torch pin or attention default into a fresh launch. The relaunch uses
[`workflow_cuda13.py`](workflow_cuda13.py) and must pass observed host/backend compatibility and longest-clip
capacity checks before creative generation.

For the current creative revision use six staged anchors (including black),
the six-entry `ASTRID_H3_SEGMENTS` from `prepare_revision.py`, and
`review_revision.py` / `assemble_revision.py`. The five-stage paths, counts,
and deployment shell script described below are historical, not launch defaults.
No `finish_*` helper is part of this regeneration route.

## Historical workflow layout

`workflow.py` builds a fresh two-anchor starter and an admitted continuation prefix
using the installed Seitanism H3 nodes. It reuses the pinned model, VAE,
text encoder and turbo LoRA declarations from
`../seitanism_h3_av_extension_verified/workflow.py`.

The exact prompts and anchor filenames come from
`../astrid_intro_h3_prompts.json`. They must match the owning shots' canonical
prompt bindings before execution. The user selected automatic execution and
review, with vivid prompts grounded in each inspected anchor.

## Controls

- `ASTRID_H3_CANONICAL_WORKFLOW`: verified imported bundle directory.
- `ASTRID_H3_PROMPTS`: exact reviewed prompt document.
- `ASTRID_H3_SEGMENT_COUNT`: number of admitted stages, initially `1`; bounded
  by the supplied segment list (five historical stages, six in the revision).
- `ASTRID_H3_WIDTH` / `ASTRID_H3_HEIGHT`: native dimensions, default `1920` / `1088`.
- `ASTRID_H3_SEGMENTS`: optional explicit segment specification for a reviewed
  variation; changing an upstream specification invalidates its descendants.

Stage the five clean PNGs in the Comfy server's input directory under the names
in the prompt document. `run_pod.sh` records the concrete runner used for this
execution; its remote paths are deployment details, not portable defaults.

## RunPod launch and shutdown checklist

Use a GPU pod only for H3 generation. Local assembly and Astrid rendering do
not require the pod. Before launching, confirm that the prompt file, five
anchors, workflow bundle, model/custom-node versions, and a unique attempt name
are ready. Record the pod id, image/template, GPU, Comfy port, checkout
revision, and attempt name in the run evidence. Never reuse an attempt
directory: `run_pod.sh` deliberately refuses to overwrite one.

After the pod is ready, verify that Comfy is reachable, the pinned nodes and
models are present, the staged anchors have the expected dimensions, and the
native 1920x1088 path is active. Run one reviewed stage first; append
continuations only while the direct 39-frame AV latent edge is available.
Follow the remote machine continuously: watch the exact pod status, setup or
runner PID, model-transfer progress, disk growth, GPU/Comfy state, runner
result, runner log, and Comfy log. A local launcher returning or an empty queue
is not proof that the remote work finished. Poll the remote process and require
the expected receipt, output decode, and hash before advancing. If a remote PID
disappears without its receipt, stop and diagnose that attempt rather than
starting another pod or silently re-queuing it. A completed process is not an
accepted take: inspect the native output for gray collage, zoom, camera drift,
endpoint mismatch, and tiny-pixel/detail loss before starting assembly.

Before terminating the pod, register or copy the native outputs, prompts,
workflow/settings, runner and Comfy logs, exit code, and source manifest in
runtime-owned evidence. Confirm that the files are readable and hashes are
recorded. Terminate the exact pod id and verify the provider reports it gone.
Keep the warm server only during bounded between-stage review when another
admitted generation needs its native cache. After the final GPU work and output
preservation, stop spend before local assembly/rendering; do not terminate while
a generation is still writing its output.

For the provider/API-level custody, budget, storage, readiness, and teardown
procedure, use the separate [RunPod lifecycle guide](../../guides/runpod-lifecycle.md).

## Continuity and timing

The measured target is **1920x1088 at 24 fps**. Starter frames are `175`;
continuation target lengths are `260,175,175,294`, for source counts
`175/260/175/175/294`. The direct audiovisual context edge carries 39 frames
from the preceding sampler's generated AV latent; it is not a decoded MP4
round-trip. The output remains silent for editorial use, while the latent
retains its internal audio context.

The starter injects both anchors in **one** CustomKeyframes call, at positions
`1` and `175`. A second call would replace that node's prior keyframe list.
Each continuation injects its destination at the final target frame and uses
the 39-frame direct AV context. The destination endpoint constraint and the
extra image appearance reference are separate controls: an appearance image
may be changed without changing the endpoint keyframe.

Append stages without changing earlier graph IDs, prompts, seeds, inputs or
dimensions to reuse the live Comfy cache. Never substitute a decoded MP4 for
the native latent link. Core SaveLatent/LoadLatent does not preserve this nested
AV structure. If the server cache disappears, regenerate the graph rather
than claiming an MP4 re-encode preserves it.

`assemble.py` removes the leading context from continuation outputs and maps
the first and last usable frames onto the exact first and last 30-fps target
frames. It uses nearest-frame sampling and produces `212/279/177/169/311`
frames. The second file spans two shot windows, split at frame 96. Keep raw
generation outputs as continuation sources and evidence. Any matte, heading
restoration, re-encode, crop, HSV mask, bounding-box scale/translation, or
other finishing pass is an explicit editorial derivative, not a native
generation output. These are not a repair strategy for generation defects:
reject and regenerate a take with gray collage, unwanted zoom/camera motion,
missing detail, or endpoint mismatch. Only use a finishing transform for a
separately approved effect after native visual QA; compare it to the native
frame at 100% detail and reject it if it removes facial, lettering, or ground
pixels. Pass an approved derivative's path/hash and raw managed identity
through `--source-manifest` when applying assembly.

## Prompt and review method

Inspect each clean anchor and its predecessor before writing that segment's
prompt. Describe the exact mink silhouette, pose, props, lettering, icon/panel
state, negative space, and destination composition, then turn those details
into a few chronological action beats. Put the pixel medium and hard-edged
orange-on-black constraints alongside the action. This is vivid, anchor-specific
direction, not a reusable generic megaprompt.

Delegate a separate Luna review pass to catch prompt/motion drift: have her
inspect the anchor set, propose concrete action and style revisions, and review
dense seams and endpoints independently of the generation operator. Preserve
the raw take even when a finishing derivative is selected for editorial
playback. In the retry-3 test, using the destination endpoint as the appearance
reference improved motion but produced a gray document collage. That was a
generation failure to reject, not a reason to add deterministic orange matte
compositing or source-heading restoration. Do not confuse that
appearance-reference choice with the endpoint constraint or feed a
decoded/finished MP4 back into the latent continuation chain.

The s03/s04 full-frame matte, the earlier top-350-pixel header replacement,
and the s05 HSV mask plus per-frame orange bounding-box scale/translation are
preserved as historical failed experiments. They must not be called
“accepted” or presented as the standard recipe. The broad s02 chromakey
cleanup (`0x808080:0.18:0.0`) removed the tiny orange center from the eye even
though it was present in the anchor and both relevant native frames. Preserve
the native raw source separately and make visual comparison against it a hard
gate for any future derivative.

Run assembly without `--apply` to prepare review files. Do not use
`--bridge-transforms` as a default. In this execution it introduced the visible
downward camera-like move at the first seam by translating s01 approximately
`(+0.5,+37.5)` pixels over its last 30 frames. Fix inconsistent authored
placements or regenerate/re-author the anchors; a bridge is an experimental
transform and requires explicit visual approval. Inspect every seam before
selection. `--apply` imports source/conformed files and provenance, then saves
fresh complete child documents with version checks while retaining all original
anchor registrations and voiceover clips. With `--source-manifest`, it also
records explicit raw/finishing lineage and creates only verified managed
`derived_from` edges. The parent overlays are untouched.

## Evidence status

### 18 September revision

Use `prepare_revision.py` and the six-entry `ASTRID_H3_SEGMENTS` document for
the current revision, not the historical five-entry prompt list. Its native
counts are `175/260/175/175/209/124`; `assemble_revision.py` conforms these to
`212/279/177/169/205/106` frames. The last two split the original 311-frame
typing window into a hold and a physical exit to black. `review_revision.py`
checks exact raw shape/prompt, extracts native frames and seams, and leaves
visual acceptance explicitly pending. A technical pass is not selection.

`assemble_revision.py` is prepare-only unless `--apply` is given. The explicit
`--prefix-count 1|2|3|4|6` supports a clearly recorded partial revision when
only an approved prefix is ready; default is all six. Five is rejected because
the typing hold and exit must replace b06 together. Unselected children remain
unchanged. A partial review must not be presented as completion of the full
request. The explicit
`--normalize-placement` option gives only the new full-canvas clips one static
origin `(0,0,1920,1080)`; it records old placements and never adds a bridge,
mask, or animated camera correction. Narration and parent timing are preserved.

The first fresh-machine attempt used a cu128 target and recorded fallback
patches after landing on an incompatible host. It failed to complete the chain
and is not the recipe to reproduce. Consult the [failed-attempt record](../../guides/astrid-intro-regeneration-20260918.md)
and [canonical-stack relaunch](../../guides/astrid-intro-cuda13-relaunch-20260918.md).
No historical render is evidence that this six-stage revision has passed.

### Historical five-stage render (visually rejected)

The five-source prepare-only assembly verified
exact output counts and full-size endpoints, and the parent timeline was then
applied at version 52 with only the intended child picture replacements. The
successful parent render is run
`4c1671f288c043ea8ddc18fb4e8249ab`, with managed video
`sha256:e2f550a7d6d7cc8152f41e1476f6e82b0a0246570fb902edefb7a2cbb6c6a632`.
The technical audit found 1920x1080/30-fps/117.066667-s video, clean full
decode, and decoded PCM byte-identical to the prior render; the render pod was
terminated after completion. This proves technical render success only. The
later visual audit rejected the result as a clean reference because the bridge
drifted the first seam and the finishing cleanup removed eye detail. Current
attempt and review evidence is recorded in
[`guides/astrid-intro-animation-execution.md`](../../guides/astrid-intro-animation-execution.md).
