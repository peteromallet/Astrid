# One canonical Hivemind source, consumed by Astrid

Status: H1 implemented and H2 independently reviewed; Astrid integration is a plan,
not an implemented or certified feature. This plan supersedes the exploratory
two-level integration proposals. It extends, rather than replaces,
`../astrid-default-packs-and-skills/PLAN.md`.

## Result

A user can run Hivemind independently or ask an Astrid agent to use it. Both
use code maintained in `banodoco/hivemind`. Astrid records the selected source,
arguments, task, run, outcome and output artifacts through its existing
workspace runtime. The personal skill and Astrid contain no separate query
implementation.

This is the general rule for integrating an existing tool: identify its owning
repository and supported interface, reuse it through an external executor,
and keep only invocation/output adaptation in the adapter. A separate CLI
framework, tool registry, installer database, or hierarchy of integration
levels is not required for Hivemind.

## Proposed caller contract

The following is the target interface, not a currently verified capability:

```python
from astrid.sdk import AstridClient

with AstridClient.open_from_launcher() as client:
    result = client.invoke_result(
        "hivemind.cli",
        kind="executor",
        inputs={"argv": ["recent", "--channel", "minimax_h3_chatter",
                         "--term", "dialogue", "--limit", "10", "--json"]},
        wait=True,
    )
```

`argv` is a list of strings, never a shell command. The pack adapter calls the
upstream CLI entrypoint, does not infer flags or universally append `--json`,
and returns the CLI's exit status and captured output. JSON is parsed only when
the chosen command actually produces it. Astrid's result carries task/run IDs
and runtime artifact references; it does not pretend every CLI result is media.
The same CLI invocation independently is `hivemind recent ... --json`.

Tool installation and its instructions come from the same selected upstream
source. The manifest records the execution interface and required permissions;
the runtime records which revision/source digest actually executed. Future
tools use this existing external-executor contract and their supported public
interface, rather than joining a second integration framework.

## Verified starting point

- The upstream Hivemind package has seven executors, shared helpers, tests,
  and the `hivemind-search` console entrypoint. Its pack manifest is still v1.
- The personal CLI contains fourteen useful commands plus help in one script.
  Its query behavior is separate, including an older `unified_feed` search.
- Astrid's dirty bundled Hivemind copy contains useful fixes that are not all
  present upstream. Preserve and port these before removing the copy.
- The workspace runtime already supports tasks without a project. This
  session verified projectless search execution and artifact-byte retrieval.
- The SDK now reads the persisted project selection for project-bound work,
  but its read-only exemption is a Hivemind-specific list to generalize.
- Verified external-source provisioning is specified in the existing default
  packs plan, but has not been implemented or certified.

## Tasks and dependencies

### H1 — Consolidate Hivemind's interface (Luna implementation)

Owner files: upstream `cli.py`, `pyproject.toml`, CLI tests and documentation.
Move the personal CLI feature surface into the package. Make CLI search call
the upstream search implementation; retain all useful researcher commands.
Preserve `hivemind-search` as a delegating compatibility entrypoint.

Acceptance: fourteen commands discoverable; tests for dispatch, scoped/keyset
paging, exact snowflakes, context retrieval, JSON/text and failure behavior.
Search must not restore broad `unified_feed` text queries. Document any
intentional flag differences. Test offline with controlled HTTP responses.

### H2 — Independent compatibility review (Luna; after H1)

Compare the old command surface against the package, inspect the patch and
run the focused tests independently. Check argument meanings, not just names:
date windows, repeated terms, limits, ID preservation, output shape, exit codes
and actual request filters. Fix regressions in H1 before moving to cutover.

### H3 — Prepare the repo-owned Astrid pack (after H2)

Port the useful fixes from the bundled copy: narrow full-message lookup,
string IDs and canonical public/secret environment declarations. Upgrade the
upstream pack manifest to Astrid's supported v2 contract and validate it.
Expose the package's CLI through a thin repo-owned executor using its public
entrypoint and a structured argv list. Capture stdout/stderr and structured
results without reimplementing command behavior. Existing structured
operations may remain delegating entrypoints; they must share their owning
implementation, not become another feature-development branch.

Acceptance: upstream pack validates, all features remain independently usable,
argv reaches the same implementation without shell interpolation, outputs are
declared, failures preserve diagnostics, and read tests make no corpus writes.

### A1 — Select the external source (after H3)

Implement the existing default-packs plan's verified source acquisition and
shared inventory, using a reviewed immutable Hivemind revision. Pass the same
selected root to SDK discovery, skills and generic-host startup. Updates stage
and validate before activation; interrupted updates retain the previous root.
Resolve duplicate IDs consistently and retain prior revisions used by runs.

