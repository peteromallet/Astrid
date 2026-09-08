# Hivemind direct CLI route (read-only investigation, 2026-09-08)

## Decision correction

The primary Astrid route must expose the actual Hivemind CLI, because the user
already relies on its complete command surface. The repository executors remain
valuable for structured operations that the CLI does not provide (notably
ingestion, contribution, and the richer paged search contract), but they should
not displace or hide the CLI.

The installed CLI is a single stdlib Python script with no package imports. It
can be invoked as an argv subprocess and returns ordinary exit codes. Its
machine surface is uneven: `--json` exists on several commands, while the
default output is deliberately human-readable. `media` is a POST refresh
operation; the other CLI commands are GET/read operations. This makes it
possible to expose the full CLI safely while still classifying effects.

## Existing Astrid seams

Astrid already has the pieces needed for a direct route:

* `ExecutorDefinition` supports typed ports, argv command templates, output
  path templates, isolation, binaries, environment passthrough, and versions.
* The generic host and runner execute argv arrays in owned process groups,
  capture diagnostics, poll cancellation, publish declared outputs, and retain
  task/run identity.
* `sdk.discover()` and `sdk.get_capability()` are the agent-facing discovery
  contract; `sdk.invoke()` supplies the normal provenance and run lifecycle.
* `extra_pack_roots` / `ASTRID_PACKS_PATH` already permit explicit external
  pack discovery, but discovery is pack-shaped. A standalone executable cannot
  currently register itself without a wrapper pack.
* `ExternalRuntimeMetadata` in
  `astrid/core/execution/executor/schema.py` is a useful schema seed (git/path/
  pypi source, install strategy, import/binary checks), but it is currently
  validation-only: no resolver/install path uses it, and `to_dict()` removes
  it from the serialized definition.

The existing agent guide says every capability belongs to a pack and every
executor invocation requires a project unless it is explicitly listed in
`_PROJECT_OPTIONAL_CAPABILITIES`. Therefore the direct-tool work has two
separate extensions: a registration/adapter seam for tools, and explicit
workspace-scoped invocation for read-only utilities such as Hivemind.

## Recommended Hivemind shape

Create a small Astrid-owned adapter pack, for example `hivemind_adapter`, whose
only runtime responsibility is to resolve and invoke the user-selected pinned
Hivemind CLI. It must not contain PostgREST logic. Its manifest can expose the
CLI either as one transparent capability with a validated `command` plus
subcommand/argument schema, or as generated thin capabilities per subcommand.

The user-facing/agent-facing experience should be per-subcommand capabilities
because that gives agents typed inputs and recoverable errors while retaining
the exact CLI behavior. The implementation can be one generic runner that
constructs argv from a descriptor:

```text
hivemind.cli.search
hivemind.cli.probe
hivemind.cli.trend
hivemind.cli.recent
hivemind.cli.around
hivemind.cli.day
hivemind.cli.profile
hivemind.cli.reactions
hivemind.cli.media
hivemind.cli.top_reacted
hivemind.cli.get
hivemind.cli.cites
```

The aliases may also preserve the natural names (`hivemind.search`, etc.) if
the pack namespace is unambiguous. The important point is that each capability
records the native subcommand, accepts only declared flags, and cannot turn
into arbitrary shell execution. For commands with JSON output, the adapter
should require `--json`, store the raw JSON as the primary artifact, and keep
stderr separately. For human-only commands, store stdout as text and include
the exact exit code and stderr in the result envelope.

The direct CLI adapter should support `hivemind` as an executable path,
`python -m ...` as a module path where available, and a pinned source checkout
as an explicit development mode. At registration it should resolve the
executable, run a version/identity probe where possible, record path plus
source/tree digest, and reject an unexpected PATH binary. The resolved identity
and adapter manifest digest must enter the immutable admission payload so a
changed CLI invalidates readiness rather than silently reusing an old worker.

Use a structured effect declaration on each descriptor:

* search/probe/trend/recent/around/day/profile/reactions/top-reacted/get/cites:
  `read_only`, workspace-scoped by default;
* media: `external_refresh`, network POST, no corpus mutation;
* upstream contribute/ingest executors: `corpus_write`, explicit write
  admission and contributor-key environment injection; dry-run remains the
  default for agent previews.

This lets agent discovery explain why a Hivemind operation is safe or requires
write admission without inspecting implementation code.

## Semantic shims

A semantic shim is useful above the direct CLI, but it should be a separate
layer. For example, an agent-friendly `hivemind.search_for_workflows` shim can
choose terms, channels, date windows, JSON mode, and pagination, then invoke
the native CLI or the structured executor. It should return the native output
plus a small normalized interpretation and retain the underlying invocation
receipt. A shim may select among CLI commands and executors, but it must not
reimplement Hivemind's database queries or silently change ranking semantics.

This gives us a general pattern for other tools:

1. direct tool capability: complete native surface and raw artifacts;
2. semantic shim: typed, task-shaped convenience operation that delegates to
   the direct capability;
