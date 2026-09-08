# Default packs and pack-owned skills: implementation plan

Status: planning complete; implementation has NOT been performed or certified.
Implementation bindings follow the prepared run configuration: Luna ordinarily,
Sol for justified XHARD assignments. Exploration: three GPT-5.6 Luna agents,
followed by coordinator source review. This document resolves the recommendations
in the attached exploration memos; those memos are evidence, not competing plans.

## Outcome

A normal Astrid setup provisions Hivemind by default. Hivemind remains its own
canonical pack, including its skill and seven executors. Skill setup inventories
the installed/enabled packs and exposes their instructions through symlinks under
one Astrid skill entry point. A fresh agent can navigate Astrid → Hivemind →
search → retrieve a full cited result without knowing a personal checkout path.

Pack installation and skill installation are separate operations:

1. **Pack setup** obtains/validates the selected pack revision and records its root.
2. **Skill sync** reads that inventory and creates/repairs links and a routing index.
3. **Runtime admission** uses the same explicitly selected pack roots to run tools.

Discovery and skill sync do not download code. Read-only discovery does not mutate
installation state. The ordinary setup command composes the first two operations
so users do not need to perform the wiring manually.

## Decisions

### Provision default packs as pinned external sources

Keep Hivemind in its existing repository. Astrid's release ships a small default
source declaration naming Hivemind's repository, immutable revision, pack id and
pack subdirectory. Setup fetches that revision into a user-writable managed
location, validates it, then records the active source. It may reuse an already
verified revision. After initial setup, discovery and skill sync work offline;
Hivemind corpus searches still require the service/network.

Do not maintain copied executors under `astrid/packs/hivemind`. Do not make a
standalone personal skill the source of truth. A separate Python wheel is not
required for this first implementation: existing external pack roots are already
the execution/discovery boundary. A wheel or offline archive could later supply
the same root, without changing the skills contract.

The default **selection policy belongs to setup configuration**, not the skill
installer and not a hardcoded `pack.id == "hivemind"` branch. The current v2 pack
schema does not accept the old `install_tier` field. Do not add a compatibility
schema or reinstate obsolete metadata merely to choose defaults.

### Reuse discovery and link installation

Use the existing pack metadata/SkillDescriptor pipeline and harness link helpers.
Fix the external-source-kind bridge. Add only the small root-resolution and
composition seams required to connect them. Do not create another capability
catalog, installer database, runtime, or generic policy framework.

Use a writable composed skill view, not generated files inside the checkout or
site-packages. The harness points to that view; pack links point to pack-owned
skill directories. All enabled installed packs with skills are eligible, not
just Hivemind. Preserve the existing explicit per-harness skill opt-out behavior.

### Preserve the full pack

Keep search, get_item, refresh_media, contribute, ingest_article, ingest_workflow,
and ingest_youtube. Having these installed does not mean their prerequisites
are all available. Read capabilities should work with the existing public read
configuration; write/ingest capabilities retain their actual credential and
publication requirements. Validation must not publish anything to the corpus.

### Keep the neutral runtime change bounded

Astrid owns `astrid/sdk/host_bootstrap.py`, which starts the generic host. Use that
existing handoff to pass the installed pack roots and their revision identity.
Do not assume the neutral launcher already provisions packs: the inspected
installed `banodoco_local.SourceProfile` has no pack-source field and rejects
unknown fields. Do not add a runtime-wide pack manager on speculation. Only
change the neutral runtime if a concrete integration test demonstrates an API
requirement that Astrid's existing host handoff cannot satisfy.

## Verified gaps

| Gap | Source evidence | Required work |
| --- | --- | --- |
| Pack acquisition is absent from current discovery | `astrid/core/pack/discovery.py`, `docs/guides/discovery-for-agents.md` | Add explicit setup provisioning of declared defaults; keep discovery read-only |
| Existing external Hivemind manifest is v1 | External `hivemind/pack.yaml`; `astrid/core/pack/loader.py`, `canonical.py` | Migrate and validate the manifest in Hivemind, then pin that resulting revision |
| Pack roots discovered as `env` lose their skills | `astrid/skills/discovery.py:_scan_discovered_packs` accepts extra/installed; `core/pack/discovery.py` emits source/local/extra/env | Consume the actual shared discovery kinds/inventory |
| Default source selection and skill enablement are conflated in prototype | Dirty `astrid/skills/__init__.py:default_descriptors` | Setup supplies installed roots; skills operate on descriptors and their own link opt-outs |
| Harness root currently points to core source; no composed parent tree | `astrid/skills/harnesses/{base,claude,codex,hermes}.py` | Build writable view and point harness root at it |
| Registry writes target source-owned skill files | `astrid/skills/registry.py` | Generate installed routing index in the writable view |
| Baseline wheel excluded the skill installer and skills | HEAD `pyproject.toml`; dirty packaging prototype | Ship installer plus the instructions/resources actually reachable from it |
| Host only starts with Astrid source pack root and strips ambient pack paths | `astrid/sdk/host_bootstrap.py:ensure_pack_host`, especially argv and child env construction | Pass validated default roots explicitly and include them in host reuse identity |
| Prototype reports source availability using a copied bundle | Dirty generic-host branch and ledger additions | Remove bundle-specific shortcut; validate actual external source/admission |

