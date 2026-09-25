# H3 compile stage

Consumes only an eligible `h3_av.prepare` manifest. It selects and freezes one
of the packaged native-no-reference, native-reference, or LanPaint workflow
trios for source-backed requests, binds the public inputs, and emits `compilation.json`,
`managed-assets.zip`, and the selected `workflow.py`, `workflow.vibe.json`, and
`source.json` members as separate declared outputs. The three workflow files
are settled as managed objects; paths nested in `compilation.json` are only
local compilation evidence. Source-free `operation=generate` is not admitted;
unsupported graph features fail before validation or GPU submission.
