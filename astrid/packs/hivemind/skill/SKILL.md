---
name: hivemind
description: >
  Search and retrieve Banodoco community knowledge about generative video and
  image tooling, including workflow tips, settings, gotchas, and cited sources.
  Use the read-only Astrid Hivemind executors when official documentation is
  incomplete or the user asks what the community recommends.
---

# Hivemind

Hivemind is a public Banodoco knowledge corpus containing Discord messages,
external resources, and curated distillations. This Astrid pack exposes
search, retrieval, media refresh, contribution, and ingest operations through
the SDK. Use search and retrieval for normal evidence gathering:

```python
import json
import astrid.sdk as sdk

client = sdk.AstridClient.open_from_launcher()
result = sdk.invoke(
    "hivemind.search",
    kind="executor",
    client=client,
    wait=True,
    inputs={"query": "Wan Animate workflow", "limit": 10},
)
if not result.ok:
    raise RuntimeError(result.error)
artifact = next(row for row in result.outputs["artifacts"] if row["name"] == "results")
page = json.loads(client.media.read_bytes(artifact["digest"]))
print(page)
```

Search, get_item, and refresh_media do not require a selected project. They
still use workspace runtime admission, execution, and artifact storage. Pass
`project="<project>"` explicitly to associate research with that project. Other
capabilities use the runtime’s last selected project when none is supplied.

The completed invocation exposes runtime artifact descriptors in
`result.outputs["artifacts"]`. Read their bytes through `client.media.read_bytes`
using the descriptor’s digest; do not read private staging files or transport
attributes.

The search result is a JSON artifact containing `results`, `total`,
`has_more`, `page`, and `next_offset`. When `has_more` is true, repeat the
same invocation with `offset=next_offset`. Search supports `kinds`, `sources`,
`since`, `channel`, `author`, `thread`, `limit`, `offset`, and `sort`.

Retrieve a promising result with its full body and citation context:

```python
item = sdk.invoke(
    "hivemind.get_item",
    kind="executor",
    client=client,
    wait=True,
    inputs={"kind": "message", "id": 1421556853787066480},
)
```

Use `kind=message`, `kind=distillation`, or `kind=resource` for retrieval.
Search returns leads with truncated bodies; `get_item` is the evidence path
for an answer. Prefer approved distillations, then pinned or channel-scoped
messages, and include the returned Discord/resource URL when presenting
community advice.

The executors query raw, index-backed PostgREST tables. They deliberately do
not text-search the `unified_feed` view because broad ILIKE scans can hit the
Supabase statement timeout. Multi-word queries are tokenized and ranked in the
client. Narrow by channel, author, thread, or date when a broad query is slow.

Contribution and ingest operations write only through Hivemind's locked edge
functions and require explicit contributor credentials. Never write directly
to corpus tables. Hivemind results are community evidence and can be stale;
verify product specifications and safety-critical details against primary
documentation.

Canonical Astrid execution uses the bundled public Hivemind read key and needs
no credentials. The `HIVEMIND_ANON_KEY` override is supported only by standalone
executor invocations; it is not passed through the canonical host.
`HIVEMIND_API_URL` overrides remain subject to the manifest network allowlist.
Contribution and ingest require `HIVEMIND_CONTRIBUTOR_KEY` through the host’s
declared secret channel.
