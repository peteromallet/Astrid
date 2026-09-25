# Authority and boundaries

The 2026-09-21 user mandate authorizes creation and validation of a portable
program handoff artifact. It explicitly forbids pod launches, billable resources,
altering active product runs, changing product source, product repository pushes,
and merges. The later instruction requires public source URLs and exact pins,
with source retrieval validation instead of bundling full repositories.

Current receiving mode is control review / handoff preparation. This packet does
not promote planning-only successor runs to delivery. Project A's historical
`mode: delivery` and `source_custody: main` remain historical source authority;
they do not authorize this preparer or receiver to mutate active runs now.
The receiver can inspect controls, verify hashes and retrieve public sources.
When product implementation is authorized, current builds/tests and acceptance
remain CPU/fake/offline under [execution scope](execution-scope.md). Live GPU/RunPod
qualification and operational caller cutover are outside all current projects;
only a separate later authorization can activate [gate L](POST-HANDOFF-GPU-GATE.md).
No generic delivery instruction, old live-test clause or available credential
automatically activates that deferred gate.
No budget balance or reusable live resource is inferred from old receipts.

One program manager owns sequencing and exclusive-surface reservations. Workers
implement only their dispatched scope after activation. Configured oracles own
consequential adjudication, and independent reviewers use the declared stage
budgets. Existing `run.yaml` files remain the sole model/stage/budget declarations
for their scopes. Renaming a stream P0–P11 never resets a counter. Unknown counts
must be recovered or conservatively accounted for before another invocation.

Reigh-worker disposition: **transitional bootstrap/readiness substrate and
Wan2GP/prebuild dependency; not required by the managed-result contract;
pending migration/retirement**. Removing its directory, deployments, images or
callers is not authorized by this handoff. Retire only the proven migrated
surface after separate post-handoff live qualification and cutover authority.
Current P7 acceptance is implementation plus offline migration/rollback proof.

No current native subagent capability is exposed to this packaging session.
No paid external launcher was used. Receiver availability of every model and
reasoning setting in the exported configurations is unknown. Check the native
capability catalog there; report missing bindings, never silently substitute.
The words “Astra High” do not prove a separately invoked reviewer or verdict.

Sanitization changes paths, host addresses, URL queries and local operational
references in exported documents. The [provenance inventory](control-provenance.json)
records original and exported hashes; no sanitized file is passed off as an
unchanged Git blob. Excluded evidence is indexed in [omissions](evidence/omissions.md).
