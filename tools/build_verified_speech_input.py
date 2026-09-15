#!/usr/bin/env python3
"""Materialize the verified-speech fixture input without changing the fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from astrid.sdk.verified_speech_authoring import build_verified_speech_materialization


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("authored_structure", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--media-digest", required=True)
    args = parser.parse_args()
    authored_bytes = args.authored_structure.read_bytes()
    authored = json.loads(authored_bytes.decode("utf-8"))
    if not isinstance(authored, dict):
        raise SystemExit("authored structure must be a JSON object")
    materialization = build_verified_speech_materialization(
        authored_bytes,
        authored,
        media_digest=args.media_digest,
    )
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output / "transcript.json").write_bytes(materialization["transcript_bytes"])
    (args.output / "speech-inputs.json").write_text(
        json.dumps(materialization["speech_inputs"], sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    manifest = {
        "transcript_declaration": materialization["transcript_declaration"],
        "config_patch": {"app": {"transcript": materialization["transcript_declaration"]}},
        "render_inputs": materialization["speech_inputs"],
        "digests": materialization["digests"],
        "preflight": materialization["preflight"],
        "runtime_input": {
            "name": "transcript.json",
            "digest": "sha256:" + materialization["digests"]["transcript_bytes"],
        },
        "host_manifest": {
            "input_object_ids": [
                "sha256:" + materialization["digests"]["transcript_bytes"]
            ],
            "inputs": {
                "transcript.json": {
                    "digest": "sha256:" + materialization["digests"]["transcript_bytes"],
                    "object_id": "sha256:" + materialization["digests"]["transcript_bytes"],
                }
            },
        },
    }
    (args.output / "authoring-materialization.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(manifest, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
