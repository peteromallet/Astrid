# UNIFIED-PLAN v3 — FINAL EXECUTION AUTHORITY

**Date:** 2026-09-09 · **Status:** RATIFIED per Astra GPT-6 formal adjudication (38a7544) — supersedes v2, v1, and the standalone 45-task ladder path
**Provenance:** v2 architecture + all 8 mandatory adjudication amendments + the adjudication's binding directive, fully incorporated
**This document is the single execution authority.** Executing P0–P7 in order is the conclusion of the astrid-gpu-single-path-20260905 operation.

---

## 0. Adjudicated state of record (binding — supersedes all prior counts and claims)

Per Astra GPT-6 formal adjudication (ASTRA-ADJUDICATION-FINAL.md):

- **22 accepted task closures** (historical, scoped): P00 T01-T03; B01 T01-T03; B02 T01,T02,T03,T04,T04a,T04b,T04c,T05; B03 T02,T03,T04,T06,T07; B04 T01,T02,T03
- **1 reopened**: R1-B03-T01 — corrected HC-04 handoff; later authority correction is REWORK and unaccepted (`receipts/R1-B03-T01-hc04-runtime-authority-correction-1-review.json`); the settled canonical sha256 object-ID decision stands and is NOT reopened
- **22 pending rows: ALL OPEN.** No pending row closes on discovered evidence. The five B03-T05a-e receipts are BLOCKED, not completions. "Blocker: none" in status.md is stale.
- **Fire-19's four GPU passes are evidence, not acceptance** — the fire-19 overlay contained verification bypasses (no-op source verification, timestamp-only liveness, digest substitution, settlement digest rewriting) and cannot establish production acceptance or warm residency.
- **Not recovered**: the exact fire-19 backend implementation (`from_host_session`/`run_compiled_workflow`, ~5,837 lines). Bounded recovery or reconstruction only.
- **Budget**: historical spend/attempt balance is UNPROVEN; no GPU advancement until reconciled. A new phase does not reset the aggregate cap.

## 1. End state (unchanged, ratified)

1. All three profiles pass end-to-end through C12: wan2gp, vibe_pip_embedded, vibe_checkout_server.
2. Warm weights via one engine-neutral SessionManager (ManagedToolSession custody envelope with warm-residency as an optional capability), adapters per engine, fencing on identity change/restart.
3. All 45 ledger rows closed under adjudicated scope — **45/45 or an honest terminal** (which states what failed/blocked; never "EXECUTED" for an unsuccessful outcome).
4. All source of record in tracked git; zero pods; evidence-integrity verified.

## 2. The custody contract (per adjudication amendment 5)

Four modes — an adapter declares its mode via a **capability descriptor**:

| Mode | Examples | Contract essentials |
|---|---|---|
| **one-shot owned process** | ffmpeg, Remotion, local Blender | Child handle; pin executable/inputs; bound execution; reap; no session proof |
| **owned persistent composite** | checkout ComfyUI, persistent Wan runner, retained EmbeddedSession | Full proof: nonce, PID birth identity, exact argv/config/source digests, listener ownership, health per admission, generation fencing, restart-with-fresh-identity, proof-backed teardown |
| **explicitly adopted external service** | Blender cloud host | Auth + service-instance attestation + per-use health + declared restart authority — never "owned" by reachability |
| **third-party API** | fal.ai, WaveSpeed | Scoped credentials, provider request IDs, idempotency, deadlines, cancellation, output validation — no PID proof |

Capability descriptor fields: ownership mode; terminate authority; residency support (unsupported/observable/releasable); admission capacity (serial/concurrent/batched); cancellation strength + uncertain-outcome reconciliation; resources claimed (GPU/ports/files/credentials); whether `close()` terminates, detaches, or releases a lease.

**Runtime remains the sole durable task/lease/settlement authority** — the manager's generation is an additional execution fence, not a second ledger.

**Warm-reuse contract** (adapters in mode 2 with residency ≠ unsupported):

