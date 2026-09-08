# Hivemind engineering comparison (read-only, 2026-09-08)

## Sources and provenance

The comparison covers the exact files requested:

* `/Users/peteromalley/Documents/poms_skills/hivemind/hivemind`
* `/Users/peteromalley/Documents/poms_skills/hivemind/SKILL.md`
* `/Users/peteromalley/Documents/poms_skills/hivemind/README.md`
* `/Users/peteromalley/Documents/banodoco-workspace/hivemind`

The two sources are in different Git repositories. The upstream Hivemind repo
has remote `https://github.com/banodoco/hivemind.git`; `origin/main` is
`45927ad` (2026-08-20, “Search rewrite: raw-table per-token search + CLI
packaging (v2.0)”), and local `main` is `abe41fd`, one policy-fix commit ahead.
The poms repo has remote `https://github.com/peteromallet/poms-skills.git`.
Its Hivemind files first appear together in `b96563f` (2026-09-08, “Publish
Hivemind and Megado skills”), followed by `99ba29d` (2026-09-08, “Generalize
public skill examples and cloud paths”). The complete CLI was published there in one commit. That dates publication,
not original development: Git alone does not establish where or when its
features were authored, or why it was placed there.

## Surface comparison

The poms script is 853 lines and dispatches a broad human CLI: search, probe,
trend, authors, top-authors, recent, around, day, profile, reactions, media,
top-reacted, get, and cites. It includes date words (`today`, `yesterday`,
relative periods), Discord URL id resolution, keyset paging for recent
messages, client-side link extraction, and human/JSON variants on several
commands. It is dependency-free and parses cleanly as Python AST. Its README
explicitly calls it a “quick CLI wrapper.”

The upstream package is version 2.0.0, stdlib-only, and has a tested executor
surface rather than the same broad CLI. `pyproject.toml` exposes
`hivemind-search`, which calls `executors.search.run:main`; the repository does
not expose the poms command names as a `hivemind` executable. Its search
executor is 1,045 lines and has 95 direct tests in `tests/test_search.py`.
The other maintained executor surfaces also have substantial tests: 29 for
get_item, 12 for refresh_media, 36 for contribute, 71 for ingest_article, 32
for ingest_workflow, and 25 for ingest_youtube. The repository has 58 test
files overall, including SQL/query-contract, timeout, security, identifier,
ingestion, and live-contract checks. The poms CLI has no colocated tests in
its skill directory.

This is not a simple quality ranking. The poms script has much more ergonomic
coverage for an interactive researcher. The upstream code has much stronger
isolated unit/contract coverage and a machine-oriented output contract.

## Material behavioral drift

The most consequential drift is search. The poms `cmd_search` at lines
206–263 queries `unified_feed` with title/body ILIKE, fetches distillations
first, sorts by recency/kind, and retries an unscoped failure with a 90-day
date bound. The upstream search rewrite in commit `45927ad` deliberately
removed text search against `unified_feed` because the derived view can hit
the anon role's statement timeout. It searches raw index-backed tables in
parallel, uses per-token predicates, deterministic client scoring, explicit
projections, and stable `limit`/`offset` paging. The upstream tests explicitly
assert that `unified_feed` is never used for text search.

Consequently, the poms CLI is a wider feature client but its primary search
implementation is behind the upstream repository's current search contract.
Its `probe`, `trend`, `authors`, and recent-message paths are useful additions,
but they carry the poms script's own query and error conventions. Copying the
script into Astrid would freeze this divergence and duplicate query ownership.

Error and output behavior also differs. The poms helper retries HTTP 5xx and
network errors up to four times, generally prints human errors, and only emits
JSON when a command-specific `--json` branch exists. The upstream executors
centralize environment resolution and HTTP helpers in `executors/_common.py`,
write declared JSON result files, keep search human summaries on stderr so
stdout is pure JSON, and return explicit structured errors. Upstream tests
exercise HTTP 400/401/409/500 cases, missing keys, dry-runs, output files,
and citation relationships. This makes upstream contracts much easier for
Astrid's generic host to capture, but does not replace the poms CLI's useful
commands.

## Verdict on where the fuller CLI was developed

The evidence supports the following nuanced verdict:

1. The fuller 14-command CLI currently lives in `poms_skills` and was added
   there on 2026-09-08 as part of a public skill publication. It was not
   present as a corresponding CLI in the upstream Hivemind repository at
   `origin/main`/local `main`.
2. The upstream repository is the domain-owned source with the more recent
   search design, seven pack executors, package metadata, and comprehensive
   tests. The poms CLI and the upstream package are presently parallel clients,
   not one implementation with two front doors.
3. It is reasonable to suspect the fuller CLI was developed in the skill
   repository rather than upstream, but Git history alone cannot prove whether
   that was intentional staging, an extraction, or accidental divergence.

The engineering action should be one-owner consolidation: port the poms
commands into the upstream Hivemind repository, refactor them onto the
upstream raw-table/common transport where semantics overlap, add tests beside
the commands, and publish one maintained `hivemind` entrypoint. Preserve the
human-friendly commands and output, while adding a consistent JSON mode and
structured exit/error contract suitable for Astrid. Astrid should consume that
single pinned Hivemind source/pack; it should not carry either a copied poms
script or a competing REST implementation.

Until consolidation is complete, Astrid should treat the upstream pack as the
currently testable machine contract and the poms CLI as an explicit migration
input/feature inventory. It should not silently mix poms search results with
upstream search results under the same capability id, because the query
semantics differ.

Evidence pointers: poms CLI `hivemind` lines 1–31, 79–101, 206–263,
372–430, 443–529, 685–790; upstream `pyproject.toml`, `README.md`,
`executors/search/run.py`, `executors/_common.py`, and tests listed above;
Git commits `poms:b96563f`, `poms:99ba29d`, `hivemind:45927ad`, and
`hivemind:abe41fd`.
