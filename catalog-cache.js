/* Public catalog bytes only. Never stores searches, history or bookmarks.
   A fresh manifest pins every shard to one content hash before cache reuse. */
(function(root){
 'use strict';
 function createCatalogReader(env = root){
  let supported=false;
  try{supported=!!(env.caches && env.crypto && env.crypto.subtle && env.Response);}catch{/* restricted storage must not abort page initialization */}
  let snapshotPromise=null,storePromise=null;
  let decoding=0,writing=0;const decodeQueue=[];
  const pending=new Map(),base=new URL('.',env.location.href),cacheName='boopadb-catalog-sha256-v1';
  const hash=async bytes=>Array.from(new Uint8Array(await env.crypto.subtle.digest('SHA-256',bytes)),x=>x.toString(16).padStart(2,'0')).join('');
  const key=(i,sha)=>new URL('search_index_'+i+'.json?__catalog_sha256='+sha,base).href;
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
     const hashes=Array.from({length:24},(_,i)=>files['search_index_'+i+'.json']);
     if(hashes.some(x=>typeof x!=='string'||! /^[a-f0-9]{64}$/.test(x)))throw Error('manifest hashes');
     // Prune only this site's catalog entries, never unrelated app/user caches.
     store().then(async cache=>{if(!cache)return;const keep=new Set(hashes.map((sha,i)=>key(i,sha)));for(const request of await cache.keys()){const url=new URL(request.url);if(new URL('.',url).href===base.href&&/\/search_index_\d+\.json$/.test(url.pathname)&&!keep.has(url.href))await cache.delete(request);}}).catch(()=>{});
     return hashes;
    }catch{return null;}finally{env.clearTimeout(timer);}
   })();
   return snapshotPromise;
  }
  async function read(i,{signal}={}){
   if(signal&&signal.aborted)throw Error('catalog aborted');
   if(!Number.isInteger(i)||i<0||i>=24)throw Error('catalog part');
   if(pending.has(i))return pending.get(i);
   const task=(async()=>{
    const hashes=await begin();
    if(!hashes){const response=await env.fetch('search_index_'+i+'.json?v=20251027-2',{signal,cache:'no-store'});if(!response.ok)throw Error('catalog');const rows=await response.json();if(!Array.isArray(rows))throw Error('catalog format');return rows;}
    const expected=hashes[i],url=key(i,expected),cache=await store();
    const decode=response=>decodeSlot(async()=>{if(signal&&signal.aborted)throw Error('catalog aborted');if(!response||!response.ok)throw Error('catalog');const bytes=await response.arrayBuffer();if(signal&&signal.aborted)throw Error('catalog aborted');if(await hash(bytes)!==expected)throw Error('catalog revision mismatch');if(signal&&signal.aborted)throw Error('catalog aborted');const rows=JSON.parse(new TextDecoder().decode(bytes));if(!Array.isArray(rows))throw Error('catalog format');return {rows,bytes};},signal);
    if(cache){try{const response=await storage(()=>cache.match(url));if(response){try{return (await decode(response)).rows;}catch{await storage(()=>cache.delete(url));}}}catch{/* unavailable storage is only a cache miss */}}
    const response=await env.fetch(new URL('search_index_'+i+'.json?v='+expected,base).href,{signal,cache:'no-store'}),result=await decode(response);
    if(signal&&signal.aborted)throw Error('catalog aborted');
    // Persist after validation; a quota/private-mode failure never fails search.
    if(cache)persist(cache,url,result.bytes);
    return result.rows;
   })();
   let abort;
   const guarded=signal?Promise.race([task,new Promise((_,reject)=>{abort=()=>reject(Error('catalog aborted'));if(signal.aborted)abort();else signal.addEventListener('abort',abort,{once:true});})]):task;
   pending.set(i,guarded);
   try{return await guarded;}finally{if(abort)signal.removeEventListener('abort',abort);if(pending.get(i)===guarded)pending.delete(i);}
  }
  async function refresh(){
   if(pending.size)throw Error('catalog requests still active');
   const previous=await begin();snapshotPromise=null;
   const current=await begin();
   return supported&&(!previous||!current||previous.some((sha,i)=>sha!==current[i]));
  }
  return {begin,read,refresh};
 }
 if(typeof module==='object'&&module.exports)module.exports={createCatalogReader};
 else root.createBoopaCatalogReader=createCatalogReader;
})(typeof window==='undefined'?globalThis:window);
