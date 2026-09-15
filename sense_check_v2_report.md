# Sense-Check v2 — Complete 100/100

Update-traps: **33/100** · high-value: **17** · medium 42 · low 41

Recommended grading: strict 43 · rubric 56 · multi-sample 1

## Pitfall frequency

| pitfall | count |
|---|--- |
| version-drift | 48 |
| env-specific | 38 |
| unreproducible | 31 |
| outcome-ambiguous | 29 |
| gpu-only | 24 |
| trivial | 23 |
| stale-workflow | 20 |
| information-poor | 19 |
| solution-too-specific | 19 |
| visual-judgment | 9 |

## All high-value discriminators

| scenario | what it really tests |
|---|--- |
| gh-comfyui-ltxvideo-492 | Trace a TypeError through SamplerCustom/stg.py to a cross-repo API signature mismatch (local apg() vs upstream APG) and apply the exact one-line fix. |
| gh-comfyui-14250 | Attribute a post-update intermittent 'HostBuffer.read_file_slice failed'/CUDA OOM to the pinned-memory change and land the confirmed mitigation (--disable-pinned-memory or GPU-hiding) on a multi-GPU rig. |
| gh-comfyui-ltxvideo-523 | Trace intermittent AAC-encoder NaN/Inf failures to AudioVAE NaNs at awkward sequence lengths amplified by the vocoder, then design a sanitize-at-the-boundary patch (nan_to_num before av.AudioFrame). |
| gh-comfyui-wanvideowrapper-1332 | Inspect the full graph (including a hidden/overlapped VACE module loader) and notice its model selector is empty — then choose main-model-with-VACE vs normal-model+VACE-module correctly. |
| gh-comfyui-gguf-477 | Debug inside third-party GGUF loader code: recognize that packed-BF16 storage dims leak for named non-layer tensors and patch tensor materialization before model load, not the workflow. |
| gh-comfyui-wanvideowrapper-1986 | Separately diagnose (a) unbounded pinned-memory RAM growth on Windows (fix: --disable-pinned-memory + older WanVideo Enhanced BlockSwap node) and (b) sageattn_3/torch.compile conflicts (per_block_mean mode; avoid reduce-overhead on Windows). |
| gh-sageattention-403 | Isolate a hard CUDA-context crash to one SM89 FP8-PV kernel path and A/B to the safe sageattn_qk_int8_pv_fp16_cuda mode. |
| gh-comfyui-wanvideowrapper-2037 | Resist blaming the ROCm stack and instead spot that num_frames:16 violates Wan's 4n+1 frame requirement (use 17+), per a peer's identical-stack evidence. |
| gh-comfyui-wanvideowrapper-1638 | Know exactly which structural changes convert a WanVideoWrapper I2V workflow to T2V (drop LoadImage + Image2Video Encode, swap to Empty Embeds, T2V checkpoints/loras). |
| gh-comfyui-kjnodes-692 | Trace an AttributeError into sageattention 2.x API drift and repair kernel dispatch for sm120 (generic sageattn call or torch.ops.sageattention_qattn_sm89 lookup). |
| gh-comfyui-ltxvideo-443 | Inspect what the conditioning saver actually persists, discover it drops pooled_output and cond_options keys, and restore complete text conditioning (or use fixed save/load nodes). |
| gh-comfyui-ltxvideo-458 | Trace the multimodal guider code path where cfg=1.0 skips the uncond branch, leaving noise_pred_neg unbound for sampler post-CFG hooks, and apply the initialization patch. |
| gh-sageattention-391 | Isolate a Windows driver-level GPU loss (nvlddmkm) to the Sage int8-QK/FP8-PV kernel via a controlled single-variable A/B, then build the confirmed workaround: keep int8-QK, demote V to FP16 and call the sm80 qk_int8_sv_f16_accum kernel. |
| gh-comfyui-wanvideowrapper-1644 | Distinguish a real wrapper-version VRAM regression from stale Triton/inductor caches, and know the missing 'blocks to swap' log line was just removed in a refactor (blockswap still works). |
| gh-comfyui-gguf-444 | Debug a 2.0.0-regression access violation where GGUFModelPatcher.unpatch_model touches mmap'd weight memory during cache cleanup, and reason about why unpatch_weights=False prevents it. |
| gh-comfyui-15643 | Recognize the LTX 2.3 audio-encode/latent-mask lipsync wiring is stale for LTX 2.5 and rebuild the lipsync path with native nodes (per UCHIJ's ported repo). |
| gh-comfyui-wanvideowrapper-2044 | Root-cause a progressive VRAM leak to the _fp8_cache dict keyed by id(context) in WanI2VCrossAttention/WanT2VCrossAttention that is only cleared in __init__, and clear it per prompt in wanvideo/modules/model.py. |
