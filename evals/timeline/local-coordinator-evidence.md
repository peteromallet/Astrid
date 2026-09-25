# Local coordinator evidence and admission status

This report records the current bounded local path. It intentionally separates
filesystem observations, Runtime health, semantic task readback, and worker
write confinement; none substitutes for the others.

## Local navigation collector

`local_coordinator.capture_local_entrypoint_before/after` fingerprints the
complete pinned fixture tree and selected copied entrypoint before and after a
run. Its result is explicitly
`astrid.timeline-eval.local-coordinator-evidence.v1`, with
`scope=filesystem_tree_unchanged` and
`runtime_closure_observed=false`. `test_target_only` remains unknown. The
collector can detect observed mutations; it does not prevent them.

The no-model rehearsal measured the collector successfully for L01, L02, L03,
L06, and L08. It did not establish a read-only/immutable worker boundary.
Accordingly, all five remain `blocked-essential-input`; L04, L05, and L09 lack
ready fixtures, and L07/L10 have unavailable semantic oracles. Current rehearsal
counts: 20 blocked, 0 executable, 0 diagnostic-only. Filesystem collector
availability alone is not an admission signal.

The native launcher now treats local before-capture as readback-collector
availability only. It does not set coordinator safety readiness from
`local_before`. A scored local navigation launch therefore blocks without an
independently proven host worker boundary. One earlier L01 local Luna run did
complete before this fail-closed correction: its semantic checks passed and
source/entrypoint trees were unchanged, but its aggregate remained failed
because the older filesystem status was not accepted by the grade predicate.
That run is observational evidence only, not worker-confinement proof or current
admission readiness.

## Runtime action evidence predicate

`runtime_action_evidence_ready` is shared by admission rehearsal and the native
launcher’s aggregate annotation. It returns true only for a current, case-bound
public action target receipt whose canonical digest agrees with the case attempt
and coordinator sidecar; a passing semantic Runtime before/after readback with a
projection; positive `source_unchanged` and `test_target_only` safety; a worker
boundary receipt; a post-teardown capture; and the expected case artifacts.
Local filesystem evidence has a distinct kind and cannot satisfy this check.
No action currently has that complete evidence pack, so all action rows remain
blocked. The predicate is an evidence check, not an alternate route for
manufacturing a target or receipt.

## Disposable loopback Runtime capability

The workspace has active canonical Runtime state under `.astrid-data/runtime`.
The disposable helper does not open or contact that state: canonical endpoint,
realm ID, and root are comparison inputs only. It creates a unique realm,
support directory, credentials, discovery data, and contract entirely below a
task-owned temporary directory, binds only `127.0.0.1` on an OS-selected port,
connects through the existing `RuntimeFixtureAdapter`, and stops the daemon and
removes the temporary root on context exit.

The real-daemon test exercised health/handshake, project creation, project-list
readback (including the runtime's `[items, cursor]` response shape), and cleanup.
It confirmed the canonical sentinel stayed empty. This proves a safe local
Runtime provisioning seam exists; it does not prove an A01 edit, publication
receipt, independent semantic closure readback, or worker confinement. U03/U05
may consume the seam, but A01 must still supply the complete case-specific
target/receipt/readback/safety pack before it can be admitted.

## Verification

Focused command:

```text
PYTHONPATH=../banodoco-workspace-runtime pytest -q \
  tests/evals/test_timeline_local_coordinator.py \
  tests/evals/test_timeline_eval_luna_native.py \
  tests/evals/test_timeline_eval_evidence_and_admission.py \
  tests/evals/test_timeline_fixture_contracts.py
```

Result: **49 passed**. The path addition is necessary in Astrid-only
environments because `runtime_protocol` is an optional package located in the
sibling `banodoco-workspace-runtime` checkout.
