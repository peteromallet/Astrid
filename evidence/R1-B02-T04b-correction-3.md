# R1-B02-T04b correction-3 Luna implementation evidence

Status: implementation complete; acceptance is withheld pending the required fresh independent review.

## Custody

- Required parent commit: `364000b5cbdcc513e24c534ed6bb7d3dfe4a4362`
- Required parent tree: `3b43d6dcc99588a6318ff81136eb3db5c47263f1`
- No prior worktree changes were present at start.
- Owned implementation files changed: `astrid/core/generation/backends/vibecomfy.py`, `tests/core/generation/backends/test_checkout_server.py`, and `tests/core/generation/backends/test_warm_cancel.py`.
- Run-dir files written: this evidence file and the matching receipt only.

## Fresh verification

- Focused suite: **105 passed**.
- Frozen suite: **151 passed**.
- Ruff gate (`E9,F63,F7,F82,I`): **passed**.
- Direct compilation of all three owned files: **passed**.
- `git diff --check`: **passed**.
- No pytest/helper process remained after verification. Existing unrelated infrastructure processes (generic host and ComfyUI) were observed and left untouched.

## Four residual corrections

- **F01 — PASS (offline/direct regression only):** added `invocation_identity` to the complete canonical structured identity record used for both session and warmth digests. Direct bindings differing only in invocation identity now produce different digests, and binding-1 digests are rejected under binding 2 before reuse or side effects. Existing complete-field and model-byte identity isolation coverage remains passing.
- **F02 — PASS (offline/direct regression only):** retained bounded iterative scan and closed strict decoder; scan/parser/resource failures are mapped through the local allowlist to fresh fixed-code errors with cleared `__context__` and `__cause__`. Canary, deep nesting, redaction, duplicate-key, non-finite, malformed UTF-8/JSON, unknown-field, header, and size-bound coverage remains passing.
- **F03 — PASS (offline/direct regression only):** removed the blocking hostname resolver path from the deadline transport. Numeric loopback addresses use the selector transport; unsupported hostname resolution fails closed as `checkout_deadline_transport_unavailable` before resolver invocation. Existing raw loopback deadline/framing/close behavior remains passing.
- **F05 — PASS (offline/direct regression only):** adapter controls and shared control paths now require the exact latched binding object plus the complete canonical attestation before probe, lifecycle mutation, or remote control. Copied-equal bindings fail closed with zero control requests; field-drift, replacement, lifecycle fencing, poisoning, and ordering coverage remains passing.

## Scope limits

These are offline fixtures and raw-loopback tests. This evidence does not claim production F05, live GPU, C12, or C14 acceptance. No ledger/status update, route/scheduler/registry change, dependency change, deployment, merge, push, or downstream dispatch was performed.
