# Hivemind external-pack contract

This is Astrid-side compatibility metadata for the independently maintained
Hivemind pack. The machine-readable contract is
[`config/hivemind-pack-contract.json`](../../config/hivemind-pack-contract.json).
Astrid does not vendor Hivemind executors, copy its backend, or treat this
document as evidence that the external pack is installed.

## Admission and source pin

The managed source must contain a canonical `pack.yaml` with
`schema_version: 2`, the `hivemind` pack id, and the executor content root.
Astrid validates that manifest before activation and records the exact source
revision and tree digests.

The delivery worktree pins the first admissible Hivemind commit at
`a4c6610cba1032adb3b4bec541ccf821afba6ba8`. It contains the v2 manifest and
the contributor-auth implementation. The commit is local to this delivery
branch; remote publication is intentionally outside this task. Until that
commit (or a later full SHA) is published to the upstream repository, remote
installation must use an explicit local source declaration or remain pending.

When the v2 commit exists, configure its complete 40- or 64-character Git
object id:

```bash
export ASTRID_HIVEMIND_REVISION=a4c6610cba1032adb3b4bec541ccf821afba6ba8
python3 -m astrid.setup --check
```

Astrid never follows a branch and never turns a short or invented SHA into a
managed source pin. For local rehearsal, set
`ASTRID_HIVEMIND_REPOSITORY=file:///absolute/path/to/hivemind` alongside the
delivery revision.

## Capability coverage

The v2 pack metadata must retain these public reads, which use Hivemind's
anonymous/public configuration and never require a contributor key:

- `hivemind.search`
- `hivemind.get_item`
- `hivemind.refresh_media`

Contributor-authenticated writes use `HIVEMIND_CONTRIBUTOR_KEY`. Resource
submission, revision proposals and decisions, canonical-guide marking, message
snapshots, and evidence submission all reuse Hivemind's existing `contribute`
backend. The active contributor operations are `submit_resource`,
`propose_revision`, `decide_revision`, `mark_canonical`,
`capture_message_snapshot`, and `submit_evidence`. The three ingestion helpers
submit through that same resource path:

- `hivemind.contribute`
- `hivemind.ingest_article`
- `hivemind.ingest_workflow`
- `hivemind.ingest_youtube`
- `hivemind.submit_vibecomfy_rating`

The `submit-vibecomfy-rating` writer remains covered as a separate Hivemind
edge-function route. It uses the same contributor identity check and
service-role boundary; it is not a public read and does not create an Astrid
second writer. Its Astrid compatibility id is
`hivemind.submit_vibecomfy_rating`.

The existing Astrid capability matrix keeps executor discovery separate from
these backend operations. The rating route and the contributor operation names
are therefore recorded in the external-pack contract rather than advertised as
in-tree Astrid executors before the v2 Hivemind pack is available.
