const test=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const os=require('node:os');const path=require('node:path');
const {execFileSync}=require('node:child_process');
const {select,lineage,sha,blob}=require('../select-input.cjs');
const {makeReceipt}=require('../proposed/src/collection-receipt');
const {writeSaveReceipt}=require('../proposed/write-save-receipt.cjs');
const REPO='MametaroGG/booth-vrc-price-tracker';
function fixture(t) {
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'boopa-selection-offline-'));
 t.after(()=>fs.rmSync(root,{recursive:true,force:true}));
 const liveDir=path.join(root,'live');fs.mkdirSync(liveDir);
 const index=Buffer.from('test index'),item=Buffer.from('test item');
 const snap=Buffer.from(JSON.stringify({validation:{rows:10,max_date:'2026-11-01'}}));
 for(const [f,b] of [['index.html',index],['item.html',item],['snapshot-manifest.json',snap]])fs.writeFileSync(path.join(liveDir,f),b);
 const pin={schema:1,baseline_commit:'1'.repeat(40),generation:1,product_count:10,max_date:'2026-11-01',
  index_html_blob:blob(index),item_html_blob:blob(item),baseline_prev_release_sentinel:sha(snap)};
 const baselinePinBytes=Buffer.from(JSON.stringify(pin));
 return {root,liveDir,baselinePinBytes,expectedBaselinePinSha256:sha(baselinePinBytes)};
}
function release(f,overrides={}) {
 const r={schema:1,generation:9,product_count:10,source_date:'2026-11-01',tracker_commit:'1'.repeat(40),
 generator_commit:'2'.repeat(40),run_id:'7',inventory_digest:'3'.repeat(64),prev_release_digest:'4'.repeat(64),...overrides};
 const b=Buffer.from(JSON.stringify(r));fs.writeFileSync(path.join(f.liveDir,'release-manifest.json'),b);return b;
}
test('explicit baseline derives generation2 and exact-byte sentinel',t=>{
 const f=fixture(t),r=lineage(f);assert.equal(r.generation,2);assert.equal(r.prev_release_digest,JSON.parse(f.baselinePinBytes).baseline_prev_release_sentinel);
});
test('existing release derives generation+1 and hash of actual bytes',t=>{
 const f=fixture(t),b=release(f);const r=lineage(f);assert.equal(r.generation,10);assert.equal(r.prev_release_digest,sha(b));
});
test('missing baseline pin cannot invent generation',t=>assert.throws(()=>lineage({liveDir:fixture(t).liveDir}),/Explicit pinned/));
test('changed pin digest fails',t=>{const f=fixture(t);f.expectedBaselinePinSha256='f'.repeat(64);assert.throws(()=>lineage(f));});
for(const file of ['index.html','item.html','snapshot-manifest.json'])test(`changed baseline ${file} fails`,t=>{
 const f=fixture(t);fs.appendFileSync(path.join(f.liveDir,file),' ');assert.throws(()=>lineage(f));
});
test('malformed existing release never falls back',t=>{const f=fixture(t);release(f,{generation:'9'});assert.throws(()=>lineage(f),/Invalid/);});
test('generation overflow fails',t=>{const f=fixture(t);release(f,{generation:Number.MAX_SAFE_INTEGER});assert.throws(()=>lineage(f),/overflow/);});
function withRepo(t) {
 const f=fixture(t);const repoDir=path.join(f.root,'repo');fs.mkdirSync(repoDir);fs.mkdirSync(path.join(repoDir,'data'));
 const git=(...args)=>execFileSync('git',['-C',repoDir,...args],{encoding:'utf8',env:{...process.env,GIT_CONFIG_GLOBAL:os.devNull,GIT_CONFIG_NOSYSTEM:'1'}}).trim();
 git('init','--quiet');git('config','user.name','Offline Test');git('config','user.email','offline@example.invalid');
 const env={COLLECTOR_SOURCE_COMMIT:'a'.repeat(40),GITHUB_REPOSITORY:REPO,GITHUB_RUN_ID:'123',GITHUB_RUN_ATTEMPT:'1',SCRAPER_RESERVATION_ID:'123-1'};
 const r=makeReceipt({status:'paused',reason:'deadline',failed:false,started_at_ms:100000,stopped_at_ms:160000,
 deadline_ms:160000,blocked_until_ms:0,reservation_completed:true,pending_retry_count:0,
 metrics:{searchPages:1,searchFailures:0,itemSuccess:1,itemFailures:0,unavailable:0,retries:0,duplicatesAvoided:0,
 chargedHttpAttempts:2,dailyChargedRequests:2}},env);
 const commit=(receipt=r)=>{
 fs.writeFileSync(path.join(repoDir,'data/collection_receipt.json'),JSON.stringify(receipt));
 fs.writeFileSync(path.join(repoDir,'data/request_budget.json'),JSON.stringify({date:'2026-11-01',blockedUntil:0,reservation:{id:'123-1',completed:true}}));
 fs.writeFileSync(path.join(repoDir,'data/crawl_state.json'),JSON.stringify({urlIndex:0,page:10,retries:[]}));
 git('add','data');git('commit','--quiet','--allow-empty','-m','offline synthetic fixture');return git('rev-parse','HEAD');};
 const shaCommit=commit();
 const saveReceipt={scraper_outcome:'success',save_outcome:'success',schema:'boopa-saved-collection-v1',repository:REPO,run_id:'123',run_attempt:'1',tracker_commit:shaCommit,
 collection_receipt_sha256:sha(Buffer.from(JSON.stringify(r)))};
 const trustedRun={repository:REPO,workflow_path:'.github/workflows/daily_scrape.yml',default_branch:'main',head_branch:'main',
 run_id:'123',run_attempt:'1',status:'completed',conclusion:'success',scraper_outcome:'success',save_outcome:'success'};
 return {...f,repoDir,saveReceipt,trustedRun,expectedDate:'2026-11-01',commit,receipt:r};
}
test('selects exact saved immutable commit rather than current HEAD',t=>{
 const f=withRepo(t);f.commit({...f.receipt,status:'failed',failed:true});
 const r=select(f);assert.equal(r.tracker_commit,f.saveReceipt.tracker_commit);assert.equal(r.generation,2);assert.equal(r.whole_catalog_complete,false);
});
for(const key of ['conclusion','scraper_outcome','save_outcome'])test(`rejects failure in ${key}`,t=>{
 const f=withRepo(t);f.trustedRun[key]='failure';assert.throws(()=>select(f));
});
test('rejects running and cross-attempt run evidence',t=>{
 const f=withRepo(t);f.trustedRun.status='in_progress';assert.throws(()=>select(f));
 f.trustedRun.status='completed';f.trustedRun.run_attempt='2';assert.throws(()=>select(f));
});
test('legacy/no receipt fails closed',()=>assert.throws(()=>select({}),/Missing immutable final-save/));
test('receipt digest mismatch fails',t=>{const f=withRepo(t);f.saveReceipt.collection_receipt_sha256='f'.repeat(64);assert.throws(()=>select(f),/does not match/);});
test('partial receipt cannot qualify even if ledger completed',t=>{
 const f=withRepo(t),r={...f.receipt,status:'partial'};
 f.saveReceipt.tracker_commit=f.commit(r);f.saveReceipt.collection_receipt_sha256=sha(Buffer.from(JSON.stringify(r)));
 assert.throws(()=>select(f),/not an eligible/);
});
test('wrong expected date and date regression fail',t=>{
 const f=withRepo(t);f.expectedDate='2026-11-02';assert.throws(()=>select(f),/Expected date/);
 f.expectedDate='2026-11-01';release(f,{source_date:'2026-11-02'});assert.throws(()=>select(f),/regression/);
});
test('save-artifact writer refuses no saved commit or failed outcome',()=>{
 assert.throws(()=>writeSaveReceipt({SCRAPER_OUTCOME:'success',SAVE_OUTCOME:'success'}),/No successful/);
 assert.throws(()=>writeSaveReceipt({SCRAPER_OUTCOME:'failure',SAVE_OUTCOME:'success',SAVED_COMMIT:'1'.repeat(40)}),/No successful/);
});
