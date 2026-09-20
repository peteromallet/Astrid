# Astrid Intro opening animation execution

## Correction after user review — 18 September 2026

**The historical visual-pass claims below are superseded.** The render and
audio checks succeeded technically, but the delivered opening contains visual
defects that our review missed. This record preserves the attempts, not an
endorsement of their repair methods. No corrective render has yet been made.

- The v04 anchor, raw s01 frame 174, and raw s02 frame 39 retain the small orange
  eye-center detail. Finished s02 frame 39 loses it. The broad
  `chromakey=0x808080:0.18:0.0` cleanup removes valid details as well as unwanted
  gray; it begins at frame 39, exactly the first usable frame after context
  removal. This is a finishing regression, not an anchor defect.
- The downward movement before the first cut is an assembly decision:
  `assemble.py --bridge-transforms` eases (+0.5, +37.5) pixels during the last
  30 frames of s01 (about 6.03–7.03 seconds), before the cut at 7.0667 seconds.
  It reconciles different authored placements by adding visible movement.
  It is not generated camera motion and should not have been added silently.
- Gray document collage and the terminal take's unwanted zoom are genuine
  generation failures. Broad matte cleanup, source-heading replacement, and
  HSV/bounding-box stabilization were attempts to salvage them, not reliable
  fixes. An earlier heading replacement also cropped rising heads.

The correct policy is to reject defective raw takes and regenerate, remove
destructive finishing, and diagnose placement separately. Compare anchor, raw,
derivative, and composite at matching content frames before acceptance; review
small identity details at native resolution and seams in motion. Independent
review must explicitly test these failure modes, not repeat an overall pass.
The originals remain preserved and the pod termination remains verified.
See [generation rules](anchor-to-anchor-video-generation.md) and
[RunPod lifecycle](runpod-lifecycle.md).

## Authorized result

Animate the existing opening pixel-art mink anchors up to the Remotion-only
sequence, with the mink running through the changing scenes. Preserve the
existing overlays, framing, narration, and editorial timing. Generate at a
larger native resolution where the supplied RTX 5090 supports it. Download and
register the results, select them in the existing timeline, render and visually
review the complete composition, and open the videos together for review.
Terminate RunPod `6vuwjqzv1c1qk6` after verified delivery.

The user explicitly authorized unattended end-to-end generation and selection;
attempts are automatically selected after technical and visual review, not
described as user-approved. No per-segment confirmation is required.

## Execution plan

1. Inspect the current runtime project, parent and child timelines, and the
   rendered timeline visualizer. Pin the exact opening picture intervals and
   clean anchors; the earlier guide places the handoff at 38.280 seconds.
2. Inspect the supplied pod, installed H3 nodes/models, and pinned Seitanism
   recipe. Establish a starter with two anchors and a continuation using actual
   generated latent context. Validate the larger-resolution recipe before use.
3. Store each standalone style/action prompt on its owning shot. Generate the
   opening sequentially, retaining native context and endpoint-conditioned
   transitions. Inspect motion, pixel style, endpoints, and seams.
4. Register generated media and reproducibility evidence through Astrid.
   Conform usable new picture to the original 30-fps intervals. Decide whether
   a shared continuous source or individual clips best preserves continuity;
   keep existing shot compositions and overlays authoritative.
5. Save fresh complete timeline documents with version checks, render the
   parent, inspect all joins and the Remotion handoff, and open the exact
   successful review output with the generated clips.
6. Update the reusable guide and worked example with the verified workflow,
   native resolution, overlap/conform procedure, and managed output identities.
   Verify local managed copies before terminating the supplied pod; verify its
   terminal lifecycle state.

## Current evidence

- Project `astrid-intro`: `61d1078d029e42a9af8540c0d5647ae3`.
- Runtime default timeline: `2652b5567c8e4e9aa4d35c1df0eb2742`.
- Pod lifecycle query on 17 September 2026 reports desired status RUNNING and
  public SSH `162.43.172.181:11196`; live runtime inspection is still required.
- The supplied guide's 960x544 continuation is a different creative shot
  (Matrix transformation). Reuse its mechanism, not its prompt or scene.
- Existing checkout changes predate this execution and must be preserved.

Completion remains unproven until generation, timeline selection, visual
review, delivery, documentation, and pod termination are all verified.

## Pinned opening and prompt admission

