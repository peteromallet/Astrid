# Standalone-tool runtime contract evidence

Read-only review of the Astrid checkout and the runtime checkout
`banodoco-workspace-runtime-storage-estimate`. This records reusable contracts
and the smallest gaps for a standalone direct-CLI tool route. It does not
change runtime behavior.

## Reusable mechanisms

### Capability shape and execution

`astrid/core/execution/executor/schema.py` already provides a single
`ExecutorDefinition` shape for `built_in` and `external` capabilities. It
declares typed `inputs`, `outputs`, an argv/cwd/env `command`, cache policy,
isolation metadata, resource requirements, and versioned metadata. The
`isolation` object is the right place for network, binaries, required secrets,
and controlled environment passthrough.

`astrid/core/execution/executor/runner.py` expands manifest placeholders and
input flags, builds a scrubbed child environment, and runs an external argv.
The runner already returns executor id/version, command/cwd, return code,
declared output paths, and run identity.

`astrid/core/execution/generic_host.py` is the stronger reusable process
boundary. `_run_command_definition` runs native commands in an owned process
group, polls cancellation, bounds/redacts diagnostics, and returns declared
outputs. `invoke_capability` runs Python capability code through
`generic_host_worker` with a serialized definition and admission fence. Both
paths clean up child state and can terminate the complete process group.

### Admission, integrity, and source identity

`CapabilityRecord` carries capability digest, source digest, dependency digest,
source root, manifest path, readiness/preflight, resources, and estimated
scratch/output bytes. `admit()` serializes the immutable definition plus
version, source roots, source digest, dependency digest, and Python import
roots. The child rechecks definition and source digests before execution.

The source fence is currently implemented by `_admitted_source_roots()` and
`_source_digest_for_roots()`. For external pack executors it includes the
executor root and the containing pack root, excluding `__pycache__` files.

### Environment and network

`generic_host.py` uses `build_child_subprocess_env`, explicit declared env,
scoped credentials, and a separate secret channel. Provider capabilities are
admitted only when the declared network policy is enforceable. The host can
start an observable loopback network broker, bind allowed routes to a fresh
nonce, inject network admission into the child, and require signed broker
evidence at settlement. This should be reused for standalone API tools.

### Durable task/project lifecycle

The runtime contract in `banodoco-workspace-runtime-storage-estimate` already
has project-scoped task/run records, task states (`queued`, `ready`, `running`,
`succeeded`, `failed`, `cancel_requested`, `cancelled`, `retrying`), leases,
heartbeats, attempt/fence identity, cancel routes, and exact idempotency by
request hash. `GenericPackHost.claim_once()` claims a task, heartbeats while
running, observes cancellation, and settles or fails with attempt/fence data.
Successful outputs are published to managed CAS/object rows and are exposed
as task outputs; project_id is present on task/run records and result receipts.

## Exact gaps for standalone direct CLI tools

1. **Discovery is pack-only.** `GenericPackHost.discover()` scans
   `discover_folder_executor_roots(root)` for configured `pack_roots` and
   attaches `source_pack`, `pack_root`, and `content_root`. There is no
   registration/admission API for a standalone manifest whose source is an
   arbitrary checkout plus an executable entrypoint. `external_runtime.source`
   is parsed but never resolves or installs anything.

2. **The existing external-runtime contract is metadata-only/dead at runtime.**
   `ExternalRuntimeSource` supports `git`, `path`, and `pypi`; install supports
   `venv`, `uv`, and `pyproject`; `ExternalRuntimeMetadata` supports mode,
   import check, and binary checks. Validation enforces combinations, but
   `_validate_external_runtime()` has no resolver, frozen checkout, install
   action, or execution integration. `ExecutorDefinition.to_dict()` explicitly
   removes the top-level `external_runtime`, so it cannot reach the generic
   host admission payload. `ExecutorSpec` also has no external-runtime
   argument. Treat this as a schema seed, not an implementation.

3. **Admission source roots are pack-shaped.** `_admitted_source_roots()` adds
   the executor root and, for external kinds, the containing `pack.yaml` root.
   `_admitted_python_roots()` only admits a non-builtin pack root. A standalone
   source root needs an explicit, validated source root list and import-root
   policy; it must not infer an ancestor checkout or use ambient
   `site-packages`.

4. **Source identity does not include dependency resolution.** The current
   digest covers admitted files and the capability definition, but the parsed
   external source URL/ref/path/package and installed environment are not
   frozen into the serialized definition. A standalone tool needs resolved
   source identity (e.g. git commit or path tree digest), lock/install digest,
   entrypoint identity, and dependency digest in registration and admission.

