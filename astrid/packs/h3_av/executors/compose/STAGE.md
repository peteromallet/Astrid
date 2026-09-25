# Compose staging

The preparation manifest must be produced by `h3_av.prepare`. `generated` is a
settled Runtime-managed artifact; a caller must not pass a stale worker path
as its identity. The transform orchestrator retrieves the managed bytes,
checks their digest, and passes the managed descriptor to this stage.

For decodable media with partial permissions, composition uses the source as
the authoritative baseline and actually selects source streams for protected
intervals and generated streams for changed intervals. The resulting MKV is
lossless for the selected samples. Non-media fixtures may be copied for legacy
unit coverage, but verification will reject them for partial preservation.
Composition records request, schedule, asset, graph, and Runtime output
provenance. Interval lists alone are never preservation evidence.
