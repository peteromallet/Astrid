Audit conclusion: the patch is pointed at the right product behavior, but the current implementation is not safe to merge. It bundles a forked/copy of Hivemind into Astrid, conflates “default skill installation” with runtime pack availability, and has registry/documentation inconsistencies. Sol should rework the seam around installed-pack discovery and symlink provisioning, while preserving the unrelated dirty work.

## Keep

- `astrid/skills/__main__.py`, the existing CLI plumbing, harness adapters, and symlink machinery.
- The state-file extension in `astrid/skills/state.py` conceptually:
  - persist per-harness default opt-outs;
  - clear the opt-out when explicitly reinstalled;
  - preserve backward compatibility for old state files.
- The default-tier concept in `astrid/skills/__init__.py`, but reimplement it from canonical discovered pack metadata rather than reparsing manifests from `descriptor.skill_dir.parent`.
- Packaging changes in `pyproject.toml` that ship agent-facing `skill/*` files and `astrid.skills*`. These are necessary for fresh installs.
- The bundled-source branch in `generic_host.py` conceptually, if the bundled pack is genuinely the approved installed source and has a stable admission digest.
- The new Hivemind capability records only if runtime discovery can actually see the installed pack and the manifest IDs match.
- Tests under `tests/packs/hivemind/` as contract tests, after changing them to validate the approved source/manifest rather than the copied implementation.

## Rework

### 1. `astrid/packs/hivemind/**`

This is the largest problem.

The external source at `/Users/peteromalley/Documents/banodoco-workspace/hivemind` is materially different from `astrid/packs/hivemind`:

- external manifest is schema v1, `origin: external`, `install_tier: default`, `pack_type: capability`;
- Astrid copy is schema v2 and omits `origin`, `install_tier`, and `pack_type`;
- executor YAML files differ;
- external source contains substantially more implementation/support files;
- copied executor modules are rewritten to import as `astrid.packs.hivemind...`;
- the external source is the authoritative pack, while this patch creates a second implementation.

Plan:

- Do not copy the Hivemind executors into Astrid.
- Treat Hivemind as an installed external pack sourced from the external repository or a packaged revision.
- Add only the Astrid-side registration/provisioning metadata needed to make that installed pack discoverable.
- If a bundled distribution artifact is required for wheels, define a deliberate source snapshot/pinning mechanism and generate it from the external repository. Do not hand-maintain a second executor tree.
- Remove the copied implementation, copied tests that assert Astrid-local module paths, and generated `__pycache__` files.
- Preserve the user-facing Hivemind skill content only if it is intentionally maintained as an Astrid-facing adapter; otherwise symlink/reference the external pack’s skill.

The current manifest’s `status: active` and seven capabilities also need reconciliation with the external manifest, especially `refresh_media`, which exists in the Astrid copy but is absent from the external manifest’s declared capabilities.

### 2. Default-pack selection in `astrid/skills/__init__.py`

The current `default_descriptors()` has several risks:

- It reparses YAML directly despite already having pack discovery infrastructure.
- It derives a pack manifest from `descriptor.skill_dir.parent`, which is wrong or fragile for nested executor/orchestrator skills.
- `or pack.id == "hivemind"` hardcodes the default independently of the source manifest.
- It may classify multiple descriptors from one pack independently.
- It does not clearly distinguish a pack that is default-installed from a pack whose skill is merely discoverable.

Rework toward:

- a pack-level default decision from canonical `discover_pack_metadata()` / installed-pack metadata;
- one default pack record per pack;
- explicit `install_tier: default`;
- `_core` always included;
- missing or malformed optional manifests classified as unavailable/opt-in, not silently defaulted;
- no hardcoded personal filesystem paths.

The default behavior should be:

1. fresh install discovers `_core` plus installed Hivemind;
2. default-tier Hivemind skill is symlinked into each detected harness;
3. rerun is idempotent and offline;
4. explicit uninstall records an opt-out;
5. explicit reinstall clears that opt-out.

### 3. Registry relocation in `astrid/skills/registry.py`

The patch changes `CORE_SKILL_MD` to:

`astrid/packs/_core/skill/creative-work/references/packs.md`

but the CLI output still says the registry is in `_core/skill/SKILL.md`, and several docstrings/help messages retain the old gateway wording.

Rework all of these as one atomic change:

- registry constant/name;
- generated block owner;
- CLI status output;
- `check` and `doctor` messages;
- docs and managed block content;
- tests asserting registry location.

The registry should remain a generated reference, not be duplicated in both the gateway and `creative-work` skill.

### 4. Runtime registration and source pinning

The bundled branch in `generic_host.py` is only valid if runtime registration supplies:

- an installed pack root;
- a matching manifest;
- a stable source/admission digest;
- executor commands that execute from that installed root.

The current preflight recognizes a path derived from Astrid’s source tree:

```python
Path(__file__).resolve().parents[3] / "astrid" / "packs" / "hivemind"
```

That is not sufficient for a wheel, editable install, external revision, or user-installed pack. Sol should resolve the actual registration seam in pack discovery/host bootstrap and make preflight consume that canonical installed-pack identity.

Use source pinning only to the extent needed for availability:

- external repository revision/tag or generated immutable snapshot;
- manifest digest and source digest;
- explicit distinction between bundled, installed external, and configured checkout sources.

Do not redesign the broader runtime.

### 5. Capability ledger and beta matrix

