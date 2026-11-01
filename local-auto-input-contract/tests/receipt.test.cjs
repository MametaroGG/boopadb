const test = require('node:test');
const assert = require('node:assert/strict');
const {makeReceipt,eligible} = require('../proposed/src/collection-receipt');
function receipt() {return makeReceipt({ status:'paused',reason:'deadline',failed:false,
    started_at_ms:100000,stopped_at_ms:160000,deadline_ms:160000,blocked_until_ms:0,
    reservation_completed:true,pending_retry_count:3,
    metrics:{searchPages:1,searchFailures:0,itemSuccess:5,itemFailures:0,unavailable:0,
      retries:0,duplicatesAvoided:0,chargedHttpAttempts:6,dailyChargedRequests:6}},
    {COLLECTOR_SOURCE_COMMIT:'a'.repeat(40),GITHUB_RUN_ID:'123',GITHUB_RUN_ATTEMPT:'1',SCRAPER_RESERVATION_ID:'123-1',
      GITHUB_REPOSITORY:'MametaroGG/booth-vrc-price-tracker'});}
test('healthy bounded deadline is eligible, not catalog completeness',()=>{
 const r=receipt(); assert.equal(eligible(r),true);assert.equal(r.whole_catalog_complete,false);
});
for (const patch of [{status:'partial'},{status:'failed'},{status:'unknown'}, {failed:true},
 {reservation_completed:false},{reason:'daily-budget'},{reason:'cooldown'},
 {whole_catalog_complete:true},{schema:undefined},{run_attempt:'2'},
 {stopped_at_ms:130000},{blocked_until_ms:160001},{pending_retry_count:-1}])
 test(`reject ${JSON.stringify(patch)}`,()=>assert.equal(eligible({...receipt(),...patch}),false));
test('ledger completion alone is insufficient',()=>assert.equal(eligible({reservation:{completed:true}}),false));
for (const k of ['itemFailures','searchFailures']) test(`reject ${k}`,()=>{
 const r=receipt();r.metrics[k]=1;assert.equal(eligible(r),false);
});
test('reject no observations and malformed counters',()=>{
 for(const [k,v] of [['itemSuccess',0],['chargedHttpAttempts',0],['itemFailures',false]]) {
 const r=receipt();r.metrics[k]=v;assert.equal(eligible(r),false); }
});
test('completed filtered segment allowed but retry-pending is not',()=>{
 const r={...receipt(),status:'completed',pending_retry_count:0};delete r.reason;
 assert.equal(eligible(r),true);r.pending_retry_count=1;assert.equal(eligible(r),false);
});
test('day boundary must actually cross JST date',()=>{
 const r={...receipt(),reason:'day-boundary',started_at_ms:53999000,stopped_at_ms:54001000,deadline_ms:55000000};
 assert.equal(eligible(r),true);r.stopped_at_ms=53999500;assert.equal(eligible(r),false);
});
