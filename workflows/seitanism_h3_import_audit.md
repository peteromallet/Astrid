# Seitanism H3 import integration audit

Date: 2026-09-15. Scope: canonical VibeComfy import, metadata preservation, and adjacent reproducibility integrations. Read-only audits by Luna agents; the import fix is tracked separately in the VibeComfy working tree.

## Confirmed adjacent findings

1. **Runtime lock snapshots omit real lockfiles.** `vibecomfy/runtime/attempt.py:_read_lockfile_snapshot` parses JSON, while `custom_nodes.lock` uses the supported TOML/text formats. A local reproduction read 14 entries through the proper lock reader but returned `None` through the runtime snapshot helper. Runtime artifacts therefore omit available lock evidence.
2. **Lockfile selection depends on the current directory in several paths.** The emitter and runtime drift checks default to `Path("custom_nodes.lock")`. Bundle approval instead anchors its lock authority to the implementation repository. Running from Astrid changes which lock evidence these paths see.
3. **ComfyUI metadata and enforcement use different keys.** `ReadyMetadata.build` adds `comfy_core`; runtime drift checks read `comfy_commit`. A recorded `comfy_core.commit` does not automatically activate the latter check. The current packaged ComfyUI snapshot also has unknown version/commit.
4. **Python dependencies are not a complete environment lock.** Pack `pip_packages` lists are inventory hints, and environment diagnostics do not install or lock those dependencies. Exact custom-node commits alone do not establish complete reproducibility.

## Implemented fixes and verification

Source provenance now survives canonical import and `port convert`, Python metadata, bundle receipts, load, and re-emission. Source records remain evidence; conflicting authored versions are not presented as one tested runtime pin. Raw source is not fed back into native-boundary normalization just to preserve this evidence.

The snapshot parser, default lockfile selection, explicit lockfile forwarding through strict drift checks, and `comfy_core.commit` fallback were fixed. Drift cache keys include the resolved lockfile path so different explicit files with equal modification times cannot collide. A complete Python/environment lock remains outside this patch.

Final artifact: `workflows/seitanism_h3_av_extension_fixed/workflow.py` with its companion and original source. The original import remains unchanged.

Verified against Seitanism's actual source:

- All 102 source records and 10 version pins match the existing extractor exactly in loaded metadata and bundle provenance, including after re-emission/reload.
- Original source bytes are unchanged.
- Effective scheduler still uses 8 steps.
- Local lock-derived headers identify MultiRef and VideoHelperSuite separately from source evidence.
- Runtime lock snapshots read all 14 entries from the repository's actual TOML lockfile when invoked from Astrid.
- Structural validation (`validate --no-schema`) passes with no issues. Full validation remains blocked by unresolved custom-node requirements; no GPU run was performed.

Combined regression run: 204 passed, 8 command tests deselected. A prior full runtime-file run found six existing command-test setup failures targeting the missing `commands.run.get_schema_provider` attribute. Both those six test bodies and the command implementation match HEAD; they were not changed as part of this fix. The other two command tests were excluded by the same broad `not test_cmd_run` selector.

## Source and presentation checks

The original `workflows/seitanism_h3_av_extension/source.json` remains the byte-preserved source. The companion is a presentation/custody projection, not a complete copy of arbitrary ComfyUI frontend data. Notes, retained-node styling, and recognized collapsed states are represented; primitive/reroute lowering explains some node/link-count differences. No additional semantic-loss defect was confirmed by this bounded audit. Runtime equivalence is not established while custom-node schemas remain unresolved.

## Relevant VibeComfy code

- `vibecomfy/porting/import_service.py`
- `vibecomfy/porting/provenance.py`
- `vibecomfy/porting/emit/emit_ready.py:_lock_entries_by_class`
- `vibecomfy/runtime/attempt.py:_read_lockfile_snapshot`
- `vibecomfy/runtime/drift.py`
- `vibecomfy/workflow_bundle.py:_approval_preconditions`
- `vibecomfy/templates.py:ReadyMetadata.build`
