# Hivemind pack

This default Astrid pack provides read-only access to the Banodoco Hivemind
corpus through `hivemind.search` and `hivemind.get_item`.

Use the SDK so discovery, isolation, result artifacts, and provenance are
handled by Astrid:

```python
import astrid.sdk as sdk
result = sdk.invoke(
    "hivemind.search", kind="executor",
    inputs={"query": "Wan Animate", "limit": 10},
)
```

The executors use the public Supabase REST endpoint and stdlib-only HTTP code.
Canonical Astrid execution uses the bundled public read key, without credential
setup. `HIVEMIND_ANON_KEY` overrides are supported only by standalone executor
invocations. `HIVEMIND_API_URL` overrides remain subject to the manifest network
allowlist. Search results are leads; retrieve a full row and citation context
with `hivemind.get_item` before making a sourced claim.
