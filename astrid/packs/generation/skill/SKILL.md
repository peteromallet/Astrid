---
name: generation
description: >
  Generate images and videos from text prompts using the elegant
  `astrid.generate` facade.  Image, audio, and video generation route through
  the same runtime-owned executor code path. Covers generate_image, generate_video, and
  generate_audio, and generate_image_openai (executor-only).
---

# Generation

The generation pack provides a first-class **library facade** for image, audio,
and video generation and also exposes the underlying executors for direct (SDK)
and automation use.

## Quick-start — runtime-backed generation

Use the runtime-backed SDK generation facade. Successful managed calls return
runtime artifact references (digest, media type, size, and name); the runtime
owns durable storage and task/run state.

### Image

```python
import astrid.sdk as sdk

# Simplest: text-to-image in the selected runtime project
img = sdk.invoke(
    "generation.generate_image",
    kind="executor",
    project="demo",
    inputs={
        "model": "flux-schnell",
        "mode": "t2i",
        "execution": "cloud",
        "prompt": "a serene mountain lake at dawn",
    },
    wait=True,
)
img.outputs["artifacts"]  # runtime-published image artifact references
img.ok                    # True on success
```

Mode (`t2i` / `i2i`) and execution (`cloud` / `local`) are inferred when
possible (SD-002).  Pass them explicitly to override:

```python
# Image-to-image (image_ref triggers i2i inference); input files must be
# runtime-owned references or an admitted materialization.
img = astrid.generate.image(
    model="flux-dev",
    image_ref="./sketch.png",
    prompt="turn this into a watercolor painting",
    strength=0.7,
)

# Explicit mode + execution
img = astrid.generate.image(
    model="flux-dev",
    mode="t2i",
    execution="cloud",
    prompt="cyberpunk city",
    seed=42,
)
```

`execution` is the sole facade backend parameter.  The retired `backend`
spelling is rejected before invocation admission; an unavailable pair (for
example `model="flux-schnell", execution="local"`) fails with the valid
backend list and creates no run.

> **Note:** `edit`, `inpaint`, `outpaint`, and `upscale` always require an
> explicit `mode` argument — they cannot be inferred from inputs (SD-002).

### Video

```python
# Text-to-video (cloud)
clip = sdk.invoke(
    "generation.generate_video",
    kind="executor",
    project="demo",
    inputs={
        "model": "wan-2.2",
        "mode": "t2v",
        "execution": "cloud",
        "prompt": "a wave crashing on rocks",
    },
    wait=True,
)
clip.outputs["artifacts"]  # runtime-published video artifact references
```

### Audio

```python
# Audio currently has a cloud-only `music` route in the model catalog.
sound = sdk.invoke(
    "generation.generate_audio",
    kind="executor",
    project="demo",
    inputs={
        "model": "stable-audio-3-medium",
        "mode": "music",
        "execution": "cloud",
        "prompt": "a two-second gentle water splash",
        "duration": 2.0,
    },
    wait=True,
)
sound.ok
```

All three typed facades run the same read-only preflight before dry-run or
live admission.  It validates the model → mode → execution matrix and required
inputs.  In particular, `mode="flf"` requires both `image_ref` and
`image_end_ref`; a missing end frame is a typed `CapabilityMissingInputError`
and creates no run.  Local routes also require the VibeComfy/ComfyUI runtime;
the preflight reports an install command and never falls back to cloud.

```python
# Image-to-video
clip = astrid.generate.video(
    model="wan-2.2",
    mode="i2v",
    image_ref="./start_frame.png",
    prompt="continue this scene",
)
```

```python
# First-last-frame interpolation
clip = astrid.generate.video(
    model="wan-2.2",
    mode="flf",
    image_ref=["./first.png", "./last.png"],
)
```

### LoRA and extra params

All keyword arguments beyond the explicit parameter list pass through to the
executor unchanged:

```python
img = astrid.generate.image(
    model="flux-dev",
    prompt="a weathered fisherman, golden hour",
    loras="z-realgen-v2@1.1",      # registry id @ scale
    steps=28,
    guidance_scale=3.5,
)
```

### Output routing

Managed generation has one output route: an admitted runtime project. The
generic host writes to an attempt-local staging directory, publishes each
declared file to the runtime content-addressed store, and records the digest
and project relation in the runtime database. Staging paths are temporary.

```python
import astrid.sdk as sdk

result = sdk.invoke(
    "generation.generate_image",
    kind="executor",
    project="my-project",
    inputs={
        "model": "flux-schnell",
        "mode": "t2i",
        "execution": "cloud",
        "prompt": "test",
    },
    wait=True,
)
result.outputs["artifacts"]  # digest, media type, size, and name
```

Do not pass `out` with `project`, and do not invoke a generation `run.py`
directly. A custom filesystem destination is an explicit export operation
after runtime publication; it is not an executor default and must not create a
second unregistered output cache.

### Self-describing outputs

Every generated file carries its own provenance, so an image stays identifiable
after it is materialized from its runtime artifact reference:

