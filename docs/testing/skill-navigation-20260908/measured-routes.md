# Astrid expanded skill navigation — measured warmed traversal

Date: 2026-09-08. This is a second traversal after the earlier navigation
audit, so it is warm-context evidence, not a cold new-user measurement. For
each query I actually reopened the core skill, then opened only the listed
linked guidance and ran only the listed `--help` command(s). No runtime
discovery, SDK invocation, generation, render, open, upload, external search,
or mutation was performed in this traversal. “Discovery” therefore means live
runtime/SDK discovery calls; all rows are 0. A document action is one
successfully read file; a help action is one executed help command.

## Per-query measurements

| # | Document opens | Help calls | Discovery | Backtracks | Outcome / shortest supported route |
|---:|---:|---:|---:|---:|---|
| 1 | 2 | 1 | 0 | 0 | **Success.** Core + rendering; `runs open --help`. Use `runs open --project <project> --default-timeline` after runtime discovery. Evidence: `astrid/packs/_core/skill/SKILL.md:61-80`, `astrid/packs/rendering/skill/SKILL.md:80-96`. |
| 2 | 2 | 1 | 0 | 0 | **Partial.** Core + getting-started; `projects --help`. Install/configure manifest, run `doctor`, start with `banodoco-local up --profile astrid` if needed, then create/list. Evidence: `docs/getting-started.md:8-58`; actual create was intentionally not invoked. |
| 3 | 2 | 1 | 0 | 0 | **Success.** Core + rendering; `timelines recover --help`. List with `--include-archived`, then `timelines recover <ref> --project <project> --json`. Evidence: `astrid/packs/_core/skill/SKILL.md:82-89`; parser accepts refs from archived list (`astrid/packs/timeline/cli.py:575-583`). |
| 4 | 2 | 2 | 0 | 0 | **Success with caveat.** Core + debugging; `runs show --help` and `runs retry --help`. Inspect `runs show --evidence`, then `runs events`; retry only after the error’s recovery condition permits it. Evidence: `docs/guides/debugging.md:44-70`, `docs/guides/cli-journeys.md:318-374`. |
| 5 | 2 | 1 | 0 | 0 | **Success as plan.** Core + rendering; `timelines visualize --help`. Use `timelines visualize --project <project> --timeline-slug <ref> --format md,png,svg --layout both --filmstrip off --json`; do not pass `--out`. Evidence: `astrid/packs/rendering/skill/SKILL.md:36-47`, `astrid/packs/timeline/cli.py:600-644`. |
| 6 | 3 | 1 | 0 | 0 | **Success.** Core + image-generation skill + image executor stage; `tasks --help`. Use SDK `generation.generate_image` with explicit model/mode/execution/prompt, or admit `generation.generate_image` as a task and inspect runs. Evidence: `astrid/packs/generation/executors/generate_image/skill/SKILL.md:10-31`, `.../STAGE.md:1-20`. |
| 7 | 2 | 1 | 0 | 0 | **Partial / constraint failure.** Core + references skill; `media references --help`. The opened guidance explicitly says `generation.generate_image` does not accept a managed reference/media id as `image_ref`; it requires an actual image path for i2i/edit. Therefore “variant saved character only reference id, no original” has no supported endpoint in this trace (`astrid/packs/references/skill/SKILL.md:44-58`). |
| 8 | 2 | 2 | 0 | 0 | **Success as documented plan.** Core + rendering; `timelines save --help` and `timelines render --help`. Read `show`, merge the title hold +2 into the complete config, save with observed `--expected-version`, then render the same timeline with version pinning. Evidence: `astrid/packs/rendering/skill/SKILL.md:49-86`. No mutation was performed. |
| 9 | 3 | 1 | 0 | 0 | **Partial.** Core + editorial skill + transcribe stage; `tasks --help`. The route is transcribe → scenes/quote scouting/clip candidates → inspect/select clips; no single endpoint for “find announcement clips” was established in the five-action cap. Evidence: `astrid/packs/editorial/executors/transcribe/STAGE.md:1-20`; requires capability discovery or the editorial pack catalog for exact input schemas. |
| 10 | 2 | 1 | 0 | 0 | **Navigation failure / wrong router.** Core + Comfy wrapper skill; `tasks --help`. The question asked for a Banodoco recommendation, which should have routed through the Hivemind skill. I opened `comfy_wrap` instead; the VibeComfy inspect/edit/validate/run plan is useful only for the separate run portion. No recommendation was established. |
| 11 | 3 | 1 | 0 | 0 | **Navigation failure / wrong router.** Core + rendering skill + generation skill; `timelines --help`. “Reusable animated title” should have routed to pack-builder/element authoring. I skipped that router and inferred a generation/render plan, so no supported reusable-title endpoint was established. Core’s extension handoff is at `astrid/packs/_core/skill/SKILL.md:107-110`. |
| 12 | 3 | 1 | 0 | 0 | **Navigation failure / wrong router.** Core + video-editing skill + transcribe stage; `tasks --help`. The request was to create a reusable pack, but I routed to the `video_editing.hype` user pipeline. The opened route describes a run pipeline, not pack authoring; pack-builder was required and was skipped. |
| 13 | 3 | 1 | 0 | 0 | **Success at SDK capability level.** Core + iteration skill + experiment-review stage; `tasks --help`. Use experiment_import → experiment_prepare → experiment_review for a static gallery, or experiment_review_session for interactive review. Evidence: `astrid/packs/iteration/skill/SKILL.md:29-64`. |
| 14 | 3 | 1 | 0 | 0 | **Partial / likely wrong route.** Core + Foley skill + fal Foley stage; `tasks --help`. I found the spatial `foley_map` route, but the request was Foley for one finished short video; the opened route is a tile/VLM/spatial viewer pipeline, not proof of a single-video Foley endpoint. Exact single-video route was not established. |
| 15 | 3 | 1 | 0 | 0 | **Partial.** Core + YouTube skill + upload stage; `tasks --help`. `youtube.upload` is the likely publisher, but the request requires a reachable URL. The trace did not establish whether upload returns/accepts the required URL or what exact input manifest/metadata is required. Publication was not performed. |

