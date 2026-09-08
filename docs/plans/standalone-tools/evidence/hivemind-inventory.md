# Hivemind inventory (read-only, 2026-09-08)

## The important boundary

There are currently two different Hivemind clients:

* `/Users/peteromalley/Documents/poms_skills/hivemind/hivemind` (also linked as `~/.local/bin/hivemind`) is a dependency-free, human-facing Python CLI. It is not present in the Hivemind git repository. Its `main()` dispatches 14 commands (plus help): search (including the bare query shorthand), probe, trend, authors, top-authors, recent, around, day, profile, reactions, media, top-reacted, get, and cites. It speaks directly to the public PostgREST endpoint and has its own retrying HTTP helper, formatting, pagination/keyset handling, date parsing, URL extraction, and Discord media refresh code.
* `/Users/peteromalley/Documents/banodoco-workspace/hivemind` is the maintained source repository at git `abe41fd` (main; parent `45927ad`). Its Python package is version `2.0.0`, stdlib-only, and its `pyproject.toml` exposes only `hivemind-search = hivemind.executors.search.run:main`. There is no installed `hivemind` console script in this repository. The package's canonical Astrid-facing surface is the executor set described by `pack.yaml`.

Therefore, Astrid must not assume that the current CLI is the canonical implementation of every feature, and it must not copy the CLI's query logic into a pack. The repo executors are the maintained reusable implementation; the standalone CLI is a separate convenience client with a wider human-oriented command set.

## Personal-skill history evidence

The available transcript evidence does not establish the original creation
date or rationale for the personal CLI. It does establish that by 2026-08-11
the personal skill existed at `/Users/peteromalley/Documents/poms_skills/hivemind/SKILL.md`,
and that `poms_skills/sync.sh` described that tree as the source of truth for
personal skills, symlinked into Claude/Codex/Agents skill directories. The
personal repository history currently shows publication commits on 2026-09-08
(`b96563f`, followed by `99ba29d`). This supports treating `poms_skills` as a
personal launcher location, but does not prove the CLI was accidentally
created there or that it was copied from upstream.

## Repository components and effects

`pack.yaml` declares an external capability pack `hivemind` version 2.0.0 with network, environment, and (only for YouTube) subprocess permissions. It declares seven capabilities:

| capability | implementation | output | effect |
|---|---|---|---|
| `hivemind.search` | raw-table, per-token ILIKE search across `message_feed`, `external_resources`, and `distillations`; deterministic client ranking and paging | JSON `results.json` with `results`, `count`, `total`, `has_more`, `page`, `pages`, `next_offset`; human summary on stderr | read-only PostgREST GETs |
| `hivemind.get_item` | one full item plus citation relationships | JSON `item.json` | read-only GETs |
| `hivemind.refresh_media` | public `refresh-media-urls` edge function | JSON `result.json` | POST refresh request; refreshes/returns Discord CDN URLs, no corpus write |
| `hivemind.contribute` | locked `add_resource` / `submit_distillation` envelope | JSON `result.json` | corpus write through edge function; requires contributor key; `--dry-run` is safe |
| `hivemind.ingest_article` | fetch HTML, extract readable text, contribute resource | JSON `result.json` | external URL fetch plus corpus write unless dry-run |
| `hivemind.ingest_workflow` | load local/remote ComfyUI JSON, extract models/custom nodes/body, contribute workflow | JSON `result.json` | local file or URL read plus corpus write unless dry-run |
| `hivemind.ingest_youtube` | shell out to `yt-dlp` for captions and metadata; contribute transcript | JSON `result.json` | network, child binary, and corpus write unless dry-run; no audio/Whisper |

All executor runtimes use `executor.yaml` command templates and `run.py` modules, write a machine-readable output file, and return non-zero on errors. `_common.py` resolves `HIVEMIND_API_URL`, `HIVEMIND_ANON_KEY`, `HIVEMIND_CONTRIBUTOR_KEY`, and edge-function URL overrides, with baked-in public read defaults. `contribute` is the only corpus mutation path; contributor keys are deliberately not manifest inputs and must be injected by the host environment.

The repo also contains database/retrieval migration scripts, embedding/backfill jobs, evaluation harnesses, and tests. These are development/operations code, not end-user Astrid capabilities. Do not expose the `scripts/` or `eval/` tree as generic user tools without a separate, explicit operation manifest.

## CLI/executor overlap and differences

The repository executor search is newer and materially different from the installed CLI's `cmd_search`: executor search searches the raw tables in parallel, uses per-token arms, ranking scores, kind/source/channel/author/thread filters, and a stable offset paging contract. The installed CLI's search queries `unified_feed`, deliberately fetches distillations first, then other rows, and falls back to a 90-day scope after timeout. The two can return different rows and should not be presented as interchangeable implementations.

The installed CLI has useful read-only operational commands with no corresponding repo executor: probe, trend, authors, top-authors, recent, around, day, profile, reactions, top-reacted, and cites (the repo `get_item` covers a related but richer single-item operation). Conversely, the repo exposes structured ingestion and contribution executors that the CLI does not expose as subcommands. The CLI's `media` is the closest match to `refresh_media`; `get` is a simpler human-oriented cousin of `get_item`.

