---
name: megado-handover
description: Prepare a portable Megado project handover for another machine or agent, including selected artifacts, dependency provenance, publication checks, and a copy-paste delivery message.
---

# Megado handover

Use this skill when a user asks to move a Megado plan and project to another
machine or agent. It packages evidence and instructions; it does not execute
the product plan. Read the canonical Megado skill first: normally
`../megado/SKILL.md` in this checkout, otherwise the source path supplied by
the user. Read its referenced run and review documents directly as needed.

## Establish the handover contract

Prefer a dedicated handover branch on top of the existing project's current
`main` (or its actual default branch), published to that project's remote.
Place the portable control package in a clearly named tracked directory such
as `docs/projects/<project-name>/`. Keep snapshot folders as evidence sources,
not the ongoing project home; do not create a separate handover repository by
default. For multi-repository work, name the host repository and pin the other
repositories and their roles in the package. This preference does not change
the plan's selected implementation revisions or authorize a push to `main`.
Explicit user destinations and base refs take precedence.

Record the authoritative project path, selected worktree or ref, run directory,
recipient, desired receiving mode (`planning_only` or `delivery`), destination
remote, base branch, and publication visibility. For this workflow, default
publication visibility is public unless the latest explicit user instruction
changes it; still record the destination. Treat that instruction as authority.
Preserve prior decisions, role assignments, budgets,
states, and historical counters; apply only a later explicit override. Do not
invent model defaults or duplicate them outside `run.yaml`.

Inspect `git status`, `HEAD`, branches, remotes, worktrees, and the selected
run. Establish whether origin is stale relative to the latest committed
project. Select and record the exact source SHA. If dirty files are included,
name them and why; preserve intentionally included source while excluding
unrelated dirt, secrets, and private notes. Never silently turn an uncommitted
working tree into the authoritative source.

## Build a portable closure

Select the necessary current plan closure outside ignored `.otto` storage:
START-HERE and the linked plan, criteria, objective, goal, status, `run.yaml`,
authorization, scope, decision, acceptance, and provenance records. Reuse
tracked project docs and include an ignored or untracked file only when it is
the intentional authoritative source. Follow links until the recipient can
start without the original absolute paths. Do not wholesale-copy logs,
archives, raw receipts, or machine-local caches. Label planning records as
planning evidence; they are not proof that product implementation or tests ran.
Keep historical exploration and counters distinct from the current state.

Package Megado dependencies with fetchable URLs the recipient can access and
exact commits or tags. The handover must state the SHA actually inspected,
provide a no-overwrite install command, and provide a direct-read fallback.
Check that native agent capability and every required model are available;
report a
missing capability or model explicitly, with no silent substitution.

## Audit and publish safely

### Private ZIPs and credentials

When the user requests an archive with execution access, build a private
transfer outside every Git worktree. Keep public planning artifacts separate
from an explicit allowlist of private credentials, resource configuration and
selected recovery evidence. Public visibility never applies to the private
transfer. Do not copy entire env files, SSH directories, credential stores,
or account/agent credentials the recipient already has.

Check the actual launch path before asking for secrets: a test harness may
create its own local Runtime and test credentials. Use credentials already
authorized for this task from configured sources; never print values, put
them in command arguments/logs, or commit them. Prefer a dedicated transfer
SSH identity or recipient public key over copying a general-purpose private
key. Document how that identity is authorized on future owned resources.

Verify access with bounded read-only authentication/resource checks where
possible; do not launch billable resources to test a handover. Distinguish
credential present, authentication verified, resource visible, and live
execution untested. A rejected or unavailable credential is an explicit
prerequisite, not a working setup. Ask for its file/secret-store reference
without requesting that the value be pasted into chat, and continue packaging
independent material. Do not ship known-rejected keys as usable credentials.

Include a private manifest of exactly what is transferred, a no-overwrite
setup/import command, a redacted readiness report, and the receiving-agent
message. Restrict local archive/staging permissions and state plainly when a
ZIP contains unencrypted credentials. For shared or untrusted transport, use
recipient-key encryption or a separately delivered secret-store reference;
do not put a decryption secret beside the encrypted payload in the same ZIP.
Validate archive paths, permissions, extraction into a fresh directory, and
setup behavior without exposing values. Never upload the private ZIP to the
public handover branch. Preserve product execution mode and budgets unless
the user actually changes them.

Audit every intended published file and reachable history for credentials,
private operational details, unnecessary personal data, watchlists, and
internal paths. A publishable key in intended configuration is not proof of
authentication. Remove an item from the publication set or sanitize it with
authority; do not rewrite history automatically. Publish only to the
authorized destination and visibility.

When publication is authorized, create or use a branch from the recorded
source, stage only explicit selected paths, commit, push normally with no
force, and verify the remote ref resolves to the local commit. Preserve other
worktrees and unrelated changes. Report omitted files and any unresolved risk.

The preparer publishes only the authorized handover branch and its artifacts.
When the user's delivery authorization includes a PR finish, the receiving
agent creates the implementation branch and PR after implementation and the
required validation, then returns its URL with outcome evidence and unresolved
risks. Record the target remote and base branch. Never infer permission to
merge, deploy, or cut over from a handover; generic planning-only or packaging
authorization does not grant a PR.

## Validate the recipient path

Use a fresh checkout or an equivalent clean path to verify clone/ref commands,
portable links, dependency installation or direct-read fallback, `run.yaml`
parsing, role/model references, prerequisites, and review-packet inputs that
actually exist. Do not manufacture product tests or claim a model packet from a
plan record; a missing packet can be created from the real candidate later.
For `planning_only`, deliver the artifact and message without executing the
product plan. For `delivery`, the recipient changes the accepted mode in the
single authoritative `run.yaml` while preserving roles, stages, budgets,
counters, and boundaries, then executes only what the authorization covers.
Unknown prerequisites are reported for resolution; they are not approval
gates invented by this skill.

Perform a bounded independent portability check when worthwhile or requested,
proportionate to the handover. Do not add mandatory two-panel audits, extra
review gates, or hide the actual product review count. Always deliver both the
durable artifact and the copy-paste message in `assets/handover-message.md`.
The message must name
the exact project and skills SHAs, current phase/state, authority, objective,
boundaries, stages and budgets from `run.yaml`, prerequisites, start commands,
and the selected finish instruction.