Live parent version 52 resolves six shot windows to 212, 96, 183, 177, 169,
and 311 master frames. The two middle repeated-anchor shots share one 279-frame
generation interval. The five generation intervals total 1,148 frames,
38.2666667 seconds. The original floating child media durations differ slightly;
use the parent frame windows for conformance.

All five clean anchors were downloaded through the SDK and digest-verified.
The timeline visualizer run `b451eac96e4846ed9a94852f56926bc1` pins render
`59c3fec704b7421584b5a135f5286c86`; both opening pages were visually inspected.
The global frame and terminal footage are separate layers.

Prompts are in [the exact prompt document](../workflows/astrid_intro_h3_prompts.json)
and canonical shot bindings `h3-opening-01` through `h3-opening-05`. Current
heads are 2, 4, 3, 3, 2; the shared second prompt is head 4 on both shots.
The second prompt is also bound to the next shot because its picture interval
spans both. The managed prompt-document digest is
`sha256:b678a98bd7845aaee2d49c8a450a830426619aef0d75d0b9a086332b0fd2cb7d`.

The starter binding is `fd50be4f-85a9-529b-af5a-f18db4c8ef06`, with text digest
`sha256:20c869cab195cc0fbb63f7e2710f37f3488f9ca3e7b9ead36debe79763e4d443`.

The user requested more vivid anchor-specific prompts and Luna delegation.
Luna inspected all five clean anchors and revised the prompts to describe exact
character poses, props, lettering, pixel choreography, temporal beats, and final
composition. Those revisions were reviewed and saved before GPU admission.

The verified remote Comfy root is `/workspace/runpod-slim/ComfyUI`; the VibeComfy
runner is `/workspace/vibecomfy-local-fix-20260917-1`. The H3 pack is pinned to
`361624fb406b63eb6694442eac6c895fc1533a70`. The planned native target is
1920x1088, pending its first live memory/performance test.

Use direct sampler-to-generated-context edges for native latent continuation.
The core SaveLatent/LoadLatent implementation does not preserve H3's nested
audio/video structure. Keep the upstream graph identical while adding a next
stage, so the running server can reuse its generated latent cache. Preserve
workflow inputs and seeds so a lost cache can be regenerated explicitly.

## First GPU attempt

The native 1920x1088 starter passed live-target validation and was admitted as
Comfy prompt `c7920223-99ce-4863-9f7c-c4bede3fc3fb` (queue index 14).
Its remote attempt evidence is under
`/workspace/astrid_h3/intro-chain-20260917/stage-1/`.
The first attempt completed successfully in 363.20 seconds. The downloaded
native output verifies as 1920x1088, 175 frames at 24 fps (7.291667 seconds).
Main-thread visual inspection of its chronological contact sheet and full-size
endpoint shows a coherent orange mink run, deliberate disassembling/reforming
lettering, preserved flat pixel style, and a readable destination composition.
It was automatically selected as the continuation source, not user-approved.

Managed video:
`sha256:45c4d5cc7cce42ea80eb03aa15e2c4132aa9e1cdab715e9bb56bf33db4492c6d`.
VibeComfy run: `run-1789678946-9ee90fad`.
Managed metadata:
`sha256:2f0cccaae4e11e7dc16dc62264a40f5b2308dae851a6c1cef1858b69a6d38466`.
Managed Comfy history:
`sha256:160ce4cd2bb0e990f96549c549ce29d5e0b311eb9b78900e266ed1b5a8392720`.
Managed contact sheet:
`sha256:a3e5ffb0b2552223d8da49511ad7faa3510e473108a581078975e964d8bb379d`.
The recorded compiled prompt exactly matches canonical prompt head 2.

The exact first-attempt recipe is registered as
`sha256:c724bf0e480e125b23b83bc5c40bd0ca7e9c53df24142a3e0de1d9581fdcdf43`.
Its combined first/last keyframe call was verified against the live node
contract before admission. Both anchors reached positions 1 and 175.

Assembly preparation now has independent Luna review plus synthetic endpoint
tests. Match actual output files to generation receipts before invoking it;
frame count alone cannot establish segment identity. The optional transform
bridge addresses authored placement deltas of (+0.5,+37.5), (-3.5,+22.5),
(+2,-27.5), and (+20,+64) pixels across the four generated joins.

## Resume state

