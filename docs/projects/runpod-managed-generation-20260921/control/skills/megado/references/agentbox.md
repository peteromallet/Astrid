# AgentBox handoff

Read only for an authorized unattended/cloud run. Use a wrapper-driven subagent run, not an implicit megaplan chain. Review/model policy comes from the current skill and user declaration; do not recreate old mandatory checkpoint/cumulative review rules in the cloud brief.

Use the current host-supplied launch manifest, such as the path exposed through
`$AGENTBOX_LAUNCH_MANIFEST`, for environment-specific steps. The established
approach uses a host-selected isolated container, required agent tooling,
dereferenced skill symlinks, transferred auth/model configuration, a Git bundle
when the chosen source is not remote, isolated project dependencies, and a
wrapper-owned orchestrator with durable status/supervision. Inspect the host
recipe before reproducing its setup; do not expose auth material in receipts or
overwrite protected workloads named by that recipe.

Transfer the recorded source/goal/North Star and task state. Freeze skill/reference digests and the actual run-specific model/reasoning/review caps in the handoff. Cloud skill copies do not update when laptop files change. Every dispatch uses the receipt wrapper; do not fall back to undocumented direct calls after bootstrap.

Probe only the models and infrastructure actually selected for this run, not every eligible model. Use tiny read-only model calls, dependency checks, and authorized sync dry runs before expensive unattended work. Do not infer remote mutation or push authority from possession of a credential.

At receipt/checkpoint boundaries, the cloud owner reloads the registered operation record before dispatching more work. If next_action contains a user/operator intervention, acknowledge it in the durable log and apply it. An intervention can narrow work/review policy within scope; it cannot silently broaden product or deployment authority.

Register the cloud project in the AgentBox project ledger, verify the registration receipt, and link the local discovery record rather than creating two owners:

```bash
python "$MEGADO_SKILL_ROOT/scripts/megado_run_index.py" handoff \
  --logical-run-key "$LOGICAL_RUN_KEY" --project-id "$AGENTBOX_PROJECT_ID" \
  --evidence "$AGENTBOX_REGISTRATION_RECEIPT"
```

After handoff the laptop index is an observer hint. AgentBox owns lifecycle/mutation. Reconciliation may repair a missing link, not launch a duplicate authority. Resume from recorded status/source and honor interventions; do not replan a completed unit or reset review budgets when supervision relaunches a process.
