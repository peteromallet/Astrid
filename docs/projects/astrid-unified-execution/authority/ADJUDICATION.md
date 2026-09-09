**Formal adjudication — astrid-gpu-single-path-20260905 — 2026-09-09**

_Portable extraction note: this is only the last formal ruling. Personal/local
operational identifiers, local links, and raw transcript material are omitted;
the ruling and named source-evidence references are unchanged._

**Verdict: RATIFY-WITH-AMENDMENTS. UNIFIED-PLAN v2 is not fit to execute unchanged.** Its architecture is substantially corrected, but its completion claim omits unfinished producer/deletion work, its evidence assumptions overstate what survived, and its GPU budget is unestablished.

**Current ruling: 22 accepted task closures, one reopened HC-04 handoff, and 22 original pending rows. No pending row closes on the discovered evidence. The operation is incomplete; C12 remains unaccepted.**

This adjudication used read-only repository, remote-ref, bundle, archive, and receipt inspection. No files were changed, tests run, or pods contacted or launched. This response is the adjudication document.

**1. Findings of fact**

| Claimed state | Ruling | Evidence and correction |
|---|---|---|
| **1. Fire-19: four passes, checkout binding failure, DEFERRED_READINESS** | **PARTIAL** | [FIRE19-FINAL-EVIDENCE.txt:1] records DEFERRED_READINESS and the four named passes. It contains a generic failed-task error, followed by a filename/size inventory. It does **not** retain per-case receipts, output hashes, task-to-output bindings, or the specific checkout exception. The checkout diagnosis is consistent with source and the reviews, but the raw Fire-19 failure trace is missing. |
| **2. Six fixes applied and preserved** | **PARTIAL; false as a pushed-code claim** | Several repairs survive in archived overlays. They are not all in the claimed pushed production composition. Detailed findings follow. |
| **3. Accepted B03/B04 work recovered through four branches and a bundle** | **PARTIAL** | All four branches exist on actual origin at the expected hashes. `062a9360..ffef517a` contains 30 commits. The bundle verifies, but preserves only `HEAD=ffef517a`, not all four tips. Also, RAM-mounted worktrees used a disk-backed shared Git repository: their location does not establish that committed objects existed only in volatile memory. Recovery of off-machine custody is real; the stronger “RAM-only committed history” claim is not established. |
| **4. Broken `from_host_session` call path; exact overlay lost** | **TRUE for the broken path; PARTIAL for the historical reconstruction** | All 40 live Astrid origin branch heads were inspected: neither required method was found. The captured [production_engine-fire7.py:161] calls `from_host_session`, then `run_compiled_workflow`. Neither exists in the relevant pushed adapters. No exact 5,837-line implementation was located in surviving worktrees, reachable history, or backend archives. Its exact recovery cannot be promised. |
| **5. Ledger unreliable: 23/45, fourteen missing acceptance entries, pending receipts, stale status** | **TRUE, with an important qualification** | JSON contains 23 completed and 22 pending. Nine completed tasks have explicit handoff entries in [acceptance-ledger.md]. The other fourteen have historical receipts/reviews; missing table entries do not erase those acceptances. The five pending receipts are **BLOCKED**, not successful closure evidence. “Blocker: none” is stale. |
| **6. Historical provider resource deletion claimed, DELETE 204, verified absent** | **PARTIAL / unverified** | No DELETE response or post-delete inventory was found in the snapshot or bounded canonical-run receipt search. This does not establish that the resource remains alive. It establishes that the claimed cleanup cannot be independently certified from this record. |
| **7. All named revisions pushed; working trees clean** | **PARTIAL** | The named revisions are remotely durable. Blanket cleanliness is false: current app main is dirty, runtime main has unresolved conflicts, and the original run-specific app/worker/runtime worktree directory no longer exists. Vibe, fast Astrid, and the four recovered RAM worktrees are clean. Remote durability is not an integrated, reviewed composition. |
| **8. V2 incorporates the restructure and completes the operation through P0–P7** | **PARTIAL** | The eight phases exist and incorporate most architectural corrections. They do not yet provide a complete execution path for the frozen objective. P7 cannot substitute ledger reconciliation for unfinished source migration and deletion. |

