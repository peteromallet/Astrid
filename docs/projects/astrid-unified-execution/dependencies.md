# Pinned handover dependencies

The host is [peteromallet/Astrid](https://github.com/peteromallet/Astrid),
base `main` at `8150c3b70887495f0fae4a55c1ac70085a900550`.
This is the handover host/base, not a replacement for the implementation
revisions selected in [the ratified plan](authority/UNIFIED-PLAN-v3.md).
The portable control root is `docs/projects/astrid-unified-execution/`.

## Megado skills

Repository: [peteromallet/poms-skills](https://github.com/peteromallet/poms-skills).
Exact inspected and published commit:
`1219b3183dde29e4b74681690c4a2351bed3cab3`.
The preparer read `megado/SKILL.md`, `megado-handover/SKILL.md`, and the
Megado run-configuration and review-packet references at this revision.
The handover skill now prefers a dedicated branch atop the existing project's
main, with a named tracked project directory.

From a chosen receiving parent directory, these commands refuse to reuse an
existing destination. They do not overwrite installed skills:

```sh
test ! -e poms-skills-1219b31 &&
git clone https://github.com/peteromallet/poms-skills.git poms-skills-1219b31 &&
git -C poms-skills-1219b31 checkout --detach 1219b3183dde29e4b74681690c4a2351bed3cab3 &&
git -C poms-skills-1219b31 rev-parse HEAD
```

If the first command refuses because the destination exists, stop and select
a fresh directory; do not execute the checkout against someone else's files.
Read the skills directly from that checkout; no global installation is needed.
The exact-commit direct-read fallback is:

- [Megado](https://raw.githubusercontent.com/peteromallet/poms-skills/1219b3183dde29e4b74681690c4a2351bed3cab3/megado/SKILL.md)
- [Megado handover](https://raw.githubusercontent.com/peteromallet/poms-skills/1219b3183dde29e4b74681690c4a2351bed3cab3/megado-handover/SKILL.md)
- [Run configuration](https://raw.githubusercontent.com/peteromallet/poms-skills/1219b3183dde29e4b74681690c4a2351bed3cab3/megado/references/run-config.md)
- [Execution mechanics, for later authorized delivery](https://raw.githubusercontent.com/peteromallet/poms-skills/1219b3183dde29e4b74681690c4a2351bed3cab3/megado/references/execution.md)
- [Review assembly](https://raw.githubusercontent.com/peteromallet/poms-skills/1219b3183dde29e4b74681690c4a2351bed3cab3/megado/references/review-packets.md)
- [Review packet template](https://raw.githubusercontent.com/peteromallet/poms-skills/1219b3183dde29e4b74681690c4a2351bed3cab3/megado/templates/review-packet.md)

## Agent capability

The preparing host exposes native `spawn_agent`, messaging, and independent
leaf contexts, with `gpt-6-astra`, `gpt-5.6-sol`, and `gpt-5.6-luna` available.
Role/reasoning assignments exist only in [run.yaml](run.yaml); read that file
before dispatch. Editing YAML does not switch the current host model.

Availability on the receiving machine is not established. Check native
delegation and each configured model/reasoning setting there before dispatch;
report a missing capability explicitly and never silently substitute models.
Planning files remain readable without agent execution or GPU access.

## Execution prerequisites

The following public repositories and commit endpoints were checked during
packaging. These are preserved plan inputs, not a final integrated composition.

| Repository | Role / selected input | Exact commit |
| --- | --- | --- |
| [Astrid](https://github.com/peteromallet/Astrid) | Handover host `main` | `8150c3b70887495f0fae4a55c1ac70085a900550` |
| [VibeComfy](https://github.com/peteromallet/VibeComfy) | P1 integration base | `cb130f1b737c6e2043a93089c24b3fcbac166b69` |
| VibeComfy | Ownership contract in base lineage | `c7f5b33da974da0ed7f97df3e6e4e6dab65f5243` |
| VibeComfy | Authored fix content to integrate | `5b39fea5b89edd71771aaaec8444449e33b82f09` |
| [reigh-app](https://github.com/banodoco/reigh-app) | Corrected HC-04 input | `cf9d772be0e2e4098171f2d1888afe5caafe466c` |
| [reigh-worker](https://github.com/banodoco/reigh-worker) | Preserved worker input | `d8fb28875f78bd189dc4046369ee34dcf50e2c1a` |
| [Runtime](https://github.com/banodoco/banodoco-workspace-runtime) | Corrected identity handoff | `70872d03ed56e6b6be608190c55e63b37bef3073` |
| Runtime | Historical checkpoint, not substitute for corrected handoff | `8ca859088b0d877306b967a7f59fa4c212fdce7f` |

Use each linked repository's HTTPS clone URL with `.git`, then check out the
selected exact commit into fresh isolated custody when delivery is authorized.
The previously reported `banodoco/banodoco-workspace-worker` URL does not
resolve; the verified worker repository is `banodoco/reigh-worker`.
The four recovered Astrid tip identities are in the adjudication; preserve
them offline during P0 rather than treating this host base as their replacement.

Product repository/ref requirements are in the ratified plan and provenance
records. Wan2GP and ComfyUI engine revisions, models, nodes, interpreter and
effective configuration still need the P0 composition census; do not replace
missing pins with moving latest versions. No model downloads are authorized.

Historical raw receipts and recovery archives are deliberately excluded from
this public plan closure. Their absence means historical acceptance and
remaining spend cannot be independently re-certified from this package alone.
P0 must recover the necessary evidence or record the gap before dependent
execution; copied planning records do not become product acceptance evidence.
