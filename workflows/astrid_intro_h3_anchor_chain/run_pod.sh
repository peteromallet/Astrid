#!/usr/bin/env bash
# Run after canonical prompts have been saved and staged. Appending segments
# retains prior graph IDs/inputs and permits Comfy's warm latent cache reuse.
set -uo pipefail
cd /workspace/vibecomfy-local-fix-20260917-1
export ASTRID_H3_CANONICAL_WORKFLOW=/workspace/astrid_h3/local_workflows/seitanism_h3_av_extension_verified
export ASTRID_H3_PROMPTS=/workspace/astrid_h3/intro-chain-20260917/prompts.json
export VIBECOMFY_CUSTOM_NODES_DIR=/workspace/runpod-slim/ComfyUI/custom_nodes
export VIBECOMFY_MODELS_ROOT=/workspace/ComfyUI/models
run_dir="/workspace/astrid_h3/intro-chain-20260917/${ASTRID_H3_ATTEMPT:-stage-${ASTRID_H3_SEGMENT_COUNT:-1}}"
if [[ -e "$run_dir/result.json" || -e "$run_dir/runner.log" ]]; then
  echo "Refusing to overwrite existing attempt: $run_dir" >&2
  exit 2
fi
mkdir -p "$run_dir"
cp /workspace/astrid_h3/intro-chain-20260917/workflow/workflow.py "$run_dir/workflow.py"
cp "$ASTRID_H3_PROMPTS" "$run_dir/prompts.json"
printf 'segment_count=%s\nsecond_reference=%s\nfuture_reference=%s\nwidth=%s\nheight=%s\n' \
  "${ASTRID_H3_SEGMENT_COUNT:-1}" "${ASTRID_H3_SECOND_REFERENCE:-none}" \
  "${ASTRID_H3_FUTURE_REFERENCE:-source}" \
  "${ASTRID_H3_WIDTH:-1920}" "${ASTRID_H3_HEIGHT:-1088}" > "$run_dir/settings.txt"
python3 -m vibecomfy.cli run /workspace/astrid_h3/intro-chain-20260917/workflow/workflow.py \
  --ready --runtime server --server-url http://127.0.0.1:8188 --deps reuse \
  --runtime-root "$run_dir/runtime" \
  --external-log-locator /workspace/runpod-slim/ComfyUI/user/comfyui_8188.log \
  --no-ensure-models --output-directory /workspace/runpod-slim/ComfyUI/output \
  --json --yes > "$run_dir/result.json" 2> "$run_dir/runner.log"
rc=$?
printf '%s\n' "$rc" > "$run_dir/exit_code"
exit "$rc"
