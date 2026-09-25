# H3 audiovisual transformations

This pack turns one small request into a deterministic preparation manifest,
an H3 workflow bundle, a generated candidate, and preservation evidence. The
v1 public request uses `changes.video` and `changes.audio` schedules. Native
continuation, references, and explicit mask assets share the canonical
request/compile path. The v2 media-list path admits source-free and audio-only
graphs, but video timeline edits and shifted/ranged video source placement
currently fail compilation. Its continuation graph outputs the original source
prefix followed by generated extension, not edits inside that prefix. The
pinned full-source V2V node needs an output-clock AV baseline at the complete
native target length; the current pack has no builder for that asset.

The v1 `operation: generate` remains unadmitted. The v2 source-free media-list
request uses the same generalized H3 graph binding; CPU compilation does not
establish GPU acceptance.

The current compiler targets the repaired Seitanism MiniMax H3 AV graph at
`workflows/seitanism_h3_av_extension_repaired/`. It fails closed when a request
asks for a graph feature that the selected workflow cannot represent. Runtime
admission and RunPod lifecycle remain Astrid/VibeComfy responsibilities.
