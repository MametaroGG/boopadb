"""Exact historical-run authentication, never a current-source selector.

Only the fixed successful run below is readable as a historical trial input.
Wall clock stays real: future evidence and expired artifacts are refused. Receipt
and observation clocks are fixed original facts, not refreshed eligibility.
No network runs on import. The caller supplies the sealed read-only utilities.
"""
import datetime as dt
from pathlib import Path
import subprocess
import trial_adapter as t

REPOSITORY='MametaroGG/booth-vrc-price-tracker'
REPOSITORY_ID=1134883798
WORKFLOW='.github/workflows/daily_scrape.yml'
WORKFLOW_ID=223837658
RUN_ID=41920338326
RUN_NUMBER=1290
ATTEMPT=1
JOB_ID=126890859190
HEAD='9090da9f5196d830800b440218ecf41f3d7a9256'
SOURCE='20c5b1c969fd1dad8c00e66540ee76f53d83a219'
SAVED='672373654eb125fea74a25ff4f0319440e0d5f14'
ROOT_TREE='af8f34cebc520b199ede867b90289854c2aa32bf'
SOURCE_ROOT='fffecacecee78cdf04adc1ade53035356eb9f2e2'
EVENT_ROOT='e5d9c8ce87a7e8a5a35b86d19b487c5de1d52605'
ARTIFACT_ID=13385305004
ARTIFACT_SIZE=389
ARTIFACT_SHA='ac48a56a06e50e185740561f73201d69afede39b3e24f70415a56d4844de4806'
SAVED_CANONICAL_SHA='f11cac40b4feeb559a442f4a6470305ed02817259fb73376078298e6537216b1'
PRODUCER_SHA='c084cb265640c00c2cfac1700e51c6d1e7e1cfbaf0032f10a9a5be66e2f8f315'
OBSERVED_DATE='2026-11-05'
ORIGINAL_AS_OF_UTC='2026-11-05T03:01:12.709Z'
RUN_STARTED='2026-11-04T21:53:58Z'
RUN_UPDATED='2026-11-05T03:04:06Z'
RECEIPT_STARTED_MS=1793829673036
RECEIPT_STOPPED_MS=1793847672709
RECEIPT_DEADLINE_MS=1793847673036
FILES={
 'data/collection_receipt.json':'b1bf94568ee1083ef2904c68e3c369069412bb6d04e2023d17c92ed64c2e6d6a',
 'data/request_budget.json':'44e96ddb75d6aa0c61dc1cd7347725632b67bdd379285e58664061ef7911b6b9',
 'data/crawl_state.json':'1967a8dc3c0513e8ebe2c23e5177ad00e2055fcf61de6260932fba08fec82a54'}
STEPS=(('Verify reviewed source before dependencies','success'),('Run tests','success'),
 ('Reserve request budget','success'),('Commit reservation','success'),
 ('Verify reviewed source before collection','success'),('Run Scraper','success'),
 ('Commit and Push','success'),('Verify reviewed source after save','success'),
 ('Report scraper failure','skipped'),('Record immutable saved collection','success'),
 ('Retain immutable saved collection','success'))
need=t.need

def exact(value, expected):
    return type(value) is type(expected) and value==expected

def original_claim():
    return {'expected_date':OBSERVED_DATE,'minimum_source_date':'2026-10-30',
            'as_of':OBSERVED_DATE,'max_source_age_days':1,'fixture':False}

