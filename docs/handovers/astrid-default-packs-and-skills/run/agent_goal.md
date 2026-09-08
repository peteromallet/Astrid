# Handover goal

Preserve the completed Astrid default-pack and skill-composition implementation
and finish the explicitly pending upstream Hivemind H3/T1 prerequisite:

- produce a valid canonical v2 Hivemind manifest/release revision;
- make that immutable revision usable by Astrid's managed source setup;
- validate live external-pack discovery, skill composition, runtime admission,
  and read-only `search`/`get_item` behavior;
- record the exact upstream revision and evidence without writing to the corpus.

The Astrid source candidate is commit
`cebd5f3b8982e785ed56973d132e8019ecc1cdbf`. The source checkout used during
the earlier in-place run was dirty and contained unrelated work; this branch
uses the committed candidate only. The original conflicted main worktree is not
part of this handover.

The scoped Astrid work already passed its declared source-contract and final
reviews, with the run recording 123 tests and 8 subtests after the final
correction. Treat those records as historical evidence for the candidate; do
not claim they prove the pending upstream H3/T1 work.

The receiving agent may implement the pending upstream task and its necessary
integration evidence. It may not broaden the product scope, merge, deploy,
publish to the Hivemind corpus, or globally install skills without separate
authorization.
