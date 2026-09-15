---
name: vibecomfy
description: >
  Import, inspect, edit, validate, and run ComfyUI workflows through VibeComfy's
  canonical Python/companion/source bundle and Astrid task history.
---

# VibeComfy

Use this pack for ComfyUI workflows that need graph inspection or edits beyond
the standard `generation` contracts, including LoRAs, IP-adapter, ControlNet,
custom samplers, and graph composition. The canonical bundle contains three
separate members: editable `workflow.py`, its `workflow.vibe.json` revision and
UI companion, and byte-identical original `source.json`.

## Executors

| Executor | Inputs and result |
|---|---|
| `vibecomfy.import` | Admitted raw `source` JSON plus a stable `workflow_id`; emits `python`, `companion`, `source`, and an origin `report`. |
| `vibecomfy.inspect` | One UI `workflow` JSON or the complete `python`/`companion`/`source` trio; emits only a read-only `projection` and `inspection`. Canonical Python requires `python_execution_consent="confirmed"`; UI JSON is inspected statically without it. |
| `vibecomfy.edit` | A canonical parent trio plus required `python_execution_consent="confirmed"`, and `operations` for one atomic typed batch or one separate `capture_python`/`capture_graph` candidate; emits the full successor trio and audited `report`. |
| `vibecomfy.validate` | A UI `workflow` JSON or the canonical trio; validates without running inference. Canonical Python requires `python_execution_consent="confirmed"`; UI JSON is validated statically without it. |
| `vibecomfy.run` | A UI `workflow` JSON or the canonical trio; executes the workflow and settles its result artifacts. |

Canonical bundle members are immutable Astrid artifacts. Each edit or capture
consumes the exact prior trio and reports its `workflow_id`, `transition_kind`,
`parent_revision`, `parent_task_id`, and `origin_task_id`. Astrid's existing
task lifecycle records admission, completion/failure, and output digests. Read
the detailed import → inspect → edit/capture → validate → run journey in
[`docs/guides/cli-journeys.md`](../../../../docs/guides/cli-journeys.md).

`vibecomfy.inspect` is read-only: it does not create a revision or canonical
bundle. Its Python-like projection is for reading, never for mutation input.
`vibecomfy.edit` is the accepted mutation path. Typed edits and manual captures
produce a successor and a structured transition report. A ComfyUI canvas Apply
does not enter Astrid task history; use explicit project-bound capture to
record a candidate.

For canonical Python bundles, include the scalar input
`python_execution_consent: "confirmed"` in `spec.inputs` for inspect, edit,
and validate. It has no default, is validated as an exact literal, and must be
explicitly present on every task that loads canonical Python. The adapter maps
it to VibeComfy's existing audited non-interactive `--yes` GateContext; task
admission and `authority_context` do not stand in for this input. Inspect,
edit, and validation artifacts include the consent value and gate audit. UI
JSON inspection and validation stay on the static ingestion path and need no
consent. `vibecomfy.run` is a separate generation capability.

## Typed edit document

The `operations` input is JSON with one ordered list of leaf operations. The
executor lowers the list to one VibeComfy `edit_batch`, so any rejected leaf
rejects the whole batch and no successor artifacts are published.

```json
{
  "schema_version": 1,
  "expected_revision": 0,
  "ops": [
    {"op": "edit_node", "target": "ksampler", "field": "steps", "value": 24}
  ]
}
```

The supported leaf tools are `edit_node`, `add_node`, `remove_node`,
`upsert_link`, `remove_link`, and `set_node_mode`. Node targets may be rendered
bindings or stable UIDs. Explicitly named new-node UIDs can be referenced by a
later operation in the same batch. For field names, node classes, and tool
schemas, use the installed `vibecomfy node` command before editing.

For task invocation, place scalar ports under `spec.inputs`; name each
immutable file port in `spec.input_digests` and authorize its media object in
`input_manifest`. Keep the same `workflow_id`, `transition_kind`,
`parent_revision`, `parent_task_id`, and `origin_task_id` in the task spec so
the report and task history describe one lineage. Import, edit, capture,
validation, and execution are separate tasks when using Astrid. Do not pass a
`--project` option to an Astrid-native executor: its admitted task already
supplies project context.

## When not to use

- Use `generation.generate_image` for standard image generation contracts.
- Use `understanding` to explain existing media.
- Use `video_editing` to cut or render timelines.
