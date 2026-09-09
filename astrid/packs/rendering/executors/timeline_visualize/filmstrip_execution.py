"""Attempt-local rendering of an SDK-admitted, immutable filmstrip snapshot."""
from __future__ import annotations

import hashlib
import json
import zipfile
from copy import deepcopy
from pathlib import Path

from astrid.core._shared.result_manifest import build_manifest, write_manifest

from .audio_analysis import AudioAnalysisError, analyze_audio, audio_analysis_identity
from .filmstrip_cards import build_filmstrip_pack
from .filmstrip_options import filmstrip_options


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
    return {'returncode': 0, 'run_root': str(out_root),
            'manifest_path': str(manifest_path), 'timeline_ids': [snapshot['timeline_id']],
            'outputs': {'pack_root': str(pack_root), 'manifest_path': str(manifest_path),
                        **result['paths'], 'pages': result['paths']['png'],
                        'filmstrip_bundle': str(bundle)}}
