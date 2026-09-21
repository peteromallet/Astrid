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

For a prepared existing pod, the standalone `runpod-lifecycle run POD_ID
--script /path/to/job/run.sh --keep-pod` is the practical upload/execute/fetch
path. It does not create Astrid task history. See the
[operator guide](../../../../guides/spinning-up-and-executing-tasks-on-runpod.md)
for verified behavior, storage checks, timeout limits and current native
integration prerequisites.

For native invocation, use a connected client and the manifest's exact input
names. `runpod.exec` accepts `pod_handle` and `remote_script`, not `pod_id` and
`script`. The claim waiter's smaller handle is not a provision handle.

```python
from astrid.sdk import AstridClient

with AstridClient.open_from_launcher() as client:
    result = client.invoke_result(
        "runpod.exec",
        kind="executor",
        project="<selected project>",
        inputs={
            "pod_handle": "/path/to/astrid-provision-pod_handle.json",
            "local_root": "/path/to/job",
            "remote_script": "/path/to/job/run.sh",
            "remote_root": "/workspace/unique-job-id",
            "timeout": 900,
            "upload_mode": "sftp_walk",
        },
        wait=True,
    )
    if not result.ok:
        raise RuntimeError(result.error)
```

Verify managed output settlement; successful remote exit alone does not prove
artifact delivery. `runpod.exec` leaves the pod alive; `runpod.session`
terminates it. Keep-running timeout currently stops local polling, not remote
inference, so bound the owned workload separately. Do not run concurrent
detached lifecycle jobs on one pod until their shared temporary paths are fixed.