External Hivemind exists at the source path recorded in `source-state.json` and
already has a pack manifest. Do not repeat the earlier mistaken claim that it is
only a bare skill directory. Its present v1 manifest is the incompatibility.

## Proposed user/API surface

The spelling below is a proposal for implementation, not a claim these commands
already work. Keep setup outside the seven-family creative product gateway.

- `python -m astrid.setup`: provision configured default packs, then sync skills.
- `python -m astrid.setup --check`: inspect installation/link readiness, no changes.
- `python -m astrid.setup --offline`: use verified cached revisions only.
- `python -m astrid.setup --disable-pack hivemind`: deactivate the managed default
  and record the user's choice; leave source bytes available for rollback/reuse.
- `python -m astrid.setup --restore-pack hivemind`: clear that opt-out and restore
  the declared revision, then sync links.
- `python -m astrid.skills sync`: reconcile skills from already installed packs;
  never fetch a missing pack. Preserve existing install/uninstall APIs for
  per-harness skill visibility. The new `astrid/skills/__main__.py` prototype may
  be retained after validation.

A normal setup rerun must honor explicit pack and skill opt-outs. A merely broken
symlink is repairable by sync. A missing source checkout requires setup repair;
it is not permission for skill sync to download an unrelated source.

An Astrid release can advance the declared default pin. Setup stages and validates
that revision before activation. Do not add branch-following auto-updates or a
separate arbitrary-version update product in this task.

## Storage and shared inventory contract

Use existing XDG/path helpers where possible. Proposed layout, centralized in one
path helper and scoped to the selected Astrid installation/profile:

```text
$XDG_DATA_HOME/astrid/packs/<pack-id>/<revision>/    real pinned source checkout
$XDG_STATE_HOME/astrid/<profile>/pack-sources.json  active roots and pack opt-outs
$XDG_STATE_HOME/astrid/<profile>/skills/<harness>/  writable composed skill view
```

Use conventional `~/.local/share` / `~/.local/state` fallbacks. This is installed
code/configuration, not a replacement project/media/task database. Explicit user
extra roots remain supported and are never owned or deleted by setup.

The release default declaration should include only necessary fields: pack id,
repository URL, immutable revision, pack subpath, and optionally a release/tree
checksum when the artifact format needs one. Do not invent a new canonical pack
schema. The selected revision's v2 `pack.yaml` supplies capabilities and resources.

One read-only resolver produces the enabled inventory used by pack/skill discovery
and host bootstrap. Each record needs `pack_id`, `pack_root`, origin of the root
(managed/source/explicit), revision/source identity, and enablement. Skill roots
come from existing pack discovery. No second independent skill copy of install
state. Per-harness skill opt-outs remain in the existing skill-state file.

Keep existing explicit-root precedence semantics where possible. A duplicate pack
id must resolve identically across CLI, SDK, skills and host; test that behavior.
Do not introduce a new precedence policy merely for Hivemind.

An interrupted provisioning/update must leave the prior selected revision intact.
Do not silently delete source revisions that active runs or views still reference.
Uninstall in this milestone means deactivate, not garbage-collect code caches.

## Skill view contract

Required visible shape:

```text
~/.codex/skills/astrid ──> <writable composed view>/
                           SKILL.md             canonical core entry point
                           creative-work/       existing core guidance
                           pack-builder/        existing core guidance
                           packs/
                             hivemind ──> <installed Hivemind root>/skill/
                             rendering ─> <Astrid rendering pack>/skill/
                             ...
                           <generated pack routing index>
```

Apply the same root convention to supported Claude/Hermes adapters, preserving
harness-specific metadata requirements. If per-harness opt-outs differ, they
must receive separate views or a view keyed by the effective pack set.

