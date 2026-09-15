# Pitfall Analysis — 100 Workflow-Problem Scenarios (10-agent swarm)

Skepticism pass: what could go wrong using each scenario in an eval, and what each problem
REALLY tests. Folded into scenario descriptors (`_tags.pitfalls/update_trap/hidden_requirement/eval_value/recommended_grade_mode`).

## Headline

- **45/100 are update-traps** — the recorded fix is 'update/rollback X', not workflow reasoning
- eval value: **high 8 · medium 44 · low 48**
- recommended grading: strict 39 · rubric 46 · multi-sample 15

## Pitfall frequency

| pitfall | count | meaning |
|---|---|--- |
| version-drift | 66 | fix depends on package versions that have moved — may not reproduce |
| outcome-ambiguous | 51 | multiple defensible answers — strict grading unfair |
| trivial | 50 | difficulty overstated; one obvious step |
| gpu-only | 29 | needs GPU runtime to verify |
| unreproducible | 29 | intermittent/hardware-specific |
| env-specific | 28 | fix is a launch-flag/env change for one setup |
| stale-workflow | 23 | workflow references nodes/files gone upstream |
| information-poor | 18 | problem too vague to know what's wrong |
| solution-too-specific | 15 | recorded fix is a one-off hack |
| visual-judgment | 15 | success requires judging generated media quality |

## The 8 high-value discriminators

| scenario | what it really tests |
|---|--- |
| gh-comfyui-15274 | tests whether the solver knows the MiniMax H3 VAE has trained-in tiling (<8GB VRAM design), making VAEDecodeTiled categorically incompatible rather than misconfigured |
| gh-comfyui-ltxvideo-430 | Tests tracing a NaN from the AAC mux back to its latent source: FP8-format LoRA incompatible with the 22B model, or bad sigma values in a two-pass setup — not an ffmpeg/audio-encoder bug |
| gh-comfyui-wanvideowrapper-1094 | Tests understanding of nonstandard node semantics: the Long-I2V WanVideoSampler stores already-decoded frames in the 'latent' dict, so VAE-decoding it is a no-op and saving raises KeyError 'samples' |
| gh-comfyui-wanvideowrapper-1638 | tests whether solver can correctly convert an I2V WanVideoWrapper graph to T2V (drop LoadImage + Image2VideoEncode, swap in WanVideoEmptyEmbeds, switch models/loras) |
| gh-image-to-video-wan-422 | Tests the diagnostic chain: 'missing class_type' -> missing DWPose nodes -> ComfyUI-tbox import failure -> broken/mixed OpenCV (cv2.dnn) install, then repairing the Python env. |
| gh-ltxv-image-to-video-477 | Tests tracing a GGUF dequantization edge case (BF16 non-layer params like learnable_registers left as GGMLTensor) into a loader-level patch, not a workflow edit. |
| gh-workflow-templates-866 | Tests whether the solver inspects node bypass/mute state and follows the image-preprocess path before blaming model weights, precision, or VAE |
| gh-workflow_templates-866 | Identical to gh-workflow-templates-866: tests whether the solver inspects node bypass/mute state and follows the image-preprocess path before blaming model weights or precision |

## Systemic findings

1. **Version-regression scenarios are mostly spent** — kornia/RoPE/SageAttention breaks were fixed upstream months ago; on current installs they won't reproduce. Keep them only as 'historical diagnosis' with pinned-old-versions, or drop.
2. **Near-duplicate clusters inflate the count** — kornia break ×5, RoPE ×4, Minimax-H3-FLF2V ×6 are the same scenario wearing different issue numbers. Dedupe by root cause, not issue id.
3. **Query text leaks fixes** in several cases (#629, #449, #669) — the problem statement names the cause, making the test trivial. Reword queries to strip the diagnosis.
4. **The best discriminators are misattribution + structural-wiring scenarios**: #430 (CUDA error blamed on wrong repo), #553 (missing-node symptom hides import failure), ref-slot miswiring, per-slot vs Batch-Images double-feed. These test reasoning, not recall.
