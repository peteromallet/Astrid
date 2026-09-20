# Astrid Intro: canonical CUDA 13 relaunch, 18 September 2026

## Status

At 11:55:31 UTC the replacement pod `o39r0b17vah9fj` passed the live host
gate: RTX 5090, driver `580.126.20`, CUDA capability `13.0`, 32607 MiB VRAM.
Pinned runtime preparation may proceed. Backend execution, full-size capacity,
creative output and final timeline delivery have **not yet passed**.

User authorized relaunch and regeneration after the failed compatibility detour.
This is a new attempt, not a claim that the remaining transitions are fixed.
The prior pod was terminated and provider absence verified; see
[the previous execution record](astrid-intro-regeneration-20260918.md).

At 11:35:51 UTC, the operator launched pod `t2bwv16uualmsr`: secure RTX 5090,
$0.99/hour, image `runpod/pytorch:1.0.3-cu1300-torch290-ubuntu2404`.
The provider GraphQL placement request explicitly used
`allowedCudaVersions: ["13.0"]`. This first pod never exposed a usable runtime
and was terminated (DELETE 204, provider list verified empty).
Safe handle: `out/sessions/astrid-continuity-20260918-cuda13/pod_handle.json`.

One replacement launched at 11:53:02 UTC with the same placement constraint
and $0.99/hour quote, using a smaller verified official CUDA 13 base image.
Its safe handle is
`out/sessions/astrid-continuity-20260918-cuda13/pod_handle-replacement.json`.
SSH and host verification completed approximately 2 minutes 29 seconds later.
The first image tag was valid, but its 9.02 GB compressed size was a possible
startup factor, not a proven cause: the provider exposed no image-pull events.

The admission cap is four hours / approximately $5 total, with a maximum accepted
hourly quote of $1.25. The original deadline remains 15:35:51 UTC. The first
watchdog was retired after its pod's verified termination. The replacement
foreground watchdog parent/sleep PIDs 98435/98438 in execution session 66417
were verified live; exact-pod teardown is scheduled around 15:35:25 UTC. Explicit
teardown and provider absence must still be recorded at completion.

## Why this retry differs

The first failure was a host CUDA 12.8 versus canonical CUDA 13 mismatch.
Later OOMs occurred on an adapted fallback stack; they are separate evidence,
not proof that CUDA caused every memory failure or that a matched 5090 will fit.
This attempt must not inherit the prior runtime math patches.

Required gates, in order:

1. Verify actual host driver CUDA capability before large downloads.
2. Restore pinned canonical Torch cu130, Comfy-kitchen and CK attention in a
   separate relaunch recipe, preserving the old attempt's recipe and evidence.
3. Verify active backend and a small end-to-end output/decode.
4. Run the production-shape 1920×1088, 260-native-frame, one-step capacity
   diagnostic, including output decode. This is not creative acceptance.
5. Generate the six-stage chain using the existing reviewed prompts and
   anchors, with 39 native latent continuation frames. Review raw output and
   seams before selection; regenerate content failures rather than masking,
   stabilizing or transforming them away.
6. Import accepted sources, preserve narration and timing, select through the
   Astrid SDK with fresh version checks, and render/verify review mode.
7. Preserve receipts and outputs, terminate the exact pod, verify absence.

The existing timeline currently contains only the previously accepted new
opening (b01); the remaining pictures are still the old versions. Its completed
partial review is not the final six-stage delivery.

## Durable operating instructions

- [RunPod lifecycle](runpod-lifecycle.md): placement, budget, custody, teardown.
- [Anchor continuations](anchor-to-anchor-video-generation.md): compatibility,
  capacity, native context, raw visual acceptance and timeline handoff.

Append observed readiness, diagnostic results, generation receipts, selection,
review render and teardown evidence below as they occur.

## Runtime execution milestones

At 11:55:31 UTC the replacement host passed the mandatory gate: NVIDIA driver
580.126.20, host CUDA 13.0, RTX 5090, and 32,607 MiB VRAM. No large dependency
transfer began before this observation.

The isolated runtime then matched the canonical declaration without carrying
forward any prior runtime patches: ComfyUI commit
`ee71d5c4993f29086b27fde1629a945ae48425bf` / 0.36.0, Torch
2.10.0+cu130 reporting CUDA 13.0, comfy-kitchen 0.2.34, comfy-aimdo 0.5.3,
H3 custom node `361624fb406b63eb6694442eac6c895fc1533a70`, and VHS
`4ee72c065db22c9d96c2427954dc69e7b908444b`. The server launched only with
`--use-ck-attention --disable-comfy-compiler`; its startup log reports the CUDA
kitchen backend available and `Using Comfy Kitchen attention`.

