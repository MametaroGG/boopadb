// Test-only dependency shared with image-drop.test.cjs: jsdom@26.1.0.
// Execute the WHOLE page, preserving declaration order (no renderer stubs).
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM, VirtualConsole} = require('jsdom');
test('complete home page starts and enriches hero metadata without initialization errors', async () => {
  let html = fs.readFileSync(process.env.HERO_TEST_HTML || path.join(__dirname, '..', 'index.html'), 'utf8');
  html = require("./fixtures/inline-local-scripts.cjs")(html, path.join(__dirname, ".."));
  const errors = [], observers = [], caught = [];
  // Observe swallowed exceptions too; leave the original catch body intact.
  html = html.replace(/catch\s*\((\w+)\)\s*\{/g, (all, name) =>
    all + ` window.__recordCaughtBootstrapError(${name});`);
  html = html.replace(/catch\s*\{/g, 'catch (__caught) { window.__recordCaughtBootstrapError(__caught);');
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(e.message));
  const dom = new JSDOM(html, {runScripts:'dangerously', url:'https://mametarogg.github.io/boopadb/',
    pretendToBeVisual:true, virtualConsole:vc, beforeParse(w){
      w.__recordCaughtBootstrapError = e => caught.push(String(e));
      // Full catalog stays pending; hero enrichment must work after script init.
      w.fetch = url => String(url).includes('/meta/')
        ? Promise.resolve({ok:true, json:async () => ({likes:123456, tags:['startup-meta-test']})})
        : new Promise(() => {});
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
    assert.deepEqual(caught, []);
    const d = dom.window.document;
    assert.equal(d.querySelectorAll('#heroTrack .hslide:not([data-clone])').length, 6);
    assert.equal(d.querySelectorAll('#heroTrack .hslide').length, 8);
    assert.equal(d.querySelectorAll('#heroDots button').length, 6);
    assert.equal(d.querySelectorAll('#heroTrack .pp-likes').length, 8);
    assert.ok(d.querySelector('#heroTrack .hname').textContent.trim());
    assert.ok(d.querySelector('#saleTrack').children.length > 0);
    // Exercise actual input/clear handlers and a programmatically restored query.
    const query = d.getElementById('spQ'), clear = d.getElementById('spClear');
    dom.window.eval('openSearch()');
    assert.equal(clear.hidden, true);
    assert.equal(query.parentElement.classList.contains('has-query'), false);
    query.value = 'avatar'; query.dispatchEvent(new dom.window.Event('input'));
    assert.equal(clear.hidden, false);
    assert.equal(query.parentElement.classList.contains('has-query'), true);
    clear.click();
    assert.equal(query.value, '');
    assert.equal(clear.hidden, true);
    assert.equal(query.parentElement.classList.contains('has-query'), false);
    query.value = '  '; query.dispatchEvent(new dom.window.Event('input'));
    assert.equal(clear.hidden, true);
    assert.equal(query.parentElement.classList.contains('has-query'), false);
    query.value = 'restored query'; dom.window.eval('openSearch()');
    assert.equal(clear.hidden, false);
    assert.equal(query.parentElement.classList.contains('has-query'), true);
    assert.deepEqual(errors, []);
    assert.deepEqual(caught, []);

    for (const el of d.querySelectorAll('#heroTrack .hmeta')) {
      assert.ok(el.textContent.includes('123,456'));
      assert.ok(el.textContent.includes('startup-meta-test'));
    }
  } finally { observers.forEach(o => o.disconnect()); dom.window.close(); }
});
