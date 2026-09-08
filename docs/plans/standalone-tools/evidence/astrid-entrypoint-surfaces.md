# Astrid entrypoint and packaging surfaces

Read-only mapping of the current Astrid user/agent entrypoints, skill CLI,
pack CLI and packaging boundary. No implementation or runtime changes were
made.

## Public entrypoints

- `pyproject.toml:38-39` installs the `astrid` console script to
  `astrid.core.gateway:main`; `astrid/__main__.py` is the module equivalent.
  `README.md:45-46` and `docs/getting-started.md:21-23` direct users through
  `python3 -m astrid`, after `banodoco-local up --profile astrid`.
- The gateway's seven-family census is documented in root `AGENTS.md`:
  projects, timelines, media, tasks, runs, doctor and backup. Hivemind should
  enter through the existing executor/pack route, not a new gateway family.
- `astrid/core/pack/cli.py:86-117` is the existing `astrid packs` handler
  surface. It re-exports parser/basic/inspect/search modules and returns
  structured exit codes through the existing `AstridError` renderer.
- `astrid/skills/__main__.py` and `astrid/skills/cli.py:35-94` expose
  `python -m astrid.skills` with list/install/uninstall/sync/doctor operations.
  The CLI is already separate from the seven-family product gateway and is the
  right place for skill-view reconciliation after setup supplies roots.

## Packaging and dependency boundary

`pyproject.toml:74-132` uses setuptools package discovery and explicit package
data. It excludes most skill/golden/test trees from package discovery while
explicitly including `packs/**/pack.yaml`, skill files, manifests and runtime
assets. Any installed-wheel solution must verify that the core skill and
pack-owned resources actually reachable from the composed view are included;
the current patterns do not automatically package external Hivemind content.

`pyproject.toml:50-52` pins the external timeline-schema package by Git
revision. `astrid/sdk/host_bootstrap.py:160-200` additionally resolves source
checkout Remotion, Node and timeline-schema roots at host launch. This is the
existing dependency bootstrap seam. Hivemind's own dependencies and public /
secret environment requirements remain Hivemind-owned and must be declared by
its future v2 manifest; Astrid should pass declared inputs rather than duplicate
Hivemind CLI behavior.

`astrid/sdk/autobootstrap.py:75-125` resolves `banodoco-local` from an explicit
environment setting, PATH, or installed module and runs `up --profile astrid`
with bounded timeout/JSON validation. The launcher source manifest is accepted
only through `BANODOCO_LOCAL_SOURCE_MANIFEST`; Astrid deliberately does not
reconstruct the neutral runtime profile. A future pack provisioner must update
that owner-facing source profile through its supported interface.

## Existing consumers and minimal integration path

The CLI-to-runtime path is: gateway/SDK invocation → registry discovery
(`astrid/sdk/discovery.py:35-130`) → generic host bootstrap
(`astrid/sdk/host_bootstrap.py:309-519`) → selected pack root and executor.
Skill setup is a parallel instruction path: `astrid.skills.discovery` builds
descriptors, harness adapters install links, and `registry.py` regenerates the
managed pack index. Both must read the same resolved pack inventory.

The smallest future entrypoint work is therefore:

1. Add or expose setup provisioning outside the seven-family gateway, with
   `--check` and offline/read-only modes as specified in the default-packs plan.
2. Make `astrid.skills sync` consume the installed inventory and correct the
   `env` versus `installed` source-kind mismatch in the current prototype.
3. Keep the Hivemind invocation as structured argv through the future thin
   external executor; preserve stdout, stderr, exit status and artifacts in
   Astrid's existing task/run result path.
4. Verify wheel package data and harness links from a clean installation.

No second tool registry, semantic shim framework, or Hivemind-specific gateway
branch is indicated by these entrypoints.

## Dirty-state and plan overlap

The checkout contains broad dirty changes, including `astrid/skills/__init__.py`,
`astrid/skills/registry.py`, `astrid/skills/state.py`, `astrid/sdk/host_bootstrap.py`,
`pyproject.toml`, a bundled `astrid/packs/hivemind/`, and many unrelated media,
timeline and rendering files. Those changes must be split by ownership before
implementation. The default-packs plan and standalone-tools plan describe the
intended provisioning/composed-view work but explicitly say it is not
implemented or certified. Their `.otto/runs/astrid-default-packs-and-skills/
run.yaml` is planning-only with no executable review stages; preserve its role
and budget policy for any later authorized run.

Acceptance later should exercise `python -m astrid --help`, `astrid packs`
validation/listing, `python -m astrid.skills --help` and `skills sync --dry-run`
against clean in-tree and external-pack fixtures, wheel package-data checks,
launcher/profile handoff, host source-digest restart, and a real Hivemind argv
round trip. This report does not run those checks.
