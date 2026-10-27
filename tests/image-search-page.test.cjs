const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {JSDOM,VirtualConsole}=require('jsdom');const root=path.join(__dirname,'..');
function setup(opts={}){
 const errors=[],revoked=[],requests=[];let seq=0;
 let source=fs.readFileSync(path.join(root,opts.home?'index.html':'image-search.html'),'utf8');
 if(opts.omitEngine)source=source.replace(/<script src="image-search-engine.js"[^>]*><\/script>/,'');
 const html=require('./fixtures/inline-local-scripts.cjs')(source,root);
 const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
 const dom=new JSDOM(html,{runScripts:'dangerously',url:'https://mametarogg.github.io/boopadb/'+(opts.home?'index.html':'image-search.html'),pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.fetch=(url,init)=>{requests.push(url);return opts.fetch?opts.fetch(url,init,w):new Promise(()=>{});};w.scrollTo=()=>{};
  w.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});w.ResizeObserver=class{observe(){}disconnect(){}};w.IntersectionObserver=class{observe(){}disconnect(){}unobserve(){}};
  w.HTMLElement.prototype.getBoundingClientRect=()=>({width:320,height:200,left:0,top:0,right:320,bottom:200});
  w.URL.createObjectURL=()=>`blob:test-${++seq}`;w.URL.revokeObjectURL=u=>revoked.push(u);
  if(opts.lang)w.localStorage.setItem('boopadb_lang',opts.lang);if(opts.theme)w.localStorage.setItem('boopadb_theme',opts.theme);
 }});
 const w=dom.window,d=w.document,el=id=>d.getElementById(id);
 function pick(files){Object.defineProperty(el('spImgFile'),'files',{value:files,configurable:true});el('spImgFile').dispatchEvent(new w.Event('change'));}
 return {dom,w,d,el,errors,revoked,requests,pick};
}
test('standalone HTML boots all scripts in production order, without home payload or iframe',()=>{
 const s=setup();try{
  assert.deepEqual(s.errors,[]);assert.ok(s.el('imageSearchTitle').textContent);assert.equal(s.el('heroTrack'),null);assert.equal(s.d.querySelector('iframe'),null);
  assert.ok(s.el('spImgDrop'));assert.ok(s.el('lensView').hidden);assert.equal(s.requests.length,0);
  assert.equal(s.d.querySelectorAll('.image-explain article').length,3);assert.equal(s.d.querySelectorAll('.image-faq details').length,8);
  assert.notEqual(s.w.getComputedStyle(s.el('themeBtn').parentElement).display,'none');
  assert.ok(s.d.querySelector('a[href="terms.html"]'));assert.ok(s.d.querySelector('a[href="privacy.html"]'));
 }finally{s.dom.window.close();}
});
test('index boots shared engine and links to separate document; legacy hash redirects',()=>{
 const s=setup({home:true});try{
  assert.deepEqual(s.errors,[]);assert.equal(s.el('imageSearchPage'),null);assert.equal(s.el('spImageSearchEntry'),null);assert.ok(s.el('spImgBtn'));
  assert.equal(typeof s.w.lvOpen,'function');s.el('tabSearch').focus();s.w.lvOpen();assert.equal(s.d.activeElement,s.el('lvBack'));s.el('lvBack').click();assert.equal(s.d.activeElement,s.el('tabSearch'));
  const src=fs.readFileSync(path.join(root,'index.html'),'utf8');assert.match(src,/location.hash === "#image-search"\) location.replace\("image-search.html"/);
 }finally{s.dom.window.close();}
});
test('picker cancel and retake cancel keep dedicated landing; selection alone never posts image',()=>{
 const s=setup();try{
  s.pick([]);assert.equal(s.el('spImgDropError').hidden,true);assert.equal(s.el('lensView').hidden,true);
  s.pick([new s.w.File(['png'],'a.png',{type:'image/png'})]);assert.equal(s.el('lvImg').src,'blob:test-1');
  assert.ok(s.requests.every(u=>!String(u).includes(':8443')));
  s.w.lvOpen();s.el('lvRetake').click();s.pick([]);assert.equal(s.el('lensView').hidden,true);assert.equal(s.d.activeElement,s.el('spImgDrop'));assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});
test('lens keyboard focus is modal and returns to upload; bad drops give accessible error',()=>{
 const s=setup();try{
  s.el('spImgDrop').focus();s.w.lvOpen();assert.equal(s.d.activeElement,s.el('lvBack'));assert.equal(s.el('imageSearchPage').getAttribute('aria-hidden'),'true');
  s.d.dispatchEvent(new s.w.KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true,cancelable:true}));assert.ok(s.el('lensView').contains(s.d.activeElement));
  s.d.dispatchEvent(new s.w.KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true}));assert.equal(s.d.activeElement,s.el('lvBack'));
  s.d.dispatchEvent(new s.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));assert.equal(s.d.activeElement,s.el('spImgDrop'));assert.equal(s.el('imageSearchPage').hasAttribute('aria-hidden'),false);
  const e=new s.w.Event('drop',{bubbles:true,cancelable:true});Object.defineProperty(e,'dataTransfer',{value:{types:['Files'],files:[new s.w.File(['x'],'x.txt',{type:'text/plain'})]}});s.el('spImgDrop').dispatchEvent(e);assert.equal(e.defaultPrevented,true);assert.equal(s.el('spImgDropError').hidden,false);assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});
