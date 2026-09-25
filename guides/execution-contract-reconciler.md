# Execution contract and reconciliation

Astrid execution is one frozen request carried by the ordinary task/run/attempt
path. Creative shot and timeline state produces a candidate; approval and
promotion remain separate from runtime execution. A technical retry keeps the
same request and creates a new attempt. A changed prompt, source, seed, or
workflow is a new request and candidate.

The request may use the existing flattened SDK spelling or the nested execution
stencil. Both normalize to the same immutable fields:

- workflow and managed-input identities, including safe task-bound filenames;
- one exact target (`default`, `profile`, `machine`, or existing `runpod`);
- lifecycle, queue/runtime/collection limits, retry policy, and output checks.

Admission derives the managed input manifest from the request and rejects a
caller-supplied manifest that differs. Canonical VibeComfy bundles are checked
before admission: all sibling members are present, bytes match their declared
digests, public bindings compile to the declared basenames, reachable prompts
are non-empty and resolved, media inputs are not blank, and source-video
bindings are not hard-coded to a particular node. H3 source audiovisual timing
is decoded before model execution when that path is requested.

Target adapters return the same typed observation for a local machine and an
existing RunPod pod. A local adapter may attach or start one owned target. An
existing-pod RunPod request validates pod/account/storage identity and never
provisions a replacement after an attach failure.

The reconciler records contract, target, admission, claim, execution, delivery,
and settlement receipts. Claims freeze the runtime epoch, lease, and fence;
heartbeat, upload, failure, and settlement reject a changed epoch. If engine
submission or delivery is uncertain, the result is `undetermined` and is not
silently rerendered. Outputs must remain inside the custody root and match
declared hashes, sizes, and decode evidence before settlement.

For a candidate timeline revision, create an approval artifact bound to the
candidate digest, publication digest, and exact base revision. Promotion checks
all three identities before calling the Runtime's atomic parent-CAS operation;
an approval for an older candidate cannot promote a newer edit. Runtime
idempotency keys govern replay and prevent duplicate task/promotion effects.

## Qualification

The focused contract and reconciler qualification is:

```text
python -m pytest -q \
  tests/core/execution/test_execution_reconciler.py \
  tests/core/execution/test_runtime_epoch_fence.py \
  tests/core/execution/test_managed_tool_session.py \
  tests/test_generic_host_canonical_sibling_bundle.py \
  tests/test_generic_host_output_contract.py \
  tests/sdk/test_execution_request_binding.py \
  tests/sdk/test_capability_selection.py \
  tests/test_vibecomfy_invocation_preflight.py \
  tests/timeline/test_authoring_bundle.py
```

This proves the local/RunPod adapter and fake-runtime paths without claiming a
live GPU render. Live provider execution remains subject to the target's
verified readiness profile and must use the same request and receipts.
