const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const root = path.join(__dirname, '..');
const pages = fs.readdirSync(root).filter(f => f.endsWith('.html') && fs.readFileSync(path.join(root,f),'utf8').includes('const _wdImgs'));
function blocks(file) {
  return [...fs.readFileSync(path.join(root,file),'utf8').matchAll(/\(function startImageWatchdog\(\)\{[\s\S]*?wdScanAll\(document.body\);\n\}\)\(\);/g)].map(m=>m[0]);
}
function harness() {
  let now=0, timers=[], observers=[], replacements=[];
  function img(src='https://booth.pximg.net/a.jpg') {return {nodeType:1,tagName:'IMG',src,isConnected:true,complete:false,getAttribute(){return this.src},setAttribute(k,v){this.src=v},getBoundingClientRect(){return {top:10,bottom:100,width:100}},cloneNode(){return img(this.src)},replaceWith(c){this.isConnected=false;replacements.push(c)}}}
  const initial=img();
  const context=vm.createContext({window:{},Map,Date:{now:()=>now},innerHeight:700,setInterval(fn){timers.push(fn)},MutationObserver:class{constructor(fn){this.fn=fn;observers.push(this)}observe(){}},document:{body:{nodeType:1,tagName:'BODY',querySelectorAll:()=>[initial]},documentElement:{}}});
  return {context,timers,observers,replacements,initial,img,tick(){now+=10000;timers.forEach(fn=>fn())}};
}
test('all watchdogs isolate Map and helper declarations in function scope',()=>{
  assert.equal(pages.length,11);
  for(const page of pages){ const source=fs.readFileSync(path.join(root,page),'utf8');assert.equal(blocks(page).length,(source.match(/const _wdImgs = new Map\(\)/g)||[]).length,page);assert(!source.includes('if (!window.__wdOn) {'),page); }
});
test('each generated page starts once, including duplicate injected watchdogs',()=>{
  for(const page of pages){const h=harness();for(const code of blocks(page))vm.runInContext(code,h.context);assert.equal(h.timers.length,1,page);assert.equal(h.observers.length,1,page);assert.equal(typeof h.context.wdReg,'undefined',page);h.tick();assert.equal(h.replacements.length,1,page);}
});
test('incomplete image retries twice; second retry bypasses a stuck URL',()=>{
 const h=harness();vm.runInContext(blocks('index.html')[0],h.context);h.tick();assert.equal(h.replacements.length,1);assert(!h.replacements[0].src.includes('wd=1'));h.tick();assert.equal(h.replacements.length,2);assert(h.replacements[1].src.endsWith('?wd=1'));h.tick();assert.equal(h.replacements.length,2);
});
test('completed images are not retried',()=>{const h=harness();h.initial.complete=true;vm.runInContext(blocks('index.html')[0],h.context);h.tick();assert.equal(h.replacements.length,0)});
test('new image nodes use the same private registration Map',()=>{const h=harness();h.initial.complete=true;vm.runInContext(blocks('index.html')[0],h.context);h.observers[0].fn([{addedNodes:[h.img()]}]);h.tick();assert.equal(h.replacements.length,1)});
