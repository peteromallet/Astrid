# Runtime Database Clean-Break Simplification Plan

Status: proposed

Date: 2026-09-10

## Decision

Astrid has no users or supported production realms yet. We should use a clean
break to remove compatibility machinery and converge on one simple database
authority and recovery model.

The target is a hybrid: keep the durable domain core and its safety
invariants, while deleting legacy migrations, compatibility shims, and
duplicate lifecycle paths.

This plan does not attempt to repair the currently corrupt realm in place. That
realm remains preserved as evidence; useful data should come through a
verified replacement workflow.

## Remove

- Numbered schema migrations and `schema_migrations`.
- Receipt backfills, migration ledgers, and migration-only activation proofs.
- `RealmStore` migration switches such as `allow_migration` and
  `strict_admission`.
- Identity-only admission exceptions and implicit realm creation on open.
- `tools/astrid_migrate/` and migration-specific restore bindings.
- Backup manifest compatibility aliases.
- Host-bootstrap fallbacks such as `legacy_empty_inventory`.
- Duplicate lifecycle orchestration and compatibility adapters across the
  server, CLI, and clients.

Existing realms and backups become unsupported legacy artifacts. Preserve them
separately when valuable, but do not turn their preservation into a shipping
migration subsystem.

## Keep

- SQLite as the domain store.
- Domain constraints, atomic command receipts, and the content-addressed
  store (CAS).
- Exclusive ownership of a realm.
- Verification before writable open, mutation, or readiness publication.
- WAL-aware immutable snapshots containing the database and referenced CAS
  objects.
- Atomic executor registration and runtime-instance fencing.
- Truthful liveness/readiness reporting.
- Replacement-only corruption recovery.
- One typed HTTP error contract and generated clients. These are interface
  correctness, not legacy compatibility.

## Target architecture

### 1. One runtime-owned manager

Introduce one private runtime boundary, conceptually `RealmManager`, that owns
create, open, transaction entry, snapshot, and replacement. `RealmStore`
becomes its private SQL implementation. Astrid and packs call the runtime;
they do not manage database files directly.

### 2. One canonical format

Define one complete schema and one format identifier. A new realm initializes
its identity and schema together. The runtime accepts exactly that format and
rejects everything else. There are no in-place schema upgrades at startup.

### 3. One verifier

The verifier is read-only and returns one structured report covering:

- SQLite quick/integrity checks;
- exact table and column shape;
- one valid realm identity;
- foreign-key and relational invariants;
- reachable CAS existence and content hashes; and
- catalog/activation consistency when configured.

The verifier never migrates, repairs, salvages, or changes the inspected root.

### 4. One admission state machine

The runtime has four states:

`closed → verifying → ready → failed`

Only `ready` permits mutation or readiness publication. A verification or
ownership failure moves the instance to `failed` and blocks writes until a
fresh verified open. Transaction entry and the admission fence use the same
lock.

### 5. One serialized registration path

Catalog registration and selection are one atomic operation around the full
read-modify-write boundary. Discovery advertises an admitted runtime instance;
it does not own database truth.

## Database lifecycle

### Create

Build a fresh staged root with the complete schema and identity. Verify it,
durably publish it, then register it. Opening a missing root is not an implicit
create operation.

### Open

Acquire exclusive ownership. Inspect a stable private copy including SQLite
WAL/journal state. Only after verification succeeds may the original be opened
writable. Opening never performs schema changes.

### Mutate

Enter one guarded transaction boundary. Enforce database constraints and commit
domain changes plus receipts together. Keep deterministic CAS publication
handling for crashes between object publication and database commit.

### Snapshot

Under the owner’s mutation/GC barrier, create a consistent SQLite snapshot and
copy all referenced CAS objects. Checksum and verify the completed candidate
before atomically publishing it. Published snapshots are immutable.

### Recover

Verify a snapshot, materialize a fresh root, verify it again, stop the old
owner, and atomically switch the catalog pointer. Retain the damaged root and
fence old workers with a fresh runtime instance.

### Publish and readiness

Publish only after admission succeeds. Separate process liveness from service
readiness. Any observed integrity or ownership failure immediately revokes
readiness and write admission.

## Clean-break cutover

1. Consolidate the current domain schema into one canonical fresh-format
   definition. Add isolated lifecycle fixtures for creation, open refusal,
   WAL/CAS snapshots, replacement, ownership contention, and stale workers.
2. Implement the single manager/verifier boundary and route every caller
   through it. Remove the compatibility machinery listed above. Regenerate
   clients once from the clean contract.
3. Preserve the corrupt realm and existing backups as forensic/recovery
   artifacts, not supported inputs to the new runtime.
4. Provision fresh development realms through an explicit operator command.
5. Gate release on corruption refusal without source mutation, owner fencing,
   WAL/CAS round trips, interrupted publication/replacement, concurrent
   registration, stale-worker rejection, and HTTP/client parity.

## Risks

- Removing compatibility code must not remove WAL handling, filesystem
  durability, CAS consistency, or worker fencing.
- Atomic file replacement does not serialize concurrent catalog updates; the
  registration lock must cover the complete read-modify-write operation.
- Replacement must issue fresh credentials and runtime epochs so stale workers
  cannot reconnect.
- Existing development data and backups will no longer be supported inputs.
  Preserve them separately if they matter, but do not reintroduce migration
  complexity into the product.

## Non-goal

This plan does not prove the original physical corruption trigger. It makes
future corruption fail closed and makes recovery a verified replacement
operation, but the initiating writer, timing, and storage mechanism remain
unknown unless separate forensic evidence establishes them.
