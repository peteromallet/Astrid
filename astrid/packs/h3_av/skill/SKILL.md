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

## Request shape

Start with `schemas/request.v1.json` or the following compact shape:

```yaml
version: 1
operation: edit # edit | continue
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

`during` uses zero-based, half-open seconds on the output timeline. A missing
`changes` list means preserve source material. References are an ordered list
and may be empty; the selected workflow advertises its actual reference
capacity in the compiled manifest rather than silently discarding extras.

Source-free `operation: generate` is not currently admitted. Although the
underlying H3 node family contains starter-oriented branches, this pack has no
verified packaged source-free output route, so a request with no source is
rejected before preparation rather than silently treated as continuation.

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

An edit-level `hard` flag is not a supported regional-edit control. The request
is rejected before preparation rather than accepting and dropping the flag.
This does not remove exact-preservation work: when the body, pose, or frame
identity must stay fixed, use the authoritative protected-baseline/in-painting
path described below. Use extension for a newly generated suffix or other
changes where motion and pose may vary.

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

Use the existing RunPod lifecycle guide for the pinned H3 CUDA-13 target and
submit through the canonical Astrid task/runtime path. Keep raw worker output,
composed output, and verification evidence together for review.