Implementation rules:

- `SKILL.md` must exist at the view root. A directory containing only `main/` and
  `packs/` is not a discoverable skill.
- Link pack **directories**, not copied instruction bodies, so their local
  references/assets remain available.
- Core entry-point files may be linked individually into a real directory
  skeleton; generated catalog files belong in the view. This avoids writes
  through a symlinked core directory into read-only package files.
- Update core routing references to the composed namespace (for example
  `packs/hivemind/SKILL.md`), and keep the complete catalog out of the main skill.
- Resolve core/view-relative routes from the composed view; once following a
  pack-owned skill, preserve that pack's source-relative resources. Do not blindly
  normalize `..` before following directory symlinks. Test actual file opens from
  the installed harness path, not just link existence.
- Audit core creative-work/pack-builder links too. Their present relative paths
  assume the old checkout layout; do not declare the view finished while these
  links or stage/document references break.
- Package the required core/pack instruction resources for installed-wheel use.
  Where instructions link to authoring guides, include or deliberately expose
  those guides through the source inventory; don't reference absent checkout docs.
- Only replace/prune Astrid-owned generated entries. Never overwrite a foreign
  file/directory merely because its name matches an intended link.
- Existing `astrid-hivemind` aliases can be migrated only when known Astrid-owned.
  The independent `poms_skills/hivemind` source and its unrelated user aliases
  are not deleted. New routing must not depend on them.

## Ordered implementation tasks

### T0 — Establish safe source custody and remove the abandoned prototype

Capture current dirty state and a patch before edits. Separate prior user work,
the completed skill restructuring, and the unfinished Hivemind bundle. No blanket
`git reset`, `git checkout -- .`, or deletion by filename pattern.

Remove the copied `astrid/packs/hivemind/**` only after preserving any useful
manifest/skill adaptation in the external Hivemind worktree. Remove the
bundle-path exception in `_hivemind_source_preflight` and tests that certify that
exception. Remove the Hivemind-specific fallback in skill default selection.
Retain/rework generic installer packaging, entrypoint and explicit opt-out ideas.

Review matrix/ledger edits against actual selected external capabilities. Undo
claims that Hivemind is shipped in Astrid; don't count a historical inventory as
proof of installation. Preserve unrelated local/Discord/Seedance and census work.
The prior registry relocation and core/creative/timeline/references restructuring
are retained; only their installed-view integration changes.

### T1 — Make the canonical external pack admissible

In an isolated Hivemind worktree, migrate the manifest to the current v2 contract,
retain all seven executor identities, and update stale installation/SDK guidance.
Use pack-owned imports and source layout, not `astrid.packs.hivemind` imports.
Validate every referenced resource and module; preserve actual permissions,
credential requirements and result contracts. Record source provenance.

Pin the completed revision in Astrid's default source declaration. The present
`abe41fdf72df3bbcfe45087eae64ccf50a1bb809` is inspection provenance, NOT an approved
post-migration release pin. Never ship a placeholder SHA or silently follow HEAD.
Local Git fixtures/commits suffice for implementation tests; remote publication
is a separate release operation, not authorized merely by this plan.

### T2 — Add explicit default provisioning and inventory

Implement the bounded setup API/module plus declared defaults and one installed
source inventory. Stage/validate/activate pinned checkouts, cache reuse, offline
mode, check, disable and restore. Reuse existing Git/process/path/atomic-file
helpers where available. This layer alone owns acquisition and pack opt-outs.

### T3 — Connect discovery and runtime to the same sources

Extend existing shared discovery with the selected installed roots. Fix `env`
skill bridging using actual source kinds, not an obsolete `installed` label.
Pass resolved/validated roots explicitly through `ensure_pack_host`; keep ambient
`ASTRID_PACKS_PATH` stripped from the child rather than using it as an execution
shortcut. Include the installed source inventory identity in host reuse/restart
checks, so changed revisions cannot leave stale capabilities registered.

Use the existing external Git pin/source-digest admission path. Do not weaken
source verification, provider/network policies, or credential checks to obtain a
successful smoke test. If a provider contract mismatch is demonstrated, fix the
manifest/adapter seam directly and document it; don't redesign runtime custody.

### T4 — Compose and install pack-owned skills

Implement writable view composition using existing SkillDescriptor and adapter
helpers. Generate root entry point/links and catalog deterministically; expose
one parent link per harness; reconcile enabled installed packs and skill opt-outs.
Make install/check/sync/uninstall consistently refer to this view. Ensure source
checkouts and read-only site-packages receive no generated writes.

