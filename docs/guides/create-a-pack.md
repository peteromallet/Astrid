# When and how to create a pack

Turn something useful into something reusable.

A pack groups tools, workflows, or visual elements with instructions for an agent to use them.

Create a pack when you have a tool or creative approach worth reusing. First check whether an existing pack already does the job; a one-off task does not need a new pack.

## Give it to your agent

```text
Help me turn this idea into an Astrid pack.
Start with Astrid’s Pack Builder skill, check what already exists,
then build and validate the smallest useful version.
```

[Open the Pack Builder skill →](../../astrid/packs/_core/skill/pack-builder/SKILL.md)

## Build it yourself

Choose the shape: an **executor** does one job, an **orchestrator** connects jobs into a workflow, and an **element** adds reusable visual behavior.

From an empty working folder, with Astrid’s environment active:

```bash
python3 -m astrid.core.pack.cli new my_pack
cd my_pack
```

Describe the pack in `pack.yaml`. Add the capability’s manifest and implementation, then explain when and how to use it in `skill/SKILL.md`.

Follow [Creating Astrid Packs](../packs/creating-packs.md) for the complete layouts and examples. Then validate:

```bash
python3 -m astrid.core.pack.cli validate .
```

Validation checks the pack’s structure; it does not install dependencies or prove its runtime behavior. Follow the authoring guide to register, discover, and try the capability in the intended environment.

[Choosing what to build](creating-tools.md) · [Pack contract](../packs/contract.md)

Have a useful finding rather than a reusable tool? [Contribute knowledge](contributing-knowledge.md).

[Back to Astrid](../../README.md)
