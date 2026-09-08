# H2 upstream Hivemind CLI review

Read-only review of `/Users/peteromalley/Documents/banodoco-workspace/hivemind`
against `/Users/peteromalley/Documents/poms_skills/hivemind/hivemind`.

## Findings

- The upstream `pyproject.toml` now declares both console entry points:
  `hivemind-search = hivemind.executors.search.run:main` and
  `hivemind = hivemind.cli:main`. Its explicit package list and
  `hivemind = "."` package-dir mapping match the repository-root package
  layout. A real isolated build/install smoke test remains the right check for
  the unusual root-package layout; no build was run in this read-only review.
- The current `cli.py` search facade has fixed the previously observed parity
  issues: it normalizes `today`/`yesterday`/relative date words, forwards both
  inclusive `--since` and exclusive `--until`, and maps `--resources` to the
  raw executor's `resource` meta-kind. The raw executor now carries both date
  predicates into each scope and `_common.postgrest_get` uses `doseq=True`, so
  the two `created_at` parameters are serialized as repeated query keys.
- Resource-kind handling is intentionally open-ended. `resource` is a
  meta-kind; concrete kinds (including future kinds such as `article`,
  `transcript`, `workflow`, `blog_post`, `repo`, and `guide`) pass through to
  `external_resources`. This is broader and more correct than the old wrapper's
  hard-coded three-kind mapping.
- The diagnostics gap is now closed: `cmd_search` forwards the captured
  canonical stderr after the delegated call, and `test_cli.py` covers
  preservation of stderr plus the exit code. Normal successful search progress
  remains on stderr, while JSON stdout stays parseable.
- The new CLI tests cover delegation, normalized bounds/resource scope, JSON
  preservation, stderr/exit-code forwarding, snowflake IDs, and Discord URL
  IDs. The existing
  upstream dirty checkout also contains unrelated modified rehearsal/common
  files and untracked CLI/test/docs files; this review made no source changes.

Focused verification: `python3 -m pytest -q tests/test_cli.py
tests/test_search.py tests/test_common.py` passed, 172 tests. No separate
install-smoke report was present; generated `hivemind.egg-info/entry_points.txt`
contains both declared console scripts.

## Command parity conclusion

The upstream facade exposes the same command families documented by the
personal CLI (`search`, `probe`, `trend`, `authors`, `top-authors`, `recent`,
`around`, `day`, `profile`, `reactions`, `media`, `top-reacted`, `get`, and
`cites`). Search's backend is intentionally the maintained raw-table executor,
so result ordering and corpus-scan behavior differ from the old
`unified_feed` implementation; the date, resource scope, JSON, and command
surface contracts are now represented in the upstream code/tests.