- **PNG outputs** get the generation metadata embedded as `astrid_*` tEXt chunks
  (`astrid_prompt`, `astrid_model`, `astrid_model_actual` = the actual endpoint,
  `astrid_seed`, `astrid_request_id`, `astrid_created`, plus `astrid_loras` when
  used). Local (vibecomfy/ComfyUI) outputs additionally keep ComfyUI's own
  `prompt`/`workflow` chunks — both are preserved.
- The universal manifest is a receipt produced inside host staging; durable
  results are runtime artifact references and task/run evidence. Do not depend
  on a local run-directory sidecar after settlement.

Read embedded fields after materializing the runtime artifact with
`PIL.Image.open(path).text` or any PNG tEXt reader.

## Scratchpad convention

For experiments, use a selected runtime project and the SDK. This keeps
generation and registration together even when the script is launched from
another working directory:

```python
# my_experiment.py
import astrid.sdk as sdk

result = sdk.invoke(
    "generation.generate_image",
    kind="executor",
    project="my-project",
    inputs={
        "model": "flux-schnell",
        "mode": "t2i",
        "execution": "cloud",
        "prompt": "a glass teapot on basalt",
    },
    wait=True,
)
print(result.outputs["artifacts"])
```

```bash
python my_experiment.py
```

The runtime selection may be used instead of `project="my-project"`; the
working directory never determines ownership or output location.

## Plugin verbs

The `astrid.generate` namespace is extensible.  Packs can register additional
verbs under `extensions.generation.verbs` in their manifest.  Registered verbs
appear as `astrid.generate.<name>` and are resolved lazily — `import astrid`
does NOT eagerly load plugin modules.

```python
# After a third-party pack registers "animate":
import astrid
astrid.generate.animate(model="...", prompt="...")
```

The built-in `image` and `video` methods always take priority over plugin
verbs.

## Executors (direct access)

The pack's three executors remain available for direct use through the SDK
(`astrid.sdk.invoke(...)`) and for subprocess/cron automation.

| Executor | What it does |
|---|---|
| `generation.generate_audio` | Generate audio from text prompts via local or cloud backends; the current mode is `music`. |
| `generation.generate_image` | Generate images from text prompts via local (vibecomfy), cloud (fal), or Codex backends. v2: model→mode→backend taxonomy with a required `mode` input. Supports t2i, i2i, and edit modes. |
| `generation.generate_video` | Generate videos from text prompts via local or cloud backends. v2: model→mode→backend with t2v, i2v, and flf (first-last-frame) modes. |
| `generation.generate_image_openai` | Generate image files with OpenAI GPT Image models from a prompt file. Requires `OPENAI_API_KEY`. |

> **⚠️  `generate_image_openai` is executor-only for this sprint.**
> The `astrid.generate.image()` facade explicitly rejects
> `execution="openai"` with a diagnostic pointing to
> `generation.generate_image_openai`.  Direct executor access via the SDK is
> the supported path for OpenAI image generation.

For detailed image generation guidance — mode selection (t2i/i2i/edit),
model decision tree, drop-with-warning behavior, and escape hatches — see
the executor-level skill at
`astrid/packs/generation/executors/generate_image/skill/SKILL.md`.

### Quick-start (SDK)

Pass every declared input as a snake_case entry in `inputs` (each is forwarded
to the executor's `run.py` as a `--kebab-case` flag). Bind a runtime project;
the host supplies its private staging `out` value.

```python
import astrid.sdk as sdk

# Image from text (cloud, fast)
result = sdk.invoke("generation.generate_image", inputs={
    "model": "flux-schnell", "mode": "t2i", "execution": "cloud",
    "prompt": "a serene mountain lake at dawn",
}, project="demo", wait=True)

# Image from text (local, open model)
result = sdk.invoke("generation.generate_image", inputs={
    "model": "z-image", "mode": "t2i", "execution": "local",
    "prompt": "a serene mountain lake at dawn",
}, project="demo", wait=True)

# Video from text (cloud)
result = sdk.invoke("generation.generate_video", inputs={
    "model": "wan-2.2", "mode": "t2v", "execution": "cloud",
    "prompt": "a wave crashing on rocks",
}, project="demo", wait=True)

# OpenAI image generation from a prompt file
result = sdk.invoke("generation.generate_image_openai", inputs={
    "prompts_file": "./prompts.jsonl",
}, project="demo", wait=True)
```

## When to use

- Use `astrid.generate.image(...)` for standard image generation from text
  prompts (the recommended primary entry point).
- Use `astrid.generate.video(...)` for video generation from text or image
  prompts.
- Use `generation.generate_image_openai` via direct executor access (the
  SDK) when you specifically need OpenAI GPT Image models and have a prompt
  file ready.

For LoRAs, IP-adapter, controlnet, custom samplers, or graph composition,
use the `vibecomfy` skill instead (escape hatch).

## Credentials

| Env var | Used by |
|---|---|
| `FAL_KEY` | generate_image (cloud), generate_video (cloud) |
| `OPENAI_API_KEY` | generate_image_openai |

Set these in the process environment, or in a `.env` / `.env.local` file at the
repo root (both are searched; `.env.local` is gitignored and wins over `.env`).
The resolver also walks `~/.env` and a few workspace locations — see
`astrid.core.util.secrets.candidate_env_files`.
