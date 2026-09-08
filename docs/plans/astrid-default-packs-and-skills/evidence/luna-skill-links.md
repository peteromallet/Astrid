Outcome: treat the dirty Hivemind/default-tier work as an incomplete prototype, retain only the useful state/default concepts, and redesign skill installation around a writable composed skill root. The composed root should be the only generated filesystem tree; harnesses should point to it with one stable root symlink.

## Findings

1. Current skill discovery is split between source-tree scanning and shared pack metadata.

- Source packs are scanned directly in [`astrid/skills/discovery.py:161`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/discovery.py:161).
- External metadata is consumed in [`astrid/skills/discovery.py:130`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/discovery.py:130).
- The current filter only accepts `"extra"` and `"installed"` at [`astrid/skills/discovery.py:143`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/discovery.py:143), but the shared discovery contract declares source kinds `("source", "local", "extra", "env")` at [`astrid/core/pack/discovery.py:41`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/core/pack/discovery.py:41). This is the reported bug: environment-provisioned packs are discovered by the pack bridge but excluded from skill discovery.

2. The dirty default-tier implementation currently adds Hivemind-specific behavior directly into the skills layer.

- `default_descriptors()` and `default_pack_ids()` are new dirty APIs at [`astrid/skills/__init__.py:20`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/__init__.py:20).
- It special-cases `pack.id == "hivemind"` at [`astrid/skills/__init__.py:54`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/__init__.py:54).
- Default behavior is threaded through sync, nudge, and uninstall state at [`astrid/skills/__init__.py:552`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/__init__.py:552), [`astrid/skills/__init__.py:460`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/__init__.py:460), and [`astrid/skills/state.py:35`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/state.py:35).

Recommended direction: keep the concept of a provisioning inventory and durable opt-out, but remove the Hivemind name-based fallback from the installer. Default setup should supply the inventory explicitly.

3. Existing adapters install individual links directly into each harness.

- The common filesystem primitives are [`astrid/skills/harnesses/base.py:145`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/harnesses/base.py:145) and [`astrid/skills/harnesses/base.py:171`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/harnesses/base.py:171).
- Claude maps `_core` to `~/.claude/skills/astrid` and other packs to `astrid-<pack>` at [`astrid/skills/harnesses/claude.py:26`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/harnesses/claude.py:26).
- Codex has the same per-pack model plus generated `AGENTS.md` content.
- `sync()` currently regenerates a registry file and then applies per-pack links at [`astrid/skills/__init__.py:158`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/__init__.py:158).

This architecture cannot safely compose installed packs when the canonical source is in read-only site-packages.

4. Wheel packaging is currently mid-transition.

HEAD explicitly excludes `astrid.skills*` and excludes `packs/**/skill/*`; the dirty tree removes both exclusions and adds skill package-data patterns at [`pyproject.toml:80`](/Users/peteromalley/Documents/reigh-workspace/Astrid/pyproject.toml:80) and [`pyproject.toml:115`](/Users/peteromalley/Documents/reigh-workspace/Astrid/pyproject.toml:115).

The intended result is correct—ship canonical pack skills in the wheel—but it needs a release test proving that:

- `pack.yaml` and `skill/SKILL.md` are present in the wheel.
- Nested skill directories are present.
- The installed source tree is treated as read-only.
- Discovery can return absolute installed paths without attempting writes there.

The external canonical pack confirms the expected source contract:

- [`/Users/peteromalley/Documents/banodoco-workspace/hivemind/pack.yaml`](/Users/peteromalley/Documents/banodoco-workspace/hivemind/pack.yaml) declares `id: hivemind`, `install_tier: default`, `pack_type: capability`, and `content.executors: executors`.
- [`/Users/peteromalley/Documents/banodoco-workspace/hivemind/skill/SKILL.md`](/Users/peteromalley/Documents/banodoco-workspace/hivemind/skill/SKILL.md) is pack-owned and must remain authoritative.

## Required provisioning inventory interface

Default setup provisioning is another agent’s scope. The skills layer should consume a narrow read-only inventory interface, for example:

```python
@dataclass(frozen=True)
class ProvisionedPack:
    pack_id: str
    pack_root: Path
    skill_root: Path
    source_kind: str
    version: str | None
    install_tier: str | None
    enabled: bool
```

Required guarantees:

- `pack_root` contains the canonical `pack.yaml`.
- `skill_root` is the canonical pack-owned `skill/` directory.
- Paths may live in read-only site-packages.
- Inventory is already provisioned and does not create or mutate packs.
- Entries are deduplicated using the normal pack precedence rules.
- Explicitly disabled/opted-out packs are either omitted or marked `enabled=False`.
- Nested skill roots are either included in the inventory or derivable through the existing `iter_executor_roots()` / `iter_orchestrator_roots()` APIs.
- The inventory exposes the source kind so `env` packs are not silently confused with source or extra packs.

