# Settled-plan wave 5 synthesis

Plan SHA-256:
`b836dbab74395860486e6ebec980a66b8a150ff238c3d3a9393b0598f554f062`

## Accepted material changes

1. **Freeze installed admission at snapshot capture; remove the pre-use state
   recheck.** A check immediately followed by execution cannot prevent an
   interleaving mutation without holding a lock across pack code. That lock is
   disproportionate and risks deadlock. Instead, the existing store-owned
   admission projection validates and captures the active revision, canonical
   provenance, manifest digest, accepted permissions, and validity once while
   constructing the top-level operation snapshot. The snapshot may execute that
   selected revision for the operation lifetime; activation/rollback/
   invalidation changes affect the next operation. Immediate pre-use checks are
   limited to the captured manifest and consumed resource handles. No rescan,
   retry, lock, revocation service, or second trust owner is added.
2. **Hard-cut installed records to an exact v2 admission record.** New records
   persist record schema version 2, revision identity, canonical root-independent
   provenance identity, normalized manifest digest, normalized accepted
   permissions, and validation disposition. Remove raw-manifest trust reparsing
   and silent missing-field defaults from the active v2 path. Pre-v2/incomplete
   records fail closed with an explicit reinstall diagnostic; there is no
   migration, defaulting shim, or revalidation fallback. Golden external-pack
   tests install a fresh v2 record and prove capability execution; external
   `database` still rejects before resource/SQL access.
3. **Close bundled direct-child discovery.** Under packaged `astrid/packs`,
   every direct child directory except the irreducible `_core` guidance
   directory must contain exactly one strict v2 `pack.yaml` and load as a
   retained product pack. There is no generic bundled “non-pack directory” skip.
   The audit compares the sorted direct-child set, loaded catalog set, and
   expected retained count/names generated from that filesystem set; missing,
   extra, legacy-only, duplicate, or unloaded children fail.
4. **Remove bundled documentation opt-outs for this beta set.** All 22 retained
   bundled product packs are user/agent-facing and must declare valid packaged
   structured documentation. `documentation.kind: none` is invalid for bundled
   candidates, so admission never consults the audit-only coverage ledger. The
   frozen goal's opt-out allowance remains unused; no internal utility pack is
   retained as a product pack.
5. **Audit Python ownership without declaring Python as package data.** The
   coverage inventory enumerates every Python file/module below each bundled
   pack root and maps it to the owning pack plus a declared typed contribution
   module/subtree or an exact justified package-initialization role. Unreachable,
   multiply owned, or unclassified Python modules fail. Python remains governed
   by normal wheel module packaging and source/wheel import-origin proof, not by
   the non-Python resource grammar.
6. **Use concrete receipt identity, not a snapshot fingerprint.** Runaway and
   other operation receipts record the ordered selected provenance identities
   relevant to the operation, their pack/revision/version fields, and the exact
   migration/resource digests consumed. They do not serialize rejected
   candidates, layer order, or an invented whole-snapshot identity.

## Deduplication and dispositions

- The manifestless-child gap was independently reported by two critics and is
  one accepted correction.
- The undefined Runaway snapshot identity was independently reported by two
  critics and is resolved by item 6.
- The admission TOCTOU and incomplete installed-record findings are resolved
  together by items 1–2. This intentionally supersedes Wave 4's pre-use store
  state recheck based on new concurrency evidence; the capture-time admission
  authority remains single and fail-closed.
- No project lock, lock-across-execution, lifecycle system, immediate revocation
  service, dynamic plugin framework, compatibility record migration, or global
  snapshot fingerprint is accepted.
- No new research lane or `[XHARD]` work is required.

## North Star disposition

**Conditionally aligned.** The new evidence exposes residual closure and
admission ambiguity, but each has a narrow direct-cut resolution that makes the
system simpler. Sol must revise the complete plan, return exact `STABLE`, and a
fresh settled-plan wave must inspect the new snapshot.