3. Astrid orchestration: project/workspace scope, task/run lifecycle,
   cancellation, provenance, and artifact publication.

## Migration from bundled duplication

The current Hivemind external pack should remain available for its unique
structured executors, but any Astrid-local duplicate of Hivemind search or
REST query code should be retired behind the adapter migration. The migration
order should be:

1. register the actual CLI route and prove every CLI subcommand is discoverable;
2. migrate agent skill guidance to call the direct capabilities, with semantic
   shims only where they add useful task vocabulary;
3. preserve the repository executors for structured search/ingest/contribute
   where they add capabilities or machine contracts the CLI lacks;
4. remove duplicated query implementations only after parity receipts exist;
5. keep a compatibility alias for old capability ids and record deprecation
   provenance until callers have migrated.

Do not make the CLI route depend on a selected project. A read-only Hivemind
query should create a first-class Astrid run with `scope=workspace` (or an
equivalent explicit system scope), optionally attach the active/last-selected
project for context, and still work when no project exists. Project selection
is host state resolution, not a precondition for using a knowledge tool.

## Agent ergonomics and validation

The SDK inventory should expose, for each direct capability, the native
subcommand, typed arguments, effect, network policy, output mode, tool version,
source digest, and whether project scope is optional. An agent should be able
to call `sdk.discover()` and then invoke `hivemind.cli.recent` without knowing
the executable path or manually managing `--json`.

The first conformance suite should run the CLI in a fixture environment and
prove: all command descriptors map to valid argv; JSON commands produce
parseable primary artifacts; stdout/stderr are not mixed; no secret appears in
logs or receipts; media is classified as an external POST; missing project
does not block read-only commands; cancellation kills the child process group;
and source/version changes invalidate the capability registration. A separate
shim test should prove that a semantic operation retains the direct CLI
receipt and raw output.

Evidence reviewed: `Astrid/astrid/core/execution/executor/schema.py`,
`Astrid/astrid/core/execution/executor/registry.py`,
`Astrid/astrid/sdk/invocation.py`,
`Astrid/astrid/core/execution/generic_host.py`,
`Astrid/docs/guides/discovery-for-agents.md`,
`Astrid/docs/plans/standalone-tools/evidence/runtime-contracts.md`, and
`/Users/peteromalley/Documents/poms_skills/hivemind/hivemind`.

## Canonical-owner finding

The repository provenance is decisive. `banodoco/hivemind` has the only Git
remote (`https://github.com/banodoco/hivemind.git`), its `origin/main` is
`45927ad` (“Search rewrite: raw-table per-token search + CLI packaging”), and
the current local `main` is one commit ahead with executor network-policy
fixes. The repo's 45927ad README calls the repository “one repo, three
products” and documents the executor's `python3 executors/search/run.py` and
the packaged `hivemind-search` entrypoint. It does not contain the standalone
`hivemind` script.

The script at `/Users/peteromalley/Documents/poms_skills/hivemind/hivemind` is
Git-tracked in a separate repository, `peteromallet/poms-skills.git`, with
recent commits `b96563f` (“Publish Hivemind and Megado skills”) and `99ba29d`
(“Generalize public skill examples and cloud paths”). It is newer local skill
tooling (mtime 2026-09-08), but its repository is separate from the Hivemind
domain repository and its history does not establish that it is the canonical
owner of the corpus product. The evidence supports calling it a maintained
secondary client, not claiming it is provenance-free. Exact intent/lineage
between the two repositories remains uncertain.

The single-owner recommendation should consequently be: **move/consolidate
the complete CLI surface into `banodoco/hivemind`, and make Astrid invoke that
one maintained Hivemind distribution.** This is an architectural
recommendation, not evidence that only one repository currently contains
Hivemind code. The upstream repo should own the command parser,
REST behavior, output contracts, retries, and all command features. Its
existing executor modules may become the implementation library behind the
CLI; where a legacy CLI command has no executor equivalent, port that command
into the same repo and tests. Do not retain a second Astrid-local Hivemind
query implementation, and do not expose a competing set of Astrid-native
Hivemind capabilities.

The migration target is one Hivemind installation with two entry styles owned
by that repo: an ordinary human CLI (`hivemind ...`) and a stable structured
machine mode (for example `--json`/JSON output and/or the existing executor
module contract). Astrid then has one thin external-tool adapter for the
distribution, with the full native CLI available through a constrained
argv/subcommand schema. Any agent convenience is a prompt/skill shim that
selects native arguments; it is not another semantic implementation or
capability family. The existing Astrid external-pack executor manifests should
be migrated into this owner or retained only as a compatibility bridge while
the upstream CLI reaches feature parity.

This removes the false choice between “CLI versus executors”: the CLI is the
single user-facing owner, and executor modules are internal/library entry
points in that same Hivemind repo. Astrid owns process custody, admission,
workspace/project scope, cancellation, artifact publication, and provenance;
Hivemind owns its domain behavior. A source checkout or pinned package of the
Hivemind repo is the only source Astrid should resolve.
