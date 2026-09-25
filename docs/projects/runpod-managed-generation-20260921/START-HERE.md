# Astra High coordinated program — portable continuation packet

Project: `runpod-managed-generation-20260921`. Snapshot date: 2026-09-21.
This is an immediately readable handoff for continuation, **not a fully accepted
program release**. Read [PENDING.md](PENDING.md) before treating any dependency,
live result, residency claim, retirement, or publication as complete.

The canonical public packet home is Astrid
`docs/projects/runpod-managed-generation-20260921/`. The earlier
`astrid-unified-execution` packet is a different historical planning project;
this directory is the sole home for this program packet. Exported controls are
frozen snapshots, not a second active `.otto` run or an instruction to restart it.

The current projects' build and acceptance scope is **CPU/fake/offline only**.
Read [current execution scope](execution-scope.md) before any exported plan or
brief. Live GPU/RunPod testing has moved to [deferred gate L](POST-HANDOFF-GPU-GATE.md),
which is outside P0–P11/Q/H and does not block their completion.

1. Read [authority and boundaries](authority-and-boundaries.md), then
   [the program manager mandate](program-manager.md) and [DAG/ownership map](program-map.md).
2. Read [the acceptance/evidence index](evidence/index.md),
   [repository lock](repo-lock.json), [dependency lock](dependency-lock.json),
   and [control provenance](control-provenance.json).
3. Follow [receiving/bootstrap](setup.md) to validate the archive, extract into
   a new directory, and retrieve public sources at exact locked commits.
4. Follow [CPU/fake validation](validation.md) only in new source custody.
   Packet validation and Git retrieval do not establish product acceptance.
5. Use [recovery/resume](recovery.md) and the [receiving-agent message](assets/handover-message.md).
   Publication state is in [publication.md](publication.md).

Project A's recorded deterministic implementation/approval is preserved in
[its status](control/runs/runpod-managed-generation-20260921/status.md),
[criteria](control/runs/runpod-managed-generation-20260921/implementation-criteria.md),
[ledger](control/runs/runpod-managed-generation-20260921/acceptance-ledger.md),
and [review](control/runs/runpod-managed-generation-20260921/reviews/final-integrated-review.md).
The review does not identify a frozen final commit. Locked current commits are
inspected candidates; `accepted_product_sha: null` honestly preserves that gap.
Source-state files within exported runs describe their historical capture, not
the packet's current lock. Original dirty/control files have individual SHA-256
identities in provenance; exported versions have separate sanitized hashes.

No full repository source, `.git` history, env files, credentials, keys, caches,
model weights, raw transcripts, or bulk logs are included. The selected skill
documents are an intentional small control dependency with a direct-read path.

The export preserves run modes, roles, stages, budgets, counters and historical
evidence. The user's scope amendment removes live testing from current tasks
and acceptance criteria; each exported project/control document carries that
amendment. Earlier GPU instructions are historical inputs to deferred gate L,
not dispatch instructions. Packaging-only authority still applies to this edit.