The remotely verified recovery branches are:

| Branch suffix, all under `otto/astrid-gpu-` | Origin head |
|---|---|
| `b03-b04-composition-20260906` | `ffef517a5e2ed69eb8190983195337c9f075298b` |
| `b03-t07-manifest-20260906` | `bcc2ad5d90f6101b0ba708784b84df6e41d9a8d7` |
| `b04-t01-vace-20260906` | `7f85824547741989acf85c6a06ceee790f44f4a1` |
| `b04-t02-ltx-20260906` | `4a35c53287f5ac49ff66bbc35c37e6d3b7d1e8a1` |

The [bundle] is valid and contains complete history through `ffef517a`. It excludes commits unique to the other three tips.

The other named revisions were verified on origin: Vibe `5b39fea5`, Astrid `19020383`, app `cf9d772be`, Worker `d8fb2887`, Runtime `8ca8590`, and object-ID checkpoint `70872d03`. Worker `d8fb2887` is on origin/main; current local Worker main is a different revision.

The six-fix adjudication is:

| Repair | What actually survives |
|---|---|
| Single-argument `exec` | Archived `sitecustomize.py:1156–1161` restores caller globals/locals. The backup diff establishes the change. Historical scipy attribution is not independently receipted. |
| Warm-case process-observation race | Archived `run_b06_final.py:1199–1209` adds a bounded observation loop. This is preserved harness code, not proof of a tracked final production composition. |
| Decorator-compatible no-op tracer | Archived `sitecustomize.py:1015–1036` preserves a decorated callable. |
| Model-root configuration | [production_engine-fire7.py:137] contains the derived base-directory/model-path configuration. The specific change is absent at pushed Astrid `19020383`; complete host environment propagation was not established. |
| Production-runner output manifest | [production_runner-fire7.py:390] writes the manifest. That runner file is absent at pushed Astrid `19020383`. |
| Worker interpreter deduplication | **Not recovered as claimed.** Worker `d8fb2887` still appends configured identities without deduplication. `worker-fix.tgz` contains a zero-byte patch. The archived harness deduplicates its expected identities; that is a different change. |

**A material acceptance-integrity finding:** the archived [`final-fixes.tgz`], member `etc/python3.11/sitecustomize.py`, also contains:

- a no-op replacement for admitted-source verification, lines 982–993;
- executor liveness reduced to existence of a timestamp, lines 186–197;
- large-file digest substitution based on filename/suffix matching, lines 137–167;
- readiness injection from profile data, lines 622–637;
- settlement digest rewriting, lines 657–665.

These are changes to what the system verifies. They cannot be carried into final acceptance merely because the archive is preserved. The exact installed Fire-19 bytes are not manifest-proven, so I do not infer deceptive intent or declare its reported renders fabricated. I rule that the four summary passes **cannot establish clean production acceptance or real warm-weight residency**.

**2. Correction of record for the ledger**

The supported count is:

| Category | Count |
|---|---:|
| Historical accepted task checkpoints | 23 |
| Currently accepted closures without an unresolved assigned correction | **22** |
| Previously accepted task reopened for its affected correction | **1** |
| Original pending tasks still open | **22** |
| Original pending tasks newly closed by evidence | **0** |

Retain these 22 scoped closures, all prefixed `R1-`:

| Group | Retained tasks |
|---|---|
| P00 | T01, T02, T03 |
| B01 | T01, T02, T03 |
| B02 | T01, T02, T03, T04, T04a, T04b, T04c, T05 |
| B03 | T02, T03, T04, T06, T07 |
| B04 | T01, T02, T03 |

