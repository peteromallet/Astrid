# Execution mechanics

Read when implementing or reviewing executable work, not merely planning. This reference supplies custody, validation and invocation evidence; review timing/model/count come only from the active skill's policy and the user-declared run contract. Nothing here creates another review gate.

## Source custody and operational preflight

Capture before source mutation: repository root, explicit source ref and SHA, branch, staged/unstaged/untracked state, worktrees, remotes/refs, relevant environment/dependency identity, and local work that must survive. Receipts must not include credentials. At kickoff, explicitly ask whether delivery should edit the invoking `main` checkout or use an isolated worktree; record the answer before mutation. If a worktree is selected, it must be `<PROJECT_ROOT>/.otto/worktrees/<RUN_ID>` inside the relevant repository. The immutable checkout contains the chosen commit only; when dirty work is authoritative, preserve it non-destructively under user authorization rather than silently dropping it.

Record the roots once:
- `PROJECT_ROOT`: invoking repository, never recomputed inside the nested worktree.
- `OTTO_DIR`: `$PROJECT_ROOT/.otto/runs/$RUN_ID`, control artifacts.
- `WORKTREE`: `$PROJECT_ROOT/.otto/worktrees/$RUN_ID` when isolated custody is chosen; otherwise `PROJECT_ROOT` itself for main-checkout delivery.
- `BASE_SHA`: resolved immutable source ref.

Create/adopt the succinct North Star and current agent goal before dispatch. Record disk/inode headroom, expected worktree/output/test size, run-owned temporary directory and dependency identity before expensive fan-out/validation. Use an available RAM-backed temp volume only when appropriate. A capacity or disk-I/O failure stops equivalent retries until corrected and rechecked. Do not turn a small read-only query into a capacity audit.

Add `/.otto/` to the repository-local Git exclude; do not alter global ignores or stage control directories. Put source mutations only in the recorded custody (main checkout or the in-repo worktree). Do not merge, deploy or push by implication.

Example setup after recording custody (resolve placeholders from the run, not blindly):

```bash
PROJECT_ROOT="$(git rev-parse --show-toplevel)"
SOURCE_REF="<explicit-ref>"
RUN_ID="<unique-run-id>"
BASE_SHA="$(git -C "$PROJECT_ROOT" rev-parse "$SOURCE_REF")"
OTTO_DIR="$PROJECT_ROOT/.otto/runs/$RUN_ID"
WORKTREE="$PROJECT_ROOT/.otto/worktrees/$RUN_ID"
BRANCH="otto/$RUN_ID"
EXCLUDE_FILE="$(git -C "$PROJECT_ROOT" rev-parse --git-path info/exclude)"
# Add /.otto/ once to EXCLUDE_FILE using a safe local file edit.
mkdir -p "$OTTO_DIR" "$(dirname "$WORKTREE")"
git -C "$PROJECT_ROOT" worktree add -b "$BRANCH" "$WORKTREE" "$BASE_SHA"
```

The command above applies only after the kickoff answer is `worktree`. For a
`main` answer, set `WORKTREE="$PROJECT_ROOT"`, do not run `git worktree add`,
and record the exact main branch/SHA before editing. In both cases the control
root remains `$PROJECT_ROOT/.otto/runs/$RUN_ID`; only source custody changes.

If a source commit is not the authoritative input, resolve that before this command. Do not stash/reset/clean the invoking checkout as a setup shortcut.

## Minimal run records and discovery

Use `northstar.md`, `agent_goal.md`, `run.yaml`, `plan.md`, `tasklist.md` and `status.md`. Resolve responsibility slots, model bindings and review/oracle budgets from run.yaml; record consumed counts in status, including across restarts. Briefs/findings/receipts hold actual dispatches; evidence holds test outputs. Create a compact acceptance ledger when tracking integrated criteria: ID, dependencies, state, evidence and oracle disposition. Keep correction notes beside the affected task rather than demand a fresh document hierarchy for every fix. Logs record events, not polling. Status names the current source, next action and unresolved findings so a restart resumes rather than replans.

Register when the source/roots are known and before background model work. The bundled Megado run index is shared discovery plumbing, not an authorization gate:

```bash
python ~/.agents/skills/megado/scripts/megado_run_index.py register \
  --run-id "$RUN_ID" --project-root "$PROJECT_ROOT" \
  --otto-dir "$OTTO_DIR" --worktree "$WORKTREE" \
  --source-ref "$SOURCE_REF" --base-sha "$BASE_SHA" \
  > "$OTTO_DIR/run-index-registration.json"
```

Locate the installed `megado/scripts/megado_run_index.py` if that alias is unavailable. Pass parent session/transcript/resume information when exposed. Registration is idempotent; save the returned logical_run_key. On failure, record one warning and continue—status/source evidence remains authoritative. Do not repeatedly gate progress on the index. Update its hint at meaningful lifecycle changes/completion, not every poll.

