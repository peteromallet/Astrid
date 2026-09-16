---
name: astrid-setup
description: Set up Astrid on a new or existing machine, verify its Runtime connection, and help the user begin.
---

# Set up Astrid

Run this checklist in order to set up Astrid. Carry out the steps; do not merely describe them or hand the checklist back to the user. Mark a step complete only after checking its result. If a step is blocked, state why and continue only with independent steps. Never report blocked or skipped checks as passed.

- [ ] Inspect the machine and existing installation.
- [ ] Follow the manual guide to install missing components, configure Runtime, and provision the default sources.
- [ ] Sync the skills and confirm the user’s agent can read them.
- [ ] Run the basic setup checks and resolve failures.
- [ ] Check direct agent launch, reconnect, and authentication reuse where supported; record any limitation.
- [ ] Close with the verified ways to use Astrid, then ask what the person wants to make.

The closing choice comes last, after the checks. If only the current-agent route works, say so explicitly.

Read this file online before installation, then follow the linked manual guide. After cloning, use the checkout’s copy and resolve links relative to that file.

## Look first

Identify the operating system. This guide documents the macOS launcher; Linux and Windows have no validated setup route. Check for an existing Astrid installation, Runtime, and configuration. Preserve existing work and credentials.

## Follow the setup guide

Use [Set up Astrid](README.md) and its route for this machine. Reuse working components and install only what is missing.

Configure the workspace Runtime through the supported launcher. Use the same installation and configuration instructions as the manual path.

If the platform or a required setup step is unsupported or undocumented, explain the specific gap before proceeding.

## Sync and check the skills

After provisioning the default sources, run:

```bash
python3 -m astrid.skills.cli sync
python3 -m astrid.skills.cli sync --check
python3 -m astrid.skills.cli doctor --json
```

Confirm the user’s agent appears in the installation report and can read the core skill and a linked pack. Preserve existing instructions and intentional skill removals. Do not use `--force` to bypass a conflict. Follow the manual guide if the agent is not detected.

## Test the setup

Follow the [complete setup checks](README.md#6-check-the-complete-setup): command help, Runtime health, project listing, skill consistency, and actual skill discovery in the agent. Fix failures before reporting success. No paid generation is needed.

Test direct interactive launch separately: discover the supported command in the installed version, open the agent, confirm it can load Astrid skills and read the workspace, then close and reconnect. Do not count gateway help as agent launch. Preserve existing authentication; verify the selected agent supports reusing it without copying secrets. Do not assume an agent subscription supplies creative-provider API keys.

The inspected gateway does not establish a direct interactive launch path. If no supported command exists, report that specific limitation and continue through the current agent; do not invent a command or claim that test passed.

## Finish with a choice

Summarize the checks briefly. When direct launch and credential reuse have passed, give the tested command and explain that the person can launch Astrid directly using that agent’s supported existing sign-in, or keep using it here. Otherwise offer the verified current-agent route and name the direct-launch limitation.

Ask what they would like to make, then follow [Astrid’s core skill](../../astrid/packs/_core/skill/SKILL.md) and the relevant pack. Guide any additional credential entry locally.
