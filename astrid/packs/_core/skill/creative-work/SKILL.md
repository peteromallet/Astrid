---
name: creative-work
description: Route requests to make, inspect, edit, render, or publish creative work to the existing Astrid pack skill that owns the operation.
---

# Creative work

Use this skill after [Astrid core orientation](../SKILL.md) when the user wants
an actual creative result. Choose the narrowest existing pack route, read that
pack's `SKILL.md`, then follow its capability and `STAGE.md` instructions.
When a pack names a capability without linking its contract, the usual source
path is `astrid/packs/<pack>/executors/<slug>/STAGE.md` (or
`orchestrators/<slug>/STAGE.md`), relative to the checkout root.
Packs own execution guidance; this skill does not duplicate their procedures or
create a new runtime pack.

## Route by intent

| User intent | Read and use | Typical entrypoints |
| --- | --- | --- |
| Generate an image, video, or audio asset from a prompt | [generation](../../../generation/skill/SKILL.md) | `generation.generate_image`, `generation.generate_video`, `generation.generate_audio` |
| Inspect, edit, validate, or run a ComfyUI/VibeComfy graph | [vibecomfy](../../../vibecomfy/skill/SKILL.md) | `vibecomfy.inspect`, `vibecomfy.edit`, `vibecomfy.validate`, `vibecomfy.run` |
| Understand or describe an image, audio clip, or video | [understanding](../../../understanding/skill/SKILL.md) | `understanding.understand`, `understanding.scene_describe` |
| Transcribe, detect scenes/shots, arrange clips, review, or validate editorial work | [editorial](../../../editorial/skill/SKILL.md) | `editorial.transcribe`, `editorial.scenes`, `editorial.shots`, `editorial.arrange`, `editorial.validate` |
| Trim or repair media, or search/download GIFs | [media](../../../media/skill/SKILL.md) | `media.clip_extract`, `media.speech_repair_lavasr`, `media.gif_search` |
| Assemble a production video, talk, thumbnail, logo grid, or image animation | [video editing](../../../video_editing/skill/SKILL.md) | `video_editing.hype`, `video_editing.event_talks`, `video_editing.thumbnail_maker` |
| Edit or render a timeline, or visualize timeline events | [rendering](../../../rendering/skill/SKILL.md) | `rendering.render`, `rendering.timeline_visualize` |
| Build an iteration video or compare experiment outputs | [iteration](../../../iteration/skill/SKILL.md) | `iteration.assemble`, `iteration.experiment_review` |
| Add sound to one short video clip | [fal](../../../fal/skill/SKILL.md), then [timeline editing and rendering](../../../rendering/skill/SKILL.md) for a finished video | `fal.fal_foley` produces audio; place it alongside the source video on a timeline and render |
| Make a spatial soundscape from video tiles | [foley](../../../foley/skill/SKILL.md) | `foley.foley_map` produces per-tile audio and a review viewer |
| Distill a long stream or event into reviewable clips | [stream content](../../../stream_content/skill/SKILL.md) | `stream_content.distill` |
| Build a training dataset or run LoRA training | [training](../../../training/skill/SKILL.md) | `training.dataset_build`, `training.training_run` |
| Render a standalone Blender scene or terminal screenplay | [blender](../../../blender/skill/SKILL.md) or [moirae](../../../moirae/skill/SKILL.md) | `blender.render`, `moirae.moirae` |
| Acquire or publish YouTube media | [youtube](../../../youtube/skill/SKILL.md) | `youtube.youtube_audio`, `youtube.upload` |

The complete discovered pack catalog is available in
[pack references](references/packs.md) when an exact route outside this table
is needed. Reusable characters, places, objects, logos, clothing, styles, and
layouts use the [references skill](../../../references/skill/SKILL.md), which
owns that workflow rather than this execution router.

## Execution shape

Most pack work is admitted through the SDK and belongs to a selected runtime
project. Use the exact qualified capability id, required `kind`, inputs, and
project binding from the selected skill and its `STAGE.md`. Inspect the
returned result, run evidence, and artifacts through the runtime; do not read a
local task store or call a pack's `run.py` directly.
Keep temporary and generated files under the output location required by the
selected pack, normally a project `runs/` tree.

## Hivemind before creative decisions

Search [Hivemind](../../../hivemind/skill/SKILL.md) before choosing an unfamiliar model, setting, workflow pattern,
or workaround. This is especially useful for ComfyUI/VibeComfy graphs,
generation settings, rendering failures, and known community solutions. Use
`hivemind.get_item` for the full evidence behind a useful result. Treat
retrieved advice as input to the selected pack, not as a replacement for its
current contract.

If the user asks to publish a finding, prepare a reviewable sanitized payload
and ask for explicit confirmation immediately before
`hivemind.contribute`. Never publish private paths, prompts, media, or URLs by
default.

## New capabilities

Do not invent a new pack merely to organize instructions. If the user wants a
new reusable pack or capability, follow the [pack-builder skill](../pack-builder/SKILL.md)
and keep execution routing here limited to existing pack skills.
