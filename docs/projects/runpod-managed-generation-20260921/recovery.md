# Recovery and resume

Start from archive hash → inner hashes → START-HERE → PENDING → program map →
the owning run's goal/status/run.yaml. Preserve historical counters, decisions,
candidate identities and receipt digests. Exported sources are immutable
snapshot evidence. Never resume a task merely because a PID, pod or conversation
identifier appeared in a historical document.

For manager loss: obtain exclusive manager ownership, reconcile current worker
and product state read-only, and compare the saved source/evidence tuple.
Recover the last dispatch/receipt before launching replacement work. If an
invocation may have happened but its result is missing, recover its result or
charge it conservatively; do not assume a free review/oracle call. Reconcile
partial file reservations with actual changes before transferring ownership.

For source-fetch failure: keep the failure report, use the missing-ref procedure
in [setup](setup.md), and continue tasks independent of that repository. Failed
directories are preserved, never reset or silently repurposed. A replacement
pin requires an explicit provenance update and affected-evidence invalidation.

For changed control/source hashes: stop only affected dispatches, identify the
new authoritative instruction/source, preserve old artifacts, and regenerate
the corresponding lock/provenance. Do not mix two versions of a run's goal and
criteria. Dirty state in the caller orchestrator/app must be resolved by the
source owner before migration; the ZIP intentionally contains no product patch.

For any live-test instruction encountered on resume, mark it deferred to
[gate L](POST-HANDOFF-GPU-GATE.md) and continue independent CPU work. Do not recover,
attach to or probe live resources during current-project execution. The following
live recovery notes are historical guidance for a separately authorized L only:

do not reconnect to historical resources automatically.
Recover current target ownership, attempt/fence and exact artifacts through the
authorized runtime. Never regenerate an already durably published result to
compensate for cleanup uncertainty. Quarantine uncertain device/session cleanup;
do not terminate unrelated processes, pods, volumes or user-owned servers.

Release refresh order: freeze selected control and product identities without
altering active runs; bind acceptance to exact tuples; resolve public pins and
CPU dependency qualification; reconcile counters and migration readiness;
carry live/model qualification as deferred L, without holding this refresh;
regenerate manifest/provenance/locks; verify all local links and YAML; retrieve
changed refs; seal SHA256SUMS; build two archives to fresh names and compare
SHA-256; validate safe extraction to a new directory. Publish only under a
separate applicable authorization. Preserve the prior archive for comparison.

Use `python3 tools/packet.py seal PACKET_DIRECTORY` only when deliberately
creating a new packet revision, then `build ... --output NEW_ARCHIVE.zip`.
Sealing cannot certify source provenance or product behavior. Update the
manifest's file inventory and readiness report before sealing; every final
inner file except SHA256SUMS is covered by checksums. The external ZIP digest
receipt is generated last and is never embedded back into its own archive.
