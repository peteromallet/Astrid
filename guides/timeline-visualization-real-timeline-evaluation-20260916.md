# Timeline visualization evaluation — Astrid Intro

Date: 2026-09-16  
Project: `astrid-intro`  
Timeline: `main-final-blackend2`  
Render: `2792e06b23af42ea918dc4ab2a3094f6` (117.0667s, 30 fps)

Evidence bundle:

`.astrid-data/timeline-visualize/astrid-intro/e789f01b3c2a6fb2c199f36472e383a846ba7583ec6f97e56f1c160f20183f3f/`

## Evaluation questions

Ten independent Luna briefs tested: section orientation/workflow search; repeated
“TWO IDEAS” placements; exact-name versus numeric shot selection; black-looking
layers versus actual blank output; frame-accurate transition inspection;
placeholder previews versus rendered pixels; persistent canonical overlay identity;
low-energy audio; burned-in text versus script context; and the final visual/audio
tail.

All evaluators were read-only and restricted to `python3 -m astrid timelines
visualize`, its help, and generated PNG/Markdown/JSON/audio-analysis artifacts.

## Results

Five questions completed from the bundle: Q4, Q7, Q8, Q9, Q10.  
Three were partial: Q1, Q5, Q6.  
Two were blocked/invalid: Q2, Q3.

This is an evaluation completion rate, not a product accuracy score: 50%
complete, 30% partial, 20% blocked/invalid.

### Proven findings

- Workflow-search is `shot_b06`, frame 993 at 33.100s; a failed focused run caused
  one evaluator to guess `shot_b05` instead.
- The early “TWO IDEAS” samples are distinct placements (`shot_b02` at 8.667s and
  `shot_b03` at 13.300s), not one continuous clip sampled twice.
- The black `shot_end_base` picture layer does not imply blank rendered output;
  frame overlay, FX, and terminal-background layers visibly supply the composite.
- The orange border is canonical asset `frame_overlay`, clip
  `canonical_tight_frame_overlay_v1`, spanning frames 0–3512.
- The workflow-search waveform contains a low-energy region inside continuous
  `vo_b06`; threshold-based quiet gaps do not prove perceptual silence.
- At 13.300s, “TWO IDEAS” and its labels are burned into the image. The associated
  script is segment-level (`timing_basis: shot_script`, not word-aligned), so the
  exact spoken word is unsupported.
- The final sign begins at frame 3263 (108.767s), while closing VO ends at frame
  3437 (114.567s); the sign holds for roughly 2.5s more. The exact last audible
  sample is not established.

## Friction adjudication

1. **P0 execution failure:** focused visualization calls from nested evaluators
   returned `neutral runtime bootstrap was not ready`, despite a valid existing
   bundle. Provide an artifact-only inspection path that does not require runtime
   bootstrap, or make the bootstrap status explicit and actionable.
2. **P0 bounded inspection:** broad `jq paths(scalars)`, whole-object JSON, and
   `rg` over SVG/base64 produced 262k+ token outputs. Add a compact inspection
   command with card/placement/audio selectors and suppress embedded payloads by
   default.
3. **P1 identity index:** expose a concise section → placement → frame/time index;
   keep authored ordinal, displayed title, clip id, and sample-card id distinct.
4. **P1 boundary evidence:** add a focused boundary report that returns adjacent
   rendered frames and timestamps for transition/ending questions.
5. **P1 status separation:** show source-preview status, input placement, and
   rendered-pixel evidence as separate fields; “placeholder” must not imply missing
   output.
6. **P2 calibration:** keep “shot script — not word-aligned” adjacent to text and
   label waveform results as threshold-based low energy.
7. **P2 environment contract:** publish and validate one authoritative skill path;
   evaluators repeatedly looked for a stale path.

## Next iteration

Repeat the ten briefs in two explicit conditions:

1. Artifact-only, with a payload-free index and no runtime dependency.
2. Runtime-enabled, after one nested focused request succeeds.

Do not award exact transition, exact-word, audible-silence, or last-audible-sample
claims without the corresponding adjacent-frame or aligned-audio evidence.