| Operation | Contract |
|---|---|
| `observe()` | Health + attested session incarnation + residency evidence |
| `resident_key(request)` | Task-independent: model artifact digests, VAE/text-encoder/LoRA residency, quantization/dtype, memory/offload/attention/compile policy, engine revision, effective environment. NEVER prompt/seed/resolution/output-path/task-id |
| `prepare(key, force_cold)` → `{ready, reused, generation, reason, evidence}` | Structured; never a bare bool |
| `run(request, spool, admission)` | Serialized per capacity; settlement rejected if admission generation stale |
| `fence(reason)` | Stop admissions + advance generation BEFORE cleanup |
| `release(reason)` | Drain/cancel + prove unload/cache clearing, or force restart |
| `close()` | Per descriptor: prove process/GPU/port gone, or release lease only |

Warmth = `state == WARM ∧ resident_key matches ∧ session_incarnation matches ∧ admission generation current ∧ no fence/poison`. The Wan JSONL journal is evidence/history only — never establishes warmth or liveness.

## 3. Phases (amended — dependencies enforced; nothing skipped)

### P0 — Custody, provenance & capacity (CPU-only) — partially complete
- [x] ~~Recover RAM-disk accepted compositions~~ — 4 branches pushed (`b03-b04-composition` @ `ffef517a`, `b03-t07` @ `bcc2ad5d`, `b04-t01-vace` @ `7f858245`, `b04-t02-ltx` @ `4a35c532`) + bundle (covers `ffef517a` history)
- [ ] **P0.a Bundle completion**: bundle the other three tips (current bundle holds only `ffef517a` lineage) into offline custody
- [ ] **P0.b Fire-19 backend recovery-or-reconstruction**: bounded attempt to locate the exact 5,837-line `backends/vibecomfy.py`; if unavailable (adjudication says likely), **reconstruct** `from_host_session` + `run_compiled_workflow` against the preserved contracts (`production_engine-fire7.py:161` call shape + c7f5b33d binding semantics); recover the five valid repairs individually — **never restore the overlay wholesale** (adjudication found verification bypasses in it: no-op source verification, timestamp liveness, digest substitution, settlement rewriting — these must NOT survive into acceptance)
- [ ] **P0.c Composition freeze (part of B06-T01)**: pin exact identities — Astrid, reigh-worker, runtime (`70872d03`), reigh-app (`cf9d772be`), vibecomfy (P1 output), Wan2GP + ComfyUI revisions, harness scripts, sitecustomize, profiles, interpreter identities, node/model manifests, effective configuration — one committed composition manifest
- [ ] **P0.d Budget reconciliation** (amendment 7): reconstruct historical spend + attempts (19 fires), remaining USD allowance under the 6-cap, per-fire max minutes/dollars, abort conditions, reserved final-run budget. **No GPU fire until signed.**
- [ ] **P0.e Ledger correction of record** (adjudication §2): apply the 22/1/22 ruling to tasklist.json + acceptance-ledger.md verbatim; reopen B03-T01 (HC-04 correction REWORK); mark five B03-T05 receipts as BLOCKED; correct "blocker: none"
- [ ] **P0.f Local capacity**: ≥4 GiB free (adjudication measured ~5.17 GiB — verify), 2 GiB evidence cap, isolated-worktree rules
- [ ] **P0.g Routing compliance** (amendment 8): Sol = implementer of P1/P2 AND independent final reviewer (never self-review); no Grok oracle unless user re-opens routing; "EXECUTED" forbidden for honest-failure terminals

### P1 — Vibe integration (CPU-only)
- [ ] Real content merge: base = `cb130f1b` (handover lineage containing c7f5b33d); integrate `fix/S1…` (`5b39fea5`) authored content — explicit cherry-pick vs merge semantics decided and documented; NOT the ancestry-only probe merge (`merge-main-probe` tree = first parent, supersedes nothing)
- [ ] Isolated CLEAN worktree; 30-file reconciliation expected; conflict allowlist; focused tests
- [ ] Independent review (Sol, not the P2 implementer if overlapped)
- [ ] **P1 exit criteria**: one branch containing launch-marker ownership + modern SessionConfig (`base_directory`, `extra_model_paths_config`, `runtime_root`/`cwd`) + `disable_known_models`; both `pip_embedded` and `checkout` paths consuming it