These are historical, scoped acceptances. They must be preserved or revalidated where the final composition changes their dependency closure. They are not 22 independent claims that the current integrated product passes.

**Reopen `R1-B03-T01` for the corrected HC-04 handoff.** Preserve its original envelope-admission PASS. Its later authority correction remains explicitly REWORK and unaccepted in the [correction review receipt]. The later `cf9d772be` commit contains the schema corrections and test source, but no later executed-test and acceptance receipt was found. Preserve the settled canonical SHA-256 object-ID decision; do not reopen that rejected finding.

Do **not** reopen the B02 foundation tasks merely because production checkout failed. Their receipts explicitly exclude production managed ownership and live C12 acceptance. For example, the [T04b review] limits its claim accordingly.

The original 22 pending rows receive these binding dispositions:

| Task, prefixed `R1-` | Ruling and remaining obligation |
|---|---|
| B03-T05a | **Open:** image-generation producer migration. Existing receipt is BLOCKED. |
| B03-T05b | **Open:** image-to-image migration with ordered CAS inputs. Existing receipt is blocked. |
| B03-T05c | **Open:** edit/inpaint/mask/Klein migration. Existing receipt is blocked. |
| B03-T05d | **Open:** upscale/video-enhance migration. Existing receipt is BLOCKED. |
| B03-T05e | **Open:** character-animation migration. Existing receipt is blocked. |
| B03-T05 | **Open:** aggregate acceptance of all five implemented children and their composition. |
| B03-T08 | **Open:** paired direct-family legacy deletion and reachability proof. |
| B04-T04 | **Open:** shared travel/join/edit producer cutover and removal of legacy task relationships. |
| B04-T05 | **Open:** dimensional/orchestration manifest convergence. |
| B04-T06 | **Open:** dimensional legacy execution and authority deletion. |
| B04-T07 | **Open:** catalog/helper deletion, including `inpaint_frames` and `qwen_image_hires`. |
| B05-T01 | **Open:** residual Worker/Reigh legacy-authority closure. |
| B05-T02 | **Open:** producer authority proof and unrelated Stage1 preservation. |
| B05-T03 | **Open:** canonical architecture, launch, and route documentation. |
| B05-T04 | **Open:** affected suites, finite route reconciliation, forbidden-path/import closure, and accepted CR2. |
| B06-T01 | **Open; amend inventory:** freeze the complete execution-affecting composition. |
| B06-T02 | **Open:** fresh provider, capacity, spend, attempt, and cleanup preflight. |
| B06-T03 | **Open:** final CPU journey on that exact composition. |
| B06-T04 | **Open:** complete representative real-GPU proof. |
| B06-T05 | **Open:** live interruption/reclaim, stale-fence rejection, CAS/settlement, and cleanup proof. |
| B06-T06 | **Open:** post-capture manifest, budgets, cleanup evidence, and final criterion matrix. |
| B06-T07 | **Open; amend routing:** independent Sol final review under the latest standing policy. |

The five blocked receipts do not claim implementations: [T05a’s receipt], for example, expressly records no source mutation or commit.

All explicit path/hash pairings inspected in the acceptance ledger and tasklist matched their surviving artifacts. That supports preservation of historical evidence, not promotion of its scope.

**No substantive producer or deletion row is approved for waiver.** Re-scoping may correct repository inventory, reviewer routing, or evidence allocation while preserving the obligation. Removing an unsupported route requires actual removal and negative evidence.

**3. Required amendments to v2**

V2 incorporates the central RESTRUCTURE findings: manager placement beneath `GenericPackHost`, foreground ownership, capability descriptors, capacity policy, mandatory checkout lifecycle coverage, harness conversion, CPU seam proofs, and a final immutable composition. The rejection of stdio-MCP-as-ownership remains correctly preserved.

The following amendments are mandatory:

