# Sense-check of the consolidated standalone-tools plan

Reviewed `docs/plans/standalone-tools/PLAN.md` against the current Astrid
external-pack/runtime contracts and the Hivemind inventory. The single-owner,
single external-pack route is internally consistent. I found two concrete
clarifications required before implementation.

## Must fix

1. **Separate failed diagnostics from failed artifacts in A2/V1.** The plan
   currently says stdout, stderr, exit status, and declared files remain
   inspectable for unsuccessful execution, while also saying a failed tool must
   not be reported as successful merely to retain output. Keep that safety
   rule, but state the exact contract: failed attempts always retain bounded,
   redacted stdout/stderr and exit status in failure evidence; declared files
   become managed artifacts only if the runtime's failure path explicitly
   ingests them. Acceptance should test both cases and must not require a
   synthetic successful settlement. This matters because the current host's
   normal output publication is coupled to successful settlement.

2. **Define where `project_scope` lives.** Hivemind's upstream v2 pack
   manifest is owned by Hivemind and must pass Astrid's strict schema. The plan
   should say that `project_scope` is Astrid-side capability metadata or a
   host admission matrix field unless the v2 manifest schema explicitly
   accepts it. Do not add an Astrid-only field to Hivemind's canonical manifest
   and then call that upstream source portable.

## No blocker

- H3's “repo-owned executor” is coherent if it means the upstream Hivemind
  repository/pack owns the thin entrypoint adapter; Astrid only consumes the
  pinned external pack. Keep that wording explicit during implementation.
- “Preserve and port useful fixes from the bundled copy” is compatible with
  removing the copy: port behavior into upstream Hivemind, then delete the
  Astrid duplicate after external validation. Do not port Astrid imports or
  make the bundle a fallback.
- The source setup prerequisite, v2 manifest gate, shared root handoff,
  revision retention, and duplicate-ID policy match the existing default-packs
  plan and current host admission model.
- The cancellation wording is accurate: Astrid can terminate its owned child
  process, but cannot retract a provider-side request already accepted.
- Large-output/deadlock testing is correctly called out as an acceptance gate;
  do not claim the current pipe path satisfies it until the fixture proves it.

No further framework or integration level is needed. The only required plan
edits are the two contract clarifications above.

