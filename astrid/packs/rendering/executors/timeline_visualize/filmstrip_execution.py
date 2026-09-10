"""Attempt-local rendering of an SDK-admitted, immutable filmstrip snapshot."""
from __future__ import annotations

import hashlib
import json
import math
import subprocess
import zipfile
from copy import deepcopy
from pathlib import Path

from astrid.core._shared.result_manifest import build_manifest, write_manifest

from .audio_analysis import AudioAnalysisError, analyze_audio, audio_analysis_identity
from .filmstrip_cards import build_filmstrip_pack
from .filmstrip_options import filmstrip_options


def _rendered_frame_count(video: Path, fps) -> int:
    """Return the actual video-frame count, not the authored timeline length.

    A managed render can contain an explicit tail (for example the current
    intro has a long black hold) that is absent from the authored picture
    timeline.  Filmstrip sampling must follow the bytes being reviewed.
    """
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=nb_frames,duration,r_frame_rate",
         "-of", "json", str(video)],
        capture_output=True, text=True, check=False,
    )
    if probe.returncode:
        raise ValueError("Unable to probe rendered video duration: " + probe.stderr[-1000:])
    try:
        stream = json.loads(probe.stdout)["streams"][0]
        frames = int(stream.get("nb_frames") or 0)
        if frames > 0:
            return frames
        duration = float(stream.get("duration") or 0)
    except (ValueError, TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
        raise ValueError("Rendered video duration probe was invalid.") from exc
    if duration <= 0:
        raise ValueError("Rendered video has no usable duration.")
    return max(1, math.ceil(duration * float(fps)))


def _align_snapshot_to_render(snapshot: dict, video: Path) -> None:
    """Make the review snapshot describe the actual rendered composition.

    The authored timeline remains authoritative for shot/script identity.  If
    the render is longer, represent its unowned tail explicitly as a black
    render tail rather than pretending it belongs to the last shot.
    """
    from fractions import Fraction

    fps = Fraction(*snapshot["fps_rational"])
    rendered_frames = _rendered_frame_count(video, fps)
    authored_frames = int(snapshot.get("duration_frames") or 0)
    snapshot["duration_frames"] = rendered_frames
    snapshot.setdefault("metadata", {})["rendered_duration_frames"] = rendered_frames
    snapshot["metadata"]["rendered_duration_seconds"] = rendered_frames / float(fps)
    snapshot["metadata"]["authored_duration_frames"] = authored_frames
    snapshot["metadata"]["duration_basis"] = "rendered_video"
    if rendered_frames > authored_frames:
        # Some media clips already encode the rendered black hold as a source
        # duration beginning at a later `at`.  Do not add a duplicate tail when
        # the normalized clip already reaches the video EOF.
        covered_until = max(
            (int(c.get("end_frame", 0)) for c in snapshot.get("clips", [])
             if c.get("kind") not in {"audio", "voiceover", "music", "sound"}),
            default=authored_frames,
        )
        tail_start = max(authored_frames, covered_until)
        tail_id = "__rendered_tail_black__"
        if tail_start < rendered_frames and not any(c.get("id") == tail_id for c in snapshot.get("clips", [])):
            snapshot.setdefault("clips", []).append({
                "id": tail_id, "asset": "black_frame", "at": tail_start / float(fps),
                "from": 0.0, "to": (rendered_frames - tail_start) / float(fps),
                "duration": (rendered_frames - tail_start) / float(fps),
                "start_frame": tail_start, "end_frame": rendered_frames,
                "track": "picture", "kind": "visual", "clipType": "media",
                "render_tail": True,
            })
    else:
        # A shorter output must not cause cards to point past EOF.
        for clip in snapshot.get("clips", []):
            clip["start_frame"] = min(int(clip.get("start_frame", 0)), rendered_frames)
            clip["end_frame"] = min(int(clip.get("end_frame", rendered_frames)), rendered_frames)


def _audio_cache_path(parent: Path, render_digest: str, settings: object) -> Path:
    key = hashlib.sha256(json.dumps(
        {"render_digest": render_digest, "settings": settings},
        sort_keys=True, separators=(",", ":"), default=str,
    ).encode("utf-8")).hexdigest()
    return parent / ".audio-analysis-cache" / f"{key}.json"


def _cached_audio(parent: Path, render_digest: str, settings: object) -> dict | None:
    path = _audio_cache_path(parent, render_digest, settings)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict) or value.get("render_digest") != render_digest:
        return None
    return value


