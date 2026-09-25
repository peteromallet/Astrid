# Remote-machine handover

Copy this message after replacing the bracketed fields with verified values.

## Source

- Project: `[project name]`
- Clone or safe existing-checkout update: `[command]`
- Project ref and exact SHA: `[branch/tag]` / `[40-char SHA]`
- Plan entrypoint: `[portable path to START-HERE.md]`
- Current phase and state: `[phase]` / `[state]`
- Megado source URL and exact SHA: `[URL]` / `[40-char SHA]`
- Publication destination and visibility: `[remote/repository]` / `[public unless explicitly changed]`
- Receiving mode: `[planning_only | delivery]`
- Finish authorization: `[package only | normal push | receiving agent creates PR after implementation and validation]`

## Objective and authority

Objective: `[what the recipient must accomplish]`

Authority: `[user/instruction that authorizes this phase]`. Preserve the
selected boundaries, prior decisions, history, and counters. Roles, stages,
budgets, and mode come from `[path to run.yaml]`; do not duplicate them here.
Do not infer merge, deploy, cutover, publication visibility, or a PR unless the
finish authorization says so.

Prerequisites and unresolved items: `[tools, models, credentials, access, or
unknowns]`. The receiving agent reports missing capabilities explicitly.

## Start on a fresh machine

```sh
git clone --branch [project branch] [project URL] [project directory]
git clone [skills URL] ~/.local/share/poms-skills
mkdir -p ~/.codex/skills
if [ ! -e ~/.codex/skills/megado ] && [ ! -L ~/.codex/skills/megado ]; then ln -s ~/.local/share/poms-skills/megado ~/.codex/skills/megado; fi
if [ ! -e ~/.codex/skills/megado-handover ] && [ ! -L ~/.codex/skills/megado-handover ]; then ln -s ~/.local/share/poms-skills/megado-handover ~/.codex/skills/megado-handover; fi
```

If a path already exists, inspect it and update only with an authorized
no-overwrite procedure. Agents without Codex can read
`~/.local/share/poms-skills/megado/SKILL.md` directly. Read Megado, then
`[project directory]/[START-HERE path]`, and verify the recorded SHAs and all
prerequisites before acting.

## Execution

The captured run is `[planning_only|delivery]`. For delivery, transition the
accepted mode in `run.yaml` as its schema requires, preserving its configured
roles, stages, budgets, counters, and boundaries; then execute `[authorized
stages/tasks]`. For planning-only, package and report without product
execution. Missing models, tools, or real review packets must be reported
explicitly; do not silently substitute or claim proof from a plan.

Finish: `[package only | normal push and verification | receiving agent creates PR after implementation and validation]`.
If PR creation is authorized, target `[remote]` and base `[branch]`; the
receiving agent reports the PR URL and evidence after implementation and
validation, then stops before merge/deploy/cutover unless separately
authorized. Return unresolved prerequisites and risks with the final artifact.
