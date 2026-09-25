# H3 audiovisual transformations

This pack turns one small request into a deterministic preparation manifest,
an H3 workflow bundle, a generated candidate, and preservation evidence. The
public request uses `changes.video` and `changes.audio` schedules. The active
H3 pack contract supports source-backed edits, native continuation, reference-guided generation,
and explicit mask assets without creating a second project or task database.

`operation: generate` accepts no source and one to nine ordered still-image
references, a prompt, output duration, and the normal settings overrides.
`src/generation.py` builds one sampling graph from the existing H3 reference
node family. Images are simultaneous conditioning inputs, not successive
segments or implicit keyframes. `edit` and `continue` still require a source.

The compiler targets the packaged native Seitanism MiniMax H3 AV continuation
graph and the packaged LanPaint source-backed edit graph. It fails closed when
a request asks for a graph feature that the selected workflow cannot represent.
Runtime admission and RunPod lifecycle remain Astrid/VibeComfy
responsibilities.

References are an ordered request list. The current continuation graph accepts
up to two image references; generation accepts one to nine; the edit graph
accepts none. Excess references fail admission or compilation. There is no
request-level `reference_strategy` or project-specific
workflow selection.

Compilation seals `capabilities.public_generation` into its digest. The
orchestrator derives `generation_intent` from that contract: all supported
routes declare one public video selector (`main-0`, ordinal 0).
The edit route's separate audio is a composition input, not another public
selector. Outputs and the composed candidate are retrieved through Runtime
managed media with size/hash verification before the final receipt is returned.

Generation requires empty video/audio change lists and creates the full AV
timeline. It supports 5..362 requested frames at 24 fps; native H3 lengths round
up to `5 + 17*k`. A 15-second request samples 362 frames, validates raw AV
coverage, and trims to exactly 360 frames and 15 seconds of audio. It does not
silently reduce duration or chain clips. Video/audio references, timed keyframes,
and source-free masks are not implemented and fail closed. The default canvas
is 1024×576; `guidance` uses the existing turbo LoRA strength convention.

The generated bundle is self-contained and portable. Reference filenames are
managed run inputs; media defaults remain empty to preserve VibeComfy's
emission/reload semantic identity. Submit through `h3_av.transform` with
`kind="orchestrator"`; do not hand-submit a separate VibeComfy generation.
CPU tests cover structure, bindings, duration and managed transport. Live target
schema/model attestation, GPU memory sufficiency, and visual acceptance remain
to be tested on the target machine.
