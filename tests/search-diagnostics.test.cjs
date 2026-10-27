const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM} = require('jsdom');
const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const script = html.match(/<script id="boopadb-diagnostics">([\s\S]*?)<\/script>/)[1];
function create(query) {
  const dom = new JSDOM('<body><div id="searchPage"><div class="sp-inner"><div class="sp-search"><input id="spQ" value="PRIVATE QUERY"><button id="spImgBtn"></button></div></div></div></body>', {url:'https://example.test/'+query, runScripts:'outside-only'});
  const w = dom.window;
  w.HTMLElement.prototype.getBoundingClientRect = () => ({left:122,right:1064,width:942,height:48});
  Object.defineProperty(w.HTMLElement.prototype,'clientWidth',{get:()=>942});
  Object.defineProperty(w.HTMLElement.prototype,'scrollWidth',{get:()=>1100});
  w.fetch = () => {throw Error('Diagnostics must not use network');};
  w.eval(script);
  w.document.dispatchEvent(new w.Event('DOMContentLoaded'));
  return dom;
}
test('search diagnostic measurements are opt-in and include no query values', () => {
  const off=create('');
  assert.equal(off.window.document.querySelector('aside'),null);
  off.window.close();
  const on=create('?diagnostics=1');
  const text=on.window.document.querySelector('aside pre').textContent;
  assert.match(text, /#searchPage .sp-search: x=122\.\.1064 w=942 client\/scroll=942\/1100/);
  assert.match(text, /#spQ: x=/);
  assert.match(text, /#spImgBtn: x=/);
  assert.ok(!text.includes('PRIVATE QUERY'));
  assert.equal(on.window.localStorage.length,0);
  assert.equal(on.window.sessionStorage.length,0);
  on.window.close();
});
