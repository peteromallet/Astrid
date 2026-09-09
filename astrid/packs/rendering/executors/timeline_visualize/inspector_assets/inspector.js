/* One navigation model drives picture, speech, waveform, lanes and details. */
'use strict';
function createInspector(data) {
  const nav=data.navigation||{}, fps=data.provenance.fps_rational[0]/data.provenance.fps_rational[1];
  const frameTargets=new Map((nav.frames||[]).map(f=>[f.card_id,f.target]));
  const state={start:null,end:null,search:'',shot:'',track:'',density:1,mode:'all',retainCuts:true,target:null,message:'',audioOpen:false,playbackTime:0,loop:null,playing:false};
  const cardTarget=c=>frameTargets.get(c.id);
  const frameCard=target=>data.cards.find(c=>cardTarget(c)===target||c.id===target);
  const cuts=c=>(c.sample_reasons||[]).some(r=>r.includes('cut'));
  const audioText=p=>[p.canonical_text,p.recognized_text,p.text].filter(Boolean).join(' ').toLowerCase();
  const audioItems=kind=>kind==='phrase'?(nav.phrases||[]):kind==='gap'?(nav.gaps||[]):(nav.waveforms||[]);
  function itemMatchesCard(item,c){return item.start_seconds<c.time_seconds+1/fps&&item.end_seconds>c.time_seconds;}
  function inScope(c) {
    const phraseHit=audioItems('phrase').some(p=>itemMatchesCard(p,c)&&audioText(p).includes(state.search.toLowerCase()));
    return (state.start===null||c.time_seconds>=state.start)&&(state.end===null||c.time_seconds<state.end)
      &&(!state.search||c.scripts.some(s=>String(s.text).toLowerCase().includes(state.search.toLowerCase()))||phraseHit)
      &&(!state.shot||c.shot_ids.includes(state.shot)||nav.shots.some(s=>s.shot_id===state.shot&&c.frame>=s.start_frame&&c.frame<s.end_frame))&&(!state.track||c.clips.some(x=>String(x.track)===state.track));
  }
  function audioVisible(item){
    return (state.start===null||item.end_seconds>state.start)&&(state.end===null||item.start_seconds<state.end)
      &&(!state.search||audioText(item).includes(state.search.toLowerCase()));
  }
  function visibleCards() {
    let interval=0; const seen=new Set();
    return data.cards.filter(c=>{
      if(!inScope(c))return false;
      const cut=cuts(c); let accept=true;
      if(state.mode==='cuts')accept=cut;
      if(state.mode==='shots')accept=c.sample_reasons.includes('shot_midpoint');
      if(state.mode==='interval')accept=c.sample_reasons.includes('interval')||(state.retainCuts&&cut);
      if(state.mode==='clips')accept=c.clips.some(x=>!['audio','voiceover','music','sound'].includes(x.kind)&&!seen.has(x.id));
      if(c.sample_reasons.includes('interval')&&interval++%state.density&&!(state.retainCuts&&cut))accept=false;
      if(accept&&state.mode==='clips')c.clips.filter(x=>!['audio','voiceover','music','sound'].includes(x.kind)).forEach(x=>seen.add(x.id));
      return accept;
    });
  }
  function record(target=state.target){return nav.targets?.[target]||null;}
  function selectedCard(){
    const target=record(); if(!target)return null;
    const direct=frameCard(state.target); if(direct)return visibleCards().find(c=>c.id===direct.id)||null;
    const start=target.start_frame,end=target.end_frame;
    if(start!==undefined&&end!==undefined)return visibleCards().find(c=>c.frame>=start&&c.frame<end&&(target.kind!=='clip'||nav.frames.find(f=>f.card_id===c.id)?.active_clip_targets.includes(state.target)))||null;
    if(target.start_seconds!==undefined)return visibleCards().find(c=>itemMatchesCard(target,c))||null;
    return null;
  }
  function select(target){
    const legacy=data.cards.find(c=>c.id===target);if(legacy)target=cardTarget(legacy);
    if(!nav.targets?.[target]){state.message='This target is not part of the pinned render.';return false;}
    state.target=target;state.message='';
    if(!selectedCard()&&!['track','phrase','gap','waveform'].includes(record().kind))state.message='No captured frame matches this selection and current filters. Use its exact focus command to sample it.';
    return true;
  }
  function update(values){Object.assign(state,values);if(state.target){const r=record();if(r?.kind==='frame'&&!selectedCard()){state.target=null;state.message='Selection cleared because the frame is outside the current filters or density.';}else if(!selectedCard()&&!['track','phrase','gap','waveform'].includes(r?.kind))state.message='No captured frame matches this selection and current filters. Use its exact focus command to sample it.';else state.message='';}}
  function step(direction){
    const current=record();
    if(current&&['phrase','gap','waveform'].includes(current.kind)){const items=audioItems(current.kind),i=items.findIndex(x=>x.target===state.target),next=Math.max(0,Math.min(items.length-1,i<0?0:i+direction));if(items.length)select(items[next].target);return;}
    const cards=visibleCards();if(!cards.length)return;const selected=selectedCard(),i=selected?cards.findIndex(c=>c.id===selected.id):-1;const next=Math.max(0,Math.min(cards.length-1,i<0?0:i+direction));select(cardTarget(cards[next]));
  }
  function clipVisible(clip){
    if(state.track&&String(clip.track_id)!==state.track)return false;
    if(state.start!==null&&clip.end_frame<=state.start*fps)return false;
    if(state.end!==null&&clip.start_frame>=state.end*fps)return false;
    if(state.shot&&clip.shot_id!==state.shot&&!data.cards.some(c=>inScope(c)&&c.clips.some(x=>x.id===clip.id)))return false;
    return !state.search||data.cards.some(c=>inScope(c)&&c.clips.some(x=>x.id===clip.id));
  }
  function selectionInterval(){const r=record();return r&&r.start_seconds!==undefined?[r.start_seconds,r.end_seconds]:selectedCard()?[selectedCard().time_seconds,selectedCard().time_seconds+1/fps]:null;}
  function setPlaybackTime(seconds){state.playbackTime=Math.max(0,Math.min(data.provenance.duration_frames/fps,Number(seconds)||0));return state.playbackTime;}
  function setLoopForSelection(){const range=selectionInterval();if(range)state.loop={start:range[0],end:range[1]};return state.loop;}
  function clearLoop(){state.loop=null;return null;}
  function decodeHash(hash){try{return decodeURIComponent(hash.replace(/^#/,''));}catch{return '';}}
  function keyboard(event){return !event.altKey&&!event.ctrlKey&&!event.metaKey&&!['INPUT','TEXTAREA','SELECT'].includes(event.target?.tagName)&&!event.target?.isContentEditable&&['ArrowLeft','ArrowRight'].includes(event.key);}
  return {state,nav,fps,record,cardTarget,frameCard,inScope,visibleCards,selectedCard,select,update,step,clipVisible,decodeHash,keyboard,audioItems,audioVisible,selectionInterval,setPlaybackTime,setLoopForSelection,clearLoop};
}
if(typeof module!=='undefined')module.exports={createInspector};
if(typeof document!=='undefined'){
  const data=JSON.parse(document.getElementById('inspector-data').textContent),app=createInspector(data),$=id=>document.getElementById(id);
  const node=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n;};
  const names=clips=>[...new Set(clips.map(c=>c.shot_name||c.shot_id).filter(Boolean))].join(' · ');
  const stepFrames=data.sampling.step_frames_rational[0]/data.sampling.step_frames_rational[1];
  $('title').textContent=data.provenance.timeline_name||data.provenance.timeline_id;$('provenance').textContent=`${data.provenance.project_slug} / render ${data.provenance.render_run_id}`;$('frozen').textContent='Frozen render snapshot · '+(data.provenance.metadata?.config_version?'version '+data.provenance.metadata.config_version:'exact render provenance');$('capture').textContent=`Captured every ${data.sampling.options.every_frames?stepFrames+' frames':(stepFrames/app.fps).toFixed(3)+' seconds'} · ${data.cards.length} frames. Density can only reduce these captured samples.`;
  const warning=data.provenance.metadata?.warnings||[];$('warnings').textContent=(Array.isArray(warning)?warning:[warning]).map(x=>typeof x==='string'?x:JSON.stringify(x)).join(' · ');
  for(const factor of [1,2,4,8]){const o=node('option',factor===1?'All captured frames':(data.sampling.options.every_frames?`${stepFrames*factor} frame intervals`:`${(stepFrames*factor/app.fps).toFixed(2)} s intervals`));o.value=String(factor);$('density').append(o);}
  const allowed=data.sampling.mode==='shots'?['all','shots']:data.sampling.mode==='cuts'?['all','cuts']:data.sampling.mode==='clips'?['all','clips','cuts','shots']:['all','interval','clips','cuts','shots'];const labels={all:'All captured frames',interval:'Regular intervals',clips:'Picture clips',cuts:'Cut boundaries',shots:'Story beats'};for(const value of allowed){const o=node('option',labels[value]);o.value=value;$('mode').append(o);}if(data.sampling.mode!=='interval')app.state.mode=data.sampling.mode;$('mode').value=app.state.mode;
  const shotNames=new Map();for(const c of data.cards)for(const clip of c.clips)if(clip.shot_id)shotNames.set(String(clip.shot_id),clip.shot_name||clip.shot_id);for(const shot of app.nav.shots)shotNames.set(String(shot.shot_id),shot.label||shot.shot_id);for(const [id,label] of shotNames){const o=node('option',label);o.value=id;$('shot').append(o);}for(const track of app.nav.tracks){const o=node('option',track.label||track.id);o.value=String(track.id);$('track').append(o);}
  function choose(target){if(app.select(target)){history.replaceState(null,'','#'+encodeURIComponent(app.state.target));render();seekToSelection(true);}}
  function syncPlayhead(){const duration=data.provenance.duration_frames/app.fps;for(const marker of document.querySelectorAll('.timeline-playhead'))marker.style.left=(app.state.playbackTime/duration*100)+'%';}
  function seekToSelection(autoplay=false){const r=app.record();if(!r||!media)return;const seek=r.actions?.seek;const start=seek?seek.start[0]/seek.start[1]:r.start_seconds;if(Number.isFinite(start)){media.currentTime=Math.max(0,start);if(autoplay)media.play().catch(()=>{});}}
  function renderGrid(){const cards=app.visibleCards(),selected=app.selectedCard();$('grid').replaceChildren();for(const c of cards){const el=node('button',undefined,'frame-card'+(selected?.id===c.id?' selected':''));el.type='button';el.setAttribute('aria-pressed',String(selected?.id===c.id));el.onclick=()=>choose(app.cardTarget(c));const img=node('img');img.src=c.image;img.alt=`Composited frame ${c.frame} at ${c.time_label}`;img.loading='lazy';el.append(img,node('span',c.time_label,'time'),node('span',names(c.clips)||'Unlabelled shot','shot-name'),node('span',c.scripts.map(s=>s.text).join('\n')||'No script','caption'));$('grid').append(el);}$('count').textContent=`${cards.length} of ${data.cards.length} captured frames · final composition`;}
  function renderTracks(){
    $('lanes').replaceChildren();const duration=data.provenance.duration_frames,lo=app.state.start===null?0:Math.max(0,app.state.start*app.fps),hi=app.state.end===null?duration:Math.min(duration,app.state.end*app.fps),span=Math.max(1,hi-lo),selected=app.selectedCard();const ruler=node('div',undefined,'ruler');ruler.append(node('span','Track'));for(let i=0;i<=4;i++)ruler.append(node('span',((lo+span*i/4)/app.fps).toFixed(1)+'s'));$('lanes').append(ruler);
    for(const track of app.nav.tracks){const row=node('div',undefined,'track-row'),label=node('button',`${track.track_kind==='audio'?'♫ Audio':'▣ Visual'} · ${track.label||track.id}`,'track-label');label.onclick=()=>{app.update({track:String(track.id)});$('track').value=String(track.id);choose(track.target);};row.append(label);const lane=node('div',undefined,'lane');const clips=app.nav.clips.filter(c=>String(c.track_id)===String(track.id));if(!clips.length)lane.append(node('span','Empty track','empty-lane'));const rowEnds=[];for(const clip of [...clips].sort((a,b)=>a.start_frame-b.start_frame||a.end_frame-b.end_frame)){if(clip.end_frame<=lo||clip.start_frame>=hi)continue;const active=selected&&selected.frame>=clip.start_frame&&selected.frame<clip.end_frame,b=node('button',(clip.shot_name||clip.label||clip.clip_kind||'Clip'),`clip ${track.track_kind==='audio'?'audio':'visual'}${active?' active':''}${app.state.target===clip.target?' selected':''}${app.clipVisible(clip)?'':' filtered'}`);let slot=rowEnds.findIndex(end=>end<=clip.start_frame);if(slot<0)slot=rowEnds.length;rowEnds[slot]=clip.end_frame;b.style.top=(9+slot*36)+'px';b.style.left=(Math.max(lo,clip.start_frame)-lo)/span*100+'%';b.style.width=Math.max(.25,(Math.min(hi,clip.end_frame)-Math.max(lo,clip.start_frame))/span*100)+'%';b.title=`${clip.shot_name||clip.id} · ${clip.start_frame}–${clip.end_frame} frames`;b.setAttribute('aria-label',b.title);b.setAttribute('aria-pressed',String(app.state.target===clip.target));b.onclick=()=>choose(clip.target);lane.append(b);}lane.style.minHeight=Math.max(48,rowEnds.length*36+12)+'px';if(selected&&selected.frame>=lo&&selected.frame<hi){const playhead=node('div',undefined,'playhead');playhead.style.left=(selected.frame-lo)/span*100+'%';lane.append(playhead);}const playback=node('div',undefined,'timeline-playhead');playback.style.left=(app.state.playbackTime/(data.provenance.duration_frames/app.fps)*100)+'%';lane.append(playback);row.append(lane);$('lanes').append(row);}
  }
  function renderAudio(){
    const audio=app.nav.audio||{},status=audio.status||'not_analyzed',speech=audio.speech||{},unavailable=(speech.unavailable||[]).length;const baseStatus=status==='no_audio_stream'?'No audio stream in this render.':status==='analysis_error'?'Audio analysis unavailable: '+(audio.error||'decoder error'):(speech.status==='no_transcript'?'No speech annotation; waveform remains available.':'Rendered mix · speech annotations are frozen to this render.');$('audio-status').textContent=unavailable?`${baseStatus} ${unavailable} speech annotation${unavailable===1?' is':'s are'} unavailable because timing or coverage is incomplete.`:baseStatus;$('audio-rows').replaceChildren();const ruler=node('div',undefined,'audio-ruler ruler');ruler.append(node('span','Audio'));for(let i=0;i<=4;i++)ruler.append(node('span',((data.provenance.duration_frames/app.fps*i/4)).toFixed(1)+'s'));$('audio-rows').append(ruler);
    const addRow=(kind,label,items)=>{const row=node('div',undefined,'audio-row');row.append(node('span',label,'audio-row-label'));const lane=node('div',undefined,'audio-lane');for(const item of items.filter(app.audioVisible)){const text=kind==='gap'?`Quiet gap · ${item.duration_seconds.toFixed(3)}s`:kind==='phrase'?(item.canonical_text||item.text||'Unavailable phrase'):`${item.level_id||'Waveform'} · ${item.start_seconds.toFixed(3)}–${item.end_seconds.toFixed(3)}s`;const b=node('button',text,`audio-item ${kind}`);b.type='button';b.setAttribute('aria-label',`${text}; starts ${item.start_seconds.toFixed(3)} seconds, ends ${item.end_seconds.toFixed(3)} seconds, duration ${item.duration_seconds.toFixed(3)} seconds`);b.title=b.getAttribute('aria-label');b.style.left=(item.start_seconds/(data.provenance.duration_frames/app.fps)*100)+'%';b.style.width=Math.max(.3,(item.duration_seconds/(data.provenance.duration_frames/app.fps)*100))+'%';b.onclick=()=>choose(item.target);lane.append(b);}const playback=node('div',undefined,'timeline-playhead');playback.style.left=(app.state.playbackTime/(data.provenance.duration_frames/app.fps)*100)+'%';lane.append(playback);row.append(lane);$('audio-rows').append(row);};addRow('waveform','Waveform bins',app.audioItems('waveform'));addRow('phrase','Speech phrases',app.audioItems('phrase'));addRow('gap','Quiet gaps',app.audioItems('gap'));const disclosure=$('audio-section');if(disclosure)disclosure.open=app.state.audioOpen;
  }
  function renderDetail(){const card=app.selectedCard(),record=app.record();$('selection-message').textContent=app.state.message;$('detail-content').replaceChildren();$('detail-empty').hidden=!!record;$('detail-actions').hidden=!record;if(!record)return;$('detail-content').append(node('div',record.kind==='frame'?'Rendered frame':record.kind==='clip'?'Clip placement':record.kind==='track'?'Track':record.kind==='phrase'?'Speech phrase':record.kind==='gap'?'Quiet gap':record.kind==='waveform'?'Waveform bin':'Story placement','eyebrow'));if(card){const img=node('img');img.src=card.image;img.alt=`Selected composited frame ${card.frame}`;$('detail-content').append(img,node('h2',`${card.time_label} · frame ${card.frame}`),node('p',names(card.clips),'shot-name'),node('p',card.scripts.map(s=>s.text).join('\n')||'No script','full-script'));}else if(['phrase','gap','waveform'].includes(record.kind)){$('detail-content').append(node('h2',record.label),node('p',record.kind==='gap'?`Measured low-amplitude interval; threshold ${record.threshold??'recorded in sidecar'}.`:record.kind==='phrase'?[record.canonical_text||record.label,record.recognized_text&&`Recognized: ${record.recognized_text}`,record.uncertainty!=null&&`Uncertainty: ${record.uncertainty}`].filter(Boolean).join('\n'):'Waveform sample bounds are recorded in the sidecar.','full-script'));}else $('detail-content').append(node('h2',record.label||record.clip_id||record.id||record.kind),node('p',record.kind==='track'?'Track selected. Its placements remain part of the full composition.':'No captured image in this selection. The focus command requests this exact placement.','muted'));const technical=node('details');technical.append(node('summary','Source and selection details'));technical.append(node('pre',JSON.stringify({target:app.state.target,selection:record,active_clips:card?.clips||[],scripts:card?.scripts||[],video_digest:data.provenance.video_digest},null,2)));$('detail-content').append(technical);$('previous').disabled=!app.visibleCards().length;$('next').disabled=!app.visibleCards().length;}
  function render(){renderGrid();renderTracks();renderAudio();renderDetail();}
  for(const id of ['start','end','search','shot','track','density','mode','retain-cuts'])$(id).addEventListener('input',()=>{const values={start:$('start').value===''?null:Number($('start').value),end:$('end').value===''?null:Number($('end').value),search:$('search').value,shot:$('shot').value,track:$('track').value,density:Number($('density').value),mode:$('mode').value,retainCuts:$('retain-cuts').checked};app.update(values);if(!app.state.target)history.replaceState(null,'',location.pathname+location.search);render();});$('reset').onclick=()=>{for(const id of ['start','end','search','shot','track'])$(id).value='';app.update({start:null,end:null,search:'',shot:'',track:''});render();};
  function move(direction){app.step(direction);if(app.state.target)history.replaceState(null,'','#'+encodeURIComponent(app.state.target));render();}$('previous').onclick=()=>move(-1);$('next').onclick=()=>move(1);document.addEventListener('keydown',e=>{if(app.keyboard(e)){e.preventDefault();move(e.key==='ArrowRight'?1:-1);}});
  async function copy(value){try{await navigator.clipboard.writeText(value);$('copy-status').textContent='Copied.';}catch{$('copy-status').textContent=value;}}$('copy-target').onclick=()=>copy(app.state.target||'');$('copy-command').onclick=()=>copy(app.record()?.actions?.focus_command||'');$('copy-time').onclick=()=>copy(String(app.selectedCard()?.time_seconds??app.record()?.start_seconds??''));
  const audioSection=$('audio-section');if(audioSection){try{app.state.audioOpen=localStorage.getItem('astrid.inspector.audioOpen')==='true';}catch{}audioSection.addEventListener('toggle',()=>{app.state.audioOpen=audioSection.open;try{localStorage.setItem('astrid.inspector.audioOpen',String(audioSection.open));}catch{};});}const media=$('rendered-media');if(media&&data.media?.path){media.src=data.media.path;media.hidden=false;media.setAttribute('aria-label','Verified rendered video for this pinned render');const tick=()=>{app.setPlaybackTime(media.currentTime);syncPlayhead();if(app.state.loop&&media.currentTime>=app.state.loop.end){media.currentTime=app.state.loop.start;if(app.state.playing)media.play().catch(()=>{});}};if(typeof media.requestVideoFrameCallback==='function'){const frameTick=()=>{tick();media.requestVideoFrameCallback(frameTick);};media.requestVideoFrameCallback(frameTick);}else media.addEventListener('timeupdate',tick);media.addEventListener('play',()=>app.state.playing=true);media.addEventListener('pause',()=>app.state.playing=false);}
  $('loop-selection').onclick=()=>{app.setLoopForSelection();render();};$('clear-loop').onclick=()=>{app.clearLoop();render();};$('context-selection').onclick=()=>{const r=app.record();if(r?.actions?.seek&&media){const start=Math.max(0,r.actions.seek.start[0]/r.actions.seek.start[1]-.5);media.currentTime=start;media.play().catch(()=>{});}};window.addEventListener('hashchange',()=>{app.select(app.decodeHash(location.hash));render();seekToSelection(false);});if(location.hash)app.select(app.decodeHash(location.hash));render();syncPlayhead();
}