### P2 — Manager core (CPU dev; GPU tests in P4+)
- [ ] `ManagedToolSession` under GenericPackHost: custody envelope, capability descriptors, warm-slot/capacity policy (single GPU: retain compatible state, else fence-and-release one backend before admitting another), lifecycle generations, admission tokens
- [ ] Reconstruct the checkout adapter call path: `from_host_session` + `run_compiled_workflow` (from P0.b reconstruction) wired for real
- [ ] Fault-injection tests (CPU-simulated): wrapper loss, orphan, PID-reuse, restart race, port-release, uncertain cancellation
- [ ] Evidence-integrity by construction (amendment 3): all verification from tracked reviewed code; genuine source/dependency digests, measured liveness/readiness, settlement fencing — corroborated by independent process/resource observation + Runtime records; **any verification bypass = immediate stop**
- [ ] Independent review (Sol)

### P3 — Harness conversion (CPU-only)
- [ ] Session-aware evidence model: long-lived owned session ≠ attempt-scoped execution (success/cancel/changed-identity/restart/cleanup assertions rewritten against manager-issued evidence + independent observation)
- [ ] `warm_reuse_expected` schema decoupled from listener ports (embedded has none)
- [ ] Delete `start_checkout()`; readiness order: worker starts owned session first; 8188 verified after; never adopt a listener
- [ ] **Freeze the executable case inventory from the actual harness** (adjudication: the "89 cases" number is unverified; use the frozen inventory, whatever its count)
- [ ] Scratch floor (4 GiB), run cap (2 GiB), deadline gates wired

### — MILESTONE 1: composition frozen (P0.c final) + C12 blocker cleared at code level. Pod budget must be signed before any fire. —

