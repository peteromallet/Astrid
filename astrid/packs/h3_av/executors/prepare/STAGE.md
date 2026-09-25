# Prepare staging

`request` is a managed JSON or YAML H3 request v1 document. `input_bundle` is
the managed, hash-verified archive of all declared request assets, built by
`h3_av.transform`. The executor materializes these into its own attempt and
writes portable member identities to `preparation.json`; it does not call ComfyUI,
RunPod, ffmpeg, or the network.