1. **Restore the missing source-work dependency chain.** Explicitly schedule corrected HC-04 acceptance, B03 producer migrations, B04 convergence/deletions, and B05 residual closure before final freeze. [P7’s instruction to “close” these rows] is not an implementation plan. B05-T04/CR2 must gate B06-T01.

2. **Replace guaranteed overlay recovery with bounded recovery or reconstruction.** Locate the exact Fire-19 backend if possible; otherwise record it unavailable and reconstruct both missing methods against preserved contracts. Recover valid repairs individually. Do not restore the bootstrap wholesale.

3. **Add an explicit evidence-integrity gate.** Final execution must use tracked, reviewed code with genuine source/dependency verification, liveness, readiness measurements, and settlement fencing. Manager-issued evidence must be corroborated by independent process/resource observations and Runtime records.

4. **Make the complete execution inventory explicit.** Replace inconsistent “six repos + harness” wording with named repositories and pinned dependencies: the four product repositories, VibeComfy, Wan2GP and ComfyUI revisions, harness, bootstrap, profiles, interpreter/environment identities, node/model manifests, and effective configuration. Preserve all four recovered tips in offline custody too.

5. **Make the generality contract precise.** Distinguish one-shot ownership, owned persistent composites, adopted services, and third-party APIs. Specify acquisition/attestation, termination authority, and whether `close()` terminates a process or merely releases a client lease. Runtime remains the sole durable task/lease/settlement authority; the manager’s generation is an additional execution fence.

6. **Finish the warmth acceptance definition.** Require observed incarnation, resident-key compatibility, engine residency/load evidence, defined telemetry thresholds, canonical output equivalence, and mandatory lifecycle behavior for each warm-enabled adapter. Wan’s native reuse API establishes feasibility, not proven VRAM retention. Embedded retention across the per-task boundary remains implementation work.

7. **Reconcile historical budgets before authorizing another fire.** Record consumed spend and attempts, remaining allowances, startup/teardown costs, abort limits, and reserved final-run capacity. Neither a new phase nor a new pod resets the aggregate cap. Fire number 19 alone does not establish budget exhaustion, but remaining capacity is presently unproven.

8. **Remove contradictory authority and outcome language.** Delete residual Grok sign-off and Astra hard-review requirements that conflict with the latest routing. The final Sol reviewer must be independent of implementation. Distinguish successful execution from an honest failed/blocked terminal; do not mark an unsuccessful operation simply “EXECUTED.”

Also restore the explicit **4 GiB free-space floor, 2 GiB generated-evidence/scratch cap, isolated-worktree rules, and every-exit cleanup**. This inspection found approximately 5.17 GiB available locally; that satisfies only the current local-space check.

The 8–10-day estimate remains an estimate. It is not substantiated for the omitted producer/deletion work plus the session redesign.

**4. What exactly earns 45/45**

**45/45 means all 45 obligations are satisfied under their accepted scope—not merely assigned terminal statuses.** Blocked, failed, deferred, or waived-out work can close accounting without completing the original goal.

| Evidence class | Rows it closes |
|---|---|
| Source, focused CPU tests, fixtures, documentation, and accepted reviews | P00–B05, including the reopened HC-04 correction and all outstanding producer/deletion work |
| Frozen composition and fresh preflight | B06-T01 and B06-T02 |
| Final canonical CPU journey | B06-T03 |
| Final real-GPU journey and live recovery proof | **B06-T04 and B06-T05** |
| Durable post-run evidence, cost accounting, and cleanup | B06-T06 |
| Independent integrated acceptance | B06-T07 |
| Re-scoping alone | **No substantive completion credit** |

The final GPU fire must demonstrate, through the canonical Worker → GenericPackHost → typed-pack path:

- Wan2GP and both Vibe profiles producing validated, task-bound CAS outputs with exactly-once settlement;
- compatible repetition and honest warm/nonreuse evidence;
- cancellation for each profile;
- changed-identity fencing and nonreuse;
- restart/interruption recovery, stale-result rejection, and owned-resource cleanup;
- the additional residency and lifecycle evidence required for each newly retained adapter.

