# Publication and custody audit

## Included

- Committed Astrid source at `cebd5f3b8982e785ed56973d132e8019ecc1cdbf`.
- Checked-in Astrid plans, implementation, tests, skills and pack resources.
- This portable handover closure, including the run configuration, current
  status, review packets, acceptance criteria and dependency provenance.

## Excluded

- The conflicted/staged/unmerged material in the original main checkout. It
  was unrelated to this handover's selected committed source and was not
  copied or resolved.
- `.otto` baseline patches, untracked archives, logs, caches and temporary
  worktrees. Selected run records were copied into this handover instead.
- Personal standalone skill installations, local virtual environments,
  credentials and corpus data.

## Audit result

No credential-shaped values or authenticated URLs were found in the selected
handover closure or in the source diff scan. Existing checked-in planning and
navigation evidence does retain machine-local `/Users/...` path references;
these are historical evidence, not runtime dependencies. They were not
silently rewritten so the source evidence remains faithful. A recipient should
treat those links as non-portable citations and use repository-relative paths.

The branch is a normal handover branch from the recorded candidate. No force
push, merge, deployment, global installation, or Hivemind corpus mutation is
part of this publication.
