# Plan 2: Ephemeral Derived-Artifact Lifecycle

Status: standalone generic facility plan; Plan 1 migration is a downstream integration

## Outcome

Provide one runtime-owned lifecycle for derived evidence across visualization and other tools. Primary image/video/audio generation outputs are durable by default. Previews, crops, filmstrips, HTML, exact frames, copied offline media, and similar derivatives are temporary by default. Extensions declare output intent; the runtime owns publication, events, retention, leases, pins, promotion and deletion. No pack-local database or parallel review event ledger.

## Scope and tasks

1. Specify the shared output-intent/provenance contract: source object/task/run identity, manifest/member digests, role, coverage, recipe/frozen inputs, durability (`durable` or `temporary`), and regeneration capability. Use generic capability ports/result manifests (`docs/contracts/capability-artifact-contract.md`, `astrid/core/_shared/result_manifest.py:574-660`).
2. Add runtime-owned metadata for mutable expiry, active leases, pin references and promotion provenance outside immutable manifests. Reuse generic task/run/receipt/artifact events and idempotency; add no review-specific event family unless a genuinely new semantic action appears.
3. Define safe publication and adoption of existing CAS/durable outputs and filesystem caches. Shared-byte references must be digest-verified; cache paths are never authority. Existing outputs must be adoptable without broad deletion or invalidating current durable media.
4. Implement retention and cleanup correctness: only unpinned, expired temporary derivatives with no active lease may be deleted; manifests and exact regeneration inputs remain available; missing inputs produce an explicit unavailable result. Pin/unpin and promotion to normal project media are runtime mutations with provenance.
5. Provide extension-author guidance and a second-producer fixture. An extension declares typed inputs/outputs/params and output intent; it does not add core tables, event families, or authored-media rows for derivatives.
6. Migrate Plan 1's render-review bundle to the shared facility. Verify overview/detail members, manifest identity, cache rehydration, pin/GC, promotion, idempotency and stale-render rejection end to end.

## Acceptance evidence

- Durable primary generation output survives cleanup; temporary derivative expires only after TTL and lease/pin checks.
- Shared bytes are deduplicated by digest and cannot be adopted under a conflicting identity.
- Pin/unpin and promotion are auditable runtime mutations; promotion creates normal project media with provenance without changing derivative identity.
- Rehydration regenerates only from recorded source digest and recipe; no `latest` substitution.
- Retry with one idempotency key returns the original publication; changed payload fails.
- Two independent producers use the same contract and runtime lifecycle without a producer-specific table or event family.
- Plan 1's visualizer passes the shared lifecycle journey, including overview/detail derivatives and final render identity.

## Estimate and dependency

Estimate: withdrawn pending one non-duplicating remaining-work breakdown at delivery setup. Scope includes runtime contract, migration/adoption safeguards, retention/pin/promotion/deletion, extension fixture and Plan 1 integration. It is independently implementable against a small synthetic producer; Plan 1 migration is the final dependent task. If the runtime cannot atomically settle manifest identity and lifecycle metadata, stop at the smallest explicit contract gap rather than silently deleting or reclassifying existing artifacts.
