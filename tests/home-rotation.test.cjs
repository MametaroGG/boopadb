const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {JSDOM, VirtualConsole} = require('jsdom');
const root = path.resolve(__dirname, '..');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const full = JSON.parse(fs.readFileSync(path.join(root, 'lists_full.json'), 'utf8'));
const selector = html.match(/\/\/ HERO_SELECTOR_START[^\n]*\n([\s\S]*?)\/\/ HERO_SELECTOR_END/)[1];
const sixHours = 21600000;
function api(now) {
  let clock = now;
  class Clock extends Date {static now(){return clock;}}
  const ctx = vm.createContext({Date: Clock});
  const f = vm.runInContext(selector + '\n({selectHeroEntries,selectFeaturedEntries,homeCandidatePools})', ctx);
  f.tick = n => { clock = n; }; return f;
}
const ids = list => Array.from(list, x => String(x.item ? x.item.id : x.id));
function shops(list){const n = {}; for(const x of list){const item=x.item || x;if(item.shop)n[item.shop]=(n[item.shop]||0)+1;}return Object.values(n);}
test('real catalog rotates at six-hour boundary, but freezes existing visit', () => {
  const boundary = Date.UTC(2026,9,28,18);
  const before = api(boundary-1), after = api(boundary);
  const old = ids(before.selectHeroEntries(full));
  assert.deepEqual(ids(api(boundary-sixHours).selectHeroEntries(full)), old);
  assert.deepEqual(ids(api(boundary-1).selectHeroEntries(full)), old);
  assert.notDeepEqual(ids(after.selectHeroEntries(full)), old);
  before.tick(boundary + sixHours);
  assert.deepEqual(ids(before.selectHeroEntries(full)), old);
  assert.notDeepEqual(ids(before.selectFeaturedEntries(full,before.selectHeroEntries(full))), ids(after.selectFeaturedEntries(full,after.selectHeroEntries(full))));
});
test('real catalog pools: 120 consecutive windows preserve variety, uniqueness and source prices', () => {
  const f=api(0), pools=f.homeCandidatePools(full);
  for(let window=82000;window<82120;window++){
    const hero=f.selectHeroEntries(full,window), featured=f.selectFeaturedEntries(full,hero,window);
    assert.equal(hero.length,6);assert.equal(featured.length,10);
    assert.deepEqual(Array.from(hero,x=>x.kind),['new','sale','new','sale','new','sale']);
    assert.equal(new Set([...ids(hero),...ids(featured)]).size,16);
    assert.ok(shops(hero).every(n=>n<=2));assert.ok(shops(featured).every(n=>n<=2));
    assert.deepEqual(ids(hero),ids(f.selectHeroEntries(pools,window)));
    assert.deepEqual(ids(featured),ids(f.selectFeaturedEntries(pools,hero,window)));
    for(const {kind,item} of hero){const original=full[kind==='sale'?'on_sale':'newest'].find(x=>String(x.id)===String(item.id));assert.equal(item.cur,original.cur);assert.equal(item.base,original.base);}
  }
});
test('empty, duplicate, invalid and shop-concentrated pools degrade without unsafe prices',()=>{
  const f=api(0), item={id:'1',image:'x',likes:1,base:100,cur:0,shop:'same'};
  const empty={newest:[],on_sale:[]};
  assert.equal(f.selectHeroEntries(empty).length,0);assert.equal(f.selectFeaturedEntries(empty,[]).length,0);
  const concentrated={newest:Array.from({length:20},(_,id)=>({...item,id})),on_sale:[]};
  assert.equal(f.selectHeroEntries(concentrated).length,2);
  const broken={newest:[item,item,{...item,id:2,cur:-1},{...item,id:3,base:NaN},{...item,id:4,likes:Infinity},null],on_sale:[item]};
  assert.deepEqual(ids(f.selectHeroEntries(broken)),['1']);
  assert.equal(f.selectFeaturedEntries(broken,f.selectHeroEntries(broken)).length,0);
  assert.equal(f.selectHeroEntries(broken)[0].item.cur,0);
});
test('all inline page scripts parse',()=>{
  for(const file of fs.readdirSync(root).filter(x=>x.endsWith('.html'))){
    const page=fs.readFileSync(path.join(root,file),'utf8');
    for(const match of page.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/gi)){
      if(/src=|application\//i.test(match[1]))continue;
      assert.doesNotThrow(()=>new vm.Script(match[2],{filename:file}));
    }
  }
});
test('whole home page keeps both initial tracks when delayed full catalog arrives across boundary',async()=>{
  const errors=[],caught=[],observers=[];let deliver;
  let source=require('./fixtures/inline-local-scripts.cjs')(html,root);
  source=source.replace(/catch\s*\((\w+)\)\s*\{/g,(all,name)=>all+` window.__caught(${name});`).replace(/catch\s*\{/g,'catch (__error) { window.__caught(__error);');
  const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
  const boundary=Date.UTC(2026,9,28,18);let now=boundary-1;
  const dom=new JSDOM(source,{runScripts:'dangerously',url:'https://mametarogg.github.io/boopadb/',pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
    w.Date.now=()=>now;w.__caught=e=>caught.push(String(e));
    w.fetch=url=>String(url).startsWith('lists_full.json')?new Promise(resolve=>{deliver=()=>resolve({ok:true,json:async()=>structuredClone(full)});}):new Promise(()=>{});
    w.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
    w.ResizeObserver=class{observe(){}disconnect(){}};w.IntersectionObserver=class{observe(){}disconnect(){}unobserve(){}};
    w.HTMLElement.prototype.getBoundingClientRect=()=>({width:320,height:200,left:0,top:0,right:320,bottom:200});
    const MO=w.MutationObserver;w.MutationObserver=class extends MO{constructor(cb){super(cb);observers.push(this);}};
  }});
  try{
    const d=dom.window.document;
    const hero=[...d.querySelector('#heroTrack').children],featured=[...d.querySelector('#featTrack').children];
    assert.equal(hero.length,8);assert.equal(featured.length,10);
    now=boundary+1;deliver();await new Promise(r=>setTimeout(r,50));
    assert.deepEqual([...d.querySelector('#heroTrack').children],hero);
    assert.deepEqual([...d.querySelector('#featTrack').children],featured);
    assert.deepEqual(errors,[]);assert.deepEqual(caught,[]);
  }finally{observers.forEach(o=>o.disconnect());dom.window.close();}
});