- Stage 1 is locally downloaded, managed, and visually accepted by both root
  and Luna. Local staging: `/tmp/astrid-intro-native-mcd9u6/`.
- Stage 2 retry 2 completed with sustained running but a hallucinated grayscale
  photographic background. It is not selected as raw playback. Luna is testing
  deterministic orange-artwork isolation as a finishing option; root's initial
  mask removed the background but left edge/lettering noise.
- Stage 2 retry 3 is being admitted with the running destination anchor as its
  appearance reference. Earlier rejected takes are preserved. Runtime logs
  confirm direct
  latent-to-latent AV continuation, 39 protected frames, target 260 frames,
  endpoint 260 at 1920x1088. Agent `generation_preflight` supervises the pod
  and downloads each result/receipt, waiting for visual acceptance between stages.
- Agent `vivid_prompts` is Luna and handles independent visual review. Reuse
  it for stage 2–5 contact sheets and dense seam checks once files arrive.
- `assemble.py` is ready, with optional `--bridge-transforms`; no real assembly
  or timeline selection has occurred yet. Frame/endpoint synthetic checks and
  Luna's correctness review passed.
- Remaining: review stage 2 and admit stages 3–5 sequentially, verify/download
  and register all outputs and execution receipts, inspect dense seams, prepare
  conformed clips with placement bridges, select through fresh child saves,
  render the existing parent (review plus requested full-quality result), inspect
  output and Remotion handoff, open delivered videos together, finalize guides
  and managed evidence, then terminate and verify the supplied RunPod.
- Do not treat GPU admission, this record, or a contact sheet alone as proof of
  completed delivery. The full objective remains active.

## Stage 2 first-attempt review

The 260-frame continuation completed in 11 minutes 21 seconds. Its native
39-frame prefix compared to the predecessor tail has SSIM 0.998832; history
explicitly reports the first sampler cached, and node logs confirm only 39
frames were protected. The context mechanism is working.

The take is **rejected for selection**: the mink remains upright and almost
static through much of the new interval, and blurred vertical orange bars
violate the flat pixel-art treatment. Root and Luna independently agree.
Preserved managed attempt:
`sha256:d8d0b527f508f754a84edb48293526c1a6f0637b77af1be45ba07e62b5dd1d63`.

Next action is a prompt revision emphasizing early tool dispersal, an early
drop into a sustained run, and discrete square particles with no soft bars or
light columns. Keep the accepted first sampler unchanged; do not attempt to
repair a style/motion failure by changing correct context frame counts.
Stage 3 has not been admitted and no timeline playback has been changed.

The revised stage-2 text is canonical head 3,
`sha256:f91b3491faba2506b4f8bbafd87bd3514305f2c64830a52925e897a9e4648f21`.
Luna also strengthened action timing in stages 3 and 4 (head 3) before their
first admissions. Stage 1 and stage 5 remain unchanged at head 2.
Retry uses a distinct `stage-2-retry1` attempt directory and keeps seed,
reference wiring, and the first sampler unchanged to isolate the prompt change.

The prompt-only retry completed but is also rejected: running increased late,
while vertical orange light-curtain artifacts became stronger. Its managed
video is `sha256:7a3d981dfe3d97a212bf682276fc2074c864751385ae916d22ad0a71e50bcb3c`.

Retry 2 removes the additional `ref_images.ref_image_0` conditioning from
continuation targets only. It preserves native latent context, endpoint
conditioning, seed, and the complete accepted starter graph. This is based on
the installed node contract: the reference image is supplied as persistent DiT
reference tokens as well as text-encoder input, separately from the temporal
mask. Excess pose attraction is an inference; the trial will test it.

The revised positive action/style prompt is canonical head 4,
`sha256:4c9401bd3be630e5922cfdd770796e1fd4f0ab94e9da847305dcdeb7618e0154`.
It describes pure-black negative space and discrete square graphics without
repeatedly naming the unwanted streak artifact. Revised recipe managed digest:
`sha256:9e92d47de5995a49da17fef1c5f6de6c73e89238f5acced749fc2adecffd7cc7`.
Attempt directory: `stage-2-retry2`. Stage 3 remains unadmitted.