test('all locales and themes boot with FAQ; language/theme switches use existing stored keys',()=>{
 for(const lang of ['ja','en','ko','zh-Hans','zh-Hant']){const s=setup({lang,theme:'light'});try{
  assert.deepEqual(s.errors,[]);assert.equal(s.d.documentElement.lang,lang);assert.equal(s.d.documentElement.dataset.theme,'light');assert.equal(s.d.querySelectorAll('#imageFaq details').length,8);assert.match(s.el('imageUploadFormats').textContent,/20\s?MiB/);
  s.el('themeBtn').click();assert.equal(s.w.localStorage.getItem('boopadb_theme'),'dark');s.el('langMenu').querySelector('[data-lang="en"]').click();assert.equal(s.w.localStorage.getItem('boopadb_lang'),'en');
 }finally{s.dom.window.close();}}
});
test('result cards link to existing product deep-links and share bookmark storage safely',()=>{
 const s=setup();try{
  const hits=s.w.imgHitsFromApi([{item_id:'123',image:'https://example.test/x.png'},{item_id:'<script>',image:'javascript:x'}]);assert.equal(hits.length,1);
  s.w.lvShowResults(hits);assert.equal(s.el('lvResults').querySelector('a').getAttribute('href'),'index.html#item-123');
  const b=s.el('lvResults').querySelector('[data-bookmark]');b.click();assert.equal(JSON.parse(s.w.localStorage.getItem('boopadb_bm'))[0].id,'123');assert.equal(b.getAttribute('aria-pressed'),'true');b.click();assert.deepEqual(JSON.parse(s.w.localStorage.getItem('boopadb_bm')),[]);assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});
test('upload never uses dashed borders; landing and FAQ styles include narrow-screen layout',()=>{
 const css=fs.readFileSync(path.join(root,'image-search.css'),'utf8'),page=fs.readFileSync(path.join(root,'image-search-page.css'),'utf8');
 assert.doesNotMatch(css,/dashed/);assert.match(css,/focus-visible/);assert.match(page,/@media\(max-width:650px\)/);assert.match(page,/\.image-explain\{grid-template-columns:1fr/);
});

test('home initialization remains intact if shared image engine download is unavailable',()=>{
 const s=setup({home:true,omitEngine:true});try{
  assert.deepEqual(s.errors,[]);assert.ok(s.el('heroTrack').children.length>0);assert.ok(s.el('saleTrack').children.length>0);
  assert.equal(s.el('spImageSearchEntry'),null);assert.ok(s.el('spImgBtn'));
  s.w.imgSimilar({id:'1'});assert.equal(s.el('spImgDropError').hidden,false);
 }finally{s.dom.window.close();}
});

test('index similar-image results render even before full catalog prices load',()=>{
 const s=setup({home:true});try{
  s.w.lvShowResults(s.w.imgHitsFromApi([{item_id:'1000786',image:'https://example.test/test.jpg'}]));
  assert.ok(s.el('lvResults').children.length>0);assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});

test('standalone crop search posts converted image and renders mocked API results',async()=>{
 const calls=[];
 const s=setup({fetch:(url,init,w)=>{
  if(String(url).endsWith('/search')){calls.push({url,init});return Promise.resolve({ok:true,json:async()=>({results:[{item_id:'123',image:'https://example.test/result.png'}]})});}
  return new Promise(()=>{});
 }});try{
  s.w.HTMLCanvasElement.prototype.getContext=()=>({drawImage(){}});
  s.w.HTMLCanvasElement.prototype.toBlob=function(cb,type){cb(new s.w.Blob(['converted'],{type}));};
  Object.defineProperties(s.el('lvImg'),{naturalWidth:{value:400},naturalHeight:{value:300}});
  await s.w.lvRunSearch();assert.equal(calls.length,1);assert.equal(calls[0].init.method,'POST');
  const file=calls[0].init.body.get('file');assert.equal(file.name,'query.jpg');assert.equal(file.type,'image/jpeg');
  assert.ok(s.el('lvResults').querySelector('[data-id="123"]'));assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});

test('shared engine has an explicit host initialization boundary; index main is not split',()=>{
 const src=fs.readFileSync(path.join(root,'index.html'),'utf8');
 const engine=fs.readFileSync(path.join(root,'image-search-engine.js'),'utf8');
 assert.ok(engine.indexOf('function initImageLens()')<engine.indexOf('lvEl("lvBack").addEventListener'));
 const script=[...src.matchAll(/<script>([\s\S]*?)<\/script>/g)].find(m=>m[1].includes('const I18N'));
 assert.ok(script);assert.ok(script[1].includes('initImageLens()'));assert.ok(script[1].includes('let _saleIds'));
});
test('standalone header/footer reuse home markup, branding and destinations',()=>{
 const home=new JSDOM(fs.readFileSync(path.join(root,'index.html'),'utf8')).window.document;
 const s=setup({lang:'ja'});try{
  const header=s.d.querySelector('body > header'),footer=s.d.querySelector('body > footer');assert.ok(header);assert.ok(footer);
  assert.equal(header.querySelector('.logo').outerHTML,home.querySelector('header .logo').outerHTML);
  assert.equal(header.querySelector('.badge').textContent,'PROTOTYPE');
  assert.equal(header.querySelector('#themeBtn').innerHTML,home.querySelector('#themeBtn').innerHTML);
  assert.deepEqual([...header.querySelectorAll('nav a')].map(a=>a.getAttribute('href')),['index.html#sale','index.html#feat','index.html#browse2']);
  assert.deepEqual([...footer.querySelectorAll('a')].map(a=>a.getAttribute('href')),['terms.html','privacy.html','app.html']);
  for(const key of ['ft_data','ft_legal','ft_tm'])assert.equal(footer.querySelector(`[data-i="${key}"]`).textContent,home.querySelector(`[data-i="${key}"]`).textContent);
  assert.equal(s.el('imageLang'),null);assert.equal(s.el('imageTheme'),null);assert.equal(s.el('imageSearchClose'),null);assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});
test('home-style language menu supports click, keyboard Escape and localized legal text',()=>{
 const s=setup({lang:'ja'});try{
  const before=s.d.querySelector('[data-i="ft_legal"]').textContent;
  s.el('langBtn').click();assert.equal(s.el('langBtn').getAttribute('aria-expanded'),'true');
  s.d.dispatchEvent(new s.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));assert.equal(s.el('langBtn').getAttribute('aria-expanded'),'false');
  s.el('langBtn').click();s.el('langMenu').querySelector('[data-lang="en"]').click();
  assert.equal(s.el('langCur').textContent,'English');assert.equal(s.el('langBtn').getAttribute('aria-expanded'),'false');assert.equal(s.d.activeElement,s.el('langBtn'));assert.notEqual(s.d.querySelector('[data-i="ft_legal"]').textContent,before);
  s.el('langBtn').click();s.el('imageSearchTitle').click();assert.equal(s.el('langBtn').getAttribute('aria-expanded'),'false');
 }finally{s.dom.window.close();}
});
test('chrome reuses bounded responsive home rules without home sidebar negative margins',()=>{
 const css=fs.readFileSync(path.join(root,'image-search-chrome.css'),'utf8');
 assert.match(css,/\.hwrap\{max-width:1080px;[^}]*flex-wrap:wrap/);
 assert.match(css,/@media \(max-width:899px\)/);assert.match(css,/\.hwrap nav\{order:5;flex-basis:100%;margin-left:0\}/);
 assert.match(css,/@media \(max-width:359px\)\{\.hwrap \.badge\{display:none\}\}/);
 assert.match(css,/#langCur\{[^}]*max-width:72px;[^}]*text-overflow:ellipsis/);
 assert.match(css,/@media \(max-width:640px\)\{header nav\{display:none\}\}/);
 assert.doesNotMatch(css,/margin-left:-118px/);
});

test('image decode closes header language menu and makes chrome inert only while lens is open',()=>{
 const s=setup();try{
  s.el('langBtn').click();assert.ok(s.el('langMenu').classList.contains('open'));
  s.pick([new s.w.File(['png'],'a.png',{type:'image/png'})]);s.el('lvImg').onload();
  assert.equal(s.el('langMenu').classList.contains('open'),false);assert.equal(s.el('lensView').hidden,false);
  for(const n of s.d.querySelectorAll('body > header, body > footer')){assert.equal(n.hasAttribute('inert'),true);assert.equal(n.getAttribute('aria-hidden'),'true');}
  s.el('lvBack').click();for(const n of s.d.querySelectorAll('body > header, body > footer')){assert.equal(n.hasAttribute('inert'),false);assert.equal(n.hasAttribute('aria-hidden'),false);}
  assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});

test('image-search camera remains the sole search-panel upload entry',()=>{
 const src=fs.readFileSync(path.join(root,'index.html'),'utf8');
 assert.doesNotMatch(src,/id="spImageSearchEntry"|\.image-search-entry/);
 assert.match(src,/getElementById\("spImgBtn"\)\.addEventListener\("click", \(\) => \{ location.href = "image-search.html";/);
});
