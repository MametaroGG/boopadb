/* Reviewed snapshot loader. No refs/base_refs fallback and no full-map download. */
(function(root,factory){
  if(typeof module==='object'&&module.exports)module.exports=factory();
  else root.BoopaRelationshipData=factory();
})(typeof globalThis!=='undefined'?globalThis:this,function(){
  'use strict';
  const schema='boopadb-relations-v1';
  const validId=id=>typeof id==='string'&&/^[1-9]\d{0,15}$/.test(id);
  function create(options={}){
    const cache=new Map();
    const request=options.fetch||((...args)=>fetch(...args));
    async function json(path){
      if(!cache.has(path)){
        const task=(async()=>{
          const controller=typeof AbortController!=='undefined'?new AbortController():null;
          let timer;
          try{
            return await Promise.race([
              (async()=>{const r=await request(path,{cache:'no-store',signal:controller&&controller.signal});if(!r.ok)throw Error('relations HTTP '+r.status);return r.json();})(),
              new Promise((_,reject)=>{timer=setTimeout(()=>{if(controller)controller.abort();reject(Error('relations timeout'));},options.timeoutMs||10000);})
            ]);
          }finally{clearTimeout(timer);}
        })();
        cache.set(path,task);task.catch(()=>cache.delete(path));
      }
      return cache.get(path);
    }
    async function get(id){
      if(options.enabled!==true||!validId(id))return {status:'unknown'};
      try{
        const manifest=await json('relation-data/manifest.json');
        if(manifest.schema!==schema||manifest.shards!==64||!/^[a-f0-9]{64}$/.test(manifest.version))throw Error('relations manifest');
        const bucket=Number(BigInt(id)%64n), childBucket=Number(BigInt(id)%8n);
        const paths=[`relation-data/items_${bucket}.json?v=${manifest.version}`,`relation-data/children_${childBucket}.json?v=${manifest.version}`];
        const data=await Promise.all(paths.map(json));
        for(let i=0;i<data.length;i++){
          const d=data[i];
          if(!d||d.schema!==schema||d.version!==manifest.version||!d.items||typeof d.items!=='object'||Array.isArray(d.items)){
            cache.delete(paths[i]);cache.delete('relation-data/manifest.json');throw Error('relations generation mismatch');
          }
        }
        const entry=Object.prototype.hasOwnProperty.call(data[0].items,id)?data[0].items[id]:null;
        const child=Object.prototype.hasOwnProperty.call(data[1].items,id)?data[1].items[id]:null;
        if(child&&(!Array.isArray(child)||child.length!==2||!Number.isSafeInteger(child[0])||child[0]<0||!Array.isArray(child[1])||child[1].length!==Math.min(child[0],2000)||!child[1].every(x=>validId(x)&&x!==id)||new Set(child[1]).size!==child[1].length))throw Error('relations children');
        return {status:'loaded',entry,children:child?child[1]:[],childrenTotal:child?child[0]:0,version:manifest.version};
      }catch(error){cache.clear();return {status:'unknown',error:String(error.message||error)};}
    }
    return {get,clear:()=>cache.clear()};
  }
  return {create};
});
