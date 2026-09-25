# Validation and acceptance boundaries

Current P0–P11/Q/H build, test and acceptance scope is **CPU/fake/offline only**.
[Execution scope](execution-scope.md) supersedes every older live-test criterion.
[Post-handoff gate L](POST-HANDOFF-GPU-GATE.md) is excluded from current acceptance.

Packet-only checks are safe without product environments:

```sh
python3 tools/packet.py verify .
python3 -m json.tool manifest.json >/dev/null
python3 -m json.tool repo-lock.json >/dev/null
python3 -m json.tool dependency-lock.json >/dev/null
```

If PyYAML is available, parse every exported `run.yaml`, check all seven role
slots, valid reviewer-role references, integer caps and real criterion paths.
Do not modify modes, stages or counts merely to make a validator pass. All
exported run YAML was parsed during packaging; [the validation report](evidence/packet-validation.json)
records actual results. Native model execution is not tested by YAML parsing.

For later product CPU/fake verification, work only in newly fetched exact
checkouts and fresh environments. A minimal environment creation pattern is:

```sh
test ! -e ../astra-high-cpu-venv && test ! -L ../astra-high-cpu-venv &&
python3 -m venv ../astra-high-cpu-venv
# Inspect pinned pyproject.toml/lock files first. Install only CPU/test extras.
# Use the absolute environment interpreter thereafter, never ambient pip.
```

Prepare an approved CPU-only dependency wheelhouse and build-backend closure
before validation; source/package retrieval is a separate setup step. Install
from that local wheelhouse with `python -m pip install --no-index --find-links
/absolute/cpu-wheelhouse ...` and use pinned local source paths. Build packages
with local backends and build isolation disabled where needed to prevent implicit
fetches. Run builds and tests with outbound network denied, no GPU devices exposed,
no provider credentials and all remote/native engine clients replaced by fakes.
Do not use GPU extras, download models or start CUDA/native generation servers.
If the CPU closure is missing, record a CPU setup prerequisite; do not fall back
to a GPU environment or live backend. These are instructions, not a claim that
a complete CPU dependency lock has been qualified. P6 owns that lock.
Never install Wan2GP GPU dependencies into this control environment or use a
global environment as a workaround. No such install was run while packaging.

Run focused fake suites from the matching pinned repo after reviewing fixtures
for external calls. Use no provider secrets, disable configured live backends,
keep network blocked during tests and stop if a fixture requires live resources:

| Repository | Command in that checkout | What it can prove |
|---|---|---|
| Astrid | `python -m pytest -q tests/test_managed_generation_result.py tests/test_vibecomfy_production_engine.py tests/test_generic_host_output_contract.py` | Neutral validation, consumer behavior and typed-output handling |
| runpod-lifecycle | `python -m pytest -q tests/test_shipping.py tests/test_runner.py` | Fake scoped transport and archive/root safety |
| VibeComfy | `python -m pytest -q tests/test_runtime_run.py tests/test_runtime_session_config.py` | Producer completion and runtime configuration seams |
| Astrid successor | `python -m pytest -q tests/core/execution/test_managed_tool_session.py tests/test_generic_host_persistent.py tests/test_wan2gp_lifecycle.py tests/test_wan2gp_persistent_session.py` | Existing session/worker fixtures; not native GPU residency |

These paths were checked at the pinned sources. Test counts in old controls are
historical recorded results; packaging did not rerun product tests. A fake
artifact that passes a MIME/hash test is not a decoded live video. The complete
integrated Project A typed-upload acceptance receipt must be rebound to exact
final commits (or rerun after authorization) before certifying those commits.

Q owns the eventual cross-repository evidence matrix: valid full lineage;
missing/duplicate/escaping/stale/corrupt artifacts; wrong size/MIME/hash;
retrieval failure after execution; cancelled/late attempt; owned process
restart/lease loss; wrong target/device; same-set retention and changed-set
release; bidirectional engine change; two-segment shot approval/restart/retry;
selection rollback and upstream invalidation. Each receipt binds command,
input/environment hashes, source tuple, result and evidence hashes.

Completion of the current projects requires the applicable CPU/fake evidence
above and their unchanged review policy. Record live checks as
`DEFERRED_POST_HANDOFF`, not failed, passed or pending current acceptance. A suite
that attempts a provider call or hardware test violates this scope: fix its
isolation or split that test into the deferred suite. Never run an unfiltered
integration suite whose side effects have not been checked.

All real GPU/RunPod qualification, native model residency, fresh-pod tests,
performance/VRAM measurements and live output checks are retained solely in
[gate L](POST-HANDOFF-GPU-GATE.md). It requires a separate later instruction and
cannot be triggered by current build/test commands or project completion.
