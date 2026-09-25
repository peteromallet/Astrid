"""Independent decoded verification resolves placed audio from every member."""

import copy
import hashlib
import subprocess
from pathlib import Path

import pytest

from astrid.packs.h3_av.src.compose import compose_candidate
from astrid.packs.h3_av.src.prepare import prepare_request
from astrid.packs.h3_av.src.request import normalize_request
from astrid.packs.h3_av.src.verify import VerificationError, verify_candidate


def _ffmpeg(*args: str) -> bytes:
    return subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", *args], check=True, capture_output=True).stdout


def _pcm(path: Path) -> bytes:
    return _ffmpeg("-i", str(path), "-map", "0:a:0", "-f", "s32le", "-acodec", "pcm_s32le", "pipe:1")


def test_two_shifted_audio_members_and_wrong_output_negative(tmp_path: Path) -> None:
    first, second = tmp_path / "first.wav", tmp_path / "second.wav"
    _ffmpeg("-f", "lavfi", "-i", r"aevalsrc=if(lt(t\,2)\,0.1\,0.7):s=48000:d=4", "-ac", "2", "-c:a", "pcm_s32le", str(first))
    _ffmpeg("-f", "lavfi", "-i", r"aevalsrc=if(lt(t\,1)\,0.3\,0.9):s=48000:d=4", "-ac", "2", "-c:a", "pcm_s32le", str(second))
    generated = tmp_path / "generated.mkv"
    _ffmpeg("-f", "lavfi", "-i", "color=c=green:s=32x32:r=24:d=4", "-f", "lavfi", "-i", "aevalsrc=0.4:s=48000:d=4", "-ac", "2", "-c:v", "ffv1", "-pix_fmt", "bgra", "-c:a", "pcm_s32le", str(generated))
    request = normalize_request({
        "version": 2, "prompt": "Compose two placed sound sources.", "duration": 4,
        "media": [
            {"id": "first", "asset": "first.wav", "role": "timeline", "modality": "audio", "range": [2, 3], "at": {"seconds": 1},
             "edit": [{"stream": "audio", "during": [0, 0.5], "text": "First change"}]},
            {"id": "second", "asset": "second.wav", "role": "timeline", "modality": "audio", "range": [1, 2], "at": {"seconds": 2},
             "edit": [{"stream": "audio", "during": [0, 0.5], "text": "Second change"}]},
        ], "settings": {},
    })
    preparation = prepare_request(request, asset_map={"first.wav": str(first), "second.wav": str(second)}, width=32, height=32)
    composition = compose_candidate(preparation=preparation, generated=generated, out_dir=tmp_path / "compose")
    assert verify_candidate(preparation=preparation, composition=composition)["status"] == "verified"
    correct = _pcm(Path(composition["candidate"]["path"]))
    first_raw, second_raw = _pcm(first), _pcm(second)
    for delivery, raw, source in ((1.75, first_raw, 2.75), (2.75, second_raw, 1.75)):
        position = int(delivery * 48000) * 8
        expected = int(source * 48000) * 8
        assert correct[position:position + 8] == raw[expected:expected + 8]

    wrong_pcm = bytearray(correct)
    position = int(1.75 * 48000) * 8
    wrong_source = int(1.75 * 48000) * 8
    wrong_pcm[position:position + 8] = first_raw[wrong_source:wrong_source + 8]
    assert wrong_pcm[position:position + 8] != correct[position:position + 8]
    pcm_path = tmp_path / "wrong.s32le"
    pcm_path.write_bytes(wrong_pcm)
    wrong_candidate = tmp_path / "wrong.mkv"
    _ffmpeg("-i", composition["candidate"]["path"], "-f", "s32le", "-ar", "48000", "-ac", "2", "-i", str(pcm_path),
            "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "pcm_s32le", str(wrong_candidate))
    wrong_report = copy.deepcopy(composition)
    wrong_report["candidate"].update({"path": str(wrong_candidate), "sha256": hashlib.sha256(wrong_candidate.read_bytes()).hexdigest(), "size": wrong_candidate.stat().st_size})
    with pytest.raises(VerificationError, match="protected decoded pixels or PCM samples differ|exact equality evidence"):
        verify_candidate(preparation=preparation, composition=wrong_report, candidate=wrong_candidate)
