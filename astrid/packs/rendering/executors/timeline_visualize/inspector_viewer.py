"""Self-contained offline timeline inspector assembled from local assets."""
from pathlib import Path
import json

_ASSETS = Path(__file__).with_name('inspector_assets')


def render_inspector(index: dict, *, columns: int = 5) -> str:
    """Images in index must already be embedded data URLs."""
    payload = json.dumps(index, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    style = (_ASSETS / 'inspector.css').read_text()
    style += '#inspector .timeline-playhead{position:absolute;top:0;bottom:0;width:2px;background:#f7b267;pointer-events:none;z-index:3}#inspector .audio-ruler{margin-top:8px}'
    return _DOCUMENT.replace('__STYLE__', style).replace('__SCRIPT__', (_ASSETS / 'inspector.js').read_text()).replace('__COLUMNS__', str(max(1, min(12, columns)))).replace('__DATA__', payload)


_DOCUMENT = '''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Timeline inspector</title><style>__STYLE__</style></head><body style="margin:0"><div id="inspector" style="--columns:__COLUMNS__">
<header><div class="topline"><div><div class="eyebrow">Timeline inspector · rendered composition</div><h1 id="title"></h1><p id="provenance" class="muted"></p></div><span id="frozen"></span></div><p id="warnings" role="status"></p><video id="rendered-media" controls hidden preload="metadata"></video>
<div class="filters"><label>Dialogue<input id="search" type="search" placeholder="Find script text"></label><label>Shot<select id="shot"><option value="">All shots</option></select></label><label>Track<select id="track"><option value="">All tracks</option></select></label><label>From (s)<input id="start" type="number" step="any"></label><label>To (s)<input id="end" type="number" step="any"></label><label>Samples<select id="mode"></select></label><label>Density<select id="density"></select></label><label class="check"><input id="retain-cuts" type="checkbox" checked>Retain cut neighbors</label><button id="reset">Reset filters</button></div><p id="capture" class="muted"></p></header>
<details id="track-section"><summary>Show tracks</summary><p class="track-note">Placements in the frozen render. Audio lanes show clip timing, not waveforms. Selecting a track or clip inspects the full composited image; it does not isolate a layer. Dimmed clips are outside the shared filters.</p><div id="lanes"></div></details><details id="audio-section"><summary>Speech and audio</summary><p id="audio-status" class="track-note"></p><div id="audio-rows"></div><div class="actions"><button id="context-selection" type="button">Audition selection</button><button id="loop-selection" type="button">Loop selection</button><button id="clear-loop" type="button">Clear loop</button></div></details>
<div class="workspace"><main class="collection"><div id="count" aria-live="polite"></div><div id="grid"></div></main><aside id="detail" aria-label="Selection details"><div class="detail-nav"><button id="previous" aria-label="Previous captured frame">← Previous</button><button id="next" aria-label="Next captured frame">Next →</button></div><p id="selection-message" role="status"></p><div id="detail-empty"><h2>Inspect a moment</h2><p class="muted">Select a frame or clip. Use left and right arrow keys to move through the captured frames.</p></div><div id="detail-content"></div><div id="detail-actions" hidden><div class="actions"><button id="copy-time">Copy time</button><button id="copy-target">Copy exact target</button><button id="copy-command">Copy focus command</button></div><div id="copy-status" role="status"></div></div></aside></div>
<p class="footer-note">Authored script segments are not word-aligned transcription. “No script” does not establish acoustic silence. Exact targets belong to this pinned inspector and are distinct from structural --from-view references.</p></div><script id="inspector-data" type="application/json">__DATA__</script><script>__SCRIPT__</script></body></html>'''
