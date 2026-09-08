"""Execute the viewer's shared state against a frozen multi-track fixture."""
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from astrid.packs.rendering.executors.timeline_visualize.filmstrip_cards import plan_filmstrip
from astrid.packs.rendering.executors.timeline_visualize.inspector_viewer import render_inspector, _ASSETS

FIXTURE = Path(__file__).parents[2] / 'fixtures/timeline_visualize/unified_inspector.json'


def index():
    snapshot = json.loads(FIXTURE.read_text())
    return plan_filmstrip(snapshot, {'every': .5})


def node_assert(code):
    if not shutil.which('node'):
        pytest.skip('Node required for actual viewer state execution')
    script = 'const assert=require("node:assert/strict");const context={module:{exports:{}}};require("node:vm").runInNewContext(require("node:fs").readFileSync(' + json.dumps(str(_ASSETS / 'inspector.js')) + ',"utf8"),context);const {createInspector}=context.module.exports;const data=' + json.dumps(index()) + ';const app=createInspector(data);' + code
    result = subprocess.run(['node'], input=script, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-3000:]


def test_frame_clip_selection_uses_one_target_model_and_unsampled_is_explicit():
    node_assert('''
assert.equal(app.nav.tracks.length,4);
assert.equal(app.nav.tracks.find(t=>t.id==='music').clip_targets.length,0);
const overlay=app.nav.clips.find(c=>c.id==='creature');
app.select(overlay.target);assert.equal(app.record().target,overlay.target);
assert.equal(app.selectedCard().frame,24);
const frame=app.nav.frames.find(f=>f.frame===24);
assert.equal(frame.active_clip_targets.length,3);
app.select(frame.target);assert.equal(app.selectedCard().frame,24);
const brief=app.nav.clips.find(c=>c.id==='brief-audio');
assert.equal(brief.frame_target,null);app.select(brief.target);
assert.equal(app.selectedCard(),null);assert.match(app.state.message,/No captured frame/);
assert.match(app.record().actions.focus_command,/--render-run render-frozen/);
''')


def test_shared_filters_preserve_or_clear_selection_and_clip_dedup_is_after_scope():
    node_assert('''
app.select(app.nav.frames[0].target);app.update({start:1});
assert.equal(app.state.target,null);assert.match(app.state.message,/Selection cleared/);
app.update({mode:'clips'});assert.equal(app.visibleCards()[0].frame,24);
app.update({mode:'all',track:'voice'});
assert.ok(app.visibleCards().every(c=>c.clips.some(x=>x.track==='voice')));
assert.equal(app.clipVisible(app.nav.clips.find(c=>c.id==='base')),false);
app.update({track:'',search:'closely'});
assert.ok(app.visibleCards().every(c=>c.scripts.length));
''')


def test_deeplink_roundtrip_previous_next_and_keyboard_does_not_capture_inputs():
    node_assert('''
const target=app.nav.clips.find(c=>c.id==='creature').target;
assert.ok(app.select(app.decodeHash('#'+encodeURIComponent(target))));
assert.equal(app.state.target,target);const frame=app.selectedCard().frame;
app.step(1);assert.ok(app.selectedCard().frame>frame);app.step(-1);assert.equal(app.selectedCard().frame,frame);
assert.equal(app.keyboard({key:'ArrowRight',target:{tagName:'INPUT'}}),false);
assert.equal(app.keyboard({key:'ArrowRight',target:{tagName:'DIV',isContentEditable:true}}),false);
assert.equal(app.keyboard({key:'ArrowRight',target:{tagName:'BODY'}}),true);
assert.equal(app.keyboard({key:'ArrowRight',target:{tagName:'BUTTON'}}),true);
assert.equal(app.select('ins:foreign:frame:0'),false);
''')


def test_repeated_occurrences_are_distinct_targets():
    node_assert('''
assert.equal(app.nav.shots.length,2);assert.notEqual(app.nav.shots[0].target,app.nav.shots[1].target);
app.select(app.nav.shots[0].target);const a=app.selectedCard().frame;
app.select(app.nav.shots[1].target);assert.ok(app.selectedCard().frame>a);
''')


def test_viewer_embeds_assets_without_network_and_escapes_authored_content():
    data=index();data['provenance']['timeline_name']='</script><script>bad()</script>'
    page=render_inspector(data)
    assert '</script><script>bad()' not in page
    assert '\\u003c/script\\u003e' in page
    assert 'Show tracks' in page and 'Selection details' in page
    assert 'https://' not in page and '<script src=' not in page
    assert '#inspector .frame-card' in page


def test_dom_initialization_track_click_and_copy_command_share_navigation():
    if not shutil.which('node'):
        pytest.skip('Node required')
    script = r'''
const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
class Element {
  constructor(tag='DIV'){this.tagName=tag.toUpperCase();this.children=[];this.value='';this.style={};this.listeners={};this.checked=true;this.textContent='';}
  append(...children){this.children.push(...children)}
  replaceChildren(...children){this.children=children}
  setAttribute(name,value){this[name]=value}
  addEventListener(name,fn){this.listeners[name]=fn}
}
const controls=new Map();const $=id=>{if(!controls.has(id))controls.set(id,new Element());return controls.get(id)};
$('inspector-data').textContent=JSON.stringify(DATA);$('density').value='1';
const copied=[];const context={document:{getElementById:$,createElement:t=>new Element(t),addEventListener(){}},location:{hash:'',pathname:'/inspector.html',search:''},history:{replaceState(a,b,hash){context.location.hash=hash}},navigator:{clipboard:{writeText(value){copied.push(value);return Promise.resolve()}}},window:{addEventListener(){}},module:{exports:{}}};
vm.runInNewContext(fs.readFileSync(ASSET,'utf8'),context);
assert.equal($('lanes').children.length,5); // ruler + all four declared tracks
const voiceRow=$('lanes').children[3];assert.match(voiceRow.children[0].textContent,/Audio/);
const emptyRow=$('lanes').children[4];assert.equal(emptyRow.children[1].children[0].textContent,'Empty track');
const overlayButton=$('lanes').children[2].children[1].children.find(x=>x.tagName==='BUTTON');overlayButton.onclick();
assert.match(context.location.hash,/clip/);$('copy-command').onclick();
assert.match(copied[0],/--clip creature/);assert.match(copied[0],/--render-run render-frozen/);
assert.ok($('detail-content').children.some(x=>x.tagName==='IMG'));
const brief=$('lanes').children[3].children[1].children.filter(x=>x.tagName==='BUTTON')[1];brief.onclick();
assert.match($('selection-message').textContent,/No captured frame/);
assert.ok(!$('detail-content').children.some(x=>x.tagName==='IMG'));
'''.replace('DATA', json.dumps(index())).replace('ASSET', json.dumps(str(_ASSETS / 'inspector.js')))
    result=subprocess.run(['node'],input=script,capture_output=True,text=True)
    assert result.returncode == 0, result.stderr[-2000:]
