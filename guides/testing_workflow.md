# End-to-end H3 masking test on RunPod

Prepared 11 September 2026. This is an execution plan, not a completed generation.

## Result to deliver

Generate one Morpheus dialogue replacement saying **“You have two options.”**, using the original voice and footage around the edit as context. Download and verify the result, import it into the existing `matrix-minkhole` Astrid project, render and open a separate review timeline with subtitles, then terminate the RunPod pod and verify termination. Preserve `rough-cut`, its v23 render, source media and revision history.

The first test is dialogue inpainting. A continuation test is a follow-up after this passes; it must not expand the scope or keep the GPU running indefinitely.

## API and existing integration

- Credential name: `RUNPOD_API_KEY`. Resolve it from the existing configured integration; never copy its value into this plan, logs, command arguments or Git.
- Lifecycle implementation: [`runpod-lifecycle`](../../runpod-lifecycle/README.md), particularly `RunPodConfig.from_env()`, `launch()`, `Pod.wait_ready()`, `Pod.exec_ssh()` and `Pod.terminate()`.
- VibeComfy integration: [`scripts/runpod_runner.py`](../../vibecomfy/scripts/runpod_runner.py), including `run_pod_detached()`, artifact collection and termination handling.
- Found configured credentials in `runpod-lifecycle/.env`, `reigh-worker-orchestrator/.env`, and `reigh-worker/.env`. Their parsed values match. Other checked shell, app and Keychain locations yielded no usable alternate; `~/.runpod/config.toml` contains a placeholder-like value. Do not print or reproduce any key.
- Verified API routes: GraphQL `https://api.runpod.io/graphql`; REST `https://rest.runpod.io/v1/pods` and `/v1/networkvolumes`; authentication is `Authorization: Bearer <RUNPOD_API_KEY>`. Both authenticated GraphQL queries and both REST endpoints returned **401** with the configured key. The integration exists and the credential was found, but it is currently rejected. Refresh the existing credential, then repeat read-only authentication before provisioning. Do not confuse a rejected key with a missing integration.
- Do not use `runpod_acceptance.py`: it is a retired refusal-only entry point. Do not run the whole corpus matrix or the generic smoke's old ComfyUI 0.26 pin for this H3 test.

## Exact workflow and prepared inputs

