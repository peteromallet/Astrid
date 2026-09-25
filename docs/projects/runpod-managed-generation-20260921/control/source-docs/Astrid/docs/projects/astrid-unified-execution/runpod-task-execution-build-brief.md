# Canonical RunPod task execution — build brief

> **Current handoff scope (2026-09-21): CPU/fake/offline only.**
> [The user's scope amendment](../../../../../../execution-scope.md) governs this entire
> document, including tasks, commands, acceptance criteria and review inputs.
> All live GPU/RunPod testing and hardware proof below are historical scope
> moved to [separate deferred gate L](../../../../../../POST-HANDOFF-GPU-GATE.md).
> They are excluded from current execution and acceptance and cannot block
> current project completion. Preserve CPU implementation/fixture requirements,
> original evidence and spent budgets; do not treat a fake PASS as GPU proof.


Status: proposed implementation, based on the Astrid and workspace-runtime
checkouts inspected on 2026-09-21. This document does not assert that the
end-to-end path is implemented or that a GPU test has run.

Scope clarification after practical-path review: this is an optional remote
worker/scheduler integration, not the minimum implementation needed to run a
job on an existing storage-backed pod. The existing lifecycle `run --keep-pod`
path passed a bounded live upload/execute/fetch test. Start with the
[operator guide](https://github.com/peteromallet/Astrid/blob/032f65bcd84bd6360f83c260aa902c3a70cc0575/guides/spinning-up-and-executing-tasks-on-runpod.md)
unless scheduler-enforced `vibecomfy.run` placement and remote settlement are
explicit requirements. That transport test did not validate H3 generation.

## Deliverable and boundary

One `client.tasks.create(...)` / `astrid tasks create` call must admit a
`vibecomfy.run` task, prepare an existing or newly requested RunPod pod, register
the generic worker, enforce exact placement, execute, and settle managed outputs.
Following the task is observation; closing the CLI must not stop preparation or
execution. No caller-written attach script, second queue, or workflow-specific
RunPod executor is required.

Runtime owns durable admission, preparation state, account/target resolution,
worker grants, scheduling, attempt fences, deadlines, settlement, and lifecycle
decisions. Astrid supplies a supervised RunPod backend and its existing generic
worker. RunPod-specific API/SSH operations remain in runpod-lifecycle.

Smallest supported slice: one provider, one immutable worker release, one exact
pod/account per task, max worker concurrency one, bounded execution, managed
inputs/outputs, and leave_running. Both attach and provision must use the same
preparation path. No fallback pod, automatic inference retries, fleet autoscaler,
profile marketplace, or new top-level Astrid command family. Other lifecycle
modes must be explicitly unsupported until implemented; never silently ignored.

## Public API and CLI (proposed additions explicitly noted)

Preserve `RemoteTasks.create` and its existing execution_request argument:

```python
client.tasks.create(
    project_id="astrid-intro",
    capability="vibecomfy.run",
    capability_digest=capability_digest,
    spec=spec,
    input_manifest=managed_input_ids,
    execution_request={
        "target": {
            "kind": "runpod",
            "pod_id": "8f18jbuh81vko9",
            "provider_account_ref": "runpod-default",
        },
        "worker_release_digest": worker_release_digest,
        "lifecycle": {"mode": "leave_running"},
        "limits": {"max_queue_seconds": 120, "max_runtime_seconds": 900},
    },
    idempotency_key="h3-continuation-8f18jbuh81vko9-test-01",
)
```

`worker_release_digest` is new: an immutable managed release manifest, resolving
Astrid/Runtime/client/VibeComfy versions, environment locks, capability definitions,
and readiness requirements. It must not mean an unpinned branch or arbitrary
bootstrap command. Resolve an operator-configured default before admission if
the caller omits it, and persist the exact digest.

Existing command plus proposed `@file`, explicit digest, and follow conveniences:

```text
python -m astrid tasks create --project astrid-intro \
  --capability vibecomfy.run --capability-digest <digest> \
  --spec @test-spec.json --input-manifest @input-manifest.json \
  --execution-request @execution-request.json \
  --idempotency-key <key> --follow --json
```

`--follow` reuses tasks follow after successful admission and emits the task ID
before waiting. Its observation timeout never changes the execution deadline.
SDK callers retain create + the existing show/events/cancel surfaces; no second
submission API is necessary.

For an existing handle, add optional SDK `pod_handle=` and CLI `--pod-handle` as
mutually exclusive aliases for target.pod_id/provision. Normalize the handle to
pod_id; account_ref remains operator-resolved and explicit in the persisted
request. Treat embedded SSH addresses and storage claims as hints: resolve and
verify them against the provider before use. Accept a local handle through the
CLI and a handle mapping through the SDK; persist only normalized non-secret data.

Provision uses the same request with target.provision instead of target.pod_id:

```json
{
  "kind": "runpod",
  "provider_account_ref": "runpod-default",
  "provision": {
    "gpu_type": "NVIDIA GeForce RTX 5090",
    "network_volume_id": "sfak8553dy",
    "container_disk_gb": 200,
    "image": "<immutable CUDA-compatible image reference>"
  }
}
```

Define this strict provision schema from the supported runpod-lifecycle launch
parameters; reject unsupported placement requirements before spending. An
existing pod request never invokes launch, including after an attach failure.

## Concrete code ownership

### Astrid: extend existing modules

- `astrid/sdk/execution_request.py`: strict request union, release digest,
  provision alternative, handle normalization, typed preparation/binding views.
- `astrid/sdk/remote.py`: send explicit capability_digest unchanged. It currently
  accepts that parameter but substitutes the registry definition_digest. Resolve
  from the pinned release/catalog when omitted, not only a live worker registry.
- `astrid/sdk/workspace_client.py`: replace metadata-only embedding in spec with
  the generated first-class admission field. Reject conflicting legacy spec
  copies; never interpret a historical stored request as an existing binding.
- `astrid/sdk/invocation.py`: use the same admission contract for SDK invocation;
  avoid a second route with different target/limit semantics.
- `astrid/core/cli/domain_tasks.py`: digest/handle/@file/follow conveniences above.
- `astrid/core/cli/task_progress.py`: expose preparation phase, binding, deadline,
  failure reason, output settlement, and pod lifecycle result.
- `astrid/sdk/host_bootstrap.py`, `astrid/core/_shared/boot_manifest.py`:
  factor reusable release/boot identity validation from local-process assumptions.
- `astrid/core/execution/generic_host.py`, `generic_host_worker.py`, and
  `process_group.py`: worker-session identity, fenced registration, input staging,
  hard attempt watchdog and cancellation, output upload/settlement. Reuse existing
  host-owned task_identity/execution_identity and VibeComfy readiness injection.
- `astrid/core/util/credential_store.py` / `credential_exec.py`: resolve provider
  secrets for the backend; never include API keys in admission or release bundles.

### Astrid: new internal modules, not public creative capabilities

- `astrid/core/execution/backends/runpod.py`: implement provider backend operations
  ensure, inspect, cancel_attempt, release using runpod-lifecycle. Reuse attach
  (`get_pod`), launch, transfer, SSH, and explicit no-termination execution.
- `astrid/core/execution/remote_bootstrap.py`: stage the pinned worker release,
  create/reconnect a loopback SSH reverse tunnel, install its isolated environment,
  verify schema/release/readiness, and start/reuse the generic worker. This is
  installed product code with typed inputs, not a generated user shell wrapper.

Expose the backend as an installed, supervised subprocess with a versioned
bounded JSONL protocol. Commands carry operation ID, execution ID, generation,
deadline, and scoped grants; responses carry progress and verifiable evidence.
Reuse existing supervisor/process fencing mechanisms where applicable. The
backend cannot write Runtime's database or select tasks. Runtime validates every
response before advancing durable state. Provider network work occurs outside
database transactions. Backend configuration/argv comes from trusted installation
configuration, never task-supplied commands.

### banodoco-workspace-runtime: contracts and authority

- `contract/openapi/workspace-v1.yaml`, `contract/schemas/task.json`,
  `contract/schemas/worker.json`: first-class execution_request, preparation,
  worker session, execution binding, deadlines, lifecycle result; binding is
  read-only to task submitters. Add `contract/schemas/execution.json` and list it
  in `contract/manifest.json` for shared execution definitions.
- `runtime_protocol/service.py`: validate admission/account/release, allocate
  execution/preparation atomically with task admission, verify worker registration,
  return preparation/binding in show/events/claim, and enforce binding at heartbeat,
  cancellation, fail and settlement boundaries.
- `runtime_protocol/store.py`: persist execution/session records and attempt
  binding snapshots; enforce target matching in both exact claim and claim_next.
  claim_next must skip ineligible tasks rather than let an unrelated queue head
  block the requested worker. Reuse capacity/resource/verified-fact checks.
- `runtime_protocol/canonical_schema.py` and the existing versioned upgrade path:
  schema additions with migration, integrity and backup/restore coverage. Old
  untargeted tasks retain their behavior; legacy target metadata is unbound and
  cannot silently become eligible for local execution.
- New `runtime_protocol/execution_controller.py`: daemon-owned reconciliation
  loop for preparation, backend supervision, restart recovery, deadlines and
  lifecycle actions. Wire its lifetime into `runtime_protocol/daemon.py`, not the
  caller CLI or a GPU inference worker. Persist progress before side effects.
- New `runtime_protocol/provider_accounts.py`: operator-configured account alias
  resolution. Map runpod-default to provider=runpod plus a credential reference;
  verify the pod is accessible under that configured account. There is no existing
  account registry to reuse. Do not accept arbitrary nonempty labels as proof.
- `runtime_protocol/auth.py`, `server.py`, `daemon.py`: issue/revoke unique,
  scoped worker-session credentials tied to the resolved execution/session and
  executor identity. Do not copy the local shared astrid-pack-host credential to
  every pod. Restrict task/object access to authorized work.
- `banodoco_local/runtime_boundary.py` and source-profile/bootstrap configuration:
  launch/reconnect the installed backend under Runtime supervision. A plain
  `banodoco-local up --profile astrid` must produce a usable installation.

Regenerate the complete Python and TypeScript client contracts using the existing
generators. Update Astrid's vendored client and provenance to the same immutable
runtime release, and package that client in the GPU worker release. Verify
generator --check and runtime/client/schema equality. Never repair compatibility
by changing only digest constants or requiring PYTHONPATH overrides.

## Binding and durable state

Use existing task/run/attempt tables plus two execution resources: a per-task
execution record and reusable pod/worker session records. Attempt binding belongs
to each existing attempt, not to mutable caller spec. Provider account mappings
can remain operator configuration; a general account-management product is not
needed for this slice.

| Record | Required fields / authority |
| --- | --- |
| Request | target.kind; provider_account_ref; exactly one of pod_id/provision; worker_release_digest; lifecycle; limits; capability_digest; immutable input IDs. Caller intent, normalized at admission. |
| Execution | execution_id, task_id, request_digest, resolved account_binding_id, preparation phase/generation, selected session_id, admitted_at, queue_deadline_at, error, lifecycle_result. Runtime-owned. |
| Pod/session | session_id, provider=runpod, provider_account_ref, account_binding_id, pod_id, pod_origin=existing/provisioned, created_by_execution_id when provisioned, worker_release_digest, executor_id, worker_session_id, worker_boot_id, readiness_digest, schema_digest, source_digest, dependency_digest, verified_at, state. Controller-verified; one compatible active session per exact account/pod/release. |
| Attempt execution_binding | binding_id, execution_id, task_id, attempt_id, session_id, account_binding_id, provider_account_ref, pod_id, executor_id, worker_session_id, worker_boot_id, runtime_epoch, lease_id, fence, capability_digest, worker_release_digest, readiness_digest, bound_at, runtime_deadline_at. Runtime-created atomically with claim. |

`account_binding_id` identifies the configured/verified account mapping version,
not the secret value. Rotation preserving the account can refresh credentials;
changing the account invalidates reuse. A worker_session_id is a runtime-issued
registration instance; worker_boot_id changes after a remote process restart.
Do not overload the existing creative execution_identity with placement identity.

Registration proves possession of the runtime-issued session credential and
must match the controller's pod/release/boot record. A self-reported pod_id or
verified_facts map alone cannot establish placement. The normal controlled SSH
bootstrap and registration witness are required; hardware attestation is outside
this implementation. Never persist secrets in binding, events or task outputs.

Preparation phases: requested -> resolving -> provisioning (only if requested)
-> bootstrapping -> ready; failures/cancellation are terminal for that preparation.
The task stays queued during preparation. Admission validates a known pinned
capability definition without requiring a live ready worker. Claim requires a
ready verified session plus the matching capability/release and exact target.

The backend journals provider-operation identity through Runtime before launch.
On an uncertain provider response, reconcile by recorded operation identity and
provider evidence. Never blindly launch again. If the provider cannot establish
whether creation happened, retain an explicit indeterminate failure for operator
reconciliation rather than risk a second paid pod. Concurrent requests share
compatible preparation via transactional uniqueness and preparation leases.

## Deadlines, recovery and output custody

- queue_deadline_at = admitted_at + max_queue_seconds; includes provision,
  bootstrap and waiting for a worker. Never reset it on reconnect/retry.
- runtime_deadline_at = first claim time + max_runtime_seconds for this no-retry
  slice; includes input transfer, engine startup, inference, output transfer and
  settlement. A heartbeat does not extend it. Persist absolute deadlines.
- Runtime enforces deadlines even with no polling client. The remote worker also
  runs an attempt watchdog so a dropped tunnel cannot leave inference unbounded.
  Use clock-offset validation plus a conservative monotonic remaining budget.
- Cancellation/deadline invalidates settlement authority and stops only the owned
  attempt process tree or its owned Comfy session. No unrelated queue clearing.
  Failure to acknowledge cancellation leaves session readiness unknown; block
  further reuse until reconciliation, rather than declaring the GPU idle.
- leave_running means no pod termination on success, failure, timeout, cancellation,
  disconnect or backend finalization. Record pod_left_running and stop task work.
  Runtime may keep a healthy idle worker/tunnel for the next task. Network storage
  is never deleted. Existing and provisioned pods obey the explicit same policy.
- Input media, canonical bundle and model readiness are digest-bound. Fetch only
  admitted managed inputs; stage Comfy input anchors through the worker input
  contract, not hard-coded developer filesystem paths.
- Reuse generic-host artifact inventory, CAS upload and fenced settleAttempt.
  Succeeded means outputs are in Runtime custody and the settlement is committed;
  a remote output path or local JSON receipt alone is insufficient.
- Runtime/backend restarts reconcile operation/session identity and rotate or
  reauthorize credentials under current runtime_epoch. Stale sessions cannot claim
  or settle. Do not silently restart inference after a lost attempt.

## Tests and acceptance evidence

1. Contract/conformance: strict request union; reject unsupported backend/policy;
   full generated-client parity; exact capability digest honored; source provenance
   matches artifacts; ordinary installed CLI works with no import-path workaround.
2. Real Runtime + fake provider/SSH: cold admission -> prepare -> register -> claim
   -> settle. Repeat with existing ready worker, cold existing pod and provision.
   Existing attach performs zero launch/terminate calls; provision performs one
   launch; all leave_running paths perform zero terminate/delete-volume calls.
3. Placement: queue two pods and a local worker. Wrong account, pod, worker session,
   boot, release, capability digest, schema, epoch or credential cannot claim or
   settle. An ineligible queue head cannot starve eligible tasks. Callers cannot
   forge execution_binding, and workers cannot register another pod's identity.
4. Idempotency/concurrency/crash injection: same key returns same task/execution;
   changed payload conflicts; duplicate prepare creates one session; disconnect
   after provider creation does not launch twice; restart at every preparation
   transition; old attempt cannot overwrite new state or duplicate outputs.
5. Real process cancellation: fake hanging inference, tunnel loss, CLI exit,
   runtime restart and queue/runtime expiry. Prove owned process termination,
   no deadline reset, no late successful settlement, pod retained, and no unrelated
   process cancelled. Reuse stays blocked if termination is unconfirmed.
6. Custody: missing anchor/model, bad hash, partial upload, settlement retry and
   invalid output inventory fail correctly. Outputs remain accessible through
   Astrid after worker exit; no raw shared-storage path is treated as settlement.
7. Live existing-pod acceptance: use only 8f18jbuh81vko9, backup volume, 200GB
   container disk, leave_running. Execute the documented small one-step H3 probe,
   then the 175-frame starter / 260-frame continuation with the native 39-frame
   context. Verify the actual workflow supports these diagnostic settings before
   admission. Record input/bundle hashes, binding, remote process witness, GPU and
   CUDA readiness, task events, output hashes, decode/frame checks and managed
   output locations. Do not advance editorial timeline state.
8. Provision acceptance: deterministic fake-provider coverage is mandatory.
   A separately authorized disposable live test is needed before claiming the
   provision branch is live-verified; this brief does not authorize another pod.

Evidence must include task/run/execution/attempt IDs, matching provider observation
and execution_binding, successful managed settlement, idempotent replay, rejected
wrong-worker claim, and provider-side confirmation that the same pod remains
running. Keep evidence in Runtime task/run history and managed outputs.

## Delivery order

1. Contracts, migration, generated clients, admission validation and exact claim
   binding; reject targeted work when its backend is unavailable.
2. Durable controller + attach-only backend + unique remote worker credentials;
   prove cold-existing-pod path with real Runtime and fake transport.
3. Reuse session path, process deadlines/cancellation, custody and restart tests.
4. Provision alternative using the same preparation journal and backend.
5. Installed CLI end-to-end acceptance on the existing pod; revise the operator
   guide to describe only demonstrated behavior and the actual public command.

No manual wrapper is a deliverable. The task-manager command and durable Runtime
evidence are the acceptance surface.