A suitable seam is a new read-only function adjacent to pack discovery, such as:

```python
def list_provisioned_skill_packs() -> tuple[ProvisionedPack, ...]:
    ...
```

The skills layer should not infer “default” by reading arbitrary manifests or special-casing `"hivemind"`.

## Proposed composed-root design

Use a writable per-user data root, never a generated tree inside site-packages:

```text
$XDG_DATA_HOME/astrid/skills/
  main -> <canonical _core/skill>
  index -> <writable registry/reference file or canonical index target>
  packs/
    hivemind -> <canonical hivemind/skill>
    rendering -> <canonical rendering/skill>
    ...
```

Fallback when `XDG_DATA_HOME` is absent:

```text
~/.local/share/astrid/skills/
```

The exact root should be centralized in a new path API, rather than reconstructed by adapters.

Recommended APIs:

```python
def composed_root() -> Path
def composed_main() -> Path
def composed_index() -> Path
def composed_pack(pack_id: str) -> Path
def ensure_composed_tree(
    inventory: Sequence[ProvisionedPack],
    *,
    registry_text: str | None = None,
    dry_run: bool = False,
) -> ComposeReport
def prune_composed_tree(
    known_pack_ids: set[str],
    *,
    dry_run: bool = False,
) -> ComposeReport
```

Composition rules:

- `main` is a stable symlink to the canonical `_core/skill` directory.
- `packs/<id>` is a stable symlink to the canonical pack-owned `skill/` directory.
- `index` is a stable link to the generated registry/reference target, or a generated file in the writable root if the harness requires a regular file.
- Do not copy pack-owned `SKILL.md` files.
- Do not rewrite source pack instructions.
- Use absolute resolved targets when creating links, because canonical sources can be outside the repository and can have relative references.
- Preserve relative assets and references by linking the entire source skill directory, not only `SKILL.md`.
- Reject path traversal or IDs that could escape `packs/`.
- Replacement is allowed only for links previously owned by Astrid; foreign files/directories must remain untouched.

Harness layout:

```text
~/.claude/skills/astrid -> $ASTRID_COMPOSED_ROOT
~/.codex/skills/astrid  -> $ASTRID_COMPOSED_ROOT
~/.hermes/skills/astrid -> $ASTRID_COMPOSED_ROOT
```

The adapters should expose one root target, while the composed root exposes the nested pack namespace. Existing `astrid-<pack>` links should be treated as a migration format, not the long-term representation.

Stable names:

- `astrid/main` resolves to the gateway/core skill.
- `astrid/index` resolves to the pack registry.
- `astrid/packs/<id>` resolves to the pack skill.
- The harness-visible root remains exactly `astrid`.

This satisfies the requested “per-harness root symlink, nested `packs/<id>` links, stable `main/index` links” model while keeping source instructions pack-owned.

## Removal, upgrades, and opt-outs

Removal:

- Remove only Astrid-owned links in the writable composed root.
- Remove empty generated directories only when they are known to be Astrid-owned.
- Never delete canonical pack directories.
- Never delete foreign harness entries.
- If a pack disappears from inventory, remove `composed_root/packs/<id>` and update state.
- The harness root symlink should remain if the core/main skill is still available; otherwise report a repairable error.

Upgrade:

- Re-run composition against the current inventory.
- If a canonical pack path changes, replace only the corresponding symlink.
- If the same pack ID changes version or source kind, update the link and state atomically.
- Registry/index content should be regenerated deterministically.
- A second run must report no changes.

Explicit opt-out:

- Preserve the existing durable `disabled_defaults` concept, but make it inventory-driven rather than Hivemind-driven.
- `uninstall --default` records an opt-out for that harness or, preferably, globally if default provisioning is global.
- A normal explicit `install <pack>` clears that pack’s opt-out.
- Re-sync must not reinstall an opted-out default.
- A new default pack appearing later should install once unless explicitly disabled.
- Removing a pack from inventory must not create a new opt-out; it is simply absent.

## Ordered implementation tasks

1. Establish the canonical inventory seam.

   - Add the `ProvisionedPack`-style read-only interface.
   - Adapt `astrid.skills.discovery.list_skills()` to consume it.
   - Include `source_kind == "env"` in the bridge.
   - Add tests proving source, extra, and env packs all produce descriptors with correct absolute paths.
   - Evidence: current mismatch at [`astrid/skills/discovery.py:143`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/skills/discovery.py:143) versus [`astrid/core/pack/discovery.py:41`](/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/core/pack/discovery.py:41).

