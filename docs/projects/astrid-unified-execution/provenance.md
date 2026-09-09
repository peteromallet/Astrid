# Portable provenance

These hashes identify the planning inputs inspected for this handover. They
are provenance records, not claims that the product or acceptance tests ran.

## Selected source identities

- Planning snapshot HEAD: `a9c0190a0440cd0a38cf677417ec818d6119a900`.
- Astrid host/base `main`: `8150c3b70887495f0fae4a55c1ac70085a900550`.
- Original custody run: `astrid-gpu-single-path-20260905` (historical source
  name only; its local custody is not published or copied wholesale).

| Input | SHA-256 |
|---|---|
| `UNIFIED-PLAN-v3.md` | `0772f5ac5196b7c0e28d19c1d636f18c26a3cc8c550f9f1a09bd9a4e2ddb7dc0` |
| `ASTRA-ADJUDICATION-FINAL.md` | `7fdcd56553090fd8e2bc2e8dd54e7ba6c288079e0f42f8a92dad669c447635e4` |
| `FIRE19-FINAL-EVIDENCE.txt` | `63e2bb8b48f27b10a2bbaa8a4904453b995f5225a0a4a9b102fd0dca3cde14e7` |
| `MEGAPLAN-IDEA.md` (supplementary, intentionally untracked input) | `67bb13a13a9b5fce02cd02f71913a661176a51b428bc2a7887da9e731645e332` |
| original `tasklist.json` | `042bef583f432d44a85e987734a2d1e2e50ca350a75b5ffeb950135d5eb344b0` |
| original `status.md` | `ea7b94d32e563432b1d95d2c7fd7533cbaa24b176247685b17697cda695cfcf4` |
| original `northstar.md` | `a8b2845edf9c515351bfe13d5b9ad28620a712dcba41859cd0cbda254a9857b7` |
| original `agent_goal.md` | `0972011cc35e5b035397ceb85bbed847c569332b3036caec553db0dbcd1ae875` |
| original `POST-COMPACTION-HANDOFF.md` | `a25bcf6344ad30a0ad258edcab3dfbdacaba097ab93091ca2cfcde741ff4e99e` |
| original `acceptance-ledger.md` | `28ba7907d02b0b82d299a2d0da7ef5bbf493a52bfa2b3265769cba0adc696c35` |

The supplementary `MEGAPLAN-IDEA.md` and the untracked `megado-unified-v3/`
input directory were intentionally present in the planning snapshot and were
inspected as inputs. They do not override v3 and are not copied as raw source
or logs. The historical custody run remains named evidence only; no wholesale
logs, archives, receipts, credentials, private links, or local paths are
included here.

## Observed host state

The Astrid host base was observed on `main` with pre-existing dirty/untracked
work preserved. Those working-tree changes are not silently treated as the
authoritative execution composition. A future delivery coordinator must
inventory the actual candidate, dependency revisions, interpreter/node/model
manifests, effective configuration, and dirty custody before dispatch.

