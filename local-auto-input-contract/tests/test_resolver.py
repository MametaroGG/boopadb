import base64
import copy
import datetime as dt
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
import urllib.parse
import zipfile

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('resolver', ROOT / 'resolve_automatic_inputs.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
NOW = dt.datetime(2026, 11, 1, 8, 30, tzinfo=dt.timezone.utc)

class Fixture:
    def __init__(self, root):
        self.root = Path(root); self.calls=[]; self.changes={}; self.redirect=False
        self.source='c'*40; self.commit='d'*40; self.head='a'*40
        self.repo={'id':12,'full_name':m.REPOSITORY,'default_branch':'main'}
        self.workflow={'id':34,'path':m.WORKFLOW,'state':'active'}
        self.run=dict(id=123,run_number=50,run_attempt=1,repository=self.repo,head_repository=self.repo,
            workflow_id=34,path=m.WORKFLOW,head_branch='main',event='schedule',status='completed',
            conclusion='success',head_sha=self.head,updated_at='2026-11-01T08:00:00Z')
        self.receipt=dict(schema='boopa-collection-receipt-v1',repository=m.REPOSITORY,
            run_id='123',run_attempt='1',source_commit=self.source,reservation_id='123-1',
            scope='bounded-filtered-search-observation',whole_catalog_complete=False,
            status='paused',reason='deadline',failed=False,reservation_completed=True,pending_retry_count=0,
            started_at_ms=1793519940000,stopped_at_ms=1793520000000,deadline_ms=1793520000000,blocked_until_ms=0,
            metrics=dict(searchPages=1,searchFailures=0,itemSuccess=1,itemFailures=0,unavailable=0,
                retries=0,duplicatesAvoided=0,chargedHttpAttempts=2,dailyChargedRequests=2))
        self.files={
            (self.commit,'data/collection_receipt.json'):json.dumps(self.receipt).encode(),
            (self.commit,'data/request_budget.json'):json.dumps(dict(date='2026-11-01',blockedUntil=0,reservation=dict(id='123-1',completed=True))).encode(),
            (self.commit,'data/crawl_state.json'):b'{"urlIndex":0,"page":10,"retries":[]}',
            (self.head,m.WORKFLOW):b'reviewed workflow fixture'}
        for name in m.SOURCE_FILES:self.files[self.source,name]=('reviewed '+name).encode()
        self.pin=dict(schema='boopa-producer-pin-v1',repository=m.REPOSITORY,
            workflow_sha256=m.digest(self.files[self.head,m.WORKFLOW]),
            files_sha256={n:m.digest(self.files[self.source,n]) for n in m.SOURCE_FILES},
            source_root_entries={'src':dict(mode='040000',type='tree',sha='e'*40)})
        self.pinpath=self.root/'producer.json';self.pinpath.write_text(json.dumps(self.pin))
        self.baseline=self.root/'baseline.json';self.baseline.write_bytes(b'{}')
        self.saved=dict(schema='boopa-saved-collection-v1',repository=m.REPOSITORY,run_id='123',run_attempt='1',
            scraper_outcome='success',save_outcome='success',tracker_commit=self.commit,
            collection_receipt_sha256=m.digest(self.files[self.commit,'data/collection_receipt.json']))
        self.pack()
        self.job=dict(run_id=123,run_attempt=1,name='scrape',status='completed',conclusion='success',steps=[
            dict(name=n,conclusion=c) for n,c in [('Verify reviewed source before dependencies','success'),
            ('Verify reviewed source before collection','success'),('Verify reviewed source after save','success'),('Run Scraper','success'),('Commit and Push','success'),
            ('Report scraper failure','skipped'),('Record immutable saved collection','success'),
            ('Retain immutable saved collection','success')]])
        self.release=json.dumps(dict(schema=1,generation=1,product_count=10,source_date='2026-11-01',
          tracker_commit='1'*40,generator_commit='2'*40,run_id='7',inventory_digest='3'*64,prev_release_digest='4'*64)).encode()
    def pack(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:z.writestr('saved-collection.json',json.dumps(self.saved))
        self.archive=b.getvalue()
        self.artifact=dict(id=56,name='boopadb-collector-123-1',expired=False,expires_at='2026-11-05T00:00:00Z',
            digest='sha256:'+m.digest(self.archive),workflow_run=dict(id=123,head_sha=self.head,head_branch='main'))
    def request(self,url,headers):
        self.calls.append((url,headers.copy()))
        if url in self.changes:
            value=self.changes[url]
            return value() if callable(value) else value
        if url.startswith('https://example.blob.core.windows.net/'):
            return 200,{},self.archive
        if url==m.LIVE+'/release-manifest.json':return 200,{},self.release
        assert url.startswith(m.API),url
        endpoint=url[len(m.API):];p=m.PREFIX
        if endpoint==p:body=self.repo
        elif endpoint==p+'/actions/workflows/daily_scrape.yml':body=self.workflow
        elif endpoint==p+'/actions/workflows/34/runs?branch=main&status=completed&per_page=100&page=1':body={'workflow_runs':[self.run]}
        elif endpoint==p+'/actions/runs/123':body=self.run
        elif endpoint==p+'/actions/runs/123/attempts/1/jobs?per_page=100&page=1':body={'total_count':1,'jobs':[self.job]}
        elif endpoint==p+'/actions/runs/123/artifacts?per_page=100&page=1':body={'total_count':1,'artifacts':[self.artifact]}
        elif endpoint==p+'/actions/artifacts/56/zip':
            if self.redirect:return 302,{'Location':'https://example.blob.core.windows.net/container/signed?secret=download-only'},b''
            return 200,{},self.archive
        elif endpoint==p+'/git/commits/'+self.commit:body={'sha':self.commit}
        elif endpoint in (p+'/git/trees/'+self.source,p+'/git/trees/'+self.commit):
            body={'truncated':False,'tree':[dict(path=k,**v) for k,v in self.pin['source_root_entries'].items()]}
        elif endpoint.startswith(p+'/contents/'):
            u=urllib.parse.urlsplit(endpoint);name=urllib.parse.unquote(u.path[len(p+'/contents/'):]);ref=urllib.parse.parse_qs(u.query)['ref'][0]
            b=self.files[ref,name];body=dict(type='file',path=name,encoding='base64',content=base64.b64encode(b).decode(),
                size=len(b),sha=hashlib.sha1(b'blob '+str(len(b)).encode()+b'\0'+b).hexdigest())
        else:raise AssertionError(endpoint)
        return 200,{},json.dumps(body).encode()
    def resolve(self):
        return m.Resolver('TOKEN_MUST_NOT_LEAK',request=self.request,now=NOW).resolve(
            self.root/'work',self.baseline,m.digest(self.baseline.read_bytes()),self.pinpath)

class ResolverTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.f=Fixture(self.temp.name)
    def refused(self):
        with self.assertRaises((m.Refused,ValueError,KeyError)):self.f.resolve()
        self.assertFalse((self.f.root/'work/resolved-inputs.json').exists())
    def test_success_and_exact_context(self):
        result=self.f.resolve();s=result['selection']
        self.assertEqual(s['tracker_commit'],self.f.commit);self.assertEqual(s['generation'],2)
        self.assertEqual(s['prev_release_digest'],m.digest(self.f.release))
        inventory=self.f.root/'inventory.json';inventory.write_bytes(b'{"files": []}\n')
        context=m.finalize_context(self.f.root/'work/resolved-inputs.json',inventory,self.f.root/'context.json',
            dict(GITHUB_ACTIONS='true',GITHUB_SHA='b'*40,GITHUB_RUN_ID='222',GITHUB_RUN_ATTEMPT='1'))
        self.assertEqual(set(context),{'synthetic','tracker_commit','generator_commit','run_id','run_attempt',
            'generation','prev_release_digest','expected_date','inventory_digest'})
        self.assertEqual(context['inventory_digest'],m.digest(inventory.read_bytes()))
        self.assertFalse(context['synthetic'])
    def test_redirect_never_forwards_token(self):
        self.f.redirect=True;self.f.resolve()
        for url,headers in self.f.calls:
            if not url.startswith(m.API+'/'):self.assertNotIn('Authorization',headers)
        for p in (self.f.root/'work').rglob('*'):
            if p.is_file():self.assertNotIn(b'TOKEN_MUST_NOT_LEAK',p.read_bytes())
    def test_unapproved_redirect_host_rejected(self):
        self.f.changes[m.API+m.PREFIX+'/actions/artifacts/56/zip']=(302,{'Location':'https://evil.example/archive'},b'')
        self.refused();self.assertFalse(any('evil.example' in u for u,h in self.f.calls))
    def test_newest_failure_never_falls_back(self):self.f.run['conclusion']='failure';self.refused()
    def test_stale_run_rejected(self):self.f.run['updated_at']='2026-10-30T00:00:00Z';self.refused()
    def test_future_run_rejected(self):self.f.run['updated_at']='2026-11-02T00:00:00Z';self.refused()
    def test_other_repo_rejected(self):self.f.repo['full_name']='other/repo';self.refused()
    def test_other_workflow_rejected(self):self.f.run['path']='.github/workflows/other.yml';self.refused()
    def test_wrong_branch_rejected(self):self.f.run['head_branch']='feature';self.refused()
    def test_fork_head_rejected(self):self.f.run['head_repository']={'id':999};self.refused()
    def test_duplicate_artifact_rejected(self):
        self.f.changes[m.API+m.PREFIX+'/actions/runs/123/artifacts?per_page=100&page=1']=(200,{},json.dumps({'total_count':2,'artifacts':[self.f.artifact,self.f.artifact]}).encode());self.refused()
    def test_expired_artifact_rejected(self):self.f.artifact['expired']=True;self.refused()
    def test_missing_digest_rejected(self):del self.f.artifact['digest'];self.refused()
    def test_digest_tamper_rejected(self):self.f.archive+=b'tamper';self.refused()
    def test_wrong_attempt_rejected(self):self.f.saved['run_attempt']='2';self.f.pack();self.refused()
    def test_partial_cannot_use_successful_job(self):
        self.f.receipt['status']='partial';b=json.dumps(self.f.receipt).encode();self.f.files[self.f.commit,'data/collection_receipt.json']=b
        self.f.saved['collection_receipt_sha256']=m.digest(b);self.f.pack();self.refused()
    def test_original_failure_rejected(self):self.f.saved['scraper_outcome']='failure';self.f.pack();self.refused()
    def test_unreviewed_workflow_rejected(self):self.f.files[self.f.head,m.WORKFLOW]=b'changed';self.refused()
    def test_unreviewed_actual_checkout_rejected(self):self.f.files[self.f.source,'src/scraper.js']=b'changed';self.refused()
    def test_failed_live_fetch_not_absence(self):self.f.changes[m.LIVE+'/release-manifest.json']=(403,{},b'');self.refused()
    def test_live_changed_rejected(self):
        responses=iter([(200,{},self.f.release),(200,{},self.f.release+b' ')])
        self.f.changes[m.LIVE+'/release-manifest.json']=lambda:next(responses);self.refused()
    def test_rerun_during_resolution_rejected(self):
        calls=[0]
        def result():
            calls[0]+=1;r=copy.deepcopy(self.f.run)
            if calls[0]>1:r['run_attempt']=2
            return 200,{},json.dumps(r).encode()
        self.f.changes[m.API+m.PREFIX+'/actions/runs/123']=result;self.refused()
    def test_api_access_failure_is_closed_and_sanitized(self):
        self.f.changes[m.API+m.PREFIX]=(403,{},b'TOKEN_MUST_NOT_LEAK')
        with self.assertRaises(m.Refused) as e:self.f.resolve()
        self.assertNotIn('TOKEN_MUST_NOT_LEAK',str(e.exception))
    def test_source_changed_by_final_rebase_rejected(self):
        self.f.changes[m.API+m.PREFIX+'/git/trees/'+self.f.commit]=(200,{},json.dumps({'truncated':False,'tree':[]}).encode());self.refused()
    def test_claimed_source_does_not_bypass_source_gate(self):
        self.f.job['steps']=[s for s in self.f.job['steps'] if s['name']!='Verify reviewed source before collection'];self.refused()
    def test_new_terminal_failure_during_downloads_rejected(self):
        endpoint=m.API+m.PREFIX+'/actions/workflows/34/runs?branch=main&status=completed&per_page=100&page=1'
        calls=[0]
        def listing():
            calls[0]+=1;r=copy.deepcopy(self.f.run)
            if calls[0]>1:r.update(id=124,run_number=51,conclusion='failure')
            return 200,{},json.dumps({'workflow_runs':[r]}).encode()
        later=copy.deepcopy(self.f.run);later.update(id=124,run_number=51,conclusion='failure')
        self.f.changes[endpoint]=listing
        self.f.changes[m.API+m.PREFIX+'/actions/runs/124']=(200,{},json.dumps(later).encode());self.refused()
    def test_newer_active_run_is_not_a_terminal_candidate(self):
        # Endpoint explicitly requests completed runs; an active successor is
        # intentionally not queried as a selectable snapshot or latest main.
        self.f.resolve()
        queries=[u for u,h in self.f.calls if '/runs?branch=' in u]
        self.assertEqual(len(queries),2)
        self.assertTrue(all('status=completed' in u for u in queries))
    def test_future_receipt_timestamp_rejected(self):
        self.f.receipt['stopped_at_ms']=int((NOW+dt.timedelta(hours=1)).timestamp()*1000)
        b=json.dumps(self.f.receipt).encode();self.f.files[self.f.commit,'data/collection_receipt.json']=b
        self.f.saved['collection_receipt_sha256']=m.digest(b);self.f.pack();self.refused()
    def test_duplicate_json_rejected(self):
        with self.assertRaises(m.Refused):m.parse(b'{"a":1,"a":2}')
    def test_extra_zip_entry_rejected(self):
        b=io.BytesIO()
        with zipfile.ZipFile(b,'w') as z:
            z.writestr('saved-collection.json',json.dumps(self.f.saved));z.writestr('../escape','oops')
        self.f.archive=b.getvalue();self.f.artifact['digest']='sha256:'+m.digest(self.f.archive);self.refused()

if __name__=='__main__':unittest.main()