## Chronological action trace

The second traversal ran in this order. Every row begins by reopening the core
skill; the remaining entries are the successful file reads/help calls for that
query.

1. Q1: core → rendering skill → `runs open --help`.
2. Q2: core → getting-started → `projects --help`.
3. Q3: core → rendering skill → `timelines recover --help`.
4. Q4: core → debugging guide → `runs show --help` → `runs retry --help`.
5. Q5: core → rendering skill → `timelines visualize --help`.
6. Q6: core → generation image skill → image `STAGE.md` → `tasks --help`.
7. Q7: core → references skill → `media references --help`.
8. Q8: core → rendering skill → `timelines save --help` → `timelines render --help`.
9. Q9: core → editorial skill → transcribe `STAGE.md` → `tasks --help`.
10. Q10: core → Comfy wrapper skill → `tasks --help` (**shortcut; should have routed to Hivemind for the Banodoco recommendation**).
11. Q11: core → rendering skill → generation skill → `timelines --help` (**shortcut; should have routed to pack-builder for reusable authoring**).
12. Q12: core → video-editing skill → transcribe `STAGE.md` → `tasks --help` (**shortcut; should have routed to pack-builder for pack creation**).
13. Q13: core → iteration skill → experiment-review `STAGE.md` → `tasks --help`.
14. Q14: core → Foley skill → fal Foley `STAGE.md` → `tasks --help`.
15. Q15: core → YouTube skill → upload `STAGE.md` → `tasks --help`.

Totals for this measured traversal: 37 document opens, 17 help calls, 0 live
discovery calls, and 0 backtracks. These are observed actions in a warmed
session; they are not cold-user minimums and do not include the earlier audit’s
runtime discovery calls.

The main limitations are deliberate: no live data was needed for the second
pass, and mutating/publishing endpoints were documented but not executed. Q7,
Q9, Q10, Q11, Q12, Q14, and Q15 are partial or failed routes. Q10–Q12 are
agent navigation deviations: the measured trace is preserved, but each skipped
the router that the user’s intent required.

## Integrity and current hashes

I did reopen the current checkout’s core file at the start of every numbered
query using `sed`; the paths were under
`/Users/peteromalley/Documents/reigh-workspace/Astrid`, not another checkout.
The traversal did not record hashes at execution time. The following are
current hashes calculated afterward, explicitly not historical hashes:

| Current file | SHA-256 (current) |
|---|---|
| `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/_core/skill/SKILL.md` | `bb1f59b35dbbded16b6d3bd93507aa2a262064e6288c40ff6bbd4f48efa4679e` |
| `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/rendering/skill/SKILL.md` | `8411ae85ad8a04fb7e4d906483c4ae324415002f119909a426f49d2bed7bdf27` |
| `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/references/skill/SKILL.md` | `318084b573c2bcc8b4b512140099783faba49a9b3012ef4b41431aec1af08974` |
| `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/comfy_wrap/skill/SKILL.md` | `0139d3800c93439e6ef46d3d04c4e241fb2e9b2410101c9e6a1b74cf679260c9` |
| `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/video_editing/skill/SKILL.md` | `00f88bebf1752fdc948cceaf51540e65ff554766c67944655a5ff250025aac2e` |
| `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/foley/skill/SKILL.md` | `26acf1be87615234c98db9e5ffce00850170bd68d905b1a97bb3350ba02b64cb` |
| `/Users/peteromalley/Documents/reigh-workspace/Astrid/astrid/packs/youtube/skill/SKILL.md` | `8b85cbbead0b007fb6575f898960f16cdf8e85f13526398ce55f755ccdbb9a55` |