def _store_audio_cache(parent: Path, render_digest: str, settings: object, value: dict) -> None:
    path = _audio_cache_path(parent, render_digest, settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    entries = sorted(path.parent.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    for stale in entries[256:]:
        stale.unlink(missing_ok=True)


def execute_filmstrip(args, *, authority=None):
    if args.filmstrip_authority:
        authority = json.loads(args.filmstrip_authority)
    if not isinstance(authority, dict) or authority.get('mode') != 'filmstrip':
        raise ValueError('Rendered filmstrips require managed SDK admission.')
    snapshot = authority.get('filmstrip_snapshot')
    if not isinstance(snapshot, dict) or snapshot.get('project_slug') != args.project_slug:
        raise ValueError('Filmstrip authority does not match the project.')
    video = args.rendered_video
    if video is None or not video.is_file():
        raise ValueError('Admitted rendered video was not materialized.')
    with video.open('rb') as stream:
        digest = 'sha256:' + hashlib.file_digest(stream, 'sha256').hexdigest()
    if digest != authority.get('video_digest') or digest != snapshot.get('video_digest'):
        raise ValueError('Materialized rendered video does not match admitted digest.')
    values = vars(args).copy()
    values['range'] = args.range_value
    options = filmstrip_options(values)
    snapshot = deepcopy(snapshot)
    # Older/unit-test authorities may omit the timing envelope.  Real managed
    # renders always carry it; leave incomplete test authorities untouched so
    # their admission checks remain focused on digest verification.
    if snapshot.get("fps_rational") and snapshot.get("duration_frames"):
        _align_snapshot_to_render(snapshot, video)
    analysis_settings = authority.get('audio_analysis_settings')
    out_root = args.out.expanduser().resolve()
    analysis = _cached_audio(out_root.parent, digest, analysis_settings)
    if analysis is None:
        try:
            analysis = analyze_audio(video, render_digest=digest, settings=analysis_settings)
            _store_audio_cache(out_root.parent, digest, analysis_settings, analysis)
        except AudioAnalysisError as exc:
            # A malformed/unsupported stream is useful evidence, not permission to
            # invent a waveform.  Keep the filmstrip itself usable and make the
            # failure visible in the sidecar/index.
            analysis = {
                'schema_version': 1, 'analysis_version': 'astrid.audio-analysis.v1',
                'analysis_identity': audio_analysis_identity(
                    digest, None, analysis_settings, status='analysis_error'
                ),
                'status': 'analysis_error', 'render_digest': digest,
                'error': str(exc), 'waveform': {'levels': []}, 'quiet_gaps': [],
                'speech': {'status': 'no_transcript', 'phrases': []},
                'coverage': {'state': 'analysis_error'},
            }
    existing_audio = snapshot.get('audio') if isinstance(snapshot.get('audio'), dict) else {}
    if isinstance(existing_audio.get('speech'), dict):
        analysis['speech'] = existing_audio['speech']
    if 'fps_rational' in snapshot and 'duration_frames' in snapshot:
        snapshot['audio'] = analysis
    pack_root = out_root / 'filmstrip-view'
    if pack_root.exists() and any(pack_root.iterdir()):
        raise ValueError(f'evidence pack output is not empty: {pack_root}')
    result = build_filmstrip_pack(out_root=pack_root, video_path=video,
                                  snapshot=snapshot, options=options)
    (pack_root / 'render-snapshot.json').write_text(
        json.dumps(snapshot, indent=2, ensure_ascii=False), encoding='utf-8')
    files = sorted(p for p in pack_root.rglob('*') if p.is_file())
    manifest = build_manifest(
        kind='timeline_filmstrip', created='1970-01-01T00:00:00Z',
        inputs={'render_run_id': snapshot['render_run_id'], 'video_digest': digest,
                'timeline_id': snapshot['timeline_id'], 'options': options,
                'analysis_identity': analysis.get('analysis_identity'),
                'media': result.get('frame_index', {}).get('media'),
                'audio_sidecar': result.get('frame_index', {}).get('audio_sidecar')},
        outputs=[{'path': p.relative_to(pack_root).as_posix(), 'type': 'file',
                  'role': 'result', 'is_primary': p.name == 'filmstrip.html',
                  'label': p.relative_to(pack_root).as_posix()} for p in files],
        entrypoints={'html': 'filmstrip.html', 'frames': 'frame-index.json'},
        timeline_ids=[snapshot['timeline_id']],
    )
    manifest_path = pack_root / 'manifest.json'
    write_manifest(manifest_path, manifest)
    bundle = out_root / 'filmstrip-bundle.zip'
    with zipfile.ZipFile(bundle, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(pack_root.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(pack_root).as_posix())
    # The generic pack host treats ``{out}/manifest.json`` as the universal
    # result receipt.  The filmstrip's own manifest intentionally lives inside
    # ``filmstrip-view/`` because it is part of the self-contained bundle, so
    # writing only that nested manifest leaves an admitted task queued forever
    # (the host reports "missing result manifest receipt").  Publish a small
    # host receipt at the assigned output root and keep the domain manifest
    # nested and authoritative for offline evidence verification.
    def _receipt_entry(name: str, path: Path, *, role: str = "auxiliary", primary: bool = False) -> dict:
        relative = path.relative_to(out_root).as_posix()
        return {
            "name": name,
            "path": relative,
            "content_hash": "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            "bytes": path.stat().st_size,
            "role": role,
            "is_primary": primary,
        }

    # Keep the host receipt small and self-contained.  The bundle is the
    # canonical delivery artifact; it contains the complete HTML viewer,
    # nested manifest, PNG pages, and (when requested) the verified video.
    # Publishing the same large members individually would expand the inline
    # settlement beyond the runtime request limit and duplicate the bundle.
    write_manifest(
        out_root / "manifest.json",
        build_manifest(
            kind="timeline_filmstrip_result",
            created="1970-01-01T00:00:00Z",
            inputs={
                "render_run_id": snapshot["render_run_id"],
                "timeline_id": snapshot["timeline_id"],
                "video_digest": digest,
            },
            outputs=[
                _receipt_entry("filmstrip_manifest", pack_root / "manifest.json"),
                _receipt_entry("filmstrip_bundle", bundle, role="result", primary=True),
            ],
        ),
    )
    return {'returncode': 0, 'run_root': str(out_root),
            'manifest_path': str(manifest_path), 'timeline_ids': [snapshot['timeline_id']],
            'outputs': {'pack_root': str(pack_root), 'manifest_path': str(manifest_path),
                        **result['paths'], 'pages': result['paths']['png'],
                        'filmstrip_bundle': str(bundle)}}
