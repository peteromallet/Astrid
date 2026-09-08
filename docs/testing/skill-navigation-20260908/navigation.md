# Astrid skill navigation audit — 2026-09-08

Scope: read-only maker navigation from `astrid/packs/_core/skill/SKILL.md`; no
conversation/audit-report reading, external search, rendering, opening, retry,
or source/runtime mutation. Runtime calls below were discovery/read calls only.

## Chronological trace and counts

1. Read `_core/skill/SKILL.md` (primary entry point).
2. Followed its getting-started link: `docs/getting-started.md`.
3. Followed its rendering link: `astrid/packs/rendering/skill/SKILL.md`.
4. Read linked `docs/guides/cli-journeys.md` for the five public journeys.
5. Read linked `docs/guides/debugging.md` for render failure inspection.
6. Read generated `astrid/packs/_core/skill/references/capabilities.md`; this
   was unnecessary for these five CLI navigation questions (no exact SDK id was
   needed).
7. Verified parser/help surfaces with eight invocations: `astrid --help`,
   `projects --help`, `runs open --help`, `timelines list --help`,
   `timelines recover --help`, `timelines visualize --help`, `runs show
   --help`, and `runs retry --help`.
8. Read-only runtime calls: `doctor --json` (returned unavailable: credential
   lacks required scope, next action `banodoco-local up --profile astrid`),
   `projects list --json` (found `astrid-intro`), `timelines list`, `runs list`,
   `projects current` (no selected project), a second `runs list` parsed with
   jq, `timelines list --include-archived`, a third `runs list` parsed for
   timeline provenance, `timelines show main-final`, `runs show --evidence` for
   the failed run, and `runs events` for that run.

Measured totals: 6 guidance documents opened (5 relevant, 1 unnecessary), 8
help/parser calls, 12 read-only product calls (including repeated narrowed
reads), 0 SDK calls, and 1 backtrack (the first jq projection assumed
`.data[0]` for `timelines show`; the corrected projection used `.data`). The
first runtime discovery warmed later queries: project slug, timeline ids, and
run inventory were reused. Minimum route counts below therefore exclude the
warm-context inventory work; they are estimates, not additional measured calls.

## Five maker trials

### 1. Find the Astrid introductory video’s main timeline and open its render

**Success.** Runtime discovery found project `astrid-intro`, configured default
timeline id `2652b5567c8e4e9aa4d35c1df0eb2742`, active slug
`main-final-blackend2`, and successful render `210e7312866f46b09038b5dd1453d320`
whose provenance names that timeline. The exact open command is:

```bash
python3 -m astrid runs open --project astrid-intro --default-timeline
```

