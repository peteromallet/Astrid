# Luna correction receipt

The existing in-place Astrid checkout was preserved. This correction stayed
within C3/C4 and did not touch Hivemind or upstream.

## Correction delta

- `astrid/sdk/host_bootstrap.py`: consume one managed source inventory per
  bootstrap, use that same inventory for identity and `--pack-root` arguments,
  and return the inventory identity on a fresh host. The empty-current versus
  stale-nonempty host case remains fenced and is covered by the existing
  regression, which now also asserts one inventory read per bootstrap.
- `astrid/skills/__init__.py`: startup auto-heal composes the harness view and
  verifies the composed gateway descriptor, then invokes `sync(deep=False)`;
  deep sync and stale-link pruning exclude disabled managed packs while still
  considering only Astrid-owned links.
- `tests/sdk/test_host_bootstrap_source_identity.py`: inventory read-count and
  fresh-result identity assertions for host provenance.
- `tests/test_skills.py`: composed gateway assertions and auto-heal failure seam
  updated to assert the composed `sync` path.
- `tests/test_skills_sync_registry.py`: regression that deep sync prunes a
  disabled managed `astrid-foley` link while preserving a foreign
  `image-generation` entry.

The already-present correction delta in the same checkout also covers the
composed writable view, lexical view-relative registry routes, pack-builder
copy/rewrite behavior, and source-registry immutability in
`astrid/skills/view.py` and `astrid/skills/registry.py`; those files were
inspected and left otherwise unchanged in this pass.

## Validation

Command:

```text
PYTHONDONTWRITEBYTECODE=1 pytest -q tests/sdk/test_host_bootstrap_source_identity.py tests/test_skills.py::AutoHealTest tests/test_skills_sync_registry.py::SyncGatewayTest
```

Result: **15 passed** in 62.75 seconds.

Command:

```text
git diff --check
```

Result: **pass** (no whitespace errors).

## Limitations

Only focused correction tests and the diff check were run. The final review
was not run, and the external Hivemind v2 release/pin and live acceptance
remain unresolved as required by the review boundary.
