# H3 transform orchestration

The orchestrator opens one connected `AstridClient` and invokes every child
through that client's `invoke_result`, waiting for settled outputs. It never
uses the module-level helper without a connected client. Runtime-managed
outputs are read through `client.media.read_bytes(object_id)` after settlement;
attempt-local paths are not treated as durable handles.

Preparation and compilation run before VibeComfy validation. The transform
retrieves the selected `workflow.py`, `workflow.vibe.json`, and `source.json`
from the settled compile outputs through `client.media.read_bytes`, verifies
each byte stream against the corresponding hash in `compilation.json`, and
passes those exact managed descriptors to both VibeComfy children. It never
falls back to a checkout workflow path. The transform carries request, asset,
schedule, graph, and Runtime task/output identities in generation metadata and
downstream manifests. Only `vibecomfy.run` receives the optional execution
target (including an existing managed RunPod target). Composition and
verification run after the generated output has been retrieved into Astrid
custody.