This was deliberately not invoked. The documented route says default-timeline
resolves `metadata.default_timeline_id` and requires matching successful
`rendering.render` provenance ([`astrid/packs/_core/skill/SKILL.md:68-80`](../../../astrid/packs/_core/skill/SKILL.md#L68)). The runtime evidence is the successful project/timeline/run list reads above.

Ambiguity: “main” is a user label rather than a unique convention: many
archived slugs contain `main`, while the project default is authoritative.
Shortest supported route after discovery: the one command above. Minimum cold
route: `projects list` → `timelines list` → `runs open --default-timeline`.

### 2. Start a first Astrid project on a new machine

**Partial (route is clear; this machine’s health check is unavailable).** The
documented cold path is:

```bash
pip install .
python3 -m pip install 'banodoco-workspace-runtime @ git+https://github.com/banodoco/banodoco-workspace-runtime.git@4050394c5395206f1ec6bf0d905ffbfb7bb0e4de'
export BANODOCO_LOCAL_SOURCE_MANIFEST=/path/to/astrid-source-profile.json
python3 -m astrid --help
python3 -m astrid doctor --json
python3 -m astrid projects list --json
```

If the runtime is unavailable, the explicit operator command is
`banodoco-local up --profile astrid`; the guide says the runtime owns durable
state and no separate database is needed ([`docs/getting-started.md:8-36`](../../getting-started.md#L8)). Actual `doctor --json` returned `state: unavailable` with `credential lacks required scope` and that next action. Once healthy, the documented create endpoint is `python3 -m astrid projects create <slug> --name "<name>" --json` (the create action was not invoked because this audit is read-only).

Ambiguity: “start my first project” can mean install/bootstrap or create a
project; the guide covers bootstrap and discovery, while project creation is a
separate mutating command. Minimum read-only route: `doctor --json`; minimum
operational route after configuration: `projects list --json`.

### 3. Resume an archived timeline

**Success.** `timelines list --include-archived` exposed archived slug
`main-final`; `timelines show --project astrid-intro main-final --json`
confirmed `archived: true`. The supported resume command is:

```bash
python3 -m astrid timelines recover main-final --project astrid-intro --json
```

It was not invoked because recovery mutates runtime state. The primary skill
explicitly pairs archived discovery with `timelines recover`
([`astrid/packs/_core/skill/SKILL.md:82-89`](../../../astrid/packs/_core/skill/SKILL.md#L82)). The
parser accepts a UUID, ULID, or slug from `list --include-archived`
([`astrid/packs/timeline/cli.py:575-583`](../../../astrid/packs/timeline/cli.py#L575)).

Ambiguity: several archived `main-*` timelines exist, so “an archived timeline”
requires choosing a returned ref; `main-final` is the measured example.
Minimum route: `timelines list --include-archived` → `timelines recover <ref>`.

### 4. Inspect a failed render and retry it

**Success with a useful caveat.** Runtime run inventory found failed run
`71f77261d3d94690b506315ea3ef2636`. `runs show --evidence` returned status
`failed` but null `failures` and null `evidence`; `runs events` exposed the
actual `task.failed` payload: Remotion exited 1 because `ENOSPC: no space left
on device`, with `retryable: false`. The shortest inspection route is:

```bash
python3 -m astrid runs show --project astrid-intro 71f77261d3d94690b506315ea3ef2636 --evidence --json
python3 -m astrid runs events --project astrid-intro 71f77261d3d94690b506315ea3ef2636 --json
```

After correcting the reported condition, the documented retry endpoint is
`python3 -m astrid runs retry --project astrid-intro 71f77261d3d94690b506315ea3ef2636 --json`; it was not invoked. The guide documents `runs show --evidence` and `runs events` ([`docs/guides/cli-journeys.md:318-335`](../../guides/cli-journeys.md#L318)), and the debugging guide says preserve the timeline, inspect the failure record, then retry only after correction ([`docs/guides/debugging.md:44-63`](../../guides/debugging.md#L44)).

Ambiguity: `runs show --evidence` is advertised as sufficient, but this real
failed run required the event stream for the error detail. Also, the measured
error says `retryable: false`, so retry guidance is conditional, not an
immediate action. Minimum route: `runs show --evidence` → `runs events`; retry
only if the corrected condition and runtime guidance permit it.

### 5. Show a visual overview before changing the main timeline

**Success as a supported plan; deliberately not invoked.** For the measured
default timeline, the endpoint is:

```bash
python3 -m astrid timelines visualize --project astrid-intro \
  --timeline-slug main-final-blackend2 \
  --format md,png,svg --layout both --filmstrip off --json
```

The command is read-only/run-owned and returns a durable `manifest_path`; omit
`--out`. The rendering skill documents the same safe first pass
([`astrid/packs/rendering/skill/SKILL.md:36-47`](../../../astrid/packs/rendering/skill/SKILL.md#L36)). Parser help confirms the timeline selector, formats, layout, filmstrip policy, and that `--out` is unsupported compatibility only ([`astrid/packs/timeline/cli.py:600-644`](../../../astrid/packs/timeline/cli.py#L600)).

Ambiguity: “visual overview” could mean one timeline or every active timeline;
the default-timeline-specific command above is shortest, while `--all` is the
documented broader option. Minimum route: one visualize call after the timeline
ref is known.

## Overall assessment

**4 success, 1 partial.** Astrid’s runtime-first discovery, archived recovery,
failed-run event inspection, and visual-evidence endpoint are actionable and
parser-verified. New-machine onboarding is documented but was not fully
reachable in this environment because `doctor` reported a missing credential
scope; first-project creation is intentionally outside this read-only trial.
The main usability friction found is that failed `runs show --evidence` can be
structurally empty, making `runs events` an extra required discovery step.
