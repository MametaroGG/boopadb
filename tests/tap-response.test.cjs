const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM, VirtualConsole} = require('jsdom');
const root = path.join(__dirname, '..');
function boot(file) {
  let html = fs.readFileSync(path.join(root, file), 'utf8');
  html = require('./fixtures/inline-local-scripts.cjs')(html, root);
  const errors = [];
  const vc = new VirtualConsole(); vc.on('jsdomError', e => errors.push(e.message));
  const dom = new JSDOM(html, {runScripts:'dangerously', url:'https://mametarogg.github.io/boopadb/'+file+(file === 'item.html' ? '?id=999999999' : ''),
    pretendToBeVisual:true, virtualConsole:vc, beforeParse(w){
      w.fetch = () => new Promise(() => {});
      w.matchMedia = () => ({matches:false, addEventListener(){}, addListener(){}});
      w.ResizeObserver = class {observe(){} disconnect(){}};
      w.IntersectionObserver = class {observe(){} disconnect(){} unobserve(){}};
      w.HTMLElement.prototype.getBoundingClientRect = () => ({width:320,height:200,left:0,top:0,right:320,bottom:200});
      w.scrollTo = () => {};
    }});
  return {dom, errors};
}
function pointer(w, target, type, pointerType='touch', pointerId=7) {
  const event = new w.Event(type, {bubbles:type !== 'pointerenter', cancelable:true});
  Object.defineProperties(event, {pointerType:{value:pointerType}, pointerId:{value:pointerId}});
  target.dispatchEvent(event);
  assert.equal(event.defaultPrevented, false, 'native events remain uncancelled');
}
for (const file of ['index.html', 'item.html']) {
 test(file+': native tap stays clickable through late scroll, cancel and repeated taps', () => {
  const {dom,errors}=boot(file), w=dom.window, d=w.document;
  try {
    const nav=d.getElementById('tabbar'), search=d.getElementById('tabSearch');
    let now = 1000; w.Date.now = () => now;
    pointer(w,search,'pointerdown');
    w.eval('onAnyScroll(200, null)');
    assert.equal(nav.classList.contains('hide'),false);
    pointer(w,search,'pointerup');
    w.eval('onAnyScroll(400, null)');
    assert.equal(nav.classList.contains('hide'),false);
    search.click();
    assert.equal(d.getElementById('searchPage').classList.contains('open'),true);
    pointer(w,search,'pointerdown'); pointer(w,search,'pointerup'); search.click();
    assert.equal(d.getElementById('searchPage').classList.contains('open'),false);
    now += 401; w.eval('onAnyScroll(500, null)');
    assert.equal(nav.classList.contains('hide'),true,'ordinary scroll hiding resumes after grace expires');
    pointer(w,search,'pointerdown'); pointer(w,search,'pointercancel');
    w.eval('onAnyScroll(600, null)');
    assert.equal(nav.classList.contains('hide'),true,'normal scroll hide resumes after cancellation');
    pointer(w,search,'pointerdown');
    w.dispatchEvent(new w.Event('blur'));
    w.eval('onAnyScroll(800, null)');
    assert.equal(nav.classList.contains('hide'),true,'blur releases interaction lock');
    // Releasing/cancelling a second finger must not unlock the first finger.
    pointer(w,search,'pointerdown','touch',7);
    pointer(w,search,'pointerdown','touch',8);
    pointer(w,search,'pointerup','touch',8);
    now += 401; w.eval('onAnyScroll(1000, null)');
    assert.equal(nav.classList.contains('hide'),false);
    pointer(w,search,'pointerdown','touch',8);
    pointer(w,search,'pointercancel','touch',8);
    w.eval('onAnyScroll(1200, null)');
    assert.equal(nav.classList.contains('hide'),false);
    pointer(w,search,'pointercancel','touch',7);
    w.eval('onAnyScroll(1400, null)');
    assert.equal(nav.classList.contains('hide'),true);
    assert.deepEqual(errors,[]);
  } finally {dom.window.close();}
 });
 test(file+': browse touch and compatibility mouseenter do not replace preview; mouse hover does', () => {
  const {dom,errors}=boot(file), w=dom.window, d=w.document;
  try {
    const row=d.querySelectorAll('#bList .brow')[1], preview=d.getElementById('bPrev');
    assert.ok(row);
    const first=preview.firstChild;
    pointer(w,row,'pointerenter','touch');
    row.dispatchEvent(new w.MouseEvent('mouseenter'));
    assert.equal(preview.firstChild,first);
    pointer(w,row,'pointerenter','pen');
    assert.equal(preview.firstChild,first);
    pointer(w,row,'pointerenter','mouse');
    assert.notEqual(preview.firstChild,first);
    assert.deepEqual(errors,[]);
  } finally {dom.window.close();}
 });
}