Acceptance: online setup, offline reuse and failure recovery agree on the same
pack identity; read-only discovery performs no installation; host reuse identity
includes the selected roots/revisions. A missing tool produces an actionable
installation error rather than a fallback to another implementation.

### A2 — Make scope and tracking generic (alongside A1)

Replace the SDK's hardcoded Hivemind exemptions with validated Astrid executor
metadata declaring whether a project is required or optional. Specify and test
the field in the executor schema; do not add an undeclared top-level field to
Hivemind's pack manifest. Default to
required for existing capabilities. Required work uses explicit project first,
then runtime selection. Optional work can run without looking up a selection;
an explicitly supplied project remains associated with the run.

Reuse the runtime's existing task/attempt/receipt, cancellation and object
publication mechanisms. Keep stdout, stderr, exit status and declared files
inspectable, including unsuccessful execution. Failure evidence must retain
bounded, redacted stdout/stderr and the exit status. Declared files become
managed artifacts on failure only through explicit runtime ingestion; files
left in an attempt directory are not published artifacts. Diagnose any concrete failure
artifact or large-output capture gap through a regression before changing host
code. A failed tool must not be reported as a successful task merely to retain
its output. Cancellation stops owned processes; it cannot undo remote effects
already accepted by a provider.

Acceptance: generic fixture tools prove project-required and optional behavior,
explicit project precedence, success/failure outputs, large output without
deadlock, cancellation, idempotency and source mismatch rejection.

### A3 — Cut over discovery and instructions (after A1/A2)

Remove the bundled Hivemind implementation from active discovery only after
its useful changes exist upstream and the external route passes. Remove its
bundle-specific source preflight exception. Complete the existing plan's
pack-owned skill view and default source selection, without Hivemind-specific
installer branches. The personal CLI becomes a small forwarding launcher only
after the canonical package is installed and the existing command still works.

Acceptance: old personal command, package command and Astrid all reach the same
version; no duplicate query code remains on either consuming path; a cold agent
can navigate Astrid's installed skill to the owning Hivemind instructions.

### V1 — End-to-end proof and review (after A3)

Run representative searches, recent-message filters, context retrieval and full
item reads both standalone and through Astrid. Compare content after allowing
for corpus changes; use deterministic fixtures for exact parity. Verify
workspace-scoped research and project-associated work, artifact reading, clear
failure and cancellation behavior. Exercise clean-install/offline/reconnect
paths from the existing default-packs plan. Do not publish test content.

Completion requires an independent review of the final source and evidence,
not just a successful demo query. Update core, pack-builder, setup and Hivemind
instructions to the paths that were actually verified.

## Handover boundary — 2026-09-08

The user split custody: package Hivemind work for another agent; continue Astrid
work in this conversation. The local portable handover is
`../../../../handover-hivemind-20260908/START-HERE.md` (a sibling workspace
artifact, not a dependency of this plan). It carries completed H1/H2 changes
and the remaining H3 scope only. A1, A2, A3 and integrated V1 remain here.
The receiving package must not edit Astrid, switch the personal launcher,
install globally, publish, merge or deploy. Hivemind owns its CLI and thin
pack adapter; Astrid owns source provisioning, project-scope metadata,
discovery, execution tracking and final integration. Coordinate the supported
manifest contract without making either side invent the other's schema.

## Work custody

There are substantial pre-existing changes in Astrid. Capture a scoped baseline
before migration; never reset or delete by a broad filename pattern. Upstream
Hivemind's unrelated briefing files are outside these tasks. Do not manufacture
an immutable revision label for uncommitted code: release pinning follows the
reviewed source commit. No push or public contribution is part of this plan.

## Review record

H1/H2 evidence: `evidence/upstream-cli-implementation.md` and
`evidence/h2-cli-review.md`. The implementer reports 181 targeted tests and an
isolated installed-wheel console smoke; the independent reviewer ran 172
focused CLI/search/common tests successfully. These suites overlap and are not
additive. Changes are local and uncommitted; the personal launcher/global
installation and Astrid discovery have not been switched. H3 through V1 remain
planned work, including consolidation of remaining overlapping operations.

Investigation: `evidence/hivemind-inventory.md`,
`evidence/engineering-comparison.md`, `evidence/runtime-contracts.md`, and
`evidence/canonical-integration-plan-review.md`. These provide evidence;
the task order and acceptance criteria above are the consolidated plan.
The independent review in `evidence/plan-sense-check.md` was incorporated:
failure evidence/publication is explicit and project scope belongs to the
validated executor contract rather than an invented pack-schema field.
