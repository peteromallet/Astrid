# Spinning up and executing tasks on RunPod

## Choose the path that exists today

For “use this pod, upload a job, run it, collect results, keep the pod”, use
`runpod-lifecycle run POD_ID --keep-pod`. This path was live-tested on the
existing storage-backed RTX 5090 on 2026-09-21. It does not need the Astrid
workspace runtime or an Astrid generic worker installed on the pod.

Astrid's `runpod.exec` wraps the same library runner, adding Astrid admission,
project/task receipts, artifact handling and cost records when invoked through
a working Astrid runtime. Its local executor controls the remote workload over
SSH.

For a generation that must become an Astrid task and Generation, use the
canonical task path below. A pod being reachable or a VibeComfy file existing
on the pod is not success; success requires task settlement, a managed output
association, a Generation record, and a verified local download.

## 1. Resolve the exact pod and existing storage

Read-only inventory:

```bash
runpod-lifecycle volumes ls --json
runpod-lifecycle list --json
```

Use the shared credential setup in [RunPod credentials](../docs/reference/runpod-credentials.md).
If the credential wrapper is installed:

```bash
astrid-with-credential --provider runpod -- runpod-lifecycle list --json
```

From this Astrid checkout, the equivalent wrapper is:

```bash
.venv/bin/python -m astrid.core.util.credential_exec \
  --provider runpod -- runpod-lifecycle list --json
```

The child lifecycle executable must be installed and its RunPod SSH identity
configured. Astrid's virtualenv and the lifecycle CLI may use different Python
environments; a working CLI does not establish Astrid executor dependencies.

Compare the pod's provider-reported networkVolumeId with the resolved volume ID.
The current normalized status omits that field, and list can return null when
the upstream SDK omits it. Null is not proof of absent storage: use an
authenticated provider GET /v1/pods/<pod-id>, printing only the needed fields.
Never print credentials or raw status containing SSH passwords.

For the reviewed pod, direct provider observation confirmed:
pod `8f18jbuh81vko9`, volume `sfak8553dy` (`backup`, 250 GB),
mount path `/workspace`, container disk 200 GB. SSH independently confirmed
`/workspace` as a mounted filesystem. Recheck these facts before later jobs.

`get_pod(pod_id, config)` resolves an existing pod; it does not attach or replace
a volume. Passing storage_name while reusing a pod does not enforce an attachment.
A mismatch must fail before upload. Never “repair” it by silently creating a pod.

## 2. Stage and execute a bounded job; leave the pod running

Put only this job's script, workflow and required input files in a dedicated
local directory. The CLI uploads the script's parent directory recursively.
Do not put the script at a repository root or beside credentials, large caches,
or previous downloaded artifacts.

```bash
runpod-lifecycle run 8f18jbuh81vko9 \
  --script /absolute/path/job/run.sh \
  --remote-root /workspace/unique-job-id \
  --upload-mode sftp_walk \
  --timeout 900 \
  --keep-pod \
  --json
```

Use a fresh simple remote path with no spaces or shell metacharacters. For
sftp_walk, its parent must already exist; /workspace/<unique-job-id> works.
Do not use tarball upload against /workspace, a model directory, or any shared
release: the current tarball implementation removes and replaces remote_root.

The script is the workload entry point, not an attach/worker-registration wrapper.
For a prepared Comfy environment it can run the existing VibeComfy workflow.
Validate the workflow, inputs, models, nodes and environment before inference.

Equivalent existing library API:

```python
pod = await get_pod(pod_id, config)
await pod.wait_ready(timeout=60)
result = await ship_and_run_detached(
    pod=pod,
    remote_script=script_text,
    local_root=job_directory,
    remote_root="/workspace/unique-job-id",
    timeout=900,
    terminate_after_exec=False,
)
```

Current operational limits:

- The CLI defaults to termination unless --keep-pod is supplied. Astrid
  runpod.exec passes terminate_after_exec=False internally.
- timeout bounds the runner's polling phase, not all upload/download time.
  On timeout it returns 124 without stopping the remote job in keep-pod mode.
  Put a tested process-level deadline in the workload, e.g. GNU
  `timeout --kill-after=5s 840s <command>`. A client timeout does not cancel
  work queued into an independently running Comfy server; that requires
  cancellation of the owned prompt/session and verification.
- Only one detached lifecycle job may run on a pod at a time: script, log,
  exit-marker and artifact archive names under /tmp are currently shared.
