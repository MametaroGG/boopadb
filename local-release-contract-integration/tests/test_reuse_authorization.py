"""All authorization records in these tests are SYNTHETIC, never owner grants."""
import copy,json,os,shutil,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from test_pipeline import PipelineTests
import release_contract as rc
import run_candidate
import reuse_authorization as reuse

class ReuseTests(PipelineTests):
    def setUp(self):
        super().setUp()
        self.ptmp=tempfile.TemporaryDirectory(prefix='.synthetic-reuse-',dir=reuse.ROOT)
        self.addCleanup(self.ptmp.cleanup); self.pr=Path(self.ptmp.name)
        # Use actual original fixture bytes but new checkout-contained paths.
        self.pin_path=self.pr/'baseline.json';rc.write_json(self.pin_path,self.pin)
        rel={}
        for i,(key,value) in enumerate(self.relation_inputs.items()):
            p=self.pr/(str(i)+'.json');shutil.copyfile(value,p);rel[key]=p.name
        self.relations_path=self.pr/'relations.json';rc.write_json(self.relations_path,rel)
        for _,ak,_,bk in run_candidate.RELATIONS: self.config[ak]=str(self.pr/rel[bk])
        rc.write_json(self.config_path,self.config)
        self.grant=self.pr/'grant.txt';self.grant.write_text('SYNTHETIC UNIT TEST ONLY. NO OWNER AUTHORITY.\n')
        self.trust={'schema':'boopa-production-reuse-v1','scope':'production-exact-historical-relations-reuse',
          'synthetic':True,'repository':'MametaroGG/boopadb','baseline_sha256':rc.digest(self.pin_path),
          'relations_binding':{k:self.pin['relations_binding'][k] for k in reuse.KEYS},
          'implementation_inventory_sha256':rc.digest(reuse.HERE/'GENERATOR-INVENTORY.json'),
          'runtime_files_sha256':{k:rc.digest(reuse.ROOT/k) for k in reuse.RUNTIME_FILES},
          'grant_sha256':rc.digest(self.grant),'grant_reference':'SYNTHETIC TEST REFERENCE'}
        self.trust_path=self.pr/'trust.json';rc.write_json(self.trust_path,self.trust)
        self.policy={'schema':'boopa-reuse-policy-v1','trust_path':'trust.json','trust_sha256':rc.digest(self.trust_path),
          'grant_path':'grant.txt','baseline_path':'baseline.json','baseline_sha256':rc.digest(self.pin_path),
          'relation_inputs_path':'relations.json','implementation_inventory_path':os.path.relpath(reuse.HERE/'GENERATOR-INVENTORY.json',self.pr)}
        self.policy_path=self.pr/'policy.json';rc.write_json(self.policy_path,self.policy)
    def verify(self,context=None):
        return reuse.verify(self.policy_path,context or self.context,self.pin_path,rc.digest(self.pin_path),self.relations_path)
    def repin_synthetic_trust(self):
        rc.write_json(self.trust_path,self.trust);self.policy['trust_sha256']=rc.digest(self.trust_path);rc.write_json(self.policy_path,self.policy)
    def test_valid_synthetic_contract(self): self.assertEqual(self.verify()['authorization_sha256'],rc.digest(self.trust_path))
    def test_missing_policy(self):
        self.policy_path.unlink()
        with self.assertRaises((ValueError,FileNotFoundError)): self.verify()
    def test_untrusted_modified_record(self):
        self.trust['grant_reference']='changed';rc.write_json(self.trust_path,self.trust)
        with self.assertRaisesRegex(ValueError,'untrusted'): self.verify()
    def test_wrong_scope(self):
        self.trust['scope']='nonpublic-test-only';self.repin_synthetic_trust()
        with self.assertRaisesRegex(ValueError,'scope'): self.verify()
    def test_no_synthetic_promotion(self):
        with self.assertRaisesRegex(ValueError,'fixture'): self.verify({**self.context,'synthetic':False})
    def test_wrong_repo(self):
        self.trust['repository']='other/repo';self.repin_synthetic_trust()
        with self.assertRaisesRegex(ValueError,'repository'):self.verify()
    def test_grant_tamper(self):
        self.grant.write_text('altered synthetic text')
        with self.assertRaisesRegex(ValueError,'grant'): self.verify()
    def test_historical_approval_tamper(self):
        (self.pr/'1.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'historical relation'):self.verify()
    def test_runtime_pin_tamper(self):
        self.trust['runtime_files_sha256'][next(iter(reuse.RUNTIME_FILES))]='0'*64;self.repin_synthetic_trust()
        with self.assertRaisesRegex(ValueError,'runtime implementation'):self.verify()
    def test_archive_and_context_replay(self):
        archive=self.pr/'archive';archive.write_bytes(b'SYNTHETIC archive')
        ev=self.pr/'envelope.json';rc.write_json(ev,reuse.envelope(self.policy_path,self.context,self.pin_path,rc.digest(self.pin_path),self.relations_path,archive))
        for field,value in [('run_id','123'),('run_attempt','2'),('generator_commit','3'*40),('tracker_commit','4'*40),('generation',3)]:
            with self.subTest(field=field),self.assertRaisesRegex(ValueError,'handoff'):
                reuse.check_envelope(self.policy_path,{**self.context,field:value},self.pin_path,rc.digest(self.pin_path),self.relations_path,archive,ev)
        archive.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError,'handoff'):
            reuse.check_envelope(self.policy_path,self.context,self.pin_path,rc.digest(self.pin_path),self.relations_path,archive,ev)
    def test_synthetic_handoff_refused_before_api(self):
        a=self.pr/'artifact';(a/'evidence').mkdir(parents=True)
        rc.write_json(a/'evidence/reuse-envelope.json',{'context':self.context})
        with self.assertRaisesRegex(ValueError,'synthetic'):
            reuse.handoff(a,self.policy_path,self.pr/'absent-run',self.pr/'absent-checkout')
    def test_full_synthetic_generation_validation_chain(self):
        before=rc.digest(self.pin_path)
        dest=self.root/'supplemented-run'
        result=run_candidate.run(dest,**self.kwargs(),reuse_policy=self.policy_path)
        self.assertEqual(result['status'],'passed');self.assertTrue(result['synthetic'])
        self.assertEqual(rc.digest(self.pin_path),before)
        build=dest/'build-artifact'; qa=dest/'qa-artifact'
        self.assertEqual(rc.digest(build/'work/reuse-envelope.json'),rc.digest(qa/'evidence/reuse-envelope.json'))
        self.assertFalse((qa/'evidence/qa-review-record.json').exists())
        common=self.kwargs();common.pop('generation_config');common['reuse_policy']=self.policy_path
        self.assertEqual(rc.validate(build,self.root/'rechecked',**common)['status'],'build-artifact-contract-validated')
        ev=rc.load_strict_json(build/'work/reuse-envelope.json');ev['context']['run_id']='123';rc.write_json(build/'work/reuse-envelope.json',ev)
        with self.assertRaisesRegex(ValueError,'handoff'):
            rc.validate(build,self.root/'tampered',**common)
    def test_api_source_binding_checks_synthetic_only(self):
        # API schema/checkout contract unit test; Git transport is explicitly
        # mocked, no real run or owner grant is represented by this fixture.
        record={'repository':{'full_name':'MametaroGG/boopadb'},'status':'completed',
                'conclusion':'success','id':int(self.context['run_id']),
                'run_attempt':1,'head_sha':self.context['generator_commit']}
        api=self.pr/'synthetic-api.json';rc.write_json(api,record)
        with patch.object(reuse.subprocess,'check_output',return_value=self.context['generator_commit']+'\n'):
            reuse.source_checks(api,reuse.ROOT,self.context,self.trust)
            for k,v in [('id',1),('run_attempt',2),('head_sha','3'*40),('status','in_progress'),('conclusion','failure'),('repository',{'full_name':'other/repo'})]:
                rc.write_json(api,{**record,k:v})
                with self.subTest(field=k),self.assertRaises(ValueError):
                    reuse.source_checks(api,reuse.ROOT,self.context,self.trust)
        rc.write_json(api,record)
        with patch.object(reuse.subprocess,'check_output',return_value='9'*40+'\n'):
            with self.assertRaisesRegex(ValueError,'checkout'):
                reuse.source_checks(api,reuse.ROOT,self.context,self.trust)
    def test_independent_qa_digest_binding(self):
        ev=self.pr/'synthetic-envelope.json';rc.write_json(ev,{'authorization_sha256':'1'*64,'synthetic':True})
        review=self.pr/'synthetic-review.json';rc.write_json(review,{'synthetic':True,'relation_reuse_binding_sha256':rc.digest(ev)})
        self.assertEqual(reuse.review_binding(ev,review)['reuse_envelope_sha256'],rc.digest(ev))
        rc.write_json(ev,{'authorization_sha256':'2'*64,'synthetic':True})
        with self.assertRaisesRegex(ValueError,'independent QA'):reuse.review_binding(ev,review)
        rc.write_json(review,{'synthetic':True})
        with self.assertRaisesRegex(ValueError,'independent QA'):reuse.review_binding(ev,review)
    def test_policy_symlink_refused(self):
        alias=self.pr/'alias.json';alias.symlink_to(self.policy_path)
        with self.assertRaisesRegex(ValueError,'symlink'):reuse.policy(alias)
    def test_old_production_scope_guard_unchanged(self):
        with self.assertRaisesRegex(ValueError,'local/synthetic'):
            run_candidate.configuration(self.config_path,self.relations_path,{**self.context,'synthetic':False})

if __name__=='__main__':unittest.main()