5. **No generic standalone entrypoint contract.** Existing command manifests
   can run a CLI, but only after pack discovery. The contract needs a direct
   `source + entrypoint` route (argv or Python module/function), with cwd,
   input/output bindings, and allowed source/import roots explicitly declared.
   A thin shim can then translate the tool's native CLI into the existing
   command/output contract; the shim must not bypass host admission.

6. **Capability status is host registration based.** Runtime readiness and
   waiting reasons are already modeled, but a standalone registration needs a
   durable capability identity and refresh rule so source/dependency changes
   invalidate the registration rather than silently reusing an old worker
   advertisement.

## Minimal contract extension

Keep `ExecutorDefinition` and the host lifecycle. Add a resolved standalone
descriptor carried in the immutable definition/admission payload:

```json
{
  "source": {
    "kind": "path|git|pypi",
    "locator": "...",
    "resolved_ref": "...",
    "source_roots": ["/validated/root"],
    "source_digest": "sha256:..."
  },
  "entrypoint": {"kind": "argv|python_module", "value": "..."},
  "dependency_digest": "sha256:...",
  "install": {"strategy": "existing|venv|uv|pyproject", "target": "..."}
}
```

Registration resolves and validates this descriptor once, records the
resolved identity, and advertises the same capability digest/source digest as
the current host. Task admission includes the resolved descriptor and
explicit `source_roots`/`python_path_roots`; the existing digest recheck,
scrubbed environment, network broker, process-group cancellation, output
publication, task status, project association, and idempotency paths remain
unchanged.

The direct CLI path should therefore be a thin adapter: resolve/freeze source
and entrypoint, build an ordinary external `ExecutorDefinition`, register it
with a standalone-capability record, then execute through
`GenericPackHost`. Do not add a second task lifecycle or a second output
format.

## Review of the proposed `metadata.standalone_tool` shape

The proposal is compatible with the existing host if it is treated as a
resolved admission descriptor, rather than a request to let the worker look
up a command. Discovery may resolve a configured absolute path or `PATH`
command once, but the admitted payload must contain the absolute executable
binding (and, for Python, the interpreter/module/script binding). The worker
must never repeat `PATH` lookup or import from ambient site-packages.

Hashing in place is sufficient and avoids copying source, with these guards:

- Resolve symlinks before admission and reject a source root that escapes the
  declared root. Hash the actual CLI file plus the declared source roots; do
  not hash an entire checkout or an unconstrained parent directory.
- Include the resolved executable identity, source-root list, runtime kind,
  interpreter/venv target, and dependency/install digest in the capability
  digest. A `which` result changing, a script edit, or an environment change
  must produce a new capability/source digest and invalidate registration.
- For a native executable, file hashing proves the binary changed but does
  not prove its dynamically loaded libraries are unchanged. Either declare
  those libraries as source roots/dependencies or document that the runtime
  identity is the resolved executable plus an operator-supplied dependency
  digest.
- Keep `source_root` optional only for genuinely self-contained binaries.
  Python scripts/packages need explicit source and import roots, with the
  existing `_admitted_python_roots` fence generalized to those roots.

The existing command/output path can capture declared files and process
status. JSON/text stdout should be a declared result channel in the shim,
while file outputs continue through the current output publication path; the
contract should not infer arbitrary stdout as an artifact.

`project_scope` is a useful declarative replacement for the current
capability-specific project exception, but it must map to an explicit
admission rule (`required`, `optional`, or `none`). `optional` may create an
unscoped runtime task when no project is selected; it must still preserve
project_id whenever one is supplied. This is a lifecycle policy, not a source
or process-host concern.

## Evidence index

- `Astrid/astrid/core/execution/executor/schema.py:173-205,355-418,591-642`
- `Astrid/astrid/core/execution/executor/registry.py:177-259`
- `Astrid/astrid/core/execution/executor/runner.py:430-580,930-1035`
- `Astrid/astrid/core/execution/generic_host.py:398-526,570-665,980-1098,1859-2075,2140-2320`
- `Astrid/astrid/core/execution/generic_host_worker.py:22-98`
- `banodoco-workspace-runtime-storage-estimate/contract/schemas/task.json`
- `banodoco-workspace-runtime-storage-estimate/contract/schemas/run.json`
- `banodoco-workspace-runtime-storage-estimate/contract/openapi/workspace-v1.yaml:141-161,430-470`
- `banodoco-workspace-runtime-storage-estimate/runtime_protocol/store.py:729-810`
- `banodoco-workspace-runtime-storage-estimate/tests/test_runtime_exact_idempotency.py`
