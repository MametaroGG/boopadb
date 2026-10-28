const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');const root=path.join(__dirname,'..');
function setup(opts={}){
 const errors=[],revoked=[],requests=[],caught=[];let seq=0;
 let source=fs.readFileSync(path.join(root,opts.home?'index.html':'image-search.html'),'utf8');
 if(opts.omitEngine)source=source.replace(/<script src="image-search-engine.js(?:\?[^"]*)?"[^>]*><\/script>/,'');
 let html=require('./fixtures/inline-local-scripts.cjs')(source,root);
 if(opts.captureCaught)html=html.replace(/catch\s*\((\w+)\)\s*\{/g,(all,name)=>all+`window.__recordCaught(${name});`).replace(/catch\s*\{/g,'catch(__e){window.__recordCaught(__e);');
 const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
 const dom=new JSDOM(html,{runScripts:'dangerously',url:'https://mametarogg.github.io/boopadb/'+(opts.home?'index.html':'image-search.html'),pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.__recordCaught=e=>caught.push(String(e));
  w.HTMLCanvasElement.prototype.getContext=()=>new Proxy({measureText:()=>({width:10})},{get:(o,k)=>k in o?o[k]:(()=>{})});
  w.fetch=(url,init)=>{requests.push(url);return opts.fetch?opts.fetch(url,init,w):new Promise(()=>{});};w.scrollTo=()=>{};
  w.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});w.ResizeObserver=class{observe(){}disconnect(){}};w.IntersectionObserver=class{observe(){}disconnect(){}unobserve(){}};
  w.HTMLElement.prototype.getBoundingClientRect=()=>({width:320,height:200,left:0,top:0,right:320,bottom:200});
  w.URL.createObjectURL=()=>`blob:test-${++seq}`;w.URL.revokeObjectURL=u=>revoked.push(u);
  if(opts.lang)w.localStorage.setItem('boopadb_lang',opts.lang);if(opts.theme)w.localStorage.setItem('boopadb_theme',opts.theme);
 }});
 const w=dom.window,d=w.document,el=id=>d.getElementById(id);
 function pick(files){Object.defineProperty(el('spImgFile'),'files',{value:files,configurable:true});el('spImgFile').dispatchEvent(new w.Event('change'));}
 return {dom,w,d,el,errors,revoked,requests,caught,pick};
}
const rawParts=Array.from({length:24},(_,i)=>JSON.parse(fs.readFileSync(path.join(root,'search_index_'+i+'.json'),'utf8'))),raw=rawParts.flat();
const lists=JSON.parse(fs.readFileSync(path.join(root,'lists_full.json'),'utf8'));
const tick=()=>new Promise(r=>setTimeout(r,0));
function realSetup(opts={}){return setup({home:true,...opts,fetch:url=>{const u=String(url),m=u.match(/^search_index_(\d+)\.json/);if(m)return opts.part?opts.part(Number(m[1])):Promise.resolve({ok:true,json:async()=>rawParts[Number(m[1])]});if(u.startsWith('lists_full.json'))return Promise.resolve({ok:true,json:async()=>lists});return new Promise(()=>{});}});}
test('real all-catalog count survives relevance, filters, sorts, category ordering, query, shop and reset',async()=>{
 const s=realSetup({captureCaught:true});try{
  await tick();s.w.openSearch();await s.w.loadFullIndex();assert.equal(s.w.eval('spTotal'),raw.length);assert.equal(raw.length,200891);assert.equal(s.el('spCatalogStatus').hidden,true);s.w.eval('HIST=[{id:"999999999999",name:"Removed item"}];spRender()');assert.equal(s.w.eval('spTotal'),raw.length);
  s.el('spQ').value='ガスマスクソルジャー';s.w.eval('spMaxPrice=500;spRender()');assert.equal(s.w.eval('spTotal'),0);s.el('spQ').value='';s.w.eval('spMaxPrice=null;spRender()');
  const total=()=>s.w.eval('spTotal');const chip=f=>s.d.querySelector('#spChips [data-f="'+f+'"]').click();
  chip('free');assert.equal(total(),raw.filter(r=>r[2]===0).length);assert.equal(total(),39394);
  const category='3Dテクスチャ 3Dモデル',chooseCat=()=>[...s.d.querySelectorAll('#spKw [data-cat]')].find(n=>n.dataset.cat===category).click();
  chooseCat();assert.equal(s.w.eval('spFilter'),'free');assert.equal(total(),raw.filter(r=>r[2]===0&&r[7]===category).length);assert.equal(total(),4107);
  chip('all');chip('free');assert.equal(s.w.eval('spCatMode'),category);assert.equal(total(),4107);
  s.el('spFilterReset').click();assert.equal(s.w.eval('spCatMode'),null);assert.equal(total(),raw.length);
  s.el('spPrice').value='0';s.el('spPrice').dispatchEvent(new s.w.Event('input'));s.w.spRender();assert.equal(total(),raw.filter(r=>r[2]!=null&&r[2]<=s.w.eval('SP_CAPS[0]')).length);s.w.eval('spMaxPrice=0;spRender()');assert.equal(total(),39394);
  s.el('spFilterReset').click();for(const sort of ['price_asc','price_desc','new','pop','rel']){s.d.querySelector('#spSortMenu [data-sort="'+sort+'"]').click();assert.equal(total(),raw.length);}
  for(const f of ['sale','lowest','free']){chip(f);const pred=f==='sale'?r=>!!r[5]:f==='lowest'?r=>!!r[6]:r=>r[2]===0;assert.equal(total(),raw.filter(pred).length);}
  s.el('spFilterReset').click();chooseCat();chip('free');s.el('spQ').value='ミルフィ';s.el('spQ').dispatchEvent(new s.w.Event('input'));assert.equal(s.w.eval('spCatMode'),category);
  const text=r=>(r[1]+'\u0001'+(r[12]||'')+'\u0001'+(r[13]||'')).toLowerCase().normalize('NFKC');assert.equal(total(),raw.filter(r=>r[7]===category&&r[2]===0&&(text(r).includes('ミルフィ')||r[7].includes('ミルフィ'))).length);
  s.el('spClear').click();assert.equal(total(),4107);s.el('spFilterReset').click();assert.equal(total(),raw.length);
  const shop=raw.find(r=>r[0]==='8167254')[12];s.w.openSearchShop(shop);assert.equal(total(),raw.filter(r=>r[12]===shop).length);assert.doesNotMatch(s.el('spCount').textContent,/200891/);chip('free');assert.equal(total(),raw.filter(r=>r[12]===shop&&r[2]===0).length);
  s.el('spFilterReset').click();assert.equal(s.w.eval('spShopMode'),null);assert.equal(total(),raw.length);
  assert.deepEqual(s.errors,[]);assert.deepEqual(s.caught,[]);
 }finally{s.dom.window.close();}
});
test('8780 fallback is explicitly partial; four concurrent shards and full count after load',async()=>{
 let release=false,active=0,peak=0;const pending=[];const s=realSetup({part:i=>{active++;peak=Math.max(peak,active);const answer=resolve=>{active--;resolve({ok:true,json:async()=>rawParts[i]});};return new Promise(resolve=>release?answer(resolve):pending.push(()=>answer(resolve)));}});
 try{await tick();s.w.openSearch();assert.equal(s.w.eval('spTotal'),8780);assert.match(s.el('spCount').textContent,/Partial/);assert.equal(s.el('spCatalogStatus').hidden,false);assert.equal(pending.length,4);
  release=true;pending.forEach(done=>done());await s.w.loadFullIndex();assert.equal(s.w.eval('spTotal'),200891);assert.ok(peak<=4);assert.equal(s.el('spCatalogStatus').hidden,true);assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});
test('failed shard shows retry and preserves successful downloads; next attempt fetches only the missing shard',async()=>{
 const counts=Array(24).fill(0);let fail=true;const s=realSetup({part:i=>{counts[i]++;return Promise.resolve(i===7&&fail?{ok:false}:{ok:true,json:async()=>rawParts[i]});}});
 try{await tick();s.w.openSearch();await s.w.loadFullIndex();assert.equal(s.w.eval('fullIndex'),null);assert.equal(s.el('spCatalogRetry').hidden,false);assert.match(s.el('spCount').textContent,/Partial/);assert.equal(counts[7],2);assert.equal(counts[0],1);s.w.eval('spSort="name";spRender()');await tick();assert.equal(counts[7],2);
  fail=false;s.el('spCatalogRetry').click();await s.w.loadFullIndex();assert.equal(counts[7],3);assert.equal(counts[0],1);assert.equal(s.w.eval('spTotal'),200891);assert.equal(s.el('spCatalogRetry').hidden,true);assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});

test('hung shard times out and retries without discarding completed parts',async()=>{
 let tries=0;const s=realSetup({part:i=>i===3&&tries++===0?new Promise(()=>{}):Promise.resolve({ok:true,json:async()=>rawParts[i]})});
 try{const original=s.w.setTimeout.bind(s.w);s.w.setTimeout=(fn,ms,...args)=>original(fn,ms===30000?5:ms,...args);s.w.openSearch();await s.w.loadFullIndex();assert.equal(tries,2);assert.equal(s.w.eval('spTotal'),raw.length);assert.equal(s.el('spCatalogRetry').hidden,true);assert.deepEqual(s.errors,[]);}finally{s.dom.window.close();}
});
