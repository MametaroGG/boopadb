const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {JSDOM, VirtualConsole} = require('jsdom');
function setup(hash='') {
 let html=fs.readFileSync(path.join(__dirname,'../index.html'),'utf8');
 html=html.replace('<script src="image-drop.js"></script>',()=>'<script>'+fs.readFileSync(path.join(__dirname,'../image-drop.js'),'utf8')+'</script>');
 const errors=[], revoked=[];let n=0;
 const vc=new VirtualConsole();vc.on('jsdomError',e=>errors.push(e.message));
 const dom=new JSDOM(html,{runScripts:'dangerously',url:'https://mametarogg.github.io/boopadb/'+hash,pretendToBeVisual:true,virtualConsole:vc,beforeParse(w){
  w.fetch=()=>new Promise(()=>{});w.scrollTo=()=>{};
  w.matchMedia=()=>({matches:false,addEventListener(){},addListener(){}});
  w.ResizeObserver=class{observe(){} disconnect(){}};
  w.IntersectionObserver=class{observe(){} disconnect(){} unobserve(){}};
  w.HTMLElement.prototype.getBoundingClientRect=()=>({width:320,height:200,left:0,top:0,right:320,bottom:200});
  w.URL.createObjectURL=()=>`blob:test-${++n}`;w.URL.revokeObjectURL=u=>revoked.push(u);
 }});
 const w=dom.window,d=w.document,el=id=>d.getElementById(id);
 function pick(files){Object.defineProperty(el('spImgFile'),'files',{value:files,configurable:true});el('spImgFile').dispatchEvent(new w.Event('change'));}
 return {dom,w,d,el,errors,revoked,pick};
}
test('dedicated direct URL boots full HTML, has branded upload card and legal links, closes safely',()=>{
 const s=setup('#image-search');try{
  assert.deepEqual(s.errors,[]);assert.equal(s.el('imageSearchPage').hidden,false);
  assert.equal(s.d.activeElement,s.el('imageSearchTitle'));
  assert.notEqual(s.w.getComputedStyle(s.el('imageSearchClose').parentElement).display,'none');
  assert.equal(s.el('spImgDrop').closest('#searchPage'),null);
  assert.equal(s.el('spImgDrop').closest('#imageSearchPage'),s.el('imageSearchPage'));
  assert.ok(s.el('imageSearchPage').querySelector('a[href="terms.html"]'));
  assert.ok(s.el('imageSearchPage').querySelector('a[href="privacy.html"]'));
  s.el('imageSearchClose').click();assert.equal(s.w.location.hash,'');assert.equal(s.el('imageSearchPage').hidden,true);
 }finally{s.dom.window.close();}
});
test('product search entry opens dedicated screen; delayed search focus cannot escape; close restores focus',async()=>{
 const s=setup();try{
  s.el('tabSearch').click();s.el('spImageSearchEntry').focus();s.el('spImageSearchEntry').click();
  assert.equal(s.w.location.hash,'#image-search');assert.equal(s.el('imageSearchPage').hidden,false);
  await new Promise(resolve=>setTimeout(resolve,410));
  assert.equal(s.d.activeElement,s.el('imageSearchTitle'));
  s.el('imageSearchClose').click();assert.equal(s.el('searchPage').classList.contains('open'),true);
  assert.equal(s.d.activeElement,s.el('spImageSearchEntry'));assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});
test('picker cancel stays on upload screen; retake cancel and lens back return there',()=>{
 const s=setup('#image-search');try{
  s.pick([]);assert.equal(s.el('imageSearchPage').hidden,false);assert.equal(s.el('spImgDropError').hidden,true);
  s.w.lvOpen();s.el('lvRetake').click();s.pick([]);
  assert.equal(s.el('lensView').hidden,true);assert.equal(s.el('imageSearchPage').hidden,false);
  assert.equal(s.d.body.style.overflow,'hidden');
  s.w.lvOpen();s.el('lvBack').click();assert.equal(s.d.activeElement,s.el('spImgDrop'));
  assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});
test('Back/Forward route sync closes lens and invalidates pending upload on exit',()=>{
 const s=setup('#image-search');try{
  s.pick([new s.w.File(['png'],'a.png',{type:'image/png'})]);const callback=s.el('lvImg').onload;
  s.w.history.replaceState(null,'','/boopadb/');s.w.dispatchEvent(new s.w.PopStateEvent('popstate'));
  callback();assert.equal(s.el('imageSearchPage').hidden,true);assert.equal(s.el('lensView').hidden,true);
  assert.deepEqual(s.revoked,['blob:test-1']);
  s.w.history.replaceState(null,'','#image-search');s.w.dispatchEvent(new s.w.PopStateEvent('popstate'));
  assert.equal(s.el('imageSearchPage').hidden,false);assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});
test('dedicated upload rejects bad drops, keyboard focus remains in screen, Escape closes',()=>{
 const s=setup('#image-search');try{
  const e=new s.w.Event('drop',{bubbles:true,cancelable:true});Object.defineProperty(e,'dataTransfer',{value:{types:['Files'],files:[new s.w.File(['x'],'x.txt',{type:'text/plain'})]}});
  s.el('spImgDrop').dispatchEvent(e);assert.equal(e.defaultPrevented,true);assert.equal(s.el('spImgDropError').hidden,false);
  const last=s.el('imageSearchPage').querySelector('a[href="privacy.html"]');last.focus();
  s.d.dispatchEvent(new s.w.KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true}));assert.equal(s.d.activeElement,s.el('imageSearchClose'));
  s.d.dispatchEvent(new s.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));assert.equal(s.el('imageSearchPage').hidden,true);
  assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});

test('lens takes keyboard focus and traps Tab above the underlying dedicated page',()=>{
 const s=setup('#image-search');try{
  s.el('spImgDrop').focus();s.w.lvOpen();
  assert.equal(s.d.activeElement,s.el('lvBack'));
  assert.equal(s.el('imageSearchPage').getAttribute('aria-modal'),'false');
  s.d.dispatchEvent(new s.w.KeyboardEvent('keydown',{key:'Tab',shiftKey:true,bubbles:true,cancelable:true}));
  assert.equal(s.el('lensView').contains(s.d.activeElement),true);
  s.d.dispatchEvent(new s.w.KeyboardEvent('keydown',{key:'Tab',bubbles:true,cancelable:true}));
  assert.equal(s.d.activeElement,s.el('lvBack'));
  s.el('lvBack').click();assert.equal(s.el('imageSearchPage').getAttribute('aria-modal'),'true');
  assert.equal(s.d.activeElement,s.el('spImgDrop'));assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});

test('existing non-dedicated lens restores keyboard focus to its opener',()=>{
 const s=setup();try{
  s.el('tabSearch').focus();s.w.lvOpen();assert.equal(s.d.activeElement,s.el('lvBack'));
  s.el('lvBack').click();assert.equal(s.d.activeElement,s.el('tabSearch'));assert.deepEqual(s.errors,[]);
 }finally{s.dom.window.close();}
});
