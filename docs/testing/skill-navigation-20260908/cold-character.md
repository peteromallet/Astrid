# Cold navigation trial: saved Astrid character, original file unavailable

Date: 2026-09-08

## Query

“Make another image of my saved Astrid character, keeping their appearance; I only have the saved reference, not its original file.”

## Navigation record

Files were read in this order:

1. `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/_core/skill/SKILL.md` — core route selection. It directs reuse of a saved subject to the References skill.
2. `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/references/skill/SKILL.md` — references lifecycle and the saved-media limitation.
3. `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/generation/skill/SKILL.md` — generation entry points and image input behavior.
4. `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/generation/executors/generate_image/skill/SKILL.md` — supported image modes and required inputs.

One path-resolution/discovery action (`readlink -f`) was used to resolve the checkout-relative References and Generation links. One attempted path read was a backtrack: the literal `astrid/references/skill/SKILL.md` path did not exist; the resolved target was then read successfully.

Counts:

- Unique documents read: 4
- File read actions: 4 successful reads
- Help/discovery actions: 1 path-resolution action
- Backtracks: 1 failed literal-path attempt
- Navigation actions: 5 successful route/read actions, plus the one recorded backtrack

No CLI help, runtime command, search, generation, or mutation was run.

## Usable plan and limitation

The supported plan would be: locate the character reference through the runtime (`media references list` / `show`), then generate an image in `i2i` or `edit` mode using the original local image path as `image_ref`, while retaining the runtime reference association for lineage.

The request cannot be completed from only the saved Astrid reference. The References skill states that the public media surface has no user-facing export/download route: `media show` returns metadata, while byte materialization is an attempt-host concern. It also states that `generation.generate_image` requires an existing absolute or invocation-relative image path for `i2i`/`edit`; a reference ID or media ID cannot be passed as `image_ref`. If only the managed media ID remains, the correct result is to report the typed limitation. No download, filesystem path, local cache, or other fallback is documented.

The generation skill confirms that `i2i` requires `image_ref`, and the executor skill confirms the same for both `i2i` and `edit`; therefore text-only generation would not preserve the saved character’s appearance.

## Evaluation

Navigation success: **successful**. Starting at the required core skill led to the relevant References route, then to the generation guidance and exact executor contract. The documented limitation was found without runtime probing or invented behavior.

Feature support: **unsupported with the stated inputs**. Astrid documents no user-facing way to turn a managed reference/media ID into the local image path required by generation. This is a product capability limitation, separate from navigation success.
