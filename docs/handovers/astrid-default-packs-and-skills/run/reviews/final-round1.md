# Review packet: final / round 1

## Assignment

Reviewer role: `final_reviewer` → GPT-6 Astra, medium reasoning. Lens:
completion_and_strategy. Trigger: T6. Scope: T0, T2, T3, T4, T5, T6, A2.
Criteria: C1–C6. This is the first of at most three final rounds. The reviewer
is an independent read-only leaf and must inspect the current candidate.

## Contract and boundary

The user authorized implementation in the existing main
`/Users/peteromalley/Documents/reigh-workspace/Astrid` checkout and explicitly
forbade creating another worktree. Preserve unrelated dirty work. Astrid’s
first useful outcome is a generic, source-pinned external-pack path: setup
provisions and validates managed roots; discovery, SDK provenance, skills, and
host startup consume the same inventory; executor metadata expresses generic
project scope; and installed skill views work from read-only package resources.

Hivemind’s upstream v2 manifest migration/release pin and final external-pack
cutover are explicitly outside this candidate. The bundled Hivemind tree is
not release proof. The published Hivemind CLI branch is provenance only.

## Candidate and preserved baseline

Base SHA: `0c852b7748f9f519413ec96f037b04b3d90e70a2`. The candidate remains an
intentionally dirty main checkout; the complete pre-existing state is recorded
in `.otto/runs/astrid-default-packs-and-skills/baseline-20260908-delivery/`.
No source commit, push, merge, deployment, global install, or corpus write was
performed.

## Evidence

- Source-contract review round 1: PASS for C1, C2, C3 and C6, recorded in
  `review-packets/source_contract-round1-result.md`. The reviewer’s narrow
  rerun was blocked by its temporary-directory environment, while the supplied
  receipts were inspectable.
- Integrated affected suite: **122 passed, 8 subtests passed** using the exact
  command recorded in `status.json`.
- T4/T5 evidence: 58 route/package tests and 16 registry-focused tests, plus
  the corrected skills package-data suite (61 focused skill tests). The worker
  also verified a temporary read-only wheel installation and 24 packaged skill
  routes; see `docs/plans/standalone-tools/evidence/result-t4-t5.md`.
- T2/T3 evidence: 17 source/host tests, 3 source/discovery tests, and setup
  `--check --offline` smoke rc 0; see `result-t2-final.md`.
- A2 evidence: generic project-scope schema/invocation tests and bundled
  manifest parsing, including explicit project precedence and projectless
  optional reads.

## Required final review

Inspect the actual complete diff and relevant entrypoints. Check C1–C6 for
cross-component contradictions, source identity, opt-outs/recovery, skill
navigation, package-read-only behavior, project scope, truthful limitations,
and unnecessary duplicate mechanisms. Distinguish a missing Hivemind v2 release
from an Astrid defect. Return PASS, REWORK, or UNKNOWN with criterion-level
evidence and the smallest correction. Do not mutate source, delegate, widen
scope, or claim live Hivemind acceptance without the external pack.