The executable case inventory must be frozen before launch and include the adapter-specific lifecycle proofs introduced by P2/P5/P6. CPU simulations remain necessary; they cannot replace the live GPU obligations.

**“89 cases,” “45 rows,” and “C01–C16” are different inventories.** There is no arithmetic conversion between them.

- **45 rows:** implementation, integration, evidence, and review obligations.
- **C01–C16:** acceptance criteria, each requiring its own evidence mapping.
- **Harness cases:** executable scenarios/assertions whose inventory must come from the frozen harness.

The retained `run_b06_final.py` schedules four scenarios per profile plus one selected restart record—**13 logical records for three profiles**, not an established 89-case GPU matrix. Delete the unsupported “89 cases → 45-row ledger → C01–C16” formulation unless a separate enumerated inventory is supplied.

Likewise, the **47-route / 11-alias / 20-family / eight-producer** reconciliation is a coverage inventory, not a GPU test count. The frozen goal permits deterministic variant coverage plus representative live engines; it does not require every model variant on GPU.

Historical criterion entries must preserve their scope. For example, **“CR1 CPU sub-proof PASS” does not mean final C14 PASS**. Final C01–C16 acceptance requires the complete frozen composition, including producer and deletion evidence. Feature-branch pushes do not establish that acceptance or promotion.

**5. Residual risks and honest stop conditions**

| Residual risk | Required stop condition |
|---|---|
| Missing source and divergent compositions | Stop advancement to GPU if any execution-affecting behavior lacks a pinned, reviewed source identity. Reconstruct on CPU where possible. |
| Verification bypasses masquerading as production proof | Reject acceptance immediately if source verification, measured readiness, liveness, or stale-settlement checks are bypassed or rewritten. |
| Retained engines escape lifecycle authority | Stop admissions on uncertain cancellation, incarnation mismatch, stale results, orphaned descendants, or unproved GPU/port release; fence and clean up. |
| Wan/embedded residency is infeasible under available capacity | Record the failed feasibility gate. Do not relabel process persistence as warm weights or silently declare the expanded v2 goal complete. |
| Hidden legacy producers or execution authority | Withhold C01/C05/C06/C11/C13 acceptance until supported reachability is removed and proved. |
| Spend, attempts, disk, or evidence capacity | Stop live work when a declared allowance is exhausted or cannot be established. Preserve evidence and terminate owned resources. |
| Missing provider cleanup evidence | Keep cleanup unverified until a receipted provider observation establishes absence; never infer zero pods from local process exit. |

An honest terminal must state which obligations failed or remain blocked. It must preserve available evidence, perform cleanup, and avoid a 45/45 claim. Ordinary implementation difficulty remains work to complete, not a reason to terminate the operation.

**6. Binding directive for the next directing session**

1. **Establish custody and remaining capacity.** Record this adjudication; inventory exact surviving local/remote identities, preserve all four recovered tips, inspect protected working trees without modifying them, and reconstruct historical spend/attempt/termination evidence. Verify disk and scratch limits. No GPU advancement while those allowances remain unknown.

2. **Correct the execution authority and ledger.** Record **22 accepted closures, B03-T01 reopened, 22 original pending**; preserve historical scoped passes; apply the eight amendments above. Bind every remaining row and C01–C16 criterion to concrete evidence and dependencies. Make CR2 precede the final freeze.

3. **Complete the corrected HC-04/Runtime handoff from durable revisions.** In isolated worktrees, validate Runtime `70872d03` with app `cf9d772be`, execute the focused schema/CAS/catalog tests, obtain the required acceptance, and then dispatch the existing producer/deletion briefs from those accepted identities. Recover or reconstruct the checkout implementation through the amended CPU phases before any new GPU fire.

**The architecture is conditionally ratified. The claimed completion path and inherited evidence are not.**
