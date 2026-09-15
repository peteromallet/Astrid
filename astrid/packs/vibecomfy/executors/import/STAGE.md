---
name: vibecomfy-import
description: Import an admitted ComfyUI source file into VibeComfy's canonical workflow bundle.
---

# VibeComfy import

Invoke `vibecomfy.import` as an Astrid executor after the raw workflow JSON has
been admitted as the immutable `source` input. Supply a stable `workflow_id`.
This task calls VibeComfy's shared `import_workflow_bytes` service and emits
the complete canonical `workflow.py` / `workflow.vibe.json` pair, byte-identical
`source.json`, and `edit-report.json` origin receipt. It does not create another
task or write Astrid events; the admitted task is the origin and Astrid settles
the four output artifacts.

The executor runs offline. It requires an Astrid host Python with the editable
VibeComfy checkout installed, so the service version is the same one used by
the standalone `vibecomfy import` command.
