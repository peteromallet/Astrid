const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');

const source = fs.readFileSync(require.resolve('../src/asset-source.ts'), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: {module: ts.ModuleKind.CommonJS},
}).outputText;
const exportsObject = {};
vm.runInNewContext(compiled, {
  exports: exportsObject,
  require(name) {
    assert.equal(name, 'remotion');
    return {
      staticFile(file) {
        if (/^https?:\/\//.test(file)) {
          throw new TypeError('staticFile() does not support remote URLs');
        }
        return `/public/${file}`;
      },
    };
  },
});

const {resolveInvocationAsset} = exportsObject;
const loopback = 'http://127.0.0.1:49555/0000-ae57f24cfc0d-sha256_asset';
assert.equal(resolveInvocationAsset(loopback), loopback);
assert.equal(resolveInvocationAsset('fonts/Inter.woff2'), '/public/fonts/Inter.woff2');
assert.throws(
  () => resolveInvocationAsset('https://example.invalid/media.mp4'),
  /staticFile\(\) does not support remote URLs/,
);
console.log('Invocation asset URL resolution passed');
