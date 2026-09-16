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
    for marker in (
        "Speech and audio",
        "Quiet gaps",
        "Audition selection",
        "requestVideoFrameCallback",
        "timeupdate",
        "audio-ruler",
        "Verified rendered video",
        "Spoken text",
        "Find spoken text",
        "Search matches spoken text and annotated speech phrases",
        "Clear search and open Speech and audio",
    ):
        assert marker in page


@pytest.mark.skipif(shutil.which("node") is None, reason="node required")
def test_card_helpers_surface_only_declared_audio_and_frozen_speech_metadata(tmp_path):
    script = tmp_path / "card-audio-test.js"
    source = """
const fs=require('fs'),vm=require('vm');
const sandbox={module:{exports:{}},exports:{},document:undefined};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),sandbox);
const {createInspector}=sandbox.module.exports;
const data=JSON.parse(process.argv[3]);
data.cards=[
  {id:'frame-0',frame:0,time_seconds:0,time_label:'0.000s',sample_reasons:[],shot_ids:[],scripts:[],clips:[
    {id:'music',kind:'music',track:'music-track',shot_name:'A name'},
    {id:'voice',kind:'voiceover',track:'voice-track',shot_name:'A name'},
    {id:'pretend',kind:'video',track:'video-track',label:'audio filename'}
  ]},
  {id:'frame-24',frame:24,time_seconds:1,time_label:'1.000s',sample_reasons:[],shot_ids:[],scripts:[],clips:[]}
];
data.navigation.frames=[{card_id:'frame-0',target:'frame-0-target'},{card_id:'frame-24',target:'frame-24-target'}];
data.navigation.tracks=[{id:'music-track',kind:'audio',label:'Music'},{id:'voice-track',kind:'audio',label:'VO'},{id:'video-track',kind:'visual',label:'Picture'}];
data.navigation.phrases=[{target:'phrase-target',start_seconds:0,end_seconds:0.25,canonical_text:'Declared phrase'}];
data.navigation.targets={'frame-0-target':{kind:'frame',frame:0,start_frame:0,end_frame:1},'frame-24-target':{kind:'frame',frame:24,start_frame:24,end_frame:25}};
data.audio={status:'analysis_complete',speech:{status:'complete',phrases:data.navigation.phrases}};
const app=createInspector(data);
const cues=app.cardAudioCues(data.cards[0]);
if(JSON.stringify(cues)!=='["Music clip","Audio clip","Speech annotation"]')throw Error(JSON.stringify(cues));
if(app.cardAudioCues(data.cards[1]).length!==0)throw Error('unexpected audio inference');
if(app.renderAudioStatus().label!=='Render audio: available')throw Error('render status');
console.log('ok');
"""
    script.write_text(source)
    module_path = str(Path(__file__).parents[3] / "astrid/packs/rendering/executors/timeline_visualize/inspector_assets/inspector.js")
    completed = subprocess.run(["node", str(script), module_path, json.dumps(_viewer_data())], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"


def test_rendered_viewer_contains_filmstrip_hierarchy_and_truthful_card_cues():
    page = render_inspector(_viewer_data())
    for marker in (
        "card-header",
        "No spoken text",
        "No audio metadata",
        "Speech annotation",
        "Render audio: available",
        "min(100%,240px)",
        "@media(max-width:600px)",
    ):
        assert marker in page
    assert page.index("header.append") < page.index("img.src")


@pytest.mark.skipif(shutil.which("node") is None, reason="node required")
def test_browser_viewer_seeks_frame_target_from_frame_number_and_shot_filter(tmp_path):
    script = tmp_path / "viewer-dom-seek-test.js"
    source = """
const fs=require('fs'),vm=require('vm');
class Element {
  constructor(id=''){this.id=id;this.textContent='';this.value='';this.checked=true;this.hidden=false;this.open=false;this.style={};this.children=[];this.listeners={};}
  append(...items){this.children.push(...items);}
  replaceChildren(...items){this.children=items;}
  addEventListener(name,fn){this.listeners[name]=fn;}
  setAttribute(name,value){this[name]=value;}
  play(){this.played=true;return Promise.resolve();}
}
const ids=['inspector-data','title','provenance','frozen','capture','warnings','density','mode','shot','track','start','end','search','retain-cuts','reset','grid','count','search-status','open-audio','track-section','lanes','audio-section','audio-status','audio-rows','selection-message','detail-content','detail-empty','detail-actions','previous','next','copy-status','copy-time','copy-target','copy-command','rendered-media','context-selection','loop-selection','clear-loop'];
const elements=Object.fromEntries(ids.map(id=>[id,new Element(id)]));
const media=elements['rendered-media'];media.readyState=4;media.duration=4;media.currentTime=0;media.play=()=>{media.played=true;return Promise.resolve();};
const data={provenance:{fps_rational:[24,1],duration_frames:96,metadata:{}},sampling:{options:{shot:'shot-1'},mode:'interval',step_frames_rational:[24,1]},cards:[
  {id:'frame-12',frame:12,time_seconds:.5,time_label:'0.500s',sample_reasons:['interval'],shot_ids:['shot-0'],scripts:[],clips:[],image:'frame-12.jpg'},
  {id:'frame-24',frame:24,time_seconds:1,time_label:'1.000s',sample_reasons:['interval'],shot_ids:['shot-1'],scripts:[],clips:[],image:'frame-24.jpg'},
  {id:'frame-48',frame:48,time_seconds:2,time_label:'2.000s',sample_reasons:['interval'],shot_ids:['shot-1'],scripts:[],clips:[],image:'frame-48.jpg'}
],navigation:{frames:[{card_id:'frame-12',target:'frame-target-12'},{card_id:'frame-24',target:'frame-target-24'},{card_id:'frame-48',target:'frame-target-48'}],targets:{
  'frame-target-12':{kind:'frame',frame:12,start_frame:12,end_frame:13},
  'frame-target-24':{kind:'frame',frame:24,start_frame:24,end_frame:25},
  'frame-target-48':{kind:'frame',frame:48,start_frame:48,end_frame:49}
},tracks:[],clips:[],shots:[{shot_id:'shot-0',label:'Shot 0',start_frame:12,end_frame:24},{shot_id:'shot-1',label:'Shot 1',start_frame:24,end_frame:72}],phrases:[],gaps:[],waveforms:[],audio:{status:'not_analyzed',speech:{status:'no_transcript'}}},media:{path:'rendered.mp4'}};
elements['inspector-data'].textContent=JSON.stringify(data);
const documentListeners={};
const sandbox={document:{getElementById:id=>elements[id],createElement:tag=>new Element(tag),querySelectorAll:()=>[],addEventListener:(name,fn)=>{documentListeners[name]=fn;}},window:{addEventListener:()=>{}},history:{replaceState:(_,__,url)=>{sandbox.location.hash=url.includes('#')?url.slice(url.indexOf('#')):'';}},location:{hash:'',pathname:'/',search:''},localStorage:{getItem:()=>null,setItem:()=>{}},navigator:{clipboard:{writeText:()=>Promise.resolve()}},console};
vm.runInNewContext(fs.readFileSync(process.argv[2],'utf8'),sandbox);
if(media.currentTime!==1)throw Error(`shot-filter seek was ${media.currentTime}`);
if(elements.grid.children.length!==2)throw Error(`expected two shot cards, got ${elements.grid.children.length}`);
elements.grid.children[1].onclick();
if(media.currentTime!==2||!sandbox.location.hash.includes('frame-target-48'))throw Error(`card seek/hash ${media.currentTime} ${sandbox.location.hash}`);
elements['previous'].onclick();
if(media.currentTime!==1||!sandbox.location.hash.includes('frame-target-24'))throw Error(`previous seek/hash ${media.currentTime} ${sandbox.location.hash}`);
elements['next'].onclick();
if(media.currentTime!==2||!sandbox.location.hash.includes('frame-target-48'))throw Error(`next seek/hash ${media.currentTime} ${sandbox.location.hash}`);
documentListeners.keydown({key:'ArrowLeft',target:{tagName:'BODY'},preventDefault:()=>{}});
if(media.currentTime!==1||!sandbox.location.hash.includes('frame-target-24'))throw Error(`arrow seek/hash ${media.currentTime} ${sandbox.location.hash}`);
elements['shot'].value='shot-0';elements['shot'].listeners.input({target:elements['shot']});
if(media.currentTime!==.5||!sandbox.location.hash.includes('frame-target-12'))throw Error(`shot-change seek/hash ${media.currentTime} ${sandbox.location.hash}`);
if(elements['detail-content'].children.length===0)throw Error('selected card detail missing');
console.log('ok');
"""
    script.write_text(source)
    module_path = str(Path(__file__).parents[3] / "astrid/packs/rendering/executors/timeline_visualize/inspector_assets/inspector.js")
    completed = subprocess.run(["node", str(script), module_path], capture_output=True, text=True, check=False)
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "ok"