The installed CLI makes one POST only for `media` (the public media refresh function); all its searches and reads are GETs. The repo ingest/contribute executors can POST corpus data and must be treated as write-capable operations. This distinction should be visible in Astrid capability metadata and admission UI.

## What Astrid already provides

Astrid's executor registry (`astrid/core/execution/executor/registry.py`) already discovers external packs, loads `executor.yaml`, validates them, attaches source-pack/path metadata, resolves the declared runtime, and admits invocations through the SDK/runtime. The existing `media.clip_extract` manifest demonstrates the useful shape: typed inputs, output path templates, an `isolation` block (`mode: subprocess`, network policy, required binaries), and an output result manifest. `astrid/sdk/invocation.py` records capability identity/version, project/task/run linkage, outputs, and failure state.

This means Hivemind's seven repo executors are already close to first-class Astrid citizens if the pack is installed/discovered from its source checkout (or a pinned packaged snapshot). The gap is a generic way to expose an independently maintained tool's own CLI, especially when the tool has commands/features not worth rewriting as separate Astrid Python executors.

## Recommended generalized design

Add an Astrid **external tool adapter** as a thin, manifest-driven executor source. A tool descriptor should declare:

* stable tool id, source URI/ref, version/digest, install/runtime strategy, and executable/module entrypoint;
* a command schema with typed positional/flag inputs, argument-list construction (never shell strings), stdin policy, and timeout/streaming policy;
* output contract: stdout/stderr capture, JSON/file outputs, exit-code mapping, and artifact globs/path templates;
* isolation: network destinations/protocols, environment names (with secret values injected by host), required binaries, working-directory and writable-root rules;
* effects: read-only, external side effect (for example URL refresh), or corpus mutation; dry-run support where available;
* provenance: source commit/version, exact argv after redaction, environment names (never values), and adapter/manifest digest.

The adapter should invoke an installed/pinned executable or module via `subprocess` with an argv array, capture stdout/stderr, enforce the declared policy, materialize declared output files, and return the normal Astrid invocation result. It should not parse or reimplement the tool's domain semantics. A shim remains appropriate for UX normalization (for example translating a Hivemind search form into `hivemind.executors.search.run` arguments), but the shim's output must retain the tool's raw JSON as an artifact and identify the exact tool version.

For Hivemind, the first adapter should point at the repo's executor package/pack, not the `~/.local/bin/hivemind` convenience CLI. Register the seven existing manifests as the canonical read/write capabilities. Add a separate optional CLI adapter for the human CLI only if Astrid needs its extra operational commands; initially expose it as one `hivemind.cli` capability with a constrained argv allowlist or generated subcommand manifests, not arbitrary executable passthrough. This preserves all existing Hivemind features without duplicating PostgREST logic and makes ownership explicit.

Project association should be optional at the execution contract level. Read-only searches such as Hivemind can run at workspace scope, while a caller may attach them to the active/last-selected/default project for provenance. The runtime should still create a run/ledger record when no project is selected, using an explicit workspace or system scope rather than failing. Project defaults belong in Astrid host state/resolution, not in the external tool adapter.

## Deployment recommendation

Support three source modes with the same manifest contract:

1. **In-tree/external pack:** source checkout is available; discover its `pack.yaml` and executors directly. This is the correct mode for the local Hivemind checkout during development.
2. **Pinned package/release:** install a tagged wheel or archive and record version plus hash. This is the correct reproducible user/runtime mode; Hivemind's stdlib-only package is well suited to it, although its current `pyproject` does not package the standalone convenience CLI as `hivemind`.
3. **System executable:** resolve a named executable only after checking identity/version and record its path, version, and digest. This is for tools that cannot be packaged; never silently trust an arbitrary PATH binary.

Keep the external pack source of truth with Hivemind. Astrid should vendor only the manifest/adapter metadata needed for discovery when offline, with a pinned provenance link, and should fail clearly if the declared runtime is missing. Do not fork Hivemind query implementations into Astrid.

## Concrete next slice

Implement the adapter contract and a workspace-scoped invocation path first, then register the Hivemind repo pack as a fixture/source. Add conformance checks proving: (a) `hivemind.search` emits valid paging JSON and preserves stderr separately, (b) `refresh_media` is classified as an external POST effect, (c) contribute/ingest require explicit write admission or dry-run, (d) secrets are absent from logs/provenance, (e) a run without a selected project still receives a stable workspace scope and artifact ledger row, and (f) a pinned source/version is visible in discovery and run results.

Relevant evidence paths: Hivemind `pack.yaml`, all seven `executors/*/executor.yaml`, `executors/_common.py`, `executors/*/run.py`, `pyproject.toml`, and the installed CLI `/Users/peteromalley/Documents/poms_skills/hivemind/hivemind`; Astrid registry `astrid/core/execution/executor/registry.py`, sample manifest `astrid/packs/media/executors/clip_extract/executor.yaml`, and invocation ledger path `astrid/sdk/invocation.py`.
