'use strict';
// Offline adapter for the PROPOSED producer receipts. Never contacts GitHub.
// trustedRun and liveDir provenance must be established by the orchestrator;
// this module is a consistency validator, NOT an authentication mechanism.
const fs = require('node:fs');
const crypto = require('node:crypto');
const {execFileSync} = require('node:child_process');
const path = require('node:path');
const {eligible} = require('./proposed/src/collection-receipt');
const REPO='MametaroGG/booth-vrc-price-tracker';
const sha = b => crypto.createHash('sha256').update(b).digest('hex');
const blob = b => crypto.createHash('sha1').update(`blob ${b.length}\0`).update(b).digest('hex');
const fail = m => { throw new Error(m); };
const match = (v,re) => typeof v === 'string' && re.test(v);
const sha40 = v => match(v,/^[0-9a-f]{40}$/);
const sha256 = v => match(v,/^[0-9a-f]{64}$/);
const positive = v => Number.isSafeInteger(v) && v > 0;
const date = v => match(v,/^\d{4}-\d{2}-\d{2}$/) && !Number.isNaN(Date.parse(v+'T00:00:00Z')) && new Date(v+'T00:00:00Z').toISOString().slice(0,10) === v;
function json(bytes) { return JSON.parse(bytes.toString('utf8')); }
function lineage({liveDir,baselinePinBytes,expectedBaselinePinSha256}) {
  const releasePath=path.join(liveDir,'release-manifest.json');
  // A malformed present release never falls back to baseline.
  if(fs.existsSync(releasePath)) {
    const bytes=fs.readFileSync(releasePath), r=json(bytes);
    if(r.schema!==1 || !positive(r.generation) || !positive(r.product_count) ||
      !date(r.source_date) || !sha40(r.tracker_commit) || !sha40(r.generator_commit) ||
      !match(r.run_id,/^[1-9]\d*$/) || !sha256(r.inventory_digest) || !sha256(r.prev_release_digest))
      fail('Invalid existing live release manifest');
    if(!Number.isSafeInteger(r.generation+1)) fail('Generation overflow');
    return {generation:r.generation+1,prev_release_digest:sha(bytes),previous_source_date:r.source_date,
      lineage_mode:'existing-live-release'};
  }
  if(!Buffer.isBuffer(baselinePinBytes) || !sha256(expectedBaselinePinSha256) ||
    sha(baselinePinBytes)!==expectedBaselinePinSha256) fail('Explicit pinned first-release baseline required');
  const p=json(baselinePinBytes);
  if(p.schema!==1 || !positive(p.generation) || !positive(p.product_count) || !date(p.max_date) ||
    !sha40(p.baseline_commit) || !sha40(p.index_html_blob) || !sha40(p.item_html_blob) ||
    !sha256(p.baseline_prev_release_sentinel)) fail('Malformed baseline pin');
  for(const [name,key] of [['index.html','index_html_blob'],['item.html','item_html_blob']]) {
    if(blob(fs.readFileSync(path.join(liveDir,name)))!==p[key]) fail(`Live ${name} is not pinned baseline`);
  }
  const bytes=fs.readFileSync(path.join(liveDir,'snapshot-manifest.json')), s=json(bytes);
  if(sha(bytes)!==p.baseline_prev_release_sentinel || s.validation?.rows!==p.product_count ||
    s.validation?.max_date!==p.max_date) fail('Live snapshot is not pinned baseline');
  if(!Number.isSafeInteger(p.generation+1)) fail('Generation overflow');
  return {generation:p.generation+1,prev_release_digest:p.baseline_prev_release_sentinel,
    previous_source_date:p.max_date,lineage_mode:'explicit-first-release-baseline'};
}
function selectCore({saveReceipt,trustedRun,liveDir,baselinePinBytes,expectedBaselinePinSha256,expectedDate}, read) {
  const s=saveReceipt,t=trustedRun;
  if(!s || s.schema!=='boopa-saved-collection-v1' || s.repository!==REPO || !sha40(s.tracker_commit) ||
    !sha256(s.collection_receipt_sha256) || s.scraper_outcome!=='success' || s.save_outcome!=='success') fail('Missing immutable final-save receipt (legacy state is not selectable)');
  if(!t || t.repository!==REPO || t.workflow_path!=='.github/workflows/daily_scrape.yml' ||
    t.head_branch!==t.default_branch || !t.default_branch || t.status!=='completed' || t.conclusion!=='success' ||
    t.scraper_outcome!=='success' || t.save_outcome!=='success' || t.run_id!==s.run_id || t.run_attempt!==s.run_attempt)
    fail('Collector run/save is not authenticated terminal success');
  // Reading through this exact commit binds all values to one immutable tree.
  const receiptBytes=read('data/collection_receipt.json');
  if(sha(receiptBytes)!==s.collection_receipt_sha256) fail('Receipt does not match saved commit');
  const r=json(receiptBytes), budget=json(read('data/request_budget.json')), state=json(read('data/crawl_state.json'));
  if(!eligible(r) || r.run_id!==t.run_id || r.run_attempt!==t.run_attempt) fail('Collection is not an eligible bounded observation');
  if(budget.reservation?.id!==r.reservation_id || budget.reservation?.completed!==true ||
    budget.blockedUntil!==r.blocked_until_ms || !Array.isArray(state.retries) ||
    state.retries.length!==r.pending_retry_count) fail('Ledger/checkpoint/receipt mismatch');
  if(!date(expectedDate) || budget.date!==expectedDate) fail('Expected date does not match saved collector ledger');
  const l=lineage({liveDir,baselinePinBytes,expectedBaselinePinSha256});
  if(expectedDate<l.previous_source_date) fail('Source date regression');
  return {tracker_commit:s.tracker_commit,generation:l.generation,prev_release_digest:l.prev_release_digest,
    expected_date:expectedDate,collector_run_id:r.run_id,collector_run_attempt:r.run_attempt,
    collection_scope:r.scope,whole_catalog_complete:false,lineage_mode:l.lineage_mode,
    selection_authority:'offline-consistency-only'};
}
function select(config) {
  const {repoDir,saveReceipt:s}=config;
  if(!s || !sha40(s.tracker_commit)) fail('Missing immutable final-save receipt (legacy state is not selectable)');
  const read = name => execFileSync('git',['-C',repoDir,'show',`${s.tracker_commit}:${name}`],
      {maxBuffer:8*1024*1024,env:{...process.env,GIT_NO_REPLACE_OBJECTS:'1',GIT_CONFIG_NOSYSTEM:'1'}});
  if(execFileSync('git',['-C',repoDir,'cat-file','-t',s.tracker_commit],
      {encoding:'utf8',env:{...process.env,GIT_NO_REPLACE_OBJECTS:'1'}}).trim()!=='commit')
    fail('Saved tracker object is not a commit');
  return selectCore(config,read);
}
function selectMaterialized(config) {
  // Caller must authenticate these exact bytes at saveReceipt.tracker_commit.
  return selectCore(config,name=>fs.readFileSync(path.join(config.materializedDir,name)));
}
module.exports={select,selectMaterialized,lineage,sha,blob};
if(require.main===module) {
  try {
    const config=json(fs.readFileSync(process.argv[2]));
    if(config.baselinePinPath) config.baselinePinBytes=fs.readFileSync(config.baselinePinPath);
    console.log(JSON.stringify(select(config),null,2));
  } catch(e) { console.error(e.message);process.exitCode=1; }
}