2. Separate discovery from composition.

   - Keep `SkillDescriptor` read-only.
   - Add composed-root path and composition APIs.
   - Add ownership checks and safe-link helpers.
   - Ensure no write path points into `descriptor.skill_dir` or its parent.
   - Add a test with a read-only source directory and writable composed root.

3. Implement the composed tree.

   - Create `main`, `index`, and `packs/<id>` links.
   - Preserve nested skill directory contents and relative paths.
   - Make output deterministic.
   - Use atomic replacement for generated regular files.
   - Add idempotence tests.

4. Refactor harness adapters.

   - Replace per-pack target calculation with one root target per harness.
   - Keep harness-specific metadata handling only where required, especially Codex `AGENTS.md`.
   - Make all adapters point to the same composed-root contract.
   - Add tests for Claude, Codex, and Hermes independently.

5. Migrate state semantics.

   - Record composed-root target and source/version metadata.
   - Preserve existing state-file compatibility.
   - Retain durable opt-outs.
   - Ensure uninstall and re-install update opt-outs deterministically.
   - Add upgrade, disappearance, and opt-out tests.

6. Fix registry ownership.

   - Decide whether `index` is a symlink to the canonical creative-work reference or a generated writable file.
   - Prefer a generated writable index if the registry is expected to include external/env packs, because site-packages must remain immutable.
   - Keep pack instructions untouched.
   - Avoid retaining the dirty change that makes the repository’s creative-work reference the only registry write target unless that is explicitly part of the product contract.

7. Finalize wheel packaging.

   - Retain the dirty package-data inclusion for `packs/**/skill/*` and `packs/**/skill/**/*`.
   - Remove the `astrid.*.skill*` package-discovery exclusion only if it is proven not to hide required package directories; otherwise use explicit package-data/resource loading without treating skill folders as Python packages.
   - Add a wheel inspection test/build check.
   - Verify installed discovery paths and composition from a simulated read-only wheel tree.
   - Evidence: HEAD excludes skills at [`pyproject.toml:87`](/Users/peteromalley/Documents/reigh-workspace/Astrid/pyproject.toml:87) and [`pyproject.toml:98`](/Users/peteromalley/Documents/reigh-workspace/Astrid/pyproject.toml:98); dirty work changes this at [`pyproject.toml:115`](/Users/peteromalley/Documents/reigh-workspace/Astrid/pyproject.toml:115).

8. Remove unsupported surface assumptions.

   - Do not add or document legacy “Astrid packs install” commands.
   - Do not add an Astrid skills gateway command that is not already supported.
   - Keep the plan/API centered on existing `astrid.skills` Python APIs, setup provisioning, and harness sync.

## Essential test matrix

- Environment pack discovery:
  - `ASTRID_PACKS_PATH` pack with `skill/SKILL.md` appears in `list_skills()`.
  - Its `source_kind` remains `env`.
  - It does not get filtered as “installed” or silently dropped.

- Read-only source:
  - Canonical pack directory is chmod/read-only or located under a simulated site-packages tree.
  - Composition succeeds in the writable user data root.
  - No source file mtime/content changes.

- Tree shape:
  - `main` points to `_core/skill`.
  - `index` is stable and correct.
  - `packs/hivemind` points to the canonical external skill directory.
  - Relative references inside the Hivemind skill still resolve.

- Harness integration:
  - Each detected harness has exactly one Astrid root link.
  - Foreign skills are untouched.
  - Existing foreign `astrid` path is not replaced without `--force`.

- Idempotence:
  - First compose changes links/files.
  - Second compose reports zero changes.
  - Reordering inventory does not change output.

- Upgrade/removal:
  - A changed canonical source path updates only that pack link.
  - A removed pack prunes only its composed link.
  - Missing canonical source reports an actionable error.

- Opt-out:
  - Default Hivemind is installed once.
  - Explicit uninstall prevents automatic reinstallation.
  - Explicit install clears the opt-out.
  - Newly provisioned defaults install once.
  - Non-default packs remain opt-in.

- Packaging:
  - Wheel contains Hivemind `pack.yaml`, `skill/SKILL.md`, and nested skill assets.
  - A wheel-installed discovery run can compose without writing to the wheel.
  - No legacy unsupported command is required by the test.

The main architectural boundary is therefore: setup provisions canonical packs; discovery inventories them; composition materializes writable links; harnesses expose one root; state records opt-outs and composition metadata.