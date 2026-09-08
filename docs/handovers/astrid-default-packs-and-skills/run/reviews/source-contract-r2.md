# Review packet: source_contract / round 2

This is a correction review of the frozen candidate after round-1 C3 finding.

## Scope

Recheck C3 only: managed source precedence and rendering trust must agree with managed discovery. H3/T1 remains external and is not in scope.

## Correction delta

- `astrid/core/pack/discovery.py`: `SOURCE_KINDS` now declares `managed` between local and extra; local-layer test seam requires the actual local root.
- `astrid/core/rendering/registry.py`: validated `managed` roots are execution-eligible with `trust_method="managed_source"`.
- Focused evidence: `pytest -q tests/core/pack/test_source_setup.py tests/packs/test_pack_discovery_metadata.py tests/packs/test_pack_discovery_canonical.py tests/sdk/test_host_bootstrap_source_identity.py tests/stage1/test_pack_host_interpreter_identity.py` — **31 passed**; `pytest -q tests/core/rendering/test_registry.py tests/core/rendering/test_registry_matrix.py` — **29 passed, 2 skipped**.

## Required result

Read the actual delta and relevant source. Return PASS/REWORK/UNKNOWN for C3, with exact evidence and any remaining concrete defect. Do not mutate or widen scope.
