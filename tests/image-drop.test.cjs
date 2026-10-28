// Test-only dependency: npm install --no-save --package-lock=false jsdom@26.1.0
const test = require('node:test');
const assert = require('node:assert/strict');
const {JSDOM} = require('jsdom');
const drop = require('../image-drop');
const image = {type:'image/png', size:100, name:'test.png'};
function setup(){
 const dom = new JSDOM('<button id="zone"><span id="child">Drop</span></button><input id="file" type="file">');
 const doc=dom.window.document, zone=doc.getElementById('zone'), input=doc.getElementById('file');
 const files=[], errors=[];
 const bound=drop.bind({document:doc,zone,input,onFile:f=>files.push(f),onError:e=>errors.push(e)});
 function fire(target,type,dt={types:['Files'],files:[image]}){
   const e=new dom.window.Event(type,{bubbles:true,cancelable:true}); Object.defineProperty(e,'dataTransfer',{value:dt}); target.dispatchEvent(e); return e;
 }
 return {dom,doc,zone,input,files,errors,bound,fire};
}
test('valid image accepted; empty, multiple, non-image and oversized rejected',()=>{
 assert.equal(drop.validate([image]),null);
 assert.equal(drop.validate([]),'img_file_empty');
 assert.equal(drop.validate([image,image]),'img_file_one');
 assert.equal(drop.validate([{type:'text/plain',size:100}]),'img_file_type');
 assert.equal(drop.validate([{...image,size:0}]),'img_file_size');
 assert.equal(drop.validate([{...image,size:drop.maxBytes+1}]),'img_file_size');
});
test('nested enter/leave does not flicker, valid drop reused once',()=>{
 const s=setup();s.fire(s.zone,'dragenter');s.fire(s.doc.getElementById('child'),'dragenter');
 s.fire(s.zone,'dragleave');assert.equal(s.zone.classList.contains('is-dragging'),true);
 assert.equal(s.fire(s.zone,'drop').defaultPrevented,true);
 assert.deepEqual(s.files,[image]);assert.equal(s.zone.classList.contains('is-dragging'),false);
});
test('invalid and multiple drops do not invoke upload',()=>{
 const s=setup();s.fire(s.zone,'drop',{types:['Files'],files:[image,image]});
 assert.equal(s.files.length,0);assert.deepEqual(s.errors,['img_file_one']);
});
test('file drop outside target prevents browser navigation, URL/text not intercepted',()=>{
 const s=setup();assert.equal(s.fire(s.doc.body,'drop').defaultPrevented,true);assert.equal(s.files.length,0);
 assert.equal(s.fire(s.doc.body,'drop',{types:['text/uri-list'],files:[]}).defaultPrevented,false);
});
test('picker supports repeated selection and cancel',()=>{
 const s=setup();Object.defineProperty(s.input,'files',{configurable:true,value:[image]});
 s.input.dispatchEvent(new s.dom.window.Event('change'));s.input.dispatchEvent(new s.dom.window.Event('change'));
 assert.equal(s.files.length,2);assert.equal(s.input.value,'');
 Object.defineProperty(s.input,'files',{value:[]});s.input.dispatchEvent(new s.dom.window.Event('change'));assert.equal(s.errors.length,2);
});
test('drag cancellation resets highlight',()=>{
 const s=setup();s.fire(s.zone,'dragenter');s.doc.dispatchEvent(new s.dom.window.Event('dragend'));assert.equal(s.zone.classList.contains('is-dragging'),false);
});

function uploadHarness(){
 const fs=require('node:fs'), vm=require('node:vm');
 const html=fs.readFileSync(require('node:path').join(__dirname,'../image-search-engine.js'),'utf8');
 const upload=html.slice(html.indexOf('function lvOpenUpload(file)'),html.indexOf('let lvZoom ='));
 const similar=html.slice(html.indexOf('async function imgSimilar(x)'),html.indexOf('let lvRequestId ='));
 const nodes={},errors=[],revoked=[];let n=0;
 const el=id=>nodes[id]||(nodes[id]={style:{},classList:{},hidden:true});
 const context={document:{getElementById:el},URL:{createObjectURL:()=>`blob:test-${++n}`,revokeObjectURL:u=>revoked.push(u)},lvUploadError:e=>errors.push(e),fetch:async()=>({ok:false,status:500}),encodeURIComponent,IMG_API:'https://example.test',lvEl:el,lvZoomReset(){},lvSheetSet(){},lvOpen(){},lvStageMode(){},lvSetState(){},lvFitLoop(){},lvRenderSvg(){},lvShowResults(){},imgHitsFromApi(){}};
 vm.createContext(context);
 vm.runInContext('let lvRequestId=0,lvUrl=null,lvRemote=false,lvRect=null,lvShown=null,lvSearched=null,lvDrag=null;\n'+upload+'\n'+similar+'\nfunction currentUrl(){return lvUrl}',context);
 return {context,el,errors,revoked};
}
test('stale upload error cannot revoke a newer upload; current decode error is reported',()=>{
 const h=uploadHarness();h.context.lvOpenUpload(image);const oldError=h.el('lvImg').onerror;
 h.context.lvOpenUpload(image);const next=h.context.currentUrl();oldError();
 assert.equal(h.context.currentUrl(),next);assert.deepEqual(h.errors,[]);assert.deepEqual(h.revoked,['blob:test-1']);
 h.el('lvImg').onerror();assert.deepEqual(h.errors,['img_file_decode']);assert.equal(h.context.currentUrl(),null);
});
test('remote similar-image route clears upload error handler and stale callback is ignored',async()=>{
 const h=uploadHarness();h.context.lvOpenUpload(image);const oldError=h.el('lvImg').onerror;
 await h.context.imgSimilar({id:'123',image:'https://example.test/image.jpg'});
 assert.equal(h.el('lvImg').onerror,null);oldError();assert.deepEqual(h.errors,[]);assert.deepEqual(h.revoked,[]);
});