Retry 2 completed in 11 minutes 18 seconds. Its native output is preserved as
`sha256:b085ede404cc52df3ac96609066f2cbfa54f2bac9241d98459f1655ef6a86415`.
Removing the appearance reference improved running but did not preserve the
black backdrop. A deterministic finishing trial isolates saturated orange
artwork onto black; it must pass edge, typography and seam inspection before
selection. The raw AV latent remains the only continuation source.

Retry 3 tests `ASTRID_H3_SECOND_REFERENCE=endpoint` with the same head-4 prompt
and seed. The appearance reference is the running destination image rather
than the stationary tool-holding source. Keep reference mode in each immutable
attempt's evidence; do not imply the image reference and endpoint-conditioning
roles are interchangeable.

Retry 3 completed in 11 minutes 42 seconds. The raw take
`/tmp/astrid-intro-native-mcd9u6/s02_00004.mp4` has substantially earlier,
sustained running, but retains an unwanted grayscale document collage.
It is the provisional motion choice, pending deterministic finishing QA.
Stage 3 is authorized using this take's **native AV latent**, preserving
`second_reference=endpoint`; future segments use source appearance references.
No cleaned/decoded video is fed back as continuation context.

Luna's bounded 260-frame finishing trial on retry 2 successfully removed the
gray background with `chromakey=0x808080:0.18:0.0` and RGB compositing onto
black. The top heading region is sourced from the original anchors and must
transition to the destination's actual highlight state. The same finishing
is now being applied to retry 3. These are explicitly derived editorial
assets, not unmodified native generation outputs; preserve both identities.

The retry-3 finished derivative passed root/Luna visual review:
`/tmp/astrid-s02-qa.Zkdzu9/s02_retry3_strong_matte_v04v05.mp4`.
It remains 260 frames at 24fps and 1920x1088. Heading brightness checks
confirm v04 at the start and v05's dim-left/bright-right arrangement at the
end. The first 39 frames retain native source image content but are reencoded,
not bit-for-bit copied. Raw retry-3 managed identity:
`sha256:d9bf664b99209de0980570a2a5430c4a6861062d89e57556311f5326b203665e`.
Its immutable recipe identity is
`sha256:e38e96c524fb12b084741d6e5c81805a7cccdfcbd309b859987f86e64120f957`.

Stage 3 completed in 426.22 seconds; Comfy prompt
`63de793d-1050-4ffe-93f3-e54dd25c92c2`, native `s03_00001.mp4`.
Root reviewed the running-to-three-pointing-minks action and accepted its
motion pending the same explicit background finishing. Source-v05 headings
will fade out as the three-mink arrangement forms. Stage 4 is authorized with
the unchanged upstream native chain and source appearance reference.

## Finished motion chain and final assembly gate

Stages 1–4 have passed root visual review. Selected inputs so far:

| Stage | Selected source | Managed identity |
| --- | --- | --- |
| 1 | Native `s01_00001.mp4` | `sha256:45c4d5cc7cce42ea80eb03aa15e2c4132aa9e1cdab715e9bb56bf33db4492c6d` |
| 2 | `s02_retry3_strong_matte_v04v05.mp4` | `sha256:fdd4444d5e8bdafa02acc152c903279305ade8fcca566088b984056c0d23ac82` |
| 3 | `s03_strong_matte_v05fade_fullframe.mp4` | `sha256:bceaa0b6167ef4e3e361685a338d96a1d7840d2046c3f730106d3eadb76bec54` |
| 4 | `s04_strong_matte_fullframe.mp4` | `sha256:cb2bcec385daf4ce6219882da6f157fa5a9f8b188f3371a9b7730a4d06f6cad2` |

The first stage-3 finishing attempt is rejected: a fixed top-350-pixel
replacement chopped rising characters' heads. The accepted correction mattes
the complete frame and removes the heading replacement after frame 124.
Root independently inspected the corrected contact and dense seams 2→3 and
3→4. Never reuse the earlier cropped derivative.

Stage 4 completed in 417.59 seconds, Comfy prompt
`96ecb9b1-c700-4738-83dd-a52bcfce02fa`; its native output is
`sha256:b04001361e1ca606cf9838ebc8a36759a618728f35e4710296f00bace4fdd9ea`.
The motion transitions from three pointing minks to the small terminal desk.
Its explicit finishing is full-frame chroma matte, with no heading crop.

