---
name: h3-av
description: Request-driven MiniMax H3 audiovisual transformations with explicit video/audio scopes, references, and approval evidence.
---

# H3 audiovisual transformations

Use `h3_av.transform` when the desired result is a generated or edited H3
video/audio candidate. The agent writes one request document; the pack resolves
assets and time ranges, compiles the selected H3 workflow, optionally executes
it through `vibecomfy.run`, composes protected material, and emits verification
evidence. The pack is an abstraction over the existing H3 workflow, not a new
media database or scheduler.

This is the one canonical path:

```text
request → prepare → compile → validate → run → compose → verify → final receipt
```

The `validate` stage checks canonical bundle and graph structure offline, with
explicit Python consent. Its `canonical_bundle_structural` report defers runtime
and target-schema checks to `vibecomfy.run`; it does not establish runtime
readiness. The run adapter verifies its attested Comfy session and fresh target
schemas before queueing. Validation must not start a second Comfy server.

Do not submit a second hand-written VibeComfy task for the same request. The
orchestrator owns the stage order and carries the resolved request, asset
digests, workflow identity, task/attempt identity, and output evidence across
the stages.

The parent accepts a local request and asset-map document. Before submitting
its first child, it normalizes the request, bundles exactly its declared source,
references and video/audio masks, verifies member hashes, and imports the request,
bundle and, when present, frozen source through Runtime media storage. Each child receives
managed object descriptors and materializes its own inputs. Prepare publishes
portable member identities; compile receives the same bundle. Compose publishes
the candidate bytes separately from its evidence JSON, and verify receives those
bytes explicitly. No worker needs access to the caller's filesystem or another
attempt's directory. Deploying pack source does not transfer task assets.

Direct managed executor calls require imported Runtime objects on every declared
file port. A local pathname is rejected before task creation with an import
instruction; GenericPackHost also rejects it before child launch. Only declared
ports and the H3 request's asset fields are interpreted, never arbitrary strings
inside JSON. An orchestrator `dry_run` previews dispatch only: it does not prove
asset transfer. The CPU transport regression in
`tests/packs/h3_av/test_runtime_contract.py` exercises real H3 stages with separate
directories and removes each preceding attempt before continuing.

## Request shape

Start with `schemas/request.v1.json` or the following compact shape:

```yaml
version: 1
operation: edit # edit | continue | generate
source:
  asset: speaking-shot.mp4
  range: [0.0, 4.0]
output:
  duration: 8.0
content:
  prompt: >-
    End state: the speaker remains in the same seated composition and begins
    with the exact line "This is your last chance." Then say the requested
    replacement line. Preserve the original voice and room perspective.
changes:
  video:
    - during: [4.0, 8.0]
      area: {full_frame: true}
      action: generate
  audio:
    - during: [4.0, 8.0]
      action: generate
      dialogue: "The replacement line."
references: []
overrides:
  steps: 8
  seed: 42
```

The machinery supplies defaults for `version: 1`, `operation: edit`, empty
references, empty overrides, 24 fps H3 preparation, the packaged graph/model,
and the graph's default sampler, steps, guidance, resolution, and audio
settings. Put a field in the request only when the creative intent or an
explicit quality override differs from those defaults. The request must still
state the source interval for edit/continue, output duration, prompt/dialogue,
and every changed video/audio interval. Runtime target, asset hashes, source normalization,
workflow filenames, timeout limits, and cleanup ownership are machinery
contracts—not creative request fields.

`during` uses zero-based, half-open seconds on the output timeline. A missing
`changes` list means preserve source material. References are an ordered list
and may be empty; the selected workflow advertises its actual reference
capacity in the compiled manifest rather than silently discarding extras.
The current continuation workflow supports up to two image references; the
edit workflow has no reference-image input. Source-free generation supports
one to nine ordered still-image references. Unsupported counts fail admission
or compilation.
Do not add request-level reference strategies or fixture-specific production
workflows to bypass these limits.

