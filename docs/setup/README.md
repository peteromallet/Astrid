# Set up Astrid

Install once. Then tell your agent what you want to make.

The current local launcher targets **macOS**. Linux and Windows setup have not yet been validated; this guide does not claim support for them.

## 1. Install

You need Git and Python 3.11 or newer. Check them in Terminal:

```bash
git --version
python3 --version
```

Use a new folder for this installation. If you already have Astrid, keep that installation and begin with [checking it](#3-check-your-workspace).

```bash
mkdir astrid-local
cd astrid-local
git clone https://github.com/peteromallet/Astrid.git
git clone https://github.com/banodoco/banodoco-workspace-runtime.git Runtime
git -C Runtime checkout bc74a4b2179de83ace55c35fa6371f10e1e58610
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e ./Astrid -e ./Runtime
```

These commands use the Runtime revision pinned in this version’s [Getting Started reference](../getting-started.md). Use a matched release pair when one is supplied; do not mix an existing installation with unrelated development revisions.

## 2. Connect Runtime once

From the same `astrid-local` folder, create the source manifest. This records where the two checkouts and their Python environment live; it contains no secrets.

```bash
python3 - <<'PYTHON'
import json
from pathlib import Path
root = Path.cwd().resolve()
manifest = root / "astrid-source-profile.json"
with manifest.open("x") as output:
    json.dump({
        "profile": "astrid",
        "source_checkout": str(root / "Astrid"),
        "runtime_checkout": str(root / "Runtime"),
        "runtime_environment": str(root / ".venv")
    }, output, indent=2)
PYTHON
banodoco-local up --profile astrid --source-manifest "$PWD/astrid-source-profile.json"
```

This is a one-time configuration for this installation. The launcher starts or reconnects to Runtime, creates the local connection credentials, and retains the source profile for later use. Keep the checkouts and environment in place; repeat configuration only if those paths or the installation change.

## 3. Check your workspace

```bash
python3 -m astrid doctor --json
python3 -m astrid projects list --json
```

Both commands should succeed. A new workspace may have no projects yet. If either fails, follow [Troubleshooting](troubleshooting.md).

## 4. Add the default knowledge pack

From the Astrid checkout, using the same environment:

```bash
cd Astrid
python3 -m astrid.setup
python3 -m astrid.setup --check --offline
```

Setup provisions the default Hivemind source. Searching its community knowledge requires an internet connection.

## 5. Sync your agent’s skills

```bash
python3 -m astrid.skills.cli sync
python3 -m astrid.skills.cli sync --check
python3 -m astrid.skills.cli doctor --json
```

Sync installs the core skill and its pack navigation into detected supported agents: Claude Code, Codex, and Hermes. Individual pack links are optional (`sync --deep`). Keep existing user instructions; do not use `--force` to replace conflicting files.

Check the install report for the agent you use. If it was not detected, use the [skills installation guide](../guides/skills-install.md). If the agent requires a new session to discover skills, open one and check that it can read Astrid’s core skill and follow a pack link.

## 6. Check the complete setup

- `python3 -m astrid --help` opens the command help.
- `python3 -m astrid doctor --json` and `projects list --json` succeed.
- Skill sync reports no drift, and the skills doctor succeeds.
- Your agent can find the core skill and a linked pack skill.

For a direct interactive launcher, also verify that launching Astrid actually opens an agent, that the agent can load the skills and read the workspace, and that closing and reopening it reconnects successfully. CLI help alone does not pass this check.

The inspected source exposes the Astrid command gateway; a direct interactive-agent launch command and its authentication reuse are not yet verified. Until they are, use Astrid through your existing agent and keep its existing sign-in. That sign-in does not automatically supply credentials to every creative provider.

## 7. Choose how to continue

Once the checks pass, your setup agent should tell you what is ready and ask what you want to make.

If direct agent launch and authentication reuse both passed, it should offer:

> Astrid is ready. You can launch it directly with the verified command and use the existing sign-in supported by that agent, or keep using Astrid here. What would you like to make?

Include the actual tested launch command and agent name. If that path is unavailable, say simply:

> Astrid is ready to use here through your current agent. Direct agent launch is not verified in this version. What would you like to make?

[How Astrid works](../guides/how-it-works.md) · [Credentials](credentials.md)

## Come back later

You do not need to recreate the manifest or credentials. From your `astrid-local` folder:

```bash
source .venv/bin/activate
banodoco-local up --profile astrid
python3 -m astrid projects list
```

[Credentials](credentials.md) · [Troubleshooting](troubleshooting.md) · [Back to Astrid](../../README.md)
