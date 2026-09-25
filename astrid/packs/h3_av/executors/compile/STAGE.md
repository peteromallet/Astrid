# H3 compile stage

Consumes an eligible `h3_av.prepare` manifest and its immutable `input_bundle`.
It verifies bundle/member identities and resolves fresh attempt-local paths,
without opening prepare's filesystem. It selects and freezes one
of the packaged native-no-reference, native-reference, or LanPaint workflow
trios for source-backed requests, binds the public inputs, and emits `compilation.json`,
`managed-assets.zip`, and the selected `workflow.py`, `workflow.vibe.json`, and
`source.json` members as separate declared outputs. The three workflow files
are settled as managed objects; paths nested in `compilation.json` are only
local compilation evidence.

For `operation=generate`, the general H3 reference adapter emits a self-contained
canonical trio using one sampling pass, 1..9 ordered image inputs and one muxed
output. Media defaults stay empty; their filenames are managed run bindings.
The native frame plan and one public generation selector are sealed into the
compilation. Unsupported graph features fail before validation or GPU submission.
