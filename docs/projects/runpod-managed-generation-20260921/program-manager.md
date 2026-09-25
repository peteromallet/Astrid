# Single program-manager mandate

Maintain one current program ledger containing P0–P11/Q/H state, exact source
tuple, dependency/checkpoint state, exclusive path reservations, assigned worker,
last receipt, counters, next action and blocking prerequisite. This packet's
[map](program-map.md) is the initial ledger; receiver execution state is created
only in chosen new custody, never by modifying an active sender run.

The coordinator runs the agreed process; the designated oracle owns consequential
judgment. Delegate substantial implementation/investigation/validation when a
native or authorized launcher is available. Workers/reviewers are leaves unless
explicitly assigned coordination. Advance on passing required evidence and
uncontested declared review outcomes. Escalate interface/architecture changes,
contested blockers, exhausted budgets or unclear hard reasoning to the owning
run's oracle; do not create a new program budget to bypass an existing cap.

Current dispatch scope is [CPU/fake/offline only](execution-scope.md). Include
that constraint in every worker/reviewer brief and acceptance receipt. Strip live
GPU/RunPod test clauses from executable assignments even when an old task ID or
review scope contains one; retain the original ID as deferred-L traceability.
Missing credentials, capacity or live evidence do not hold P0–P11/Q/H. Current
projects can finish `CPU_COMPLETE / GPU_UNQUALIFIED`. Do not schedule L on completion,
on a wakeup tick, on a test failure or when a provider credential becomes available.

Dispatch protocol after authority and custody are established:

1. Refresh dependencies and active-writer ownership. Select every ready task
   that has disjoint reserved files, exact input pins and available capabilities.
2. Record a dispatch ID, outcome, full relevant North Star, goal boundaries,
   source/dependency tuple and control hashes, exclusive files, acceptance tests,
   limits, expected artifacts, and `normal`/`xhard` route. XHARD needs its specific
   irreducible reasoning justification. Read the owning `run.yaml`; do not copy
   model defaults into a divergent manager document.
3. Reserve files and charge applicable invocation counters before launching.
   Record actual tool/model/reasoning, start time and resumable handle if exposed.
   A missing model/capability is a prerequisite, not permission to substitute.
4. Require result receipts with source SHA/tree or snapshot hash, changed paths,
   commands, environment/input identities, outcomes, evidence hashes and residual
   failures. Require outbound-network isolation for build/validation, fake
   provider/engine clients and no mounted GPU or provider credentials. A running process, worker summary or plan document is not acceptance.
5. Integrate only under the existing authority; test affected boundaries and
   release reservations. Record checkpoints as concrete source/evidence tuples.
   Do not merge or push under this packaging mandate.
6. Dispatch newly ready work; hold only affected dependents. Preserve completed
   evidence if its input/source closure is unchanged. Do not reset rounds after
   renamed scopes, crashes or handoff.

Control ownership: P0 uses the A run; P1–P4 use the GPU-engine successor with
its residency and Wan follow-up decisions preserved; P5 uses canonical jobs;
P6 uses golden-template and dependency-contract controls; P8–P11 use shot-generation
controls. P7, Q and H do not yet have adopted delivery role/stage configurations;
declare those when execution is actually authorized, without charging reviews
to unrelated new names. H's current work is packaging only.

Wakeup limitations: a chat sleep/wakeup loop lasts only while that conversation,
process and host remain alive. It is not a durable scheduler, does not survive
machine loss/reboot by itself, and does not prove any worker is progressing.
No wakeup loop or scheduler was started by this handoff.

Unattended operation needs a separately configured durable scheduler/supervisor
on an authorized machine: persistent state, a single-manager lease/fencing token,
bounded tick, restart/reboot recovery, per-run idempotency, secret injection on
that machine, logs with redaction, and a tested resume command. Record scheduler
identity, owner, cadence, health and recovery receipt before claiming unattended
coverage. An existing product scheduler may satisfy this after inspection;
this packet does not authorize creating infrastructure or purchasing capacity.

Each tick reconciles receipts and actual process state, applies existing rulings,
dispatches ready work, and saves a compact checkpoint. Ten no-progress checks
trigger coordination diagnosis. A repeated decision twice with no new evidence
must produce a concrete brief/tool/dependency repair, not another identical poll.
