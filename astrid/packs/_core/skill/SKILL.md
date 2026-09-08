---
name: "astrid"
short_description: "Astrid — the file-based toolkit for making video, image, and audio art alongside a human."
description: "Use for Astrid orientation: connect to the workspace runtime, find or open project work, choose the creative-work route, and use Hivemind for shared knowledge."
---

# Astrid

Astrid is a client and pack toolkit for making creative work with a human.
The workspace runtime owns projects, media, timelines, tasks, runs, receipts,
and events. The checkout supplies the CLI, SDK, and capability packs; it is not
the product database or a second run store.

Choose the route by the requested result. Read only that route's guidance:

| Request | Start here |
| --- | --- |
| Find a project, inspect a run, or open a render | The CLI recipes below |
| Change timing, text, layout, or existing timeline clips, then render | [Timeline editing and rendering](../../rendering/skill/SKILL.md) |
| Generate images, video, or audio (including Foley); understand, assemble, compare, or publish work | [Creative work](creative-work/SKILL.md), then the relevant pack |
| Reuse a character or other saved subject | [References](../../references/skill/SKILL.md) |
| Build your own reusable tool, workflow, or visual element | [Pack builder](pack-builder/SKILL.md) |
| Find Banodoco advice, model settings, or workflow precedents | [Hivemind](../../hivemind/skill/SKILL.md) |

Using an existing workflow and building a reusable extension are different
requests: pack builder handles the latter, including deciding what to reuse.

## Start here

**Establish the current project when opening or switching project work.**
Discover the requested project with `projects list`, then persist it with
`projects select <project>` (workspace scope by default). Commands such as `runs open` use that selection without `--project`. Some
family parsers still require an explicit `--project`; check their help.
Use `projects current` when the user has not named a project. Use explicit
`--project` when the command requires it or when inspecting another project
without changing the current selection.

The persisted selection is the default for project-bound SDK invocations too:
an explicit project overrides it. Read-only Hivemind search and retrieval do
not need a selected project; they can run at workspace scope.

```bash
python3 -m astrid projects list
python3 -m astrid projects select <project>
python3 -m astrid runs open
```

`--json` is optional machine-readable output, not a required argument or input
payload. Use it when structured results help; ordinary commands and examples
for users can omit it.

On a new machine, follow the brief [getting started guide](../../../../docs/getting-started.md)
for Python, the runtime package, and the source manifest. Then check the
runtime:

```bash
python3 -m astrid doctor --json
```

If the runtime is not already configured, the explicit operator command is:

```bash
banodoco-local up --profile astrid
```

The gateway is the stable command surface. Begin with its census, then inspect
one family when needed:

```bash
python3 -m astrid --help
python3 -m astrid projects --help
python3 -m astrid timelines --help
```

The top-level families are `projects`, `timelines`, `media`, `tasks`, `runs`,
`doctor`, and `backup`. `timelines shots` and `media references` are nested
mounts. Packs and capabilities are invoked through the SDK, not as extra
gateway verbs.

## Find and open work

Use the runtime to discover work. Do not infer current state from checkout
filenames, modification times, a local database, or event-log files.

```bash
python3 -m astrid projects list --json
python3 -m astrid projects current --json
python3 -m astrid timelines list --project <project>
python3 -m astrid runs list --project <project>
```

To return to the latest successful render for a project:

```bash
python3 -m astrid projects select <project>
python3 -m astrid runs open
```

Use an exact run id when one is known. Use `--default-timeline` when the
request is to open the project's main/default timeline render, and
`--timeline <slug-or-id>` for another named timeline:

```bash
python3 -m astrid runs open <run-id>
python3 -m astrid runs open --default-timeline
python3 -m astrid runs open --timeline <timeline>
```

`runs open` selects a successful `rendering.render` run. It does not claim that
the render is editorially approved; the runtime has no separate promotion
pointer yet. If no matching render exists, the command fails clearly.

For paused work, include archived resources in discovery and recover through
the runtime:

```bash
python3 -m astrid timelines list --project <project> --include-archived --json
python3 -m astrid timelines recover <timeline> --project <project> --json
python3 -m astrid media references list --project <project> --include-archived --json
```

Use `timelines show`, `save`, `history`, `diff`, `visualize`, and `render` for
timeline work. Timeline editing and rendering conventions live in the
[rendering pack skill](../../rendering/skill/SKILL.md), which is the single
route for those operations. Use `tasks` and `runs` to inspect or manage
admitted work:

```bash
python3 -m astrid tasks list --project demo --json
python3 -m astrid runs show <run-id> --project demo --json --evidence
python3 -m astrid runs events <run-id> --project demo --json
```

For a failed run, start with `runs show --evidence`; if the failure detail is
empty, inspect `runs events`. Correct the reported cause before retrying, and
follow the runtime's retryability guidance. See
[debugging](../../../../docs/guides/debugging.md) for deeper diagnosis.

Every product command supports `--json` as its machine-readable surface. The
normal product result is an `ok` / `data` / `error` / `receipt` /
`idempotency_key` envelope. Exit code `0` means success, `1` a typed
runtime/SDK error, and `2` a usage or parse error.

## Shared knowledge: Hivemind

For community practice, model behavior, settings, known failures, and workflow
precedents, read the [Hivemind pack skill](../../hivemind/skill/SKILL.md).
Hivemind ships with Astrid by default. Use its search capability, then retrieve
the full source behind useful hits before presenting community advice.

The skill and executors belong to that pack. If the default pack or its skill is
missing, follow the pack's documented installation recovery; do not redirect to
an unrelated personal skill installation. Hivemind contributions are public;
preview the payload and obtain explicit publication authorization before writing.

## Runtime and SDK boundary

All live capability admission and lifecycle transitions cross the workspace
runtime. Use the SDK for packs.

Connect explicitly through the canonical launcher before invoking a pack:

```python
import json
from astrid.sdk import AstridClient

with AstridClient.open_from_launcher() as client:
    result = client.invoke_result(
        "hivemind.search",
        kind="executor",
        inputs={"query": "MiniMax H3 dialogue", "limit": 10},
        wait=True,
    )
    if result.ok:
        artifact = next(a for a in result.outputs["artifacts"] if a["name"] == "results")
        matches = json.loads(client.media.read_bytes(artifact["digest"]))
```

Check `result.ok` and the runtime result/artifacts. The module-level SDK
helper requires a connected `client`; importing `astrid.sdk` alone does not
connect or start a runtime.

Read the selected pack's `SKILL.md` and capability `STAGE.md` before invoking
work. Pass `kind` explicitly and bind execution to a project when the
capability contract requires it. Do not invoke `run.py` modules directly; do
not edit runtime state, receipts, or event streams by hand.

Capability discovery is available through `sdk.discover()`. A generated
[capability catalog](references/capabilities.md) is available when an exact id
is needed.

## Safety and ownership

Keep generated files under `runs/` or another ignored output directory. Do not
commit source media, rendered videos, local dependency environments, or
secrets. Runtime-owned media and timeline references must be changed through
the CLI/SDK. A route that the connected runtime does not expose returns a
typed `unavailable` result; do not fall back to a local store or invent a
second authority.

Resolve this skill's installed symlink before following checkout-relative links.
Creative work and pack builder are linked guidance within this core skill;
they do not introduce new runtime packs.