### T5 — Finish packaging, navigation, and migration

Ship the installer and all needed instruction resources. Update getting-started,
skills-install, core Hivemind routes, generated catalog destinations, and exact
supported command spellings. Repoint only owned stale aliases to the canonical
view/pack source. Verify the existing timeline/rendering, references, Hivemind,
creative-work and pack-builder routes from each installed harness entry point.

### T6 — Validate the combined journey and hand off

Run the acceptance matrix below. Report tested source revision, installed roots,
link targets, selected capability identities, commands and results. Distinguish
source availability, skill visibility, runtime readiness, and remote service
availability. An installed skill link is not evidence of a working executor.

## Acceptance matrix

Use temporary homes, a tiny local Git pack fixture, and an isolated/fake runtime
for deterministic tests. Use actual Hivemind for the final two read-only calls.

| Scenario | Required evidence |
| --- | --- |
| Fresh setup with no personal Hivemind source or environment overrides | Declared Hivemind revision provisioned; root skill and nested pack skill navigable |
| Second setup/sync with network disabled | No downloads or changes; same canonical roots and targets |
| Explicit external/env fixture | Pack and its skill both discovered; no dropped `env` skill |
| Actual installed wheel with source directory read-only | Installer runs; root SKILL exists; nested resources and stage links open; no writes in site-packages |
| Existing source checkout | Same pack ids/roots selected by CLI, SDK, skills and host |
| Pack revision changes | Stage and validate before activation; host identity changes and correct new revision is registered |
| Failed/interrupted download or validation | Prior valid active root and skill view remain usable |
| Source modified after selection/admission | Existing source verification rejects mismatch; no fake readiness |
| Missing pack vs missing link | Check distinguishes them; sync repairs link only; setup restores source |
| Explicit pack disable | Subsequent normal setup honors opt-out; user extra roots untouched |
| Per-harness skill uninstall | That harness hides the skill after sync; pack runtime enablement and other harness choices preserved |
| Explicit restore/reinstall | Clears the matching opt-out, restores declared source/link only |
| Foreign file at generated target | Left untouched with an actionable conflict |
| Duplicate pack id | All consumers apply the same existing documented rule |
| Fresh agent navigation | Astrid → Hivemind pack skill without personal paths or guessing |
| Live Hivemind reads | SDK/runtime search then get_item returns full body and usable source/citation identity; capture receipts/artifacts |
| Remote service unavailable | Clear service failure; installed pack/link still reported present; no reinstall loop |
| Write paths | All seven discovered; credential-gated behavior checked without corpus publication |

Existing suites to select from after reading current tests: `tests/test_skills.py`,
`tests/test_skills_sync_registry.py`, packaging tests, pack discovery tests,
`tests/integrations/test_generic_host_external_provider.py`, and
`tests/v10/test_docs_cli_alignment.py`. Add source/host parity and composed-view
resource tests rather than tests that merely assert rewritten prose.

## Scope, estimate, and stopping point

Expected effort: approximately 2–4 focused engineering days, depending
on external v2 manifest/resource compatibility and host source-root integration.
This is an engineering estimate, not a promised agent wall-clock duration.

Out of scope: rewriting Hivemind search, dropping its write capabilities,
marketplace/catalog UI, new runtime state stores, arbitrary dependency solvers,
background auto-updating packs, broad pack taxonomy redesign, and fixing unrelated
creative pipelines. A small explicit default-source list is sufficient.

This turn delivers a plan only. Implementation should stop when the complete
fresh-install → skill-navigation → read-only search/retrieval path and the key
recovery/opt-out cases pass. Do not certify completion from symlink or unit tests
alone. The exact post-migration Hivemind pin is an implementation output, not an
unanswered user preference.

## Evidence and corrections to agent memos

- [Luna default provisioning investigation](evidence/luna-default-packs.md)
- [Luna skill linking investigation](evidence/luna-skill-links.md)
- [Luna cleanup/review inventory](evidence/luna-cleanup.md)
- [Source state](source-state.json)

The coordinator resolves several overbroad or incorrect suggestions in those
memos: the neutral setup owner was not established; Astrid host bootstrap is a
concrete existing seam. A skill view must contain root SKILL.md. Default policy
must not depend on a v2-invalid install_tier field. Historical installed counts
are not live discovery. Unrelated dirty files are to preserve, not revert.
