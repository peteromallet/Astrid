---
name: vibecomfy
description: >-
  Escape hatch. For standard image generation use the generate-image skill.
  Reach for vibecomfy directly when you need LoRAs, IP-adapter, controlnet,
  custom samplers, graph composition, or any path the registry does not cover.
---

# VibeComfy — the escape hatch

For standard image generation use the `generate-image` skill.  Reach for this
skill when you need LoRAs, IP-adapter, controlnet, custom samplers, graph
composition, or any path the registry doesn't cover.

`vibecomfy.run` is the **escape hatch** for generation features that fall
outside the basic happy-path contracts of `generation.generate_image` and
`generation.generate_video` (and the planned audio executor).  Use it directly for:

- **LoRAs** — attach custom weights to any node in the ComfyUI graph.
- **IP-adapter** — image-prompt / style-reference conditioning.
- **ControlNet** — depth, canny, pose, scribble, and other structural conditioning.
- **Custom samplers** — DPM++ 3M, UniPC, LCM, etc.
- **Exotic conditioning** — regional prompting, attention injection, CFG
  scheduling, and any other node-graph surgery not covered by the opinionated
  `generation.generate_image` contract.

The builtin image executor supports six canonical modes (`t2i`, `i2i`, `edit`,
`inpaint`, `outpaint`, `upscale`) across a growing Tier-1 model list.  Everything
beyond those modes — LoRAs, IP-adapter, ControlNet, custom samplers — belongs here.

## How to use

- `vibecomfy.run` maps to `python -m vibecomfy.cli run {workflow}`
- `vibecomfy.validate` maps to `python -m vibecomfy.cli validate {workflow}`

For Astrid tasks, list-shaped ComfyUI UI JSON remains on static UI ingestion and
needs no Python consent. A versioned VibeWorkflow envelope is validated through
the package's lossless envelope decoder, exact identity/round-trip checks, and
structural validation; its graph data remains authoritative and stored API
projections cannot replace it. Ambiguous, malformed, or inconsistent envelope
data fails closed. These static JSON paths do not execute Python or start
ComfyUI. A canonical Python/companion/source bundle requires the explicit
scalar `python_execution_consent="confirmed"`; that value is mapped to the
existing audited VibeComfy `--yes` gate. The `validation-report.json` artifact
records the validation authority/mode, consent value, and gate audit.

Install the executor packages before running these actions. Both executors
share the `vibecomfy` package environment via the folder-level `PACKAGE_ID`.

## Cross-links

- `docs/generation/` — modality contracts, manifest schema, feature list
- `astrid/packs/generation/skill/SKILL.md` — the `generate-image` skill (primary entry point)
- `astrid/packs/generation/executors/generate_image/STAGE.md` — the basic image executor
- `astrid/packs/generation/executors/generate_video/STAGE.md` — the basic video executor (Sprint 04)
- `docs/generation/30-image-contract.md` — image modality contract (all six canonical modes)
- `docs/generation/31-video-contract.md` — video modality contract (implemented Sprint 04)
- `docs/generation/32-audio-contract.md` — audio modality contract (spec-only)