def public_labels(proof):
    """Fixed scalar provenance projection, not an authenticator for arbitrary JSON."""
    want={'schema':'boopa-historical-resolved-inputs-v1','repository':REPOSITORY,
        'run_id':str(RUN_ID),'run_attempt':'1','artifact_id':ARTIFACT_ID,
        'artifact_digest':'sha256:'+ARTIFACT_SHA,'source_commit':SOURCE,
        'producer_pin_sha256':PRODUCER_SHA,'historical_replay':True,
        'current_source_eligible':False,'automatic_intake_eligible':False,'production_eligible':False,'publication_authorized':False,
        'original_as_of':OBSERVED_DATE,'original_source_date':OBSERVED_DATE,
        'original_source_as_of_utc':ORIGINAL_AS_OF_UTC,'workflow_event_head':HEAD,
        'original_receipt_started_at_ms':RECEIPT_STARTED_MS,'original_receipt_stopped_at_ms':RECEIPT_STOPPED_MS,
        'original_run_updated_at':RUN_UPDATED,
        'currentness_policy':'deliberately-not-evaluated-exact-historical-replay-only'}
    need(type(proof)is dict and set(proof)==set(want)|{'selection','evaluated_at'} and all(exact(proof.get(k),v) for k,v in want.items()),'Historical public labels differ from exact proof')
    selection=proof.get('selection',{})
    selection_want={'tracker_commit':SAVED,'generation':2,'prev_release_digest':t.PREVIOUS,
        'expected_date':OBSERVED_DATE,'collector_run_id':str(RUN_ID),'collector_run_attempt':'1',
        'collection_scope':'bounded-filtered-search-observation','whole_catalog_complete':False,
        'lineage_mode':'explicit-first-release-baseline',
        'selection_authority':'authenticated-exact-historical-run-and-live-legacy-lineage'}
    need(type(selection)is dict and set(selection)==set(selection_want) and
         all(exact(selection.get(k),v) for k,v in selection_want.items()),'Historical selection labels differ')
    stamp=proof.get('evaluated_at');need(type(stamp)is str and len(stamp)<=40,'Historical evaluation timestamp missing')
    try:when=dt.datetime.fromisoformat(stamp.replace('Z','+00:00'))
    except ValueError:raise t.Refused('Historical evaluation timestamp invalid') from None
    need(when.tzinfo is not None and when.utcoffset()==dt.timedelta(0) and when.isoformat()==stamp and
         when>=dt.datetime.fromisoformat(RUN_UPDATED.replace('Z','+00:00')),'Historical evaluation timestamp is not canonical actual UTC time')
    return {'historical_replay':True,'current_source_eligible':False,'automatic_intake_eligible':False,'production_eligible':False,'publication_authorized':False,
        'collector_run_id':str(RUN_ID),'collector_run_attempt':ATTEMPT,'collector_artifact_id':ARTIFACT_ID,
        'collector_artifact_sha256':ARTIFACT_SHA,'collector_artifact_bytes':ARTIFACT_SIZE,
        'collector_artifact_created_at':'2026-11-05T03:04:02Z','collector_artifact_expires_at':'2027-02-02T21:53:59Z',
        'saved_source_commit':SAVED,'collector_runtime_commit':SOURCE,'collector_workflow_event_head':HEAD,
        'source_date':OBSERVED_DATE,'source_original_as_of_jst_date':OBSERVED_DATE,
        'source_original_as_of_utc':ORIGINAL_AS_OF_UTC,'source_receipt_started_at_ms':RECEIPT_STARTED_MS,
        'source_receipt_stopped_at_ms':RECEIPT_STOPPED_MS,'source_run_updated_at':RUN_UPDATED,
        'historical_evaluated_at':stamp,'published_predecessor_snapshot_sha256':t.PREVIOUS}

