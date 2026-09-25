# Prepare staging

`request` is a JSON or YAML H3 request v1 document. `asset_map`, when supplied,
is a JSON object of managed asset identifiers to local files. The executor only
reads these inputs and writes `preparation.json`; it does not call ComfyUI,
RunPod, ffmpeg, or the network.
