# Astrid Intro: worked example

> **Current handoff scope (2026-09-21): CPU/fake/offline only.**
> [The user's scope amendment](../../../../execution-scope.md) governs this entire
> document, including tasks, commands, acceptance criteria and review inputs.
> All live GPU/RunPod testing and hardware proof below are historical scope
> moved to [separate deferred gate L](../../../../POST-HANDOFF-GPU-GATE.md).
> They are excluded from current execution and acceptance and cannot block
> current project completion. Preserve CPU implementation/fixture requirements,
> original evidence and spent budgets; do not treat a fake PASS as GPU proof.


The reusable procedure is [Anchor-to-anchor video generation for any timeline](anchor-to-anchor-video-generation.md). This page records the Astrid Intro inspection and H3 execution from 17–18 September 2026 so those project facts do not get mistaken for general rules. Reinspect the live timeline before generating; timings, assets, and coverage can change.

## Picture inventory at inspection

| Timeline interval | Picture policy |
| --- | --- |
| 0–27.892 s | Image-backed opening; candidate for animation |
| 27.892–38.280 s | Background image plus terminal content; inspect carefully before animating behind the terminal |
| 38.280–64.592 s | No child-shot background anchor wired in; retain the Remotion/process sequence and terminal layers |
| 64.592–117.072 s | Image-backed ending sections, with overlays where authored |

The 38.280–64.592 s section is not an H3 endpoint target. It is a Remotion/process sequence with no child-shot background anchor, so the opening generation chain should end at 38.280 s and a new chain should begin only when image-backed picture resumes. Giving that section a generated background would require a separate creative decision and newly authored anchors.

The guidance image beginning at 64.592 s continues into the next shot, then changes internally at 74.652 s (72.492 + 2.160). The image at 7.076 s is reused at 10.264 s, so that boundary does not require a transition.

## Project-specific render facts

- The parent timeline inspected was `main-final-blackend2`.
- The editorial timeline is 30 fps; the H3 workflow generates at **1920x1088,
  24 fps**. The starter/continuation source counts are
  `175/260/175/175/294`; conformance produces `212/279/177/169/311` frames at
  30 fps.
- Continuations use a direct 39-frame audiovisual latent context from the
  preceding sampler. Do not decode an MP4 and feed it back as continuation
  context. The destination endpoint constraint and any extra image appearance
  reference are separate inputs.
- Existing Remotion layers, terminal footage, narration, and the soundtrack remain authoritative during assembly.
- The black base is not an end-frame target. Use an explicit hold, cut, or new anchor at the boundary.

## Failure policy: generation defects are not finishing problems

Judge the native H3 output before any cleanup. If it introduces a gray
document/collage background, an unwanted zoom or camera move, a missing prop,
or damaged eye/letter/pixel detail, reject that take and regenerate it (or
change the anchor/prompt). Do not rescue it with a crop, matte, HSV mask,
bounding-box scale/translation, heading replacement, blur, or other
post-generation transform. Those operations can hide a symptom while changing
the authored image and cannot restore information the model did not generate.

The useful name for these operations is **finishing transforms** (or editorial
derivatives), not generation. They are allowed only for a separately approved
editorial effect after the native take passes visual review, and every
derivative must be checked against the native frame at 100% detail. A clean
decode, matching audio, valid provenance, or technically successful render is
not visual acceptance.

This project exposed three traps. The gray collage and terminal zoom were
native generation failures and should have been rejected. The apparent
downward camera move at the first seam was introduced by the assembler's
optional `--bridge-transforms` translation: s01 moved approximately
`(+0.5,+37.5)` pixels over its last 30 frames to reconcile authored offsets.
Do not enable that option by default; fix the shot placement or regenerate or
re-author the anchors. Finally, the tiny orange eye center existed in the
anchor and in raw s01 frame 174 and raw s02 frame 39, but disappeared only
after the broad `chromakey=0x808080:0.18:0.0` cleanup was applied to s02. That
is detail loss caused by finishing, not by H3 or the anchor.

These facts feed the general guide's interval and duration procedure: each eligible picture interval's editorial gap determines its usable new-picture duration, while H3 context remains overlap rather than added timeline footage.

## Live opening execution, 17–18 September 2026

The current inspection and execution plan are recorded in
[the opening animation execution record](https://github.com/peteromallet/Astrid/blob/032f65bcd84bd6360f83c260aa902c3a70cc0575/guides/astrid-intro-animation-execution.md).
Parent `main-final-blackend2`, version 52, resolves the opening to these exact
30-fps frame windows:

| Master frames | Seconds | Clean picture transition |
| --- | --- | --- |
| 0–212 | 0–7.066667 | Intro sign mink → tools mink |
| 212–491 | 7.066667–16.366667 | Tools mink → knowledge-network running mink |
| 491–668 | 16.366667–22.266667 | Running mink → three pointing minks |
| 668–837 | 22.266667–27.900000 | Three minks → lower-right typing mink |
| 837–1148 | 27.900000–38.266667 | Typing vignette, stable position beneath terminal |

The second generated section spans two authored shots (96 and 183 frames).
Those shots can reference adjacent portions of the same conformed media object;
they do not need separately generated clips or a transition at their boundary.
Keep the six shot containers so their narration, text bindings and parent
compositing continue to work. Preserve every raw generation output as evidence
and as a possible continuation source. Matte compositing, source-heading
restoration, and re-encoding are explicit finished derivatives; never describe
those files as native outputs. Use the anchor-chain assembler's
`--source-manifest` to bind each derivative's path/hash to raw managed identity
and finishing recipe/evidence identifiers.

The five native takes and their finishing derivatives are preserved for audit,
but the finishing recipes are failed experiments, not an acceptance recipe.
The s03/s04 full-frame matte, s05 HSV mask plus bounding-box
scale/translation, source-heading restoration, and any re-encode must not be
used to repair a bad generation without new visual approval. In particular,
the broad s02 chromakey cleanup destroyed fine eye and ground-pixel detail.
Keep the five native raws as the continuation sources and evidence, and record
any genuinely approved derivative as a separate editorial asset.

### Vivid anchor customization and independent review

For each segment, inspect the clean start/end anchors and the predecessor's
motion before writing the prompt. Inventory the mink's silhouette, exact pose
and screen placement, props, lettering, panel/icon states, palette, negative
space, and destination arrangement. Convert that inventory into a few ordered
physical beats (continue motion, perform the change, settle into the endpoint)
with explicit hard-edged pixel-art and orange-on-black constraints. This is
anchor-specific direction, not a generic megaprompt or a filename-based prompt.

Delegate Luna as a separate reviewer: she checked the anchor set and prompts
independently, then reviewed motion, endpoints, and dense seams so the
generation operator did not grade their own take. In the retry-3 experiment,
using the destination endpoint as the extra
appearance reference gave the best running motion but introduced a grayscale
document collage. That was a generation failure to reject, not a reason to add
a deterministic orange matte or source-heading restoration. The
appearance-reference choice must not be conflated with the endpoint constraint.
The reviewer must compare native output before and after every finishing pass,
including dense seams and small facial details; a derivative that loses detail
is rejected even if its silhouette or color looks cleaner.

The exact prompts are saved on the owning shots and mirrored in
[`astrid_intro_h3_prompts.json`](https://github.com/peteromallet/Astrid/blob/032f65bcd84bd6360f83c260aa902c3a70cc0575/workflows/astrid_intro_h3_prompts.json).
The new starter/continuation recipe is
[`astrid_intro_h3_anchor_chain/workflow.py`](https://github.com/peteromallet/Astrid/blob/032f65bcd84bd6360f83c260aa902c3a70cc0575/workflows/astrid_intro_h3_anchor_chain/workflow.py).
Its target is native 1920x1088 with direct 39-frame AV continuation. At this
document revision, the six-child application is complete and the successful
parent render is run `4c1671f288c043ea8ddc18fb4e8249ab` (managed video
`sha256:e2f550a7d6d7cc8152f41e1476f6e82b0a0246570fb902edefb7a2cbb6c6a632`).
The technical audit verified 1920x1080/30-fps/117.066667-s video, clean full
decode, and decoded PCM byte-identical to the prior render; the render pod was
terminated after completion. That is a technical success only. Visual QA later
found the bridge drift and eye-detail loss described above, so this render is
not a clean visual reference and must not be described as having passed overall
visual QA. Do not treat a recipe, managed raw output, or structural validation
alone as proof of final rendered or delivered video.