`astrid/core/execution/capability_ledger.py` and `config/astrid-beta-capabilities.json` should be retained only after reconciling them with actual installed-pack discovery.

Specific issues:

- the ledger now calls the seven-item count “shipped by the default pack,” which is false if Hivemind is external/installed rather than shipped;
- the beta matrix adds contribution and ingest capabilities, but these are credential-gated write paths and should not be treated like ordinary read-only availability;
- `refresh_media` and manifest capability declarations disagree across the two Hivemind sources;
- the “historical eighth item” logic appears unrelated to default skill provisioning and should stay isolated unless required by existing ledger contracts.

Prefer wording such as “available from the installed default Hivemind pack” and derive the installed count from the discovered manifest.

### 6. Tests

Add focused tests, but do not run them during this planning pass.

Required coverage:

- fresh/default installation selects `_core` and Hivemind from `install_tier: default`;
- non-default packs remain opt-in;
- repeated offline install/sync makes no network request and makes no repository edits;
- all supported harnesses receive symlinks to the installed skill source;
- symlink targets are valid and point outside harness state as intended;
- explicit uninstall removes the link and records the default opt-out;
- later sync does not resurrect an opted-out default;
- explicit reinstall clears the opt-out;
- missing pack produces `missingpack`;
- present pack with absent/broken link produces `missinglink`;
- remote source outage is reported as `remote outage`/unavailable and does not corrupt state;
- no personal absolute paths occur in packaged metadata, generated manifests, or runtime code;
- `hivemind.search` and `hivemind.get_item` perform reads only;
- corpus-write executors require explicit contributor credentials and do not become part of the read-only acceptance path;
- installed external pack and bundled/package source both resolve through the same registration API.

The current `test_generic_host_external_provider.py` additions are too narrow: they test a repository-relative copied pack and a fabricated digest, not the actual installed-pack registration flow.

## Revert or exclude from this task

These files are unrelated to the requested provisioning behavior and should remain exactly as the user’s prior dirty work left them:

- timeline/domain CLI changes:
  - `astrid/core/cli/domain_media.py`
  - `domain_projects.py`
  - `domain_runs.py`
  - `domain_tasks.py`
  - `astrid/packs/timeline/cli.py`
  - `astrid/packs/shots/cli.py`
  - related v10 tests
- rendering/remotion changes:
  - `astrid/packs/rendering/backends/remotion/run.py`
  - rendering skill changes and tests
  - `astrid/sdk/project_render.py`
  - related rendering tests
- references pack/skill changes:
  - `astrid/packs/references/cli.py`
  - `astrid/packs/references/skill/`
- local/Discord/Seedance integration and census changes.
- storyboard and generator changes:
  - `scripts/build_storyboard.py`
  - `scripts/gen_capability_index.py`
  - `storyboards/astrid-intro.storyboard.json`
- unrelated documentation restructuring except the narrow skills-install/architecture updates required by this feature.
- the broad `_core`, `fal`, and rendering `SKILL.md` rewrites should not be folded into this feature unless they are independently part of the prior skill restructuring.

The untracked `__pycache__` and `.DS_Store` files under the new areas should be excluded from any eventual patch.

## Acceptance scenarios

Minimal end-to-end matrix:

| Scenario | Expected result |
|---|---|
| Fresh install with default Hivemind available | `_core` and Hivemind skill links created in every detected harness |
| Repeat install with no network | No changes, no remote access, success |
| `sync --check` after install | Clean; no registry drift or missing links |
| Explicit Hivemind uninstall | Link removed; opt-out persisted per harness |
| Sync after opt-out | Hivemind not recreated |
| Explicit reinstall | Link recreated; opt-out cleared |
| Manifest absent | `missingpack`; no attempted symlink |
| Manifest present, link absent/broken | `missinglink`; repairable by sync |
| External source unreachable | clear remote/unavailable result; existing valid install remains usable |
| No personal paths | package and runtime metadata contain only relocatable paths |
| Search/get item | successful read-only calls; no corpus mutation |
| Contribution/ingest without contributor key | blocked with credential-gated status |

## Unresolved questions Sol must answer

1. Is Hivemind bundled into Astrid distributions, or installed as an external pack at setup time? The current patch attempts both.
2. What exact external source revision is authoritative?
3. Is the installed pack expected at `~/.astrid/packs/...`, through `extra_pack_roots`, or through the normal installed-pack registry?
4. Does “default” mean default skill symlink only, default runtime capability availability, or both?
5. Should Hivemind write-capable executors be installed by default, or only the read-only skill surface?
6. Is `refresh_media` part of the approved external pack contract?
7. What is the canonical registry owner: `_core/SKILL.md` or the `creative-work` supporting reference?
8. What error taxonomy is already established for `missingpack`, `missinglink`, and remote outage, and where should those statuses be emitted?
9. Is source digest admission already authoritative in host bootstrap, making the new generic-host special case unnecessary?
10. Should explicit uninstall opt out only the skill link, or also suppress runtime capability advertisement?

## Focused effort

Approximately 0.5–1 day for a careful implementation if the installation/registration seam is already usable:

- 1–2 hours: reconcile external source contract and choose pinning model;
- 2–3 hours: rework default pack selection, state opt-out, and registry ownership;
- 1–2 hours: connect installed-pack runtime registration/preflight;
- 2–3 hours: add the acceptance tests and remove copied Hivemind implementation artifacts.

If the existing installed-pack registry cannot expose a stable source root/digest, add roughly another half day for that narrow seam—not a broader runtime redesign.