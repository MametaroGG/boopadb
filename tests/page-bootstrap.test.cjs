// Test-only dependency shared with image-drop.test.cjs: jsdom@26.1.0.
// Execute the WHOLE page, preserving declaration order (no renderer stubs).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM, VirtualConsole} = require('jsdom');
test('complete home page starts with six hero products and no runtime errors', async () => {
  const html = fs.readFileSync(process.env.HERO_TEST_HTML || path.join(__dirname, '..', 'index.html'), 'utf8');
  const errors = [], observers = [];
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(e.message));
  const dom = new JSDOM(html, {runScripts:'dangerously', url:'https://mametarogg.github.io/boopadb/',
    pretendToBeVisual:true, virtualConsole:vc, beforeParse(w){
      // Keep network pending: first paint must work before any JSON response.
      w.fetch = () => new Promise(() => {});
      w.matchMedia = () => ({matches:false, addEventListener(){}, addListener(){}});
      w.ResizeObserver = class {observe(){} disconnect(){}};
      w.IntersectionObserver = class {observe(){} disconnect(){} unobserve(){}};
      w.HTMLElement.prototype.getBoundingClientRect = () => ({width:320,height:200,left:0,top:0,right:320,bottom:200});
      const MO = w.MutationObserver;
      w.MutationObserver = class extends MO {constructor(cb){super(cb);observers.push(this);}};
    }});
  try {
    await new Promise(resolve => setTimeout(resolve, 30));
    assert.deepEqual(errors, []);
    const d = dom.window.document;
    assert.equal(d.querySelectorAll('#heroTrack .hslide:not([data-clone])').length, 6);
    assert.equal(d.querySelectorAll('#heroTrack .hslide').length, 8);
    assert.equal(d.querySelectorAll('#heroDots button').length, 6);
    assert.equal(d.querySelectorAll('#heroTrack .pp-likes').length, 8);
    assert.ok(d.querySelector('#heroTrack .hname').textContent.trim());
    assert.ok(d.querySelector('#saleTrack').children.length > 0);
  } finally { observers.forEach(o => o.disconnect()); dom.window.close(); }
});
