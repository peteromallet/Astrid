# Eval Run Results — 59 Medium/High Scenarios (DeepSeek-V4-Flash)

**Score: 35/59 = 59%**

Run config: live agentic harness, 6 workers, answer-only lane for diagnosis scenarios
(53) + graph-edit lane (6), 20-min timeout each. Model: deepseek/deepseek-v4-flash-0731 via OpenRouter.

## Failures (5)
- `gh-comfyui-ltxvideo-541` — executor_failure: fail response.ok is False: The model provider is temporarily unavailable. The graph is unchanged.
- `gh-comfyui-wanvideowrapper-1332` — executor_failure: fail response.ok is False: The model response could not be parsed. The graph is unchanged.
- `gh-comfyui-wanvideowrapper-1644` — executor_failure: fail response.ok is False: The model response could not be parsed. The graph is unchanged.
- `gh-comfyui-wanvideowrapper-1745` — executor_failure: fail response.ok is False: The model provider is temporarily unavailable. The graph is unchanged.

## What was fixed to make the eval gradeable
1. `expect_graph_changed` — set false for diagnosis-only scenarios (agent correctly refuses to edit env/version problems)
2. `interaction_mode: answer_only` — required lane for bare non-edit scenarios
3. `answer_guidance` in `desired` — feeds the intent-judge's desired-outcome rubric with the actual fix from the issue thread
