const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync(require.resolve('../src/ReviewOverlay.tsx'), 'utf8');
const compiled = ts.transpileModule(source, {compilerOptions: {module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX}}).outputText;
const exportsObject = {};
vm.runInNewContext(compiled, {exports: exportsObject, require});
const {reviewLabel} = exportsObject;
const review = {shots: [
  {shot_id: 'a', name: '01 Opening', at: 0, hold: 1},
  {shot_id: 'b', name: '02 Detail', at: 1, hold: 2},
  {shot_id: 'c', name: '03 Overlap', at: 2, hold: 1},
]};
assert.equal(reviewLabel(review, 0, 30), '01 Opening  ·  00:00:00.000');
assert.equal(reviewLabel(review, 29, 30), '01 Opening  ·  00:00:00.966');
assert.equal(reviewLabel(review, 30, 30), '02 Detail  ·  00:00:01.000');
assert.equal(reviewLabel(review, 60, 30), '02 Detail / 03 Overlap  ·  00:00:02.000');
assert.equal(reviewLabel(review, 90, 30), 'No shot  ·  00:00:03.000');
assert.equal(reviewLabel({shots: []}, 108030, 30), 'No shot  ·  01:00:01.000');
console.log('Review overlay boundaries, clock, overlaps, gaps passed');