A dispatch receipt records actual model/provider, command or native tool, source SHA, cwd, brief and North Star digests, result path/digest, start/end, PID when available and exit status. The executable brief and receipt also record the concrete outcome, acceptance evidence, dependency scope, route to `worker_normal` or `worker_xhard`, and—when XHARD—the irreducible hard-question justification. Generated brief paths avoid quoting large model content into hand-built shell commands; seal CLI stdin and use bounded process supervision. A running process is not a useful result—read its output.

## Integration and test evidence

Tasks consume the latest coherent dependency state, not stale parallel edits. Parallelize independent work and converge at real integration seams. A checkpoint is source/evidence identity, not necessarily a model review. Known failed criteria block their dependents; keep unrelated work moving. Integrate useful increments as they land: reconcile shared interfaces, source changes, task status and affected test results before dependent dispatches. Do not defer convergence until the final reviewer or let independent workers accumulate incompatible assumptions for days. Frequent integration and shared current state are required even with final-only model review; they do not require another model verdict.

Use this proof ladder:
1. Focused tests/fixtures while implementing.
2. Affected integration checks when components converge.
3. Broad affected suite once on the final integrated candidate.
4. Live, destructive, costly or full-scale validation only when necessary to prove an agreed criterion and authorized for that environment.

Declare concrete scenarios and proportionate runtime/data/disk/network limits. Assign one owner to broad/expensive checks and reuse passing receipts when candidate/input/environment are unchanged. A reviewer inspects those receipts rather than rerunning every suite. Correcting a file invalidates only affected criteria and their dependencies. For expensive checks, record the exact command, candidate SHA, input fingerprint, relevant environment/dependency identity, result and duration; include observed disk/memory use when practical. This makes receipt reuse verifiable without burdening every small unit test.

For migration, separate logical correctness from scale: use representative fixtures first, one necessary affected-data inventory/export and the smallest real-scale rehearsal justified by actual data. Avoid multiple full copies unless each protects a distinct invariant. A cheap direct cutover can still require transactionality, source preservation and a rollback boundary. Do not invent user migration complexity or ignore real consumers.

## Frozen executable review

Only when a review is scheduled under the run policy: freeze the integrated candidate and stop its mutators. Normally commit reviewed source in the execution worktree, require clean tracked/untracked state, and record `REVIEWED_SHA`, `REVIEWED_TREE` plus relevant evidence digests. Use a separate detached read-only checkout for the reviewer; output/scratch lives under the run-owned directories. Do not execute untrusted tests with mutation/network permissions merely because this is a review.

If commit authority is absent, use a non-destructive immutable snapshot with a content manifest and record it as such, rather than committing without authorization or pretending HEAD captures dirty content. A plan-only document review uses document digests; it does not require a source commit/worktree.

For a committed candidate:
```bash
REVIEWED_SHA="$(git -C "$WORKTREE" rev-parse HEAD)"
REVIEWED_TREE="$(git -C "$WORKTREE" rev-parse 'HEAD^{tree}')"
REVIEW_WORKTREE="$PROJECT_ROOT/.otto/review-worktrees/$RUN_ID/$REVIEWED_SHA"
mkdir -p "$(dirname "$REVIEW_WORKTREE")"
git -C "$PROJECT_ROOT" worktree add --detach "$REVIEW_WORKTREE" "$REVIEWED_SHA"
chmod -R a-w "$REVIEW_WORKTREE"
```

Before accepting the review, verify SHA/tree and clean `git diff`, staged diff and untracked state in both source and review checkouts, plus unchanged evidence digests. Snapshot reviews verify the snapshot manifest instead. Mutation invalidates the affected verdict; repair source identity and perform only the justified affected verification within the run budget. Do not let concurrent future work mutate a candidate under review.

Build the packet using [review-packets.md](review-packets.md) and its template before the scheduled invocation. Reviewer input: agreed criteria/scope, complete North Star, frozen source identity, relevant diff/tests and previous oracle dispositions. Do not seed it with persuasive prior reviewer verdict narratives. Record the review lens/question and assignment routing with findings and oracle rulings. The coordinator advances under the configured evidence/gate rules; unresolved judgment goes to the designated oracle, not a mandatory oracle invocation after every result. Review counts and correction limits are defined in the skill, not repeated here.

## Completion and sync

Map agreed outcomes to actual evidence. Distinguish complete, blocked (external prerequisite/authority), failed (reproduced unmet criterion), undetermined (missing proof), retryable (owned safe retry remains), and escalate (scope/risk exceeds authority). Do not label a working harness or model PASS as product completion.

Stage only explicit intended source paths and commit/sync only within the agent goal's authorization. Specify the remote and refspec; never broad-stage `.otto/`. Merge to main, production cutover and deployment remain distinct authorized actions. Do not push merely because the pipeline ends in “sync.”

After completion, update the discovery hint with the saved key and actual final SHA/evidence:
```bash
python ~/.agents/skills/megado/scripts/megado_run_index.py set-hint \
  --logical-run-key "$LOGICAL_RUN_KEY" --lifecycle-hint completed \
  --phase completion --candidate-sha "$FINAL_SHA" --evidence "$OTTO_DIR/status.md"
```

For planning completion use a planning-complete phase and source baseline, without suggesting it is an implemented candidate. Report delivered artifacts or executable outcome, important validation and actual limitations.