- Detached inference can outlive the caller. There is no durable task-manager
  recovery or deadline guarantee in this standalone command.
- --json currently prints progress lines before its final JSON summary. Do not
  feed all stdout directly into json.loads. Preserve the log and parse the
  final object, or use the typed library return value.

## 3. Collect and verify results

The detached runner collects only remote_root/out and remote_root/output into
the local script directory's artifacts/ folder. Arrange for the workload to
put intended outputs there; for an external Comfy server, explicitly copy its
owned prompt outputs there. Use the existing fetch/pull tools for other paths.

Require all of: returncode=0, terminated=false, expected nonempty downloaded
files, matching hashes, and full decode/frame checks for media. Download failure
can currently leave the remote exit code at zero; no error code alone proves
delivery. The detached result's stdout/stderr are not a complete workload log;
write relevant workload logs into out/ as well.

Standalone downloaded files are not Astrid managed objects and create no Astrid
task history. If project custody is required, import selected results through
`python -m astrid media import <file> --project <project> --json` on a working
runtime. That records media ingestion; it does not retroactively establish a
managed generation task or a scheduler execution binding.

## 3a. Run the continuation-guide test

For an H3 continuation test, use
[Anchor-to-anchor video generation](anchor-to-anchor-video-generation.md) for
the graph and context rules, and use this lifecycle path for transport and
pod custody. The continuation test is a workload script submitted to an
existing pod; it is not a new worker-registration path and it must not call
the old watcher that provisions or tears down pods.

Use the following bounded sequence:

1. Start with a one-segment, one-step capacity smoke using the production
   graph and the longest admitted shape (`1920x1088`, `260` native frames).
   This checks model loading, node resolution, backend selection and memory
   without spending the time required for a creative take.
2. If that passes, run the reviewed starter/continuation prefix: a `175`-frame
   starter followed by a `260`-frame continuation. Keep the same ComfyUI
   server and workflow graph, and pass the generated AV latent edge directly
   into the continuation with its `39` native context frames.
3. Download both raw outputs into the job's `artifacts/` directory. Verify
   dimensions, frame counts, decodability, hashes and the continuation seam.
   Do not decode an MP4 and feed it back as continuation context.

The existing storage-backed pod and release currently used for this test are:

```text
pod:     8f18jbuh81vko9
storage: backup / sfak8553dy mounted at /workspace
release: /workspace/h3-golden/releases/h3-cu130-v1-candidate
bundle:  /workspace/astrid-continuity-20260918
```

Historical scripts in the continuity bundle use `/opt/astrid-continuity-20260918`;
that path is not present on the current pod. Adapt them to the mounted
`/workspace/astrid-continuity-20260918` path inside the submitted job instead
of running them unchanged. In particular, do not treat an old result or PID
file on the persistent volume as evidence that the current server is alive.

Submit the bounded workload through the canonical lifecycle runner and leave
the existing pod running:

```bash
runpod-lifecycle run 8f18jbuh81vko9 \
  --script /absolute/path/to/continuation-job/run.sh \
  --remote-root /workspace/jobs/h3-continuation-<utc-stamp> \
  --upload-mode sftp_walk \
  --timeout 900 \
  --keep-pod \
  --json
```

The job script should start or reuse only its owned loopback ComfyUI process,
wait for `/system_stats` or `/object_info`, run VibeComfy against that server,
write logs and a result manifest under `out/`, and copy intended media under
`output/`. Put a process-level deadline inside the script as well as the
runner timeout. A passing transport result is not an H3 result: the release
must still pass the CUDA/Torch, custom-node, model, backend and capacity gates
in [RunPod lifecycle](runpod-lifecycle.md). At the time of this review, the
candidate venv was missing Torch while the provider Python exposed
`torch==2.4.1+cu124`; that mismatch is a fail-closed preflight finding, not a
successful continuation run.

## 4. Canonical Astrid task path on a prepared RunPod pod

The prepared pod needs a registered Astrid `GenericPackHost` for
`vibecomfy.run`, connected to the same Runtime that admits the task. The host
claims the task, runs VibeComfy, stages the result, and settles it. Keep the
RunPod handle and task id in the receipt so the result remains traceable.