Upstream workflow: [LanPaint MiniMax H3 AV inpainting](https://github.com/scraed/LanPaint/blob/master/example_workflows/MiniMax_H3_AV_EncodeDecode_Inpaint.json). The original inspected graph is pinned at LanPaint commit `32cf848e93971da380d868936e007f5611218bee`; its saved JSON hash is `2dd64fe26c42281962e434841c458cc935b1d1858e83093b882bbaeb02dc3121`.

- Editable builder: [`MiniMax_H3_AV_EncodeDecode_Inpaint.py`](../../vibecomfy/comfy-inspection/MiniMax_H3_AV_EncodeDecode_Inpaint.py).
- Pilot recipe: [`recipe_v1.py`](../runs/matrix-minkhole/h3-pilot-20260911/recipe_v1.py).
- Input directory: [`h3-pilot-20260911`](../runs/matrix-minkhole/h3-pilot-20260911/).
- Canonical original source: `sha256:059624abaab9d27a3d9901e0c78961cc10c995890ecd200f254a9cbb1612cba7`.
- Prepared clip: `canonical-source-grid-52-61.416667s-226f-24fps.mp4`, source interval 52–61.416667 seconds, 1920×1080, 226 frames at 24fps, with original audio. Hash: `432e119055a58f9b1059660efd36961b4cccc1d61f7542d2d57daf1d44828c88`.
- Replace audio only at clip-local **3–8 seconds**. Preserve original context before and after. Temporary Astrid narration is not the source voice.
- Video masks: black/preserve at frames 0 and 71; mouth mask at 72 and 191; black at 192 and 215. Last source frame is 225; confirm the editor holds the final black mask to the end. Mask value 1 regenerates, 0 preserves. PNG filenames must resolve in ComfyUI's input directory.
- The H3 duration control of 9 seconds quantizes to 226 frames in this graph. Keep the measured input and generated lengths aligned; do not substitute a nominal nine-second, 216-frame clip.
- Evidence: [`source-extraction-v3.json`](../runs/matrix-minkhole/h3-pilot-20260911/source-extraction-v3.json), [`schema-diagnostics-v1.json`](../runs/matrix-minkhole/h3-pilot-20260911/schema-diagnostics-v1.json).

## Execute

1. **Verify credentials and record the run.** Use the supported RunPod client to list pods and query available GPU capacity. Confirm successful authentication, record the selected credential *location* only, and create a local execution record with a unique test ID. Provision a dedicated test pod so cleanup cannot terminate someone else's machine. Record its exact pod ID immediately after creation.

2. **Choose adequate resources before launch.** The selected files total approximately 54 GB: diffusion `minimax_h3_fl2va_pruned_fp8_scaled.safetensors` (~21 GB), text encoder `qwen3vl_32b_minimax_h3_int8_convrot.safetensors` (~27 GB), video VAE `minimax_h3_video_vae_fp16.safetensors` (~5.2 GB), and audio VAE `minimax_h3_audio_vae_fp32.safetensors` (~0.6 GB). Allocate at least 100 GB usable model/work space plus adequate container space; inspect any existing `Peter` network volume before reusing it. Never delete its contents. Verify GPU/RAM compatibility with these exact quantizations; the configured RTX 4090 is a candidate, not a proven fit. Query current prices and choose the smallest supported configuration. Use a two-hour total watchdog and at most one corrective generation retry.

3. **Launch through `runpod-lifecycle`.** Use the existing integration and a uniquely named pod. Establish SSH, confirm CUDA/GPU/RAM/free disk, and install the compatible ComfyUI and LanPaint versions. Record exact commits and package versions. Do not assume that merely having H3 core nodes means LanPaint is installed. Download the four exact model files to the remote model directories, verifying sizes and available published hashes. Keep downloads off this Mac.

4. **Stage the Python workflow and media.** Upload the builder, recipe, source video and masks. The current recipe contains an absolute local builder path: replace that path in the staged recipe with its remote sibling path and record the change. Put mask PNGs and source video under the server's input directory. Retain the original recipe and workflow hash locally. Do not upload `.env` files, unrelated project media or local environments.

5. **Validate against the real target.** Start ComfyUI and capture its authoritative `/object_info`. Confirm `MiniMaxH3ImageToVideo`, `LanPaint_VideoMaskEditor`, `LanPaint_SamplerCustomAdvanced`, `LanPaint_AVEncode`, `LanPaint_AVDecode`, and a `CLIPLoader` supporting `minimax`. Refresh VibeComfy schema evidence from that target and run `load_bundle`, validation and approved bundle compilation. Raw `VibeWorkflow.compile("api")` already succeeds locally, but approved bundle compilation currently blocks on missing schemas; raw JSON emission is not permission to bypass that gate. Verify model selections, mask paths, input dimensions, frame count and audio intervals in the compiled graph.

6. **Run one generation.** Start with the inspected baseline: 864×480 output, 20 base steps, five LanPaint inner steps, Euler/simple, denoise 1, seed `20260911`, blend overlap 7, audio crossfade 0.02. These are experiment settings, not established best settings. Verify that the builder actually emits each value. Use the exact replacement dialogue in the H3 prompt, keeping identity, sunglasses, hands, chair, camera and room tone stable. Queue through VibeComfy's supported server/runtime route; save prompt ID, compiled graph, logs and output paths. Poll until success, a concrete failure, or the watchdog deadline. If a correction is justified, change only the failed setting and keep both attempts.

7. **Collect and verify before deleting the pod.** Download generated video/audio, workflow, source hashes, model/version manifest, masks, logs and run metadata. Verify remote/local SHA-256 agreement, nonzero file sizes, full decoding, audio presence and duration. Watch the entire short clip with sound. Check exact wording, speaker similarity, lip movement, identity, the preserved context and both edit boundaries. Inspect adjacent frames and listen for clicks, missing words, duplicated dialogue or voice changes. A completed task alone is not a passing creative test. Record `pass`, `needs_revision` or `failed`, with evidence.

8. **Deliver through Astrid.** Import the generated output as managed media into `matrix-minkhole`. Create a separate `h3-dialogue-pilot-<test-id>` timeline, leaving `rough-cut` unchanged. Add the intended line as correctly timed review subtitles, render with `--review`, open the exact successful render, and record its run ID and output digest. Provide both the raw generated clip and review render. Use local downloaded media for this step; no GPU is needed while the user watches.

9. **Terminate and verify.** Call `await pod.terminate()` for the exact test pod, then query the RunPod API until it confirms that pod is gone/terminated. Save the response and timestamp in `termination.json`. Stopping ComfyUI, closing SSH, or exiting the Python process does not count as terminating the machine. Never delete the network volume or unrelated pods.

## Cleanup on failure or interruption

The execution wrapper must own the pod ID in a `try/finally` block. On success, download, verify and deliver before termination. On any error, cancellation or timeout, make one bounded attempt to retrieve outputs/logs and then terminate in `finally`; do not keep billing while waiting for feedback. If Astrid review rendering fails after the output is safely downloaded, terminate the pod and finish the local review afterward.

Configure an independent maximum-lifetime guard before long downloads/generation. Verify the integration's watchdog is armed; the local `finally` block alone cannot clean up after a dead laptop. After a restart, reconcile the recorded pod ID with the API and clean up that exact test pod. If the termination API fails, record the failure, retry with a bounded backoff and explicitly report an unconfirmed running pod rather than claiming cleanup succeeded.

The existing detached runner sets `terminate_after_exec=True`. Check its collection/termination ordering before reuse: it may collect and terminate before the later local Astrid delivery. For the user's requested strict success order, use the lifecycle primitives to retain ownership through delivery, with the same failure/watchdog cleanup. Do not assume the generic wrapper's default artifact list includes the generated clip; name the required output paths explicitly.

## Completion record

Save `result.json` alongside the pilot with: source/recipe/model hashes, settings, prompt ID, pod ID, generation outcome, local artifact paths and hashes, review run ID, quality findings, termination confirmation and timestamps. The test is complete only when the result is delivered **and** pod termination is confirmed. If authentication or GPU setup prevents execution, report `blocked`; never describe this preparation as a generated result.
