# Upstream Hivemind CLI implementation report

Implemented in `/Users/peteromalley/Documents/banodoco-workspace/hivemind`:

* Added `cli.py`, carrying the existing Hivemind human CLI command surface:
  bare/search query, probe, trend, authors, top-authors, recent, around, day,
  profile, reactions, media, top-reacted, get, and cites.
* Added the `hivemind` console entrypoint in `pyproject.toml`; the existing
  `hivemind-search` entrypoint remains unchanged and continues to call the
  canonical search executor.
* Routed `cli.py` search through `executors.search.run.main`, so CLI text
  search uses the upstream raw-table, per-token, timeout-safe implementation.
  Human output retains the previous readable result shape; `--json` preserves
  the executor's structured JSON. Added canonical executor support for an
  exclusive `--until` bound, encoded as a repeated PostgREST `created_at`
  parameter alongside `--since`; relative CLI date words are normalized
  before delegation. `--resources` now uses the executor's `resource`
  meta-kind, preserving all external resource kinds rather than guessing a
  fixed list.
* Preserved the existing CLI implementations for the other operational
  commands initially, including string-preserving Discord snowflake handling,
  keyset recent paging, Discord URL id resolution, media refresh, and citation
  lookup. No corpus writes were performed.
* Added `tests/test_cli.py` covering raw-search delegation/JSON, human output
  with a large snowflake, honest unsupported-flag behavior, recent keyset
  filtering, and Discord URL lookup.

Validation:

* `python3 -m unittest tests.test_cli tests.test_search tests.test_get_item tests.test_refresh_media tests.test_contribute`
  passed: 181 tests.
* `PYTHONPATH=/Users/peteromalley/Documents/banodoco-workspace/hivemind python3 -m cli --help`
  and the package-style `python3 -m hivemind.cli --help` both resolve and show
  the CLI help.
* A temporary isolated wheel build/install succeeded, and the installed
  `hivemind --help` console entrypoint printed the full CLI help. No global
  installation was performed.

Known bounded limitations:

* The imported operational commands still use the CLI's original transport
  and output conventions. They are now owned by this upstream repository, but
  further consolidation onto `_common.py` and colocated tests can follow.
* Search's legacy ranking/display is intentionally replaced by the canonical
  raw-table ranking. `--since`, `--until`, channel/author, kind/resource,
  limit, offset, and JSON are supported through the canonical executor.
* The poms-skills copy was not modified, no global installation was performed,
  and unrelated existing worktree files were preserved.