For source-free reference-guided generation, use the same `h3_av.transform`
entrypoint with `operation: generate`, omit `source`, supply `output.duration`,
and leave both change lists empty. This creates the entire audiovisual timeline.
The compiler builds one ordinary `MiniMaxH3ReferenceToVideo` sampling graph with
one muxed output. It never treats reference count as a segment count or adds
implicit first/last keyframes. References are numbered `<Picture 1>` through
`<Picture N>` in list order; use these tags in the prompt when their roles matter.

```yaml
version: 1
operation: generate
output: {duration: 15}
content:
  prompt: "The subject in <Picture 1> moves through the setting in <Picture 2>."
changes: {video: [], audio: []}
references:
  - {asset: subject.png, purpose: appearance}
  - {asset: setting.png, purpose: style}
overrides: {steps: 8, seed: 42}
```

The general adapter accepts 1..9 still images (including four), frame-aligned
durations of 5..362 frames at 24 fps, and the existing model/steps/seed/sampler/
guidance overrides. Here `guidance` controls the existing turbo LoRA strength;
it is not classifier-free guidance. Default resolution is 1024×576. A 15-second
request samples 362 native frames and deterministically trims two frames and
the matching audio tail to deliver 360 frames. Media filenames are managed run
bindings, never graph defaults or caller/worker filesystem dependencies.

This adapter does not yet support video/audio references, timed keyframes, or
source-free masks/preservation schedules. Those requests fail before GPU work.
Its CPU bundle and transport tests do not establish live GPU acceptance or
visual quality; target attestation and a live run remain separate gates.

## Mask semantics

Use a full-frame region, a supplied mask asset, a geometry region, or an
explicit semantic target. The preparation stage keeps three truths separate:

1. requested scope — what the user asked to change;
2. delivery permissions — the exact video frames/audio intervals allowed to
   change; and
3. expanded sampling scope — any larger latent/context area the H3 graph needs.

Expanded H3 context must never expand the final composition permission. A
semantic or tracked region without a supplied mask is marked
`requires_resolution` and cannot be claimed as pixel-accurate until the
resolver supplies a mask. Audio intervals are independent of video intervals;
“voice only” requires a real stem/separation input and is not inferred from a
video mask.

For native continuation, the protected prefix is authoritative and the
generated suffix is explicit. For continuation plus a spatial mask, provide a
suffix baseline or an explicit policy; the compiler never silently freezes the
last frame.

## Workflow choice

- Use this H3 extension workflow when pose/camera can vary within the declared
  end state and audiovisual continuation is the main goal.
- Use the existing in-painting workflow/guide when exact body position or
  frame identity must be preserved. That route supplies a preservation mask to
  the in-paint graph instead of asking continuation to reproduce it.

## Validation and approval

Run preparation and compilation before any GPU submission. The compiler emits
the exact request digest, asset bindings, graph capacity, and resolved mask
schedule. `h3_av.verify` checks that generated outputs exist and that protected
intervals/regions have not been claimed as changed. A passing runtime model
check is not editorial approval; review the candidate and evidence separately.

The sealed compilation's `capabilities.public_generation` supplies the
`generation_intent` for the canonical run. Each supported route
declares one public video selector (`main-0`, ordinal 0); separate edit audio
remains an input to composition. Retrieve outputs and the composed candidate
through Runtime managed media, verifying their size and hash locally. Worker
paths or manually copied files do not establish managed retrieval.

Use the existing RunPod lifecycle guide for the pinned H3 CUDA-13 target and
submit through the canonical Astrid task/runtime path. Keep raw worker output,
composed output, and verification evidence together for review.

The worker must fail before registration when its configured source checkout
digest does not match the launcher's digest, or when a required exact target is
missing or malformed. Its readiness marker records the normalized target,
target digest, source checkout digest, source inventory identity, and boot
manifest hash. A target claim is not evidence that the worker is attached to
the intended machine; the startup attestation and the Runtime binding must
agree.

The final receipt deliberately separates four facts:

```text
task_succeeded → candidate_verified → editorially_approved → cleanup_verified
```

Successful execution and technical verification do not imply editorial
approval or resource cleanup. When a resource is owned, the cleanup receipt
must list its exact kind/id, expected postcondition, observed postcondition,
and verification result. A network volume that must be preserved is recorded
as a non-owned resource with its preservation postcondition; it is never
silently treated as part of pod deletion.
