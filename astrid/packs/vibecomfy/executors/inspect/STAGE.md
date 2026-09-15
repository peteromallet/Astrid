---
name: vibecomfy-inspect
description: Inspect an admitted ComfyUI UI workflow through VibeComfy's readable IR.
---

# VibeComfy inspect

Invoke `vibecomfy.inspect` as an executor capability. It emits
`workflow-ir.py` and `inspection.json`; both are read-only projections. UI
JSON inspection is static and needs no Python consent. A canonical
Python/companion/source bundle must be supplied with the exact scalar
`python_execution_consent="confirmed"`; its value and VibeComfy gate audit are
recorded in the inspection artifact. Inspection never lands edits.