All five canonical model assets were downloaded remotely and received
per-file SHA-256 receipts. Their observed sizes were 605,254,808;
1,956,193,000; 2,811,065,184; 20,970,379,616; and 27,141,342,152 bytes.
No model file was copied to the low-space local workstation.

The first compile stopped before queueing because the staged source transport
had omitted VibeComfy's authoritative `custom_nodes.lock`. The matching local
lock was then staged with SHA-256
`7741945b99176bedf97fd14009539156ccccde41c3cbe4f03b9f26df0ccead42`;
its H3 and VHS records match the commits above. This was a custody/transport
correction, not a workflow or runtime compatibility patch.

The small end-to-end smoke passed as VibeComfy run
`run-1789733451-b8ac9361`, prompt
`97130c95-229b-4036-99a5-1dfa3380277a`: 1920x1088, five frames, one sampling
step, CK sampling plus VAE decode in 14.13 seconds. Full `ffmpeg -xerror` decode
also passed. The production-shape native-context capacity diagnostic was then
admitted on the same server: exact s01 175-frame starter followed by exact s02
260-frame continuation with 39-frame generated context, both at 1920x1088 and
one sampling step. It is diagnostic evidence only, not a creative take.

That production-shape diagnostic passed as VibeComfy run
`run-1789733667-ffc544e7`, prompt
`a1b90152-75db-46d5-9f39-b9fb91a6416d`, in 165.05 seconds. It produced the
175-frame starter and 260-frame native-context continuation without OOM or
runtime error; full `ffmpeg -xerror` decode passed for both MP4 files. The
successful one-step diagnostic does not establish creative quality. After this
gate, exact creative s01 (175 frames, eight steps, seed 2026091801) was admitted
on the same server. Later creative stages remain subject to raw review and the
current anchor-continuity decision.

Creative s01 completed as VibeComfy run `run-1789734026-bd0aeb55`, prompt
`ea4e992c-fb92-46e7-8530-f56f5d900169`, in 340.74 seconds. The locally
preserved raw MP4 is
`out/sessions/astrid-continuity-20260918-cuda13/s01/out/output/s01_00003.mp4`
with SHA-256
`16202ca9babb963859d841ef58974dd663e930ab19587c3f211b3f87f5cfc73e`.
It is 1920x1088, 24 fps, 175 frames / 7.291667 seconds, and passed full local
`ffmpeg -xerror` decode. Raw visual acceptance remains a separate gate; no
creative s02 was queued at this checkpoint.
### 2026-09-18 13:13 UTC (15:13 Europe/Berlin) — bounded s02 retry rejected and pod terminated

The original creative s02 completed technically but was rejected visually: its
black negative space became a dense grayscale photographic paper/portrait
collage. A single bounded diagnostic retry restored the v04 source anchor as
the appearance reference while preserving the exact seed, prompt, v04/v05
endpoints, 39-frame native context, eight steps, CUDA 13/CK runtime, and warm
s01 cache. That retry (`run-1789736183-8d34dff5`, Comfy prompt
`5874fccd-7d11-4abf-ab5b-b294c75c4a1f`) also produced the collage and was
rejected. Its raw MP4 is
`out/sessions/astrid-continuity-20260918-cuda13/s02-source-retry/out/output/s02_00003.mp4`
(SHA-256 `ea53e5a33ab4b92641d41ada52586c72f2f8de81321d30252624e3de9a78ecce`)
and its contact sheet is the sibling `qa/contact.jpg`.

The source-reference-only change did not resolve the defect; two samples are
not enough to prove a single cause. Timeline assembly and the old finish
scripts were not used in either raw take, and both takes decoded cleanly on
the verified CUDA 13 runtime. A plausible but not yet proven prompt-level trigger is the request
for "document" icons combined with a negative-style sentence inside the same
positive-only BasicGuider conditioning ("no grayscale collage,
photographic/document background"). Both clauses name the unwanted semantic,
and H3 repeatedly expanded it into photographic papers and portraits. The next generation attempt should
remove that semantic entirely and describe only the exact abstract orange
pixel geometry visible in the destination anchor; if needed, split this long
260-frame change with a deliberately authored clean midpoint anchor. It should
not repair the rejected raw with masks, crops, crossfades, or transforms.

No later creative segment was admitted. Exact pod `o39r0b17vah9fj` was
terminated at 13:13:06 UTC / 15:13:06 Europe/Berlin (`DELETE` 204), and an authenticated provider list
immediately returned `[]`. The owned deadline watchdog processes were then
stopped. The network volume was not deleted.
