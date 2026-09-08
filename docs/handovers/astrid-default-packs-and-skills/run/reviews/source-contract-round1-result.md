PASS — scoped source-contract review

- C1 — PASS. The baseline inventory and `tracked.patch` preserve the intentionally dirty checkout: `.otto/runs/astrid-default-packs-and-skills/baseline-20260908-delivery/source.json`. Receipts explicitly state that the upstream Hivemind pin/default remains unresolved; no bundled copy is used as release proof. No correction.

- C2 — PASS for generic fixture-backed provisioning. `astrid/core/pack/source_setup.py:351-400` stages immutable revisions, validates v2 manifests, atomically records activation, supports cache/offline/check, disable/restore, and preserves prior state on failure. Negative coverage is in `tests/core/pack/test_source_setup.py:110-197`. The real Hivemind default pin remains externally pending, as required; no Astrid correction.

- C3 — PASS. The same managed inventory is consumed by discovery (`astrid/core/pack/discovery.py:116-191, 198-383`), SDK provenance (`astrid/sdk/discovery.py:118-156`), and host startup (`astrid/sdk/host_bootstrap.py:329-479`). Revision, manifest/tree digests, inventory identity, host reuse invalidation, and tamper rejection are covered by `tests/core/pack/test_source_setup.py` and `tests/sdk/test_host_bootstrap_source_identity.py`. No correction.

- C6 — PASS. `astrid/core/execution/executor/schema.py:66-79` defines `required|optional`; `astrid/sdk/invocation.py:1383-1392, 1714-1726` defaults missing metadata to required, honors explicit projects, uses the saved runtime selection for required work, and permits projectless optional work. Negative and precedence cases are covered in `tests/packs/hivemind/test_projectless_admission.py:26-160` and `tests/core/test_executor_schema_capabilities.py:59-69`. No correction.

Evidence note: the packet’s reported focused validations were green (17 source/host tests plus the A2 tests). My narrow rerun could not start because the environment has no usable temporary directory; this is an execution-environment limitation, not a source finding.

The unresolved upstream Hivemind v2 release pin/default declaration remains explicitly pending and is not an Astrid implementation defect.