### P4 — Checkout proof on GPU (first budgeted fire)
- [ ] Preflight gate (8 steps): free port → registry complete (`pid`,`url`,`config.json`,`source_revision`,`launch.json`,`daemon.log`) → binding-only call → kill/restart proof
- [ ] checkout_server **cold + warm + cancel + changed_identity + restart** (adjudication: lifecycle coverage for C12/C09 is mandatory, not deferrable)
- [ ] Receipt: "checkout_runtime_binding proven" — per-case receipts, output hashes, task-to-output bindings (fire-19's missing evidence shape — required for every subsequent fire)

### P5 — Wan persistent runner (second consumer)
- [ ] CPU seam proof first (native API supports retention: `shared.api.init` reusable session; skip-reconstruction on compatible model/profile)
- [ ] **GPU residency feasibility gate** (amendment 6): observed incarnation + no reconstruction event + engine-reported resident components + meaningful VRAM residency + load-time reduction + canonical output equality (CAS: cold→warm, A→B→A, cancellation, restart). **If infeasible: record the failed gate honestly; do not relabel process persistence as warm weights**
- [ ] Fix the resident-key: Wan's current fingerprint hashes prompt/seed/resolution — replace with model-artifact/policy identity
- [ ] Keep MP4 canonicalization after every run (mutagen ©cmt); keep `warm_reuse_expected: false` until the gate passes
- [ ] Per-task output-spool rebind (construction-time `output_dir` is incompatible with retention)

### P6 — Embedded retained session (third consumer)
- [ ] CPU spike first: retention across the per-task production_runner boundary (host-level seam — changes cancellation semantics; not a trivial flip)
- [ ] Retained `EmbeddedSession`; `warm_policy: "never"` flipped only with the same evidence class as P5

### P7 — Final acceptance (one frozen composition, budgeted fires)
- [ ] **Gate: B05-T04 / CR2 PASS** (adjudication: CR2 precedes the final freeze) — which requires P0-ledger-corrected execution of: B03-T05a-e + T05 + T08 (producer migrations + deletion manifest), B04-T04→T07 (cutover, convergence, deletions incl. `inpaint_frames`/`qwen_image_hires` with negative evidence), B05-T01→T04 (legacy authority closure, Supabase-lifecycle removal proof, docs, frozen suites)
- [ ] Freeze ONE immutable composition (all repos + harness at final heads; all four recovered tips preserved offline)
- [ ] CPU gates re-run on the frozen composition
- [ ] **Budgeted GPU acceptance fire(s)**: the frozen case inventory → **B06-T04 real-GPU journey** (validated task-bound CAS outputs, exactly-once settlement, compatible repetition + honest warm/nonreuse evidence, cancellation per profile, changed-identity fencing, restart/interruption recovery, stale-result rejection, owned-resource cleanup) + **B06-T05** live interrupt/reclaim proof
- [ ] **B06-T06**: post-capture manifest, spend accounting, cleanup evidence — **zero pods verified by provider observation, never inferred from local process exit**
- [ ] **B06-T07**: independent Sol final integrated review (implementer-independent per routing)
- [ ] Close the ledger: every one of the 45 rows → closed-under-scope or honest terminal; if terminal: state what failed/blocked, preserve evidence, "EXECUTED" forbidden
- [ ] Zero pods; everything pushed; UNIFIED-PLAN status → COMPLETED (or TERMINAL-HONEST); archive run

## 4. Evidence classes — what earns what (adjudication §4, binding)

| Evidence class | Closes |
|---|---|
| Source + focused CPU tests + fixtures + docs + accepted reviews | P00-B05 rows incl. reopened B03-T01 correction, all producer/deletion work |
| Frozen composition + fresh preflight | B06-T01, B06-T02 |
| Final canonical CPU journey | B06-T03 |
| Final real-GPU journey + live recovery proof | B06-T04, B06-T05 |
| Durable post-run evidence + cost accounting + cleanup | B06-T06 |
| Independent integrated acceptance | B06-T07 |
| Re-scoping alone | **nothing** |

45/45 = all 45 obligations satisfied under accepted scope. The three inventories (45 rows / C01-C16 criteria / frozen harness case count) are distinct; no arithmetic conversions.

## 5. Stop conditions (honest-terminal triggers)

- Any execution-affecting behavior without a pinned reviewed source identity → stop GPU advancement
- Any verification bypass or rewritten check → reject acceptance immediately
- Uncertain cancellation / incarnation mismatch / stale results / orphaned descendants / unproved GPU-port release → stop admissions, fence, clean up
- Wan/embedded residency infeasible → record failed gate; do not fake warmth
- Spend/attempt/disk/evidence allowance exhausted or unestablishable → stop live work, preserve evidence, terminate owned resources
- Provider cleanup unverifiable → keep cleanup unverified; never infer zero pods from local exit

Ordinary implementation difficulty is work, not a stop reason.

## 6. Routing (per POST-COMPACTION-HANDOFF, restored — adjudication amendment 8)

- **Astra (GPT-6, low):** direction, briefs, custody, user updates
- **Sol (GPT-5.6):** P1 merge, P2 manager, P0.b reconstruction; **independent final reviewer** (never reviews own implementation)
- **Luna (GPT-5.6):** adapters, harness conversion, tests, evidence
- **Grok:** not on the default path (standing policy: fallback after receipted exhaustion; user may re-open oracle routing explicitly)

## 7. Schedule

| Week | Days | Content | Pod? |
|---|---|---|---|
| 1 | 1 | P0 finish (recovery/reconstruction, ledger ruling, budgets, freeze-prep) | no |
| 1 | 2-3 | P1 merge + independent review | no |
| 1 | 4-5 | P2 manager + P3 harness (CPU) | no |
| 2 | 6-7 | P4 checkout GPU proof + P5 Wan adapter (feasibility gate) | **yes — budgeted** |
| 2 | 8 | P6 embedded + evidence-gated flag flips | **yes** |
| 2 | 9 | B03-B05 closure work on the composition (producer migrations already accepted upstream where receipts exist; deletions with negative evidence) | no |
| 2 | 10 | P7: freeze → CPU gates → one acceptance fire → 45-row ledger → independent review → zero pods | **yes — reserved budget** |

**Estimate:** 10 working days / ~2 calendar weeks (adjudication: 8-10 days is an optimistic floor, not a promise; the producer/deletion closure is now explicitly in scope).
**Milestones:** M1 (day 5) = composition frozen, blocker cleared in code, budget signed. M2 (day 10) = **45/45 or honest terminal + warm machinery on all three backends + ledger closed + zero pods + all pushed.**

## 8. Deferred (explicit — requires receipts at P7)

- Broader combinatorial hardening beyond mandatory C12 lifecycle paths
- Blender cloud adoption-mode attestation (documented gap; separate fix under mode-3 contract)
- Comfy-MCP pilot — only under the 8 guardrails (ASTRA-SECOND-OPINION-MCP.md); off critical path
- Provider-side warmth (fal/WaveSpeed) — uniform semantics, provider owns VRAM
