# Contributing knowledge

Share something useful so the next person—and their agent—can build on it.

Astrid uses [Hivemind](https://github.com/banodoco/hivemind) for shared knowledge. You can add a resource, improve an existing one, or contribute evidence from something you tried.

## Give it to your agent

```text
Help me contribute this to Hivemind.
Read the Hivemind skill, check what’s already there,
and prepare a resource, revision, or piece of evidence.
Show me the draft before publishing it.
```

[Open the Hivemind skill →](https://github.com/banodoco/hivemind/blob/main/skill/SKILL.md)

## Add a resource

Bring an article, workflow, transcript, or practical guide. Include its origin and enough context to understand what it is useful for. Search first: a different method deserves a new resource; an improvement to the same method belongs in a revision.

The contribution action is `submit-resource`. Adding a resource does not configure an ongoing feed or crawler.

## Suggest an edit

Find the resource and read its current accepted revision. Prepare a complete updated version with `propose-revision`, referencing that exact base revision. Explain what changed and preserve its sources.

Your proposal does not overwrite the accepted version. It becomes current only after acceptance. See the [contribution playbook](https://github.com/banodoco/hivemind/blob/main/skill/SKILL.md#contribution).

## Share what you tried

Contribute **evidence** with the `evidence` action. Its basis describes where the claim comes from:

- **Observed:** something you tested or witnessed yourself.
- **Reported:** something a source says happened.

For an experiment, record the model and version, settings, conditions, what you changed, and the result—including failures. Attach relevant outputs or source links and identify the exact resource revision the evidence concerns. Keep conclusions as narrow as the test supports.

These are evidence labels, rather than a separate “experiment” contribution type. The [contribution command](https://github.com/banodoco/hivemind/blob/main/executors/contribute/run.py) defines the supported fields.

## Review and contribute

Your agent checks the installed Hivemind version, prepares the appropriate submission, and previews it with `--dry-run`. Review the content before authorizing publication. For the current Astrid integration, run `astrid login` and approve the browser flow, then check `astrid status`. The contributor credential is stored locally; never paste it into chat. See [Contributor login](../getting-started.md#optional-hivemind-contributor-login) for details and troubleshooting.

Keep the returned resource, revision, or evidence ID so you can find and improve the contribution later. If your installed version lacks these actions, keep the draft locally until a compatible version is available.

[How Astrid works](how-it-works.md) · [Create a pack](create-a-pack.md) · [Get help](../setup/troubleshooting.md)

[Back to Astrid](../../README.md)
