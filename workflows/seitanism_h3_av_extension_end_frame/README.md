# Seitanism H3 AV extension with end frame

Derived from `../seitanism_h3_av_extension_verified/workflow.py`.

The recipe adds the existing `neo_mink_run` image as a soft endpoint guide at
the final one-based target frame of the H3 extension. The default comparison
length is three seconds (73 quantized target frames); set
`ASTRID_H3_EXTENSION_SECONDS=5` for the full D14-sized extension (124 target
frames). The 39-frame audiovisual overlap and the
`MiniMaxH3GeneratedAVMaskedContext` latent path remain unchanged.

The prompt is first-principles and standalone: it describes the pixelated mink
turning, throwing aside its tools, transforming into a realistic mink in a
realistic Matrix environment, and Neo running alongside it, without relative
“continue directly” boilerplate.

Run or validate this recipe with VibeComfy by passing:

```text
workflows/seitanism_h3_av_extension_end_frame/workflow.py
```

For a remote runner, set `ASTRID_H3_CANONICAL_WORKFLOW` and
`ASTRID_H3_END_FRAME` to the staged paths. Set `ASTRID_H3_SOURCE_VIDEO` when
the source video is not already embedded in the canonical loader. Set
`ASTRID_H3_EXTENSION_SECONDS=3` for the quick comparison test.
