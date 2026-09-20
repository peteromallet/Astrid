# Seitanism H3 AV extension with reference-only end frame

Derived from `../seitanism_h3_av_extension_verified/workflow.py`.

This variant uses the `neo_mink_run` image as the second appearance reference
on the canonical `MiniMaxH3ReferenceToVideo` node. It does not add a
`MiniMaxH3CustomKeyframes` node and does not inject the image at a target frame.
The source-tail image remains the first reference. Both variants use the same
first-principles action prompt so the comparison isolates endpoint injection
versus reference guidance. It defaults to a three-second / 73-frame H3 test;
set `ASTRID_H3_EXTENSION_SECONDS=5` for the full D14-sized extension.

For a remote runner, set `ASTRID_H3_CANONICAL_WORKFLOW`, `ASTRID_H3_END_FRAME`,
`ASTRID_H3_SOURCE_VIDEO`, `ASTRID_H3_REFERENCE_IMAGE`, and
`ASTRID_H3_REMOTE_INPUT_NAMES=1` as appropriate.
