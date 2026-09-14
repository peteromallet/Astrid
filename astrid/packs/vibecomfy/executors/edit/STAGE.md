---
name: vibecomfy-edit
description: Apply a typed VibeComfy delta batch to an admitted ComfyUI UI workflow.
---

# VibeComfy edit

Invoke `vibecomfy.edit` as an executor capability with the canonical
Python/companion/source parent trio, explicit scalar
`python_execution_consent="confirmed"`, and either a typed operations
document or one separate capture candidate. The only accepted operations are
`edit_node`, `add_node`, `remove_node`, `upsert_link`, `remove_link`, and
`set_node_mode`, wrapped by one atomic `edit_batch`. Direct Python and canvas
changes require `manual_capture`; that path uses the same explicit consent and
records the audited gate decisions in its transition report.
