from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from astrid.packs.rendering.executors.timeline_visualize.inspector_viewer import render_inspector


def _viewer_data():
    return {
        "provenance": {"fps_rational": [24, 1], "duration_frames": 48, "video_digest": "sha256:" + "a" * 64},
        "sampling": {"options": {}, "mode": "interval", "step_frames_rational": [12, 1]},
        "cards": [{"id": "frame-0", "frame": 0, "time_seconds": 0, "time_label": "0.000s", "sample_reasons": [], "clips": [], "scripts": [], "image": "frames/frame-0.jpg", "shot_ids": []}],
        "navigation": {"frames": [], "targets": {}, "tracks": [], "clips": [], "shots": [], "audio": {"speech": {"phrases": []}}, "waveforms": [], "gaps": [], "phrases": []},
    }


@pytest.mark.skipif(shutil.which("node") is None, reason="node required")
def test_viewer_state_keeps_audio_selection_playback_loop_and_text_input_safe(tmp_path):
    script = tmp_path / "viewer-test.js"
    source = """
const fs=require('fs'),vm=require('vm');
const sandbox={module:{exports:{}},exports:{},document:undefined};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),sandbox);
const {createInspector}=sandbox.module.exports;
const data=JSON.parse(process.argv[3]);
data.navigation.frames=[{card_id:'frame-0',target:'frame-target'}];
data.navigation.targets={
  'phrase-target':{kind:'phrase',start_seconds:1,end_seconds:2},
  'gap-target':{kind:'gap',start_seconds:3,end_seconds:4},
  'frame-target':{kind:'frame',frame:0,start_frame:0,end_frame:1}
};
data.navigation.phrases=[{target:'phrase-target',start_seconds:1,end_seconds:2,canonical_text:'Blue pill'}];
data.navigation.gaps=[{target:'gap-target',start_seconds:3,end_seconds:4}];
const app=createInspector(data);
if(!app.select('phrase-target')||app.selectionInterval()[0]!==1)throw Error('phrase selection');
app.setPlaybackTime(1.5);if(app.state.playbackTime!==1.5)throw Error('media clock');
if(!app.setLoopForSelection()||app.state.loop.start!==1||app.state.loop.end!==2)throw Error('loop');
app.update({start:1.25});if(app.audioVisible(data.navigation.phrases[0])!==true)throw Error('range filter');
app.update({search:'missing'});if(app.audioVisible(data.navigation.phrases[0])!==false)throw Error('search filter');
if(app.keyboard({key:'ArrowLeft',target:{tagName:'INPUT'}})!==false)throw Error('text input');
console.log('ok');
"""
    script.write_text(source)
    module_path = str(Path(__file__).parents[3] / "astrid/packs/rendering/executors/timeline_visualize/inspector_assets/inspector.js")
    completed = subprocess.run(["node", str(script), module_path, json.dumps(_viewer_data())], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_rendered_viewer_contains_audio_controls_and_media_clock_fallback():
    page = render_inspector(_viewer_data())
    for marker in ("Speech and audio", "Quiet gaps", "Audition selection", "requestVideoFrameCallback", "timeupdate", "audio-ruler", "Verified rendered video"):
        assert marker in page