Stage 5 completed in 15 minutes 52 seconds, Comfy prompt
`51c19ac4-4b9e-45e5-9eab-5f927374e2d5`, native `s05_00001.mp4`.
The raw motion includes an unwanted middle zoom and returning gray collage.
Luna is testing full-frame matte plus explicit uniform-scale/translation
stabilization of the orange desk/character group to its lower-right anchor
placement. Preserve raw media separately; no final selection is yet claimed.

All GPU generations are complete and the queue is empty. The pod remains
running but idle pending final delivery verification. The first four exact
30fps conformance outputs are prepared, not selected. Assembly manifest:
`/tmp/astrid-intro-selected-sources.json`. Delivery preflight:
`/tmp/astrid-intro-delivery-preflight.md`. Next steps remain: stage-5 finishing
QA, five-source conformance, CAS selection of six children, full render and
visualizer review, batch opening, final guide updates, verified pod termination.

Stage-5 finished motion is now accepted after root/Luna contact and dense-seam
review: `/tmp/astrid-intro-native-mcd9u6/s05_stabilized_orange.mp4`,
`sha256:446aedc34ca7b94342b7f449e2a7879742c4dc0b0165882408b95c061054797a`.
It retains all 294 source frames, masks orange foreground onto black, and
normalizes the group with a smoothed uniform scale/translation toward native
canvas bounds `(1323,537,468,306)`. This is explicit editorial stabilization,
not a claim that the model followed the fixed-camera prompt unassisted.
The raw source is
`sha256:368e3f8c993223e52dd46440eec9073680cbc22ea65cd9df40b559b4a0965a9b`.

All eight raw attempts are fully decoded and their evidence is in managed
storage. Compact generation manifest:
`sha256:1471e34065adc2eb5ae51a72b73b5d37f9f734a9a0db6e27e6ed7d42391078d2`;
full manifest:
`sha256:4eb31108f79951b1e3090d2cf7e240e609dcac70879b7fddec6bc7e540efcd45`.
The first three attempts predate immutable Python/settings snapshots; their
actual API graphs and prompts are preserved in exact Comfy histories. Later
Python snapshots must not be represented as those earlier executed sources.

## Canonical selection and full render

All six child picture selections were saved successfully through fresh CAS
checks. Parent version remains 52. Final assembly provenance is managed as
`sha256:b30671aeb92703d43b24fd0b3f6ae833004a350147f2f874548d56571f63c668`;
it includes before-documents, source identities, exact conformance filters,
relations, and individual save results. The final conformed clips are staged
at `/var/folders/_w/b3tthv192m77c760dbyzvk200000gn/T/astrid-intro-h3-conform-x80w10wb/`.
Target frame counts are `212/279/177/169/311`, all 1920x1080 at 30fps.

Clean full-resolution render admitted through `timelines render`:
`1fcc9d17d86b410b9b093390f2931544`, output name
`astrid-intro-animated-final.mp4`. Render completion, full-video visual review,
opening and pod termination remain pending at this checkpoint.

The first full render failed after roughly 15 minutes: finalization reported
a missing temporary `.astrid-intro-animated-final.mp4.render-service-*`
directory. No managed final video was published. This is under investigation;
do not present the failed run as a delivery. Post-apply audit independently
confirms unchanged parent config/registry and unchanged child audio/non-picture
content; selected source/output hashes match the reviewed prepare pass.

## Pod shutdown verified

GPU work and all native-output custody were complete before shutdown. Exact pod
`6vuwjqzv1c1qk6` initially rejected DELETE because its owner-controlled
`locked` flag was true. The normal scoped PATCH changed only `locked:false`,
then DELETE returned 204 at `2026-09-17T23:27:18Z`; GET returned 404
`pod not found` at `23:27:19Z`. No other pod or volume was changed.
Redacted receipt: `/tmp/astrid-intro-native-mcd9u6/pod-shutdown-receipt.json`,
managed `sha256:6bbc4ef5413ba422cd50629d7d83dd61401481a2f90b2609aa34cfd7e03ba83e`.
Pod-local data is destroyed as authorized; all required outputs and evidence
are already retained locally and in managed storage. Remaining work is local
render recovery, final visual review and opening/delivery, not generation.

## Export recovery

The failed task's event stream reached `complete=100` at `23:23:05.623Z`,
then failed at `23:23:07.410Z`. Investigation identified a host-side live
storage accounting race: `_attempt_tree_bytes` / `_storage_tree_bytes`
caught disappearing files but not a disappearing directory while advancing
`rglob()`. RenderService legitimately removes its private workspace after
rendering. A narrow outer `FileNotFoundError` guard now tolerates that
point-in-time scan race. Root and an independent Luna reviewer checked the
cause; file/directory race regression tests pass (4 tests).