Create the task through Astrid, rather than calling ComfyUI directly. Put the
generation intent at the admission level. Its `metadata` object is the light
association layer for caller labels such as `shot_id`; Runtime copies it to
the Generation published by the task. The raw `tasks create` route also needs
the generic `generation.publish_v1` settlement effect. The higher-level SDK
invocation route composes that effect from the registered capability, so this
is publication metadata, not an H3 adapter.

```bash
# Replace the angle-bracket placeholders with the claimed pod, project, and
# managed workflow object before running this command.
cat > /tmp/task-spec.json <<'JSON'
{
  "inputs": {"workflow": {"digest": "sha256:<workflow-object>"}},
  "input_digests": [{"name": "workflow", "digest": "sha256:<workflow-object>"}]
}
JSON

cat > /tmp/generation-intent.json <<'JSON'
{
  "version": 1,
  "modality": "video",
  "partial_success_policy": "reject",
  "groups": [{
    "group_key": "main",
    "selectors": [{
      "selector": "main-0",
      "ordinal": 0,
      "variant_key": "original",
      "required": true
    }]
  }],
  "metadata": {
    "shot_id": "shot-17",
    "scene_id": "scene-3",
    "take": 2
  }
}
JSON

cat > /tmp/generation-effect.json <<'JSON'
{
  "effect_type": "generation.publish_v1",
  "target_id": "<project-id>",
  "payload": {
    "version": 1,
    "modality": "video",
    "generation_type": "vibecomfy.run",
    "metadata": {"shot_id": "shot-17", "scene_id": "scene-3", "take": 2},
    "partial_success_policy": "reject",
    "groups": [{
      "group_key": "main",
      "selectors": [{
        "selector": "main-0",
        "ordinal": 0,
        "variant_key": "original",
        "required": true,
        "output_port": "vibecomfy_run"
      }]
    }]
  }
}
JSON

python3 -m astrid tasks create --project <project-id> \
  --capability vibecomfy.run \
  --spec "$(cat /tmp/task-spec.json)" \
  --input-manifest '["sha256:<workflow-object>"]' \
  --generation-intent "$(cat /tmp/generation-intent.json)" \
  --settlement-effect "$(cat /tmp/generation-effect.json)" \
  --execution-request '{"target":{"kind":"runpod","pod_id":"<claimed-pod-id>","provider_account_ref":"runpod-default"},"lifecycle":{"mode":"leave_running"},"limits":{"max_queue_seconds":300,"max_runtime_seconds":1800}}' \
  --idempotency-key "generation-<unique-key>" \
  --json
```

The effect's `target_id` must be the same project id passed to the command. For
a capability whose primary output port differs, use that declared port in the
generic effect. Do not put `generation_intent` inside `spec`: that makes it
opaque executor input and does not publish a Generation. If using
`client.invoke_result("vibecomfy.run", kind="executor", ...)`, pass the intent
in `inputs`; the SDK validates it and composes the same settlement effect.

Follow the returned `task_id` until it is `succeeded` or `settled`. Then read
the task's managed output associations and the Generation created by the
`generation.publish_v1` settlement. Download each selected object through the
Runtime object API, verify its SHA-256 and media decode locally, and only then
terminate the exact pod id:

```python
from astrid.sdk import AstridClient

with AstridClient.open_from_launcher() as client:
    task = client.tasks.show("<task-id>")
    outputs = client.tasks.list_managed_outputs("<task-id>")
    generation_rows = client.generations.list("<project-id>")
    data = client.media.read_bytes(outputs.data[0]["object_id"])
```

The task id, attempt id, output association, Generation id, `shot_id`, local
path, byte count and digest belong in the receipt. A direct Comfy/VibeComfy
smoke is useful diagnosis, but it does not replace this task-to-Generation
check.

The acceptance run on 2026-09-22 used task
`2e61fe96ac544d1c96e85800c24b2850`, published Generation
`generation-5f60f79456bb0309c8c394f765e219f7ebcb9ca343765fc74ba3d9e0c6f0cf6c`,
verified two decoded MP4 outputs locally, and terminated the claimed pod. The
local receipt is kept under
`Astrid/.otto/runs/astrid-runpod-task-queue-20260918/artifacts/managed-generation-8step-20260921-r5i/`.

## 5. Astrid-native lifecycle invocation

Use the connected SDK and exact manifest input names:

