# T4/T5 skills composition receipt

Date: 2026-09-08

Implemented in the existing Astrid checkout, preserving the pre-existing dirty
skills and project-scope work.

- `astrid/skills/view.py` composes a per-harness writable view under the skills
  state directory. The view has a real root `SKILL.md`, real core routing files,
  a writable generated `creative-work/references/packs.md`, and symlinked pack
  directories under `packs/<pack-id>/`. Core and pack source files are not
  written by registry generation.
- Normal `skills.sync()` uses that view as the single `astrid` parent link for
  each detected harness. Existing explicit `skill_md_path` remains available
  for isolated operator/test use. Existing per-harness install state, default
  opt-outs, orphan pruning, and foreign-file protections remain in place.
- Skill discovery now consumes the shared inventory's `env` source kind while
  retaining compatibility with older `installed` records. A fixture test proves
  an environment-root pack is visible through the normal skill discovery path.
- The old Hivemind hardcoded default fallback was removed; default selection now
  follows declared manifest install tiers.
- Registry rendering accepts a view root so generated catalog routes are view
  relative rather than absolute checkout paths.
- Wheel package data now includes the declared `seedance_local` `README.md` and
  `AGENTS.md` resources. Before this correction, an installed wheel failed
  read-only pack discovery because those manifest-declared resources were
  absent; the actual wheel smoke now passes.

Validation:

- `pytest -q tests/test_skills_sync_registry.py` — **16 passed**.
- `pytest -q tests/test_skills.py tests/test_skills_sync_registry.py` — **56 passed**.
- The composed-view test verifies the harness gateway resolves to the temporary
  writable view, a pack directory symlink opens its `SKILL.md`, the generated
  registry exists in the view, and the source registry bytes are unchanged.
- `git diff --check` passed for the owned skills/test paths.
- Actual wheel smoke (`pip wheel . --no-deps --no-build-isolation`, temporary
  venv with no source checkout on `sys.path`, installed package made read-only)
  passed: core/pack-builder/creative-work/reference/rendering resources and
  `seedance_local` declared resources opened, and 24 packaged skills were
  discovered.

No install, global home mutation, source checkout write, host bootstrap edit, or
pack source/setup edit was performed.

Bootstrap acceptance follow-up:

- `pytest -q tests/sdk/test_host_bootstrap_source_identity.py` — **1 passed**.
- The deterministic fake launcher asserts the selected inventory identity is
  passed in `--source-inventory-identity`, managed roots become repeated
  `--pack-root` arguments, readiness records carry the same identity, and a
  changed identity terminates/relaunches instead of reusing the old ready host.
