---
name: runpod
description: >
  RunPod pack — provision GPU pods, execute scripts remotely, pull
  artifacts, and tear down, including a guaranteed-cleanup composite
  session. Requires a RunPod credential through Astrid's resolver.
---

# RunPod

The runpod pack manages ephemeral cloud GPU compute on RunPod: provision pods,
ship and run scripts, pull artifacts, and tear down — with a composite session
executor that guarantees cleanup.

## Executors

| Executor | What it does |
|---|---|
| `runpod.session` | Composite provision → exec → teardown session with guaranteed cleanup. **Preferred for one-shot jobs.** |
| `runpod.provision` | Provision a RunPod GPU pod and emit a pod handle. |
| `runpod.exec` | Execute a script on an existing RunPod pod and download artifacts. |
| `runpod.pull` | Pull artifacts from an existing RunPod pod into local storage. |
| `runpod.teardown` | Terminate a RunPod pod. Idempotent. |

## When to use

- Use `runpod.session` for one-shot GPU jobs that should always clean up.
- Use individual executors (`provision`, `exec`, `pull`, `teardown`) when you
  need manual control over the pod lifecycle.

## When NOT to use

- Do not use for orchestrating LoRA training workflows end to end — use the
  `training` pack, which drives RunPod under the hood.

## Credentials

Local Astrid commands resolve the configured credential reference from the
shared per-user `~/.astrid/astrid.env` file, overridden by an explicit
operation value and then process environment. Compute profiles store only the
reference. CI, containers, and deployed services should inject
`RUNPOD_API_KEY` through their own secret manager. See
[RunPod credentials](../../../../docs/reference/runpod-credentials.md) for the
local setup and replacement path.

## Quick-start

```python
# One-shot session with guaranteed cleanup
import astrid.sdk as sdk
result = sdk.invoke(
    "runpod.session",
    inputs={"script": "./train.py", "gpu_type": "NVIDIA RTX 4090"},
    out="./out",
)

# Manual lifecycle
result = sdk.invoke("runpod.provision", inputs={"gpu_type": "NVIDIA RTX 4090"}, out="./pod_handle.json")
result = sdk.invoke("runpod.exec", inputs={"pod_id": "<id>", "script": "./train.py"}, out="./artifacts")
result = sdk.invoke("runpod.teardown", inputs={"pod_id": "<id>"})
```