class HistoricalResolver:
    def __init__(self, base_module, token, *, request, now):
        need(isinstance(now,dt.datetime) and now.tzinfo is not None,'Actual aware evaluation time required')
        need(base_module.REPOSITORY==REPOSITORY and base_module.WORKFLOW==WORKFLOW,'Wrong sealed source utility')
        self.base=base_module;self.now=now.astimezone(dt.timezone.utc)
        self.reads=base_module.Resolver(token,request=request,now=self.now)
        self.api=self.reads.api;self.contents=self.reads.contents
        self.PREFIX=base_module.PREFIX

    def exact_run(self):
        repo=self.api(self.PREFIX);workflow=self.api(self.PREFIX+'/actions/workflows/daily_scrape.yml')
        need(exact(repo.get('id'),REPOSITORY_ID) and repo.get('full_name')==REPOSITORY and repo.get('default_branch')=='main',
             'Historical repository identity differs')
        need(exact(workflow.get('id'),WORKFLOW_ID) and workflow.get('path')==WORKFLOW,'Historical workflow identity differs')
        run=self.api(self.PREFIX+'/actions/runs/'+str(RUN_ID))
        want={'id':RUN_ID,'run_number':RUN_NUMBER,'run_attempt':ATTEMPT,'workflow_id':WORKFLOW_ID,
              'path':WORKFLOW,'head_branch':'main','head_sha':HEAD,'event':'repository_dispatch',
              'status':'completed','conclusion':'success','created_at':RUN_STARTED,
              'run_started_at':RUN_STARTED,'updated_at':RUN_UPDATED}
        need(all(exact(run.get(k),v) for k,v in want.items()),'Pinned historical successful run changed')
        for key in ('repository','head_repository'):
            need(exact(run.get(key,{}).get('id'),REPOSITORY_ID) and run[key].get('full_name')==REPOSITORY,'Historical fork/repository mismatch')
        need(self.base.timestamp(RUN_STARTED)<=self.base.timestamp(RUN_UPDATED)<=self.now,'Historical run is future-dated')
        return repo,workflow,run

    def jobs(self):
        value=self.api(self.PREFIX+f'/actions/runs/{RUN_ID}/attempts/{ATTEMPT}/jobs?per_page=100&page=1')
        need(exact(value.get('total_count'),1) and isinstance(value.get('jobs'),list) and len(value['jobs'])==1,'Exact historical job required')
        job=value['jobs'][0]
        want={'id':JOB_ID,'run_id':RUN_ID,'run_attempt':ATTEMPT,'head_sha':HEAD,'name':'scrape','status':'completed','conclusion':'success'}
        need(all(exact(job.get(k),v) for k,v in want.items()),'Historical job identity/outcome differs')
        need(isinstance(job.get('steps'),list),'Historical steps missing')
        for name,outcome in STEPS:
            matches=[s for s in job['steps'] if s.get('name')==name]
            need(len(matches)==1 and matches[0].get('status')=='completed' and matches[0].get('conclusion')==outcome,
                 'Historical required step missing or unsuccessful')
        return job

    def artifact(self):
        value=self.api(self.PREFIX+f'/actions/runs/{RUN_ID}/artifacts?per_page=100&page=1')
        rows=value.get('artifacts')
        need(type(value.get('total_count'))is int and isinstance(rows,list) and value['total_count']==len(rows)<=100,'Historical artifact listing incomplete')
        name=f'boopadb-collector-{RUN_ID}-{ATTEMPT}';matches=[a for a in rows if a.get('name')==name]
        need(len(matches)==1,'Exact historical artifact missing or ambiguous');a=matches[0]
        want={'id':ARTIFACT_ID,'name':name,'size_in_bytes':ARTIFACT_SIZE,'digest':'sha256:'+ARTIFACT_SHA,
              'expired':False,'created_at':'2026-11-05T03:04:02Z','updated_at':'2026-11-05T03:04:02Z','expires_at':'2027-02-02T21:53:59Z'}
        need(all(exact(a.get(k),v) for k,v in want.items()),'Historical artifact identity/digest differs')
        run=a.get('workflow_run',{});want={'id':RUN_ID,'repository_id':REPOSITORY_ID,'head_repository_id':REPOSITORY_ID,'head_sha':HEAD,'head_branch':'main'}
        need(all(exact(run.get(k),v) for k,v in want.items()),'Historical artifact origin differs')
        need(self.base.timestamp(a['created_at'])<=self.now<self.base.timestamp(a['expires_at']),'Historical artifact expired or future-dated')
        return a

    def resolve(self, workdir, baseline_pin, baseline_sha, producer_pin):
        workdir=Path(workdir);need(not workdir.exists() and not workdir.is_symlink(),'Fresh historical resolver workspace required')
        workdir.mkdir(parents=True,mode=0o700)
        pin_raw=t.regular(producer_pin);need(t.sha(pin_raw)==PRODUCER_SHA,'Installed producer pin changed')
        pin=t.strict(pin_raw);need(pin.get('schema')=='boopa-producer-pin-v1' and pin.get('repository')==REPOSITORY and
             set(pin.get('files_sha256',{}))==set(self.base.SOURCE_FILES) and bool(pin.get('source_root_entries')),'Historical producer contract differs')
        need(t.sha(t.regular(baseline_pin))==baseline_sha==t.BASELINE,'Historical baseline input changed')
        repo,workflow,run=self.exact_run();job=self.jobs();artifact=self.artifact()
        saved=self.reads.archive(artifact)
        need(t.sha(t.encode(saved))==SAVED_CANONICAL_SHA,'Historical save receipt bytes differ')
        need(saved.get('tracker_commit')==SAVED and saved.get('run_id')==str(RUN_ID) and saved.get('run_attempt')=='1' and
             saved.get('repository')==REPOSITORY and saved.get('scraper_outcome')=='success' and saved.get('save_outcome')=='success',
             'Historical save receipt identity differs')
        need(t.sha(self.contents(WORKFLOW,HEAD))==pin['workflow_sha256'],'Historical evaluated workflow differs')
        commit=self.api(self.PREFIX+'/git/commits/'+SAVED)
        need(commit.get('sha')==SAVED and commit.get('tree',{}).get('sha')==ROOT_TREE and
             commit.get('url')==self.base.API+self.PREFIX+'/git/commits/'+SAVED,'Historical saved Git root differs')
        for sha,tree_sha in ((SOURCE,SOURCE_ROOT),(HEAD,EVENT_ROOT)):
            obj=self.api(self.PREFIX+'/git/commits/'+sha)
            need(obj.get('sha')==sha and obj.get('tree',{}).get('sha')==tree_sha and
                 obj.get('url')==self.base.API+self.PREFIX+'/git/commits/'+sha,'Historical source/event Git root differs')
        materialized=workdir/'tracker-proof';(materialized/'data').mkdir(parents=True)
        for name,digest in FILES.items():
            raw=self.contents(name,SAVED);need(t.sha(raw)==digest,'Historical original source receipt/state changed')
            (materialized/name).write_bytes(raw)
        receipt=t.strict(t.regular(materialized/'data/collection_receipt.json'))
        need(receipt.get('source_commit')==SOURCE and saved.get('collection_receipt_sha256')==FILES['data/collection_receipt.json'],
             'Historical actual source/receipt mismatch')
        for source in (SOURCE,SAVED):
            tree=self.api(self.PREFIX+'/git/trees/'+source)
            need(tree.get('truncated') is False and isinstance(tree.get('tree'),list),'Incomplete historical root')
            entries=tree['tree'];need(len({e['path'] for e in entries})==len(entries),'Duplicate historical root member')
            actual={e['path']:{k:e[k] for k in ('mode','type','sha')} for e in entries if e['path'] not in ('data','meta','.github')}
            need(actual==pin['source_root_entries'],'Historical actual source roots differ from installed producer')
        for name in self.base.SOURCE_FILES:
            need(t.sha(self.contents(name,SOURCE))==pin['files_sha256'][name],'Historical source file changed')
        for key,value in (('started_at_ms',RECEIPT_STARTED_MS),('stopped_at_ms',RECEIPT_STOPPED_MS),('deadline_ms',RECEIPT_DEADLINE_MS)):
            need(exact(receipt.get(key),value),'Original historical receipt clock changed')
        need(self.base.timestamp(RUN_STARTED).timestamp()*1000<=RECEIPT_STARTED_MS<=RECEIPT_STOPPED_MS<=self.base.timestamp(RUN_UPDATED).timestamp()*1000<=self.now.timestamp()*1000,
             'Historical observation chronology invalid')
        stopped=dt.datetime.fromtimestamp(RECEIPT_STOPPED_MS/1000,dt.timezone.utc)
        need(stopped.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat()==OBSERVED_DATE,'Historical JST observation date differs')
        ledger=t.strict(t.regular(materialized/'data/request_budget.json'));need(ledger.get('date')==OBSERVED_DATE,'Historical saved ledger date changed')
        live=workdir/'live';live.mkdir()
        need(self.reads.live_bytes('release-manifest.json',absent_ok=True) is None,'Historical legacy predecessor no longer serving')
        for name in ('index.html','item.html','snapshot-manifest.json'):(live/name).write_bytes(self.reads.live_bytes(name))
        need(t.sha(t.regular(live/'snapshot-manifest.json'))==t.PREVIOUS,'Historical trial fixed predecessor changed')
        need(self.reads.live_bytes('release-manifest.json',absent_ok=True) is None,'Live predecessor changed during historical acquisition')
        trusted={'repository':REPOSITORY,'workflow_path':WORKFLOW,'default_branch':'main','head_branch':'main',
            'run_id':str(RUN_ID),'run_attempt':'1','status':'completed','conclusion':'success','scraper_outcome':'success','save_outcome':'success'}
        config={'materializedDir':str(materialized.resolve()),'saveReceipt':saved,'trustedRun':trusted,'liveDir':str(live.resolve()),
            'baselinePinPath':str(Path(baseline_pin).resolve()),'expectedBaselinePinSha256':baseline_sha,'expectedDate':OBSERVED_DATE}
        config_path=workdir/'selector-config.json';t.write(config_path,config)
        script=Path(self.base.__file__).with_name('select-input.cjs')
        command="const fs=require('node:fs'),m=require(process.argv[1]),c=JSON.parse(fs.readFileSync(process.argv[2]));c.baselinePinBytes=fs.readFileSync(c.baselinePinPath);console.log(JSON.stringify(m.selectMaterialized(c)));"
        child=subprocess.run(['node','-e',command,str(script),str(config_path)],capture_output=True,text=True,timeout=120,env=t.clean_env(workdir))
        need(child.returncode==0,'Historical receipt/live-lineage consistency refused')
        selection=t.strict(child.stdout.encode())
        need(selection['tracker_commit']==SAVED and selection['prev_release_digest']==t.PREVIOUS and selection['expected_date']==OBSERVED_DATE,
             'Historical selection differs from fixed contract')
        # Re-authenticate the exact attempt and artifact, never ask for latest success.
        final=self.exact_run();need(final[2]==run and self.jobs()==job and self.artifact()==artifact,'Historical evidence changed during acquisition')
        selection['selection_authority']='authenticated-exact-historical-run-and-live-legacy-lineage'
        proof={'schema':'boopa-historical-resolved-inputs-v1','repository':REPOSITORY,'run_id':str(RUN_ID),'run_attempt':'1',
            'artifact_id':ARTIFACT_ID,'artifact_digest':'sha256:'+ARTIFACT_SHA,'source_commit':SOURCE,
            'producer_pin_sha256':PRODUCER_SHA,'evaluated_at':self.now.isoformat(),'selection':selection,
            'historical_replay':True,'current_source_eligible':False,'automatic_intake_eligible':False,'production_eligible':False,'publication_authorized':False,
            'original_as_of':OBSERVED_DATE,'original_source_date':OBSERVED_DATE,
            'original_source_as_of_utc':ORIGINAL_AS_OF_UTC,'workflow_event_head':HEAD,
            'original_receipt_started_at_ms':RECEIPT_STARTED_MS,'original_receipt_stopped_at_ms':RECEIPT_STOPPED_MS,
            'original_run_updated_at':RUN_UPDATED,'currentness_policy':'deliberately-not-evaluated-exact-historical-replay-only'}
        t.write(workdir/'resolved-inputs.json',proof);return proof
