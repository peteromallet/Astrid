# Astrid execution surfaces

Read-only surface map of the current Astrid checkout. Hivemind owns its CLI;
this document covers only the Astrid boundary that could consume it later. No
implementation or runtime operation was performed.

## Invocation and project resolution

- The public SDK enters through `astrid/sdk/client.py:116-198`. `AstridClient.open`
  requires explicit endpoint, credential, realm, actor, client name/version,
  validates runtime health and schema digest, then performs the exact worker
  handshake scopes. `open_from_launcher` is the explicit cold-launch path
  (`client.py:200+`); ordinary SDK construction does not launch a process.
- CLI task admission is `astrid/core/cli/domain_tasks.py:128-166`, calling
  `client.tasks.create(project_id, capability, spec, input_manifest,
  idempotency_key)`. Project commands resolve/select/current through
  `astrid/core/cli/domain_projects.py:80-122` and
  `astrid/sdk/workspace_client.py:271-311`; project references may be IDs or
  immutable slugs. Task and run follow/show/cancel/events consumers are in
  `domain_tasks.py:169-215`, `domain_runs.py:84-123`, and
  `core/cli/task_progress.py:196-360`.
- `astrid/sdk/remote.py:307-349,638-661` is the SDK-to-runtime translation:
  task creation resolves the capability's registered definition digest and
  sends `admit_task`; invocation uses the same task route and project ID.
  `core/project/kernel_admission.py:41-100` is the narrower orchestrator
  admission helper and requires an explicit project, tool ID, client, and
  deterministic request hash.

## Capability, admission, and host boundary

- `astrid/core/execution/executor/schema.py:186-315` is the canonical
  `ExecutorDefinition` with typed inputs/outputs, command, isolation, and
  metadata. `ExecutorSpec` in `executor/api.py:22-79` normalizes code-first
  declarations into that same schema. Registry discovery is pack-root based in
  `executor/registry.py:140-228`.
- `GenericPackHost.discover()` (`generic_host.py:987-1037`) scans configured
  pack roots, creates `CapabilityRecord` values, computes capability/source/
  dependency digests, and applies the capability matrix. `admit()`
  (`generic_host.py:1039-1065`) returns the immutable definition plus source
  roots, Python roots, version, and digests. The worker rechecks definition and
  source digests before execution (`generic_host_worker.py:58-79`).
- Source fencing currently hashes the executor root and, for external packs,
  its containing `pack.yaml` root (`generic_host.py:479-525`). It does not
  resolve an arbitrary standalone checkout or executable. `CapabilityRecord`
  does carry `dependency_digest` (`generic_host.py:599-655`), but the current
  discovery/admission path derives it from pack capability relationships, not a
  resolved external install.
- Child process environment and network controls are already host-owned:
  `_run_command_definition` builds the scrubbed environment, injects declared
  secrets/routes, confines cwd, starts an owned process group, and polls
  cancellation (`generic_host.py:1859-1977`). Python capabilities use the
  serialized worker path (`generic_host_worker.py:80-105` and
  `generic_host.py:1980+`).

## Lifecycle, outputs, failures, and cancellation

- `GenericPackHost.claim_once()` refreshes discovery/preflight, claims only
  ready capability IDs, preserves the claim's attempt/fence/spec snapshot, and
  calls `run_task` (`generic_host.py:2366-2445`). `run_task` heartbeats,
  observes runtime cancellation, runs the child, uploads declared files to
  managed objects, and settles with project ID, effect, process evidence, and
  network evidence (`generic_host.py:2128-2355`). Lease/cancel/fail/settle
  operations are idempotent runtime calls via the generated client.
- Successful native command results currently expose declared file paths and a
  payload containing return code/capability/process identity
  (`generic_host.py:1955-1973`). Stdout/stderr are captured for diagnostics;
  stdout is not automatically returned as a result artifact. A CLI adapter
  therefore needs a declared JSON/text output file or a small host/result
  contract extension. Non-zero exit raises `HostError` with scrubbed stderr or
  stdout and causes `fail`, while cancellation raises `HostCancelled` and
  returns a cancelled task without settlement.
- Client-facing result consumers read durable task `result.outputs` and expose
  object/path locators through `task_progress.py:173-193`; product JSON uses
  the exact five-key envelope in `core/cli/domain_output.py:56-166`.

## External-runtime mismatch and minimum future scope

`ExecutorDefinition.external_runtime` is parsed and validated in
`schema.py:355-415,591-642`, but `to_dict()` deliberately removes the
top-level field (`schema.py:207-210`) and no resolver/install/registration path
consumes it. Its current source kinds are `git`, `path`, and `pypi`; install
strategies are the schema's `venv`, `uv`, and `pyproject` values. This is a
metadata seed, not a runnable standalone dependency contract.

The smallest future scope is one Astrid-owned adapter that resolves and freezes
the upstream Hivemind source/entrypoint at registration, records the resolved
source and dependency identity in the admitted definition, and emits an
ordinary external `ExecutorDefinition` consumed by `GenericPackHost`. It must
reuse the existing task/run, digest fence, scrubbed environment, network
broker, output publication, failure, cancellation, project, and idempotency
paths. It should declare stdout/JSON as a managed output channel rather than
assuming captured stdout becomes an artifact. No second executor schema,
runner, lifecycle, or Hivemind implementation belongs in Astrid.

## Current checkout caveat

The checkout is substantially dirty, including existing generic-host, SDK,
CLI, pack, docs, and test changes. This map describes the current files and
does not attribute those changes to this review or attempt to separate their
ownership.