```python
from astrid.sdk import AstridClient

with AstridClient.open_from_launcher() as client:
    result = client.invoke_result(
        "runpod.exec",
        kind="executor",
        project="astrid-intro",
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

This API exists, but this review did not live-verify the native wrapper.
Its prerequisites differ from the proven standalone CLI:

- Use the handle emitted by runpod.provision. The current
  5090-backup-pod.json has schema astrid.runpod.claim.v1 and lacks the
  config_snapshot and hourly_rate expected by runpod.exec. Do not pass it
  unchanged or invent account/cost fields. Use its exact pod_id with the
  lifecycle CLI until canonical handle resolution is added.
- Astrid doctor must pass with matching installed runtime/client contracts.
  The reviewed Astrid .venv cannot import runpod_lifecycle; ensure the actual
  executor environment has the required package before invocation.
- The current RunPod executor network manifest admits API HTTPS destinations,
  while the library uses direct Paramiko SSH. The generic host's broker/sandbox
  path must support and admit that resolved SSH destination. This remains an
  integration concern, not a reason to bypass the sandbox.
- Require successful Runtime settlement and visible output digests, not merely
  an exec_result.json or a local download directory. The task capability here
  is runpod.exec; it is not a remote vibecomfy.run task.

## 6. New pods, only when requested

For the prepared H3 release, use the repository claim waiter. It is a thin
operator wrapper around the canonical lifecycle launch path: it preserves the
existing `backup` volume, requests the validated CUDA-13 image/host profile,
waits for SSH readiness, verifies the mounted release venv with a real CUDA
initialization, and terminates an allocated pod that fails that preflight.
It leaves a passing pod running and prints a secret-free lifecycle handle.

```bash
python Astrid/scripts/claim_runpod_5090_backup.py \
  --gpu-type "NVIDIA GeForce RTX 5090" \
  --storage-name backup \
  --container-disk-gb 200 \
  --image "runpod/base:1.0.3-dev-fix-pytorch-version-verification-cuda1300-ubuntu2404" \
  --allowed-cuda-versions 13.0 \
  --handle-path /absolute/path/h3-cu130-pod-handle.json
```

Do not omit the image or CUDA constraint for this release: the generic
`runpod-torch-v240` default is Torch 2.4/CUDA 12.4 and is not an H3 target.
The claim handle is lifecycle-oriented; normalize it through the canonical
`runpod.provision` contract before passing it to Astrid `runpod.exec`.

The equivalent raw lifecycle launch command is:

```bash
runpod-lifecycle launch --gpu-type "NVIDIA GeForce RTX 5090" \
  --storage-name backup --container-disk-gb 200 \
  --image "runpod/base:1.0.3-dev-fix-pytorch-version-verification-cuda1300-ubuntu2404" \
  --allowed-cuda-versions "13.0" --detach
```

Use the installed CLI help to verify flags. The reviewed current checkout
supports --allowed-cuda-versions. Pin existing volume size if a launch
configuration could otherwise resize it; the claim script does this. After
launch, the release path is
`/workspace/h3-golden/releases/h3-cu130-v1-candidate/runtime/venv/bin/python`
and the Comfy entrypoint is
`/workspace/h3-golden/releases/h3-cu130-v1-candidate/runtime/launch-comfy.sh`.
Do not use --probe-only: it claims and terminates a pod.

The Astrid equivalent is runpod.provision followed by runpod.exec. Provision
leaves the pod running; runpod.session intentionally tears it down and is not
the keep-running route. Never delete the backup volume during pod cleanup.
Keeping a pod running continues provider billing; runner timeout is not a
pod-lifetime limit.

## Live review and H3 boundary

The 2026-09-21 bounded transport test passed: upload -> execute -> fetch ->
SHA-256 verification, returncode 0, terminated false, and provider-side
confirmation that the same pod remained RUNNING on backup. It ran no inference
and admitted no Astrid task. Evidence:
[practical-path review](../docs/projects/astrid-unified-execution/runpod-practical-path-review-20260921.md).

This does not establish H3 readiness. The current pod image is the Torch
2.4/CUDA 12.4 provider default. The candidate H3 virtualenv exists, but a bounded
import torch probe failed with ModuleNotFoundError. Follow the CUDA, node/model,
backend, input and capacity gates in [RunPod lifecycle](runpod-lifecycle.md)
before the continuation test; SSH/GPU presence is insufficient.

The [remote task-manager build brief](../docs/projects/astrid-unified-execution/runpod-task-execution-build-brief.md)
is an optional future integration for scheduler-enforced placement and remote
worker settlement. It is not a prerequisite for the practical path above.