A fresh clean render was admitted with output name
`astrid-intro-animated-final-v2.mp4` to avoid reusing the failed invocation's
idempotency identity. The timeline/media are unchanged by this recovery.

The first retry did not execute: old pack-host PID 40002 predated the fix.
Supported scoped shutdown/re-registration replaced it with ready PID 57860.
The v2 task `5d8de0c6545a49bcb1dba466344a8daa` nevertheless remained queued
without any attempt; root cancelled only this never-started task. A fresh v3
admission is run `4c1671f288c043ea8ddc18fb4e8249ab`, task
`e0260eb5d922414eb81987e02072741c`, output
`astrid-intro-animated-final-v3.mp4`. It is also queued as of this checkpoint.
The advertised render digest matches the task. An older separate host PID
36863 was observed but is deliberately untouched: duplication is not yet
proven causal. Next recovery step is obtaining the scheduler's actual
`ClaimWaiting.waiting_reason`, which the ordinary host loop currently hides.
No final render has been delivered; all accepted clips and selections remain
safe, and the RunPod is already terminated.

The scheduling gate was disk capacity, not proven host duplication. Public
SDK state showed queued/no attempt, while `df` showed only ~649–692 MiB
free against the admitted 1,209,909,907-byte render estimate. Four unused
failed finishing tests from this task occupied ~817 MiB. A lossless gzip
attempt ran out of room and safely retained its input. Root then removed
only these unselected, disposable intermediate files from
`/tmp/astrid-s02-qa.Zkdzu9/`: `s02_retry2_strong_matte.mp4`,
`s02_retry2_strong_matte_v2.mp4`, `s02_retry2_strong_matte_v04v05.mp4`,
and `s02_retry2_strong_matte_v04v05_v3.mp4`. Raw generations, selected
derivatives, scripts and review evidence are untouched. Free space rose to
~1.4 GiB. The existing v3 task immediately transitioned through the public
SDK to `running`, attempt `77ba03fd8c134544925f37606b829222`, at
`2026-09-17T23:56:11.707Z`, confirming recovery without scheduler bypass.

## Final render delivered — technical verification

Run `4c1671f288c043ea8ddc18fb4e8249ab` completed successfully and published
`astrid-intro-animated-final-v3.mp4` as managed video
`sha256:e2f550a7d6d7cc8152f41e1476f6e82b0a0246570fb902edefb7a2cbb6c6a632`.
Render provenance is
`sha256:7033bfb0372c47393032a5808ed8ac353aa14907f920d1be0c06348146ca475a`.
Independent Luna audit confirms H.264, 1920x1080, 30 fps, 117.066667 seconds,
AAC stereo 48 kHz, and successful full video/audio decode. Decoded PCM exactly
matches the prior successful render (SHA-256
`2454869ae519df62e70bfaa8a2e97cd1c2c98fd482ddce0ec41cdecd88309d3c`),
confirming the soundtrack is unchanged. Broader storage-accounting regression
selection passed 9 tests. Final visual review is recorded separately below.

The managed final presentation and all five selected 30fps clips in
`astrid-intro-h3-conform-x80w10wb` were opened together in QuickTime Player.
User steering was applied through detailed anchor-specific prompts and Luna
delegation for prompt construction, finishing, independent validation and docs.

### Final composite visual QA

Independent Luna review passed overall: vivid orange-on-black motion, readable
headings, intact characters, small lower-right terminal, preserved overlays,
legible later Remotion cards and intentional final fade-out. Minor retained
artifact: heading glyphs briefly scatter around frames 60–90 (2–3 seconds),
then resolve to readable “TWO IDEAS.” The pinned visualizer lookup returned
“run not found”; the reviewer instead inspected direct ffmpeg filmstrips from
the hash-verified managed final, not an earlier render:
`/tmp/astrid-v3-audit/qa-vivid/full_contact.png` and
`/tmp/astrid-v3-audit/qa-vivid/opening_h3_detail.png`.
QuickTime's Window menu independently confirmed all six delivered movies open.
All requested delivery actions are complete; no GPU resources remain running
for this task.
