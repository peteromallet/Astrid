# Handover provenance

## Astrid source

- Repository: `https://github.com/peteromallet/Astrid.git`
- Handover branch base: `cebd5f3b8982e785ed56973d132e8019ecc1cdbf`
- Parent of candidate: `0c852b7748f9f519413ec96f037b04b3d90e70a2`
- Handover branch: `handover/astrid-default-packs-and-skills-20260908`
- Base branch: `main`

Clone without overwriting an existing checkout:

```bash
git clone --branch handover/astrid-default-packs-and-skills-20260908 \
  https://github.com/peteromallet/Astrid.git Astrid-handover
```

Direct-read fallback:

```bash
git fetch origin handover/astrid-default-packs-and-skills-20260908
git show origin/handover/astrid-default-packs-and-skills-20260908:docs/handovers/astrid-default-packs-and-skills/README.md
```

## Megado skill

- Repository: `https://github.com/peteromallet/poms-skills.git`
- Inspected skill revision: `ef42515942adfb1683cde4b7b2d53d4e56dbe25e`
- Relevant files: `megado/SKILL.md` and `megado-handover/SKILL.md`

No overwrite install:

```bash
git clone https://github.com/peteromallet/poms-skills.git poms-skills-handover
git -C poms-skills-handover checkout --detach ef42515942adfb1683cde4b7b2d53d4e56dbe25e
```

Direct-read fallback:

```bash
git fetch https://github.com/peteromallet/poms-skills.git \
  ef42515942adfb1683cde4b7b2d53d4e56dbe25e
git show FETCH_HEAD:megado-handover/SKILL.md
```

## Upstream Hivemind dependency

- Repository: `https://github.com/banodoco/hivemind.git`
- Inspected source revision: `abe41fdf72df3bbcfe45087eae64ccf50a1bb809`
- CLI handoff provenance: `52e6e357aeba15861b6237b2fa6dd48af2e0a607`
- Status: pending valid canonical v2 manifest/release pin and live acceptance.

Do not substitute the CLI provenance commit for the missing v2 release pin.
