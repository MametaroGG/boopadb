/* Public catalog bytes only. Never stores searches, history or bookmarks.
   A fresh manifest pins every shard to one content hash before cache reuse. */
(function(root){
 'use strict';
 function createCatalogReader(env = root, options = {}){
  let supported=false;
  try{supported=!!(env.caches && env.crypto && env.crypto.subtle && env.Response);}catch{/* restricted storage must not abort page initialization */}
  let snapshotPromise=null,storePromise=null,currentSnapshot=null;
  let decoding=0,writing=0;const decodeQueue=[];
  const pending=new Map(),base=new URL('.',env.location.href),cacheName='boopadb-catalog-sha256-v1';
  const hash=async bytes=>Array.from(new Uint8Array(await env.crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
  const key=(path,sha)=>new URL(path+'?__catalog_sha256='+sha,base).href;
  const storage=async operation=>{let timer;try{return await Promise.race([Promise.resolve().then(operation),new Promise(resolve=>{timer=env.setTimeout(()=>resolve(null),250);})]);}catch{return null;}finally{env.clearTimeout(timer);}};
  const store=()=>storePromise||(storePromise=storage(()=>env.caches.open(cacheName)));
  function abortable(promise,signal){
   if(!signal)return promise;
   return new Promise((resolve,reject)=>{
    const abort=()=>reject(Error('catalog aborted'));
    if(signal.aborted)abort();else signal.addEventListener('abort',abort,{once:true});
    promise.then(resolve,reject).finally(()=>signal.removeEventListener('abort',abort));
   });
  }
  const releaseDecode=()=>{const next=decodeQueue.shift();if(next)next();else decoding--;};
  async function decodeSlot(operation,signal){
   if(signal&&signal.aborted)throw Error('catalog aborted');
   if(decoding>=2){
    let resume;const waiting=new Promise(resolve=>{resume=resolve;});decodeQueue.push(resume);
    try{await abortable(waiting,signal);}catch(error){const i=decodeQueue.indexOf(resume);if(i>=0)decodeQueue.splice(i,1);else releaseDecode();throw error;}
   }else decoding++;
   try{return await abortable(Promise.resolve().then(operation),signal);}finally{releaseDecode();}
  }
  function persist(cache,url,bytes){
   // Never queue the complete 24-shard catalog behind slow/hung disk writes.
   // At most two response bodies remain owned by outstanding persistence calls.
   if(writing>=2)return;
   writing++;
   Promise.resolve().then(()=>cache.put(url,new env.Response(bytes,{headers:{'Content-Type':'application/json'}}))).catch(()=>{}).finally(()=>writing--);
  }
  async function begin(){
   if(!supported)return null;
   if(!snapshotPromise)snapshotPromise=(async()=>{
    const controller=new env.AbortController();let timer;
    try{
     const manifest=await Promise.race([env.fetch(new URL('snapshot-manifest.json',base).href,{cache:'no-store',signal:controller.signal}).then(response=>{if(!response.ok)throw Error('manifest unavailable');return response.json();}),new Promise((_,reject)=>{timer=env.setTimeout(()=>{controller.abort();reject(Error('manifest timeout'));},1500);})]);
     const files=manifest&&manifest.files;
     if(manifest.schema!==1 || manifest.fixture!==false || !files)throw Error('manifest format');
     let paths=Array.from({length:24},(_,i)=>'search_index_'+i+'.json'),images=null,partRows=null;
     const validHash=x=>typeof x==='string'&&/^[a-f0-9]{64}$/.test(x);
     if(manifest.catalog_core&&options.core!==false){
      const core=manifest.catalog_core;
      if(core.schema!==1||core.format!=='image-free-v1'||core.image_buckets!==512||!Array.isArray(core.part_rows)||core.part_rows.length!==24||core.part_rows.some(n=>!Number.isInteger(n)||n<0)||core.part_rows.reduce((a,b)=>a+b,0)!==core.rows||core.rows!==manifest.validation.rows)throw Error('core manifest');
      paths=Array.from({length:24},(_,i)=>'search-core/core_'+i+'.json');partRows=core.part_rows;
      images=Array.from({length:512},(_,i)=>files['search-core/images_'+i+'.json']);
      if(images.some(x=>!validHash(x)))throw Error('image manifest hashes');
     }
     const hashes=paths.map(path=>files[path]);
     if(hashes.some(x=>!validHash(x)))throw Error('manifest hashes');
     const snapshot={paths,hashes,images,partRows,version:paths.join('|')+hashes.join('')+(images||[]).join('')};
     // Only this application's known resources; nested applications are excluded.
     store().then(async cache=>{if(!cache)return;const keep=new Set(hashes.map((sha,i)=>key(paths[i],sha)));if(images)images.forEach((sha,i)=>keep.add(key('search-core/images_'+i+'.json',sha)));for(const request of await cache.keys()){const url=new URL(request.url),relative=url.href.startsWith(base.href)?url.pathname.slice(base.pathname.length):'';if(/^(?:search_index_\d+\.json|search-core\/(?:core|images)_\d+\.json)$/.test(relative)&&!keep.has(url.href))await cache.delete(request);}}).catch(()=>{});
     currentSnapshot=snapshot;return snapshot;
    }catch{currentSnapshot=null;return null;}finally{env.clearTimeout(timer);}
   })();
   return snapshotPromise;
  }
  async function readResource(path,expected,validate,signal){
   const url=key(path,expected),cache=await store();
   const decode=response=>decodeSlot(async()=>{if(signal&&signal.aborted)throw Error('catalog aborted');if(!response||!response.ok)throw Error('catalog');const bytes=await response.arrayBuffer();if(signal&&signal.aborted)throw Error('catalog aborted');if(await hash(bytes)!==expected)throw Error('catalog revision mismatch');if(signal&&signal.aborted)throw Error('catalog aborted');const rows=JSON.parse(new TextDecoder().decode(bytes));if(!validate(rows))throw Error('catalog format');return {rows,bytes};},signal);
   if(cache){try{const response=await storage(()=>cache.match(url));if(response){try{return (await decode(response)).rows;}catch{await storage(()=>cache.delete(url));}}}catch{/* storage failure is only a miss */}}
   const response=await env.fetch(new URL(path+'?v='+expected,base).href,{signal,cache:'no-store'}),result=await decode(response);
   if(signal&&signal.aborted)throw Error('catalog aborted');if(cache)persist(cache,url,result.bytes);return result.rows;
  }
  async function shared(name,operation,signal){
   if(signal&&signal.aborted)throw Error('catalog aborted');
   const prior=pending.get(name);if(prior&&!(prior.signal&&prior.signal.aborted))return prior.promise;
   const task=Promise.resolve().then(operation),guarded=abortable(task,signal),entry={promise:guarded,signal};pending.set(name,entry);
   try{return await guarded;}finally{if(pending.get(name)===entry)pending.delete(name);}
  }
  async function read(i,{signal}={}){
   if(!Number.isInteger(i)||i<0||i>=24)throw Error('catalog part');
   return shared('part:'+i,async()=>{
    const snapshot=await begin();
    if(!snapshot){const response=await env.fetch('search_index_'+i+'.json?v=20251027-2',{signal,cache:'no-store'});if(!response.ok)throw Error('catalog');const rows=await response.json();if(!Array.isArray(rows))throw Error('catalog format');return rows;}
    const valid=rows=>Array.isArray(rows)&&(!snapshot.images||(rows.length===snapshot.partRows[i]&&rows.every(r=>Array.isArray(r)&&r.length===14&&r[9]==='')));
    return readResource(snapshot.paths[i],snapshot.hashes[i],valid,signal);
   },signal);
  }
  async function image(id,{signal}={}){
   id=String(id);if(!/^[1-9][0-9]*$/.test(id)||!Number.isSafeInteger(Number(id)))return null;
   const snapshot=await begin();if(!snapshot||!snapshot.images)return null;
   const bucket=Number(id)%512,path='search-core/images_'+bucket+'.json';
   const valid=rows=>rows&&typeof rows==='object'&&!Array.isArray(rows)&&Object.entries(rows).every(([key,value])=>/^[1-9][0-9]*$/.test(key)&&Number.isSafeInteger(Number(key))&&Number(key)%512===bucket&&typeof value==='string');
   const rows=await shared('image:'+bucket,()=>readResource(path,snapshot.images[bucket],valid,signal),signal);
   if(!Object.prototype.hasOwnProperty.call(rows,id))throw Error('image missing from snapshot');
   return rows[id];
  }
  async function refresh(){
   if(pending.size)throw Error('catalog requests still active');
   const previous=await begin();snapshotPromise=null;
   const current=await begin();
   return supported&&(!previous||!current||previous.version!==current.version);
  }
  return {begin,read,refresh,image,revision:()=>currentSnapshot&&currentSnapshot.version,isCore:()=>!!(currentSnapshot&&currentSnapshot.images)};
 }
 if(typeof module==='object'&&module.exports)module.exports={createCatalogReader};
 else root.createBoopaCatalogReader=createCatalogReader;
})(typeof window==='undefined'?globalThis:window);
