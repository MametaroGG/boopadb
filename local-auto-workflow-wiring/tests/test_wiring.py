import contextlib
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE))
import workflow_driver as d

class WiringTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=HERE)
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tracker = self.root / 'tracker'
        (self.tracker / 'data').mkdir(parents=True)
        (self.tracker / 'meta').mkdir()
        (self.tracker / 'data/1.json').write_text('{"id": "1"}')
        (self.tracker / 'meta/note.txt').write_text('Every regular file inventoried')
        subprocess.run(['git', 'init', '-q', str(self.tracker)], check=True)
        subprocess.run(['git', '-C', str(self.tracker), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.tracker), '-c', 'user.name=local test',
                        '-c', 'user.email=local@example.invalid', 'commit', '-qm', 'synthetic local test'], check=True)
        self.commit = d.head(self.tracker)
        self.env = dict(GITHUB_ACTIONS='true', GITHUB_SHA='2'*40,
                        GITHUB_RUN_ID='100', GITHUB_RUN_ATTEMPT='2')
        self.config = {'schema':1,'config_sha256':'9'*64,'baseline_pin':self.root/'pin.json',
                       'baseline_sha256':'8'*64,'producer_pin':self.root/'producer.json',
                       'relation_inputs':self.root/'relations.json','generation_config':self.root/'generation.json'}
        for key in ('baseline_pin','producer_pin','relation_inputs','generation_config'):
            self.config[key].write_text('{}')
        self.proof = {'schema':'boopa-resolved-inputs-v1',
                      'producer_pin_sha256':d.sha(self.config['producer_pin']),
                      'selection': {'tracker_commit':self.commit, 'generation':2,
                      'prev_release_digest':'3'*64, 'expected_date':'2026-11-01',
                      'selection_authority':'authenticated-github-read-and-live-lineage',
                      'whole_catalog_complete':False,'collection_scope':'bounded-filtered-search-observation'}}
        self.calls=[]

    def mock_run(self, script, *args):
        self.calls.append((Path(script).name, tuple(map(str,args))))
        if Path(script) == d.RESOLVER and args[0] == 'resolve':
            dest=Path(args[args.index('--workdir')+1]);dest.mkdir()
            d.write_new(dest/'resolved-inputs.json',self.proof)
        elif Path(script) == d.RESOLVER and args[0] == 'finalize-context':
            # Execute the REAL offline context finalizer, not a fake output.
            spec=importlib.util.spec_from_file_location('actual_resolver',d.RESOLVER)
            resolver=importlib.util.module_from_spec(spec);spec.loader.exec_module(resolver)
            vals={args[i]:args[i+1] for i in range(1,len(args),2)}
            resolver.finalize_context(vals['--selection'],vals['--inventory'],vals['--output'])
        elif Path(script).name == 'inventory_snapshot.py':
            # Execute the real canonical inventory CLI against a local Git fixture.
            subprocess.run([sys.executable,str(script),*map(str,args)],check=True,capture_output=True)
        elif Path(script).name == 'run_candidate.py':
            dest=Path(args[args.index('--dest')+1]);dest.mkdir()
            # Runner process itself is mocked: no false claim these are QA bytes.
            (dest/'MOCK-NOT-QA.txt').write_text('No generator execution in wiring test')
        elif Path(script).name == 'validation_job.py':
            dest=Path(args[args.index('--dest')+1]);dest.mkdir()
        else: self.fail('Unexpected executable: '+str(script))

    def test_real_inventory_finalize_and_mocked_shell_contract_in_order(self):
        work=self.root/'work';output=self.root/'outputs'
        with patch.dict(os.environ,{**self.env,'GITHUB_OUTPUT':str(output)}), \
             patch.object(d,'preflight',return_value=self.config),patch.object(d,'run',side_effect=self.mock_run):
            d.resolve('not-used',work)
            self.assertEqual(output.read_text(),f'tracker_commit={self.commit}\n')
            d.build('not-used',work,self.tracker)
            context=d.load(work/'context.json')
            self.assertEqual(set(context),d.CONTEXT_KEYS)
            self.assertEqual(len(context),9)
            self.assertFalse(context['synthetic'])
            self.assertEqual(context['run_id'],'100')
            self.assertEqual(context['run_attempt'],'2')
            self.assertEqual(context['inventory_digest'],d.sha(work/'input-inventory.json'))
            self.assertIn('meta/note.txt',d.load(work/'input-inventory.json'))
            receiver=self.root/'receiver';shutil.copytree(work/'selection-handoff',receiver)
            d.validate('not-used',receiver,self.tracker,'incoming',self.root/'qa')
        self.assertEqual([x[0] for x in self.calls],['resolve_automatic_inputs.py',
            'inventory_snapshot.py','resolve_automatic_inputs.py','run_candidate.py',
            'inventory_snapshot.py','resolve_automatic_inputs.py','validation_job.py'])
        for name,args in self.calls:
            if name=='run_candidate.py':
                self.assertIn('--generation-config',args)
                self.assertIn('--baseline-sha256',args)
                self.assertNotIn('--fixture',args)
        self.assertEqual((work/'input-inventory.json').read_bytes(),(receiver/'input-inventory.json').read_bytes())

    def test_wrong_checkout_rejected_before_inventory(self):
        work=self.root/'work';(work/'selection').mkdir(parents=True)
        self.proof['selection']['tracker_commit']='1'*40
        d.write_new(work/'selection/resolved-inputs.json',self.proof)
        d.write_new(work/'config-binding.json',{'config_sha256':self.config['config_sha256']})
        with patch.object(d,'preflight',return_value=self.config),patch.object(d,'run') as run:
            with self.assertRaisesRegex(ValueError,'Tracker checkout differs'):
                d.prepare('unused',work,self.tracker)
            run.assert_not_called()

    def test_no_fallback_or_qa_after_resolver_failure(self):
        with patch.object(d,'preflight',return_value=self.config), \
             patch.object(d,'run',side_effect=subprocess.CalledProcessError(1,['resolver'])):
            with self.assertRaises(subprocess.CalledProcessError): d.resolve('unused',self.root/'failed')
        self.assertFalse((self.root/'failed/selection-handoff').exists())
        self.assertFalse((self.root/'failed/candidate').exists())

    def test_malformed_selection_refused(self):
        p=self.root/'proof.json'
        for field,value in [('tracker_commit','main'),('generation',True),
                            ('whole_catalog_complete',True),('expected_date','2026-02-30')]:
            proof=json.loads(json.dumps(self.proof));proof['selection'][field]=value
            p.write_text(json.dumps(proof))
            with self.subTest(field=field),self.assertRaises(ValueError):d.selection(p)

    def test_configuration_placeholders_unknown_keys_and_digest_refused(self):
        with self.assertRaisesRegex(ValueError,'Real baseline SHA256'):
            d.configuration(HERE/'production-config.EXAMPLE.json')
        p=self.root/'config.json'
        c={'schema':1,'baseline_sha256':d.sha(self.config['baseline_pin']),
           **{k: self.config[k].name for k in ('baseline_pin','producer_pin','relation_inputs','generation_config')}}
        p.write_text(json.dumps(c));self.assertEqual(d.configuration(p)['baseline_pin'],self.config['baseline_pin'])
        c['producer_pin']='producer-pin.PROPOSAL.json';p.write_text(json.dumps(c))
        with self.assertRaisesRegex(ValueError,'proposal/example/placeholder'):d.configuration(p)
        c['extra']='ignored?';p.write_text(json.dumps(c))
        with self.assertRaisesRegex(ValueError,'exact production'):d.configuration(p)

    def test_schema_two_reuse_forwarded_and_exact(self):
        policy=self.root/'reuse-policy.json';policy.write_text('{}')
        c={**self.config,'schema':2,'reuse_policy':policy}
        args=d.common(c,self.root/'work',self.tracker)
        self.assertEqual(args[-2:],['--reuse-policy',policy])
        self.assertNotIn('--reuse-policy',d.common(self.config,self.root/'work',self.tracker))
        config={'schema':2,'baseline_sha256':d.sha(self.config['baseline_pin']),
                **{k:self.config[k].name for k in ('baseline_pin','producer_pin','relation_inputs','generation_config')},
                'reuse_policy':policy.name}
        path=self.root/'schema-two.json';path.write_text(json.dumps(config))
        self.assertEqual(d.configuration(path)['reuse_policy'],policy)
        del config['reuse_policy'];path.write_text(json.dumps(config))
        with self.assertRaisesRegex(ValueError,'exact production'):d.configuration(path)

    def test_duplicate_json_rejected(self):
        p=self.root/'duplicate.json';p.write_text('{"x":1,"x":2}')
        with self.assertRaisesRegex(ValueError,'Duplicate'):d.load(p)

    def test_actual_shell_passes_quoted_env_without_execution(self):
        bin=self.root/'bin';bin.mkdir();log=self.root/'args.json'
        shim=bin/'python3'
        shim.write_text('#!'+sys.executable+'\nimport sys,json,os\nopen(os.environ["ARG_LOG"],"w").write(json.dumps(sys.argv[1:]))\n')
        shim.chmod(0o755)
        marker=self.root/'must-not-exist'
        value=f'config name; touch {marker}; $(touch {marker})'
        result=subprocess.run(['bash',str(HERE/'run_stage.sh'),'build'],cwd=HERE.parent,
            env={**os.environ,'PATH':str(bin)+':'+os.environ['PATH'],'CONFIG_FILE':value,'ARG_LOG':str(log)},capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        args=json.loads(log.read_text());self.assertEqual(args[args.index('--config')+1],value)
        self.assertFalse(marker.exists())
        self.assertEqual(args[:2],['local-auto-workflow-wiring/workflow_driver.py','build'])

    def test_changed_config_handoff_refused(self):
        work=self.root/'work';(work/'selection').mkdir(parents=True)
        d.write_new(work/'selection/resolved-inputs.json',self.proof)
        d.write_new(work/'config-binding.json',{'config_sha256':'0'*64})
        with patch.object(d,'preflight',return_value=self.config),patch.object(d,'run') as command:
            with self.assertRaisesRegex(ValueError,'Configuration differs'):
                d.prepare('unused',work,self.tracker)
            command.assert_not_called()

    def test_reuse_refused_without_overwriting_context(self):
        work=self.root/'work';output=self.root/'outputs'
        with patch.dict(os.environ,{**self.env,'GITHUB_OUTPUT':str(output)}), \
             patch.object(d,'preflight',return_value=self.config),patch.object(d,'run',side_effect=self.mock_run):
            d.resolve('unused',work)
            d.prepare('unused',work,self.tracker)
            before=(work/'context.json').read_bytes()
            with self.assertRaises(subprocess.CalledProcessError):d.prepare('unused',work,self.tracker)
            self.assertEqual((work/'context.json').read_bytes(),before)
            with self.assertRaisesRegex(ValueError,'must be new'):d.resolve('unused',work)

    def test_actual_generator_identity_matches_and_wrong_head_refused(self):
        with patch.object(d,'ROOT',self.tracker),patch.dict(os.environ,{**self.env,'GITHUB_SHA':self.commit}):
            d.identity()
        with patch.object(d,'ROOT',self.tracker),patch.dict(os.environ,self.env):
            with self.assertRaisesRegex(ValueError,'Generator checkout HEAD differs'):d.identity()

    def test_workflow_audit_refuses_unpinned_actions_and_incompatible_inputs(self):
        import audit_workflow
        original=(HERE/'boopadb-daily.OFF.yml').read_text()
        mutants=[original.replace('actions/checkout@11d5960a326750d5838078e36cf38b85af677262','actions/checkout@v4'),
                 original.replace("python-version: '3.12'","invented-python-option: '3.12'"),
                 original.replace('if: ${{ false }}','if: ${{ true }}'),
                 original.replace('workflow_dispatch:', 'schedule:')]
        for index,text in enumerate(mutants):
            file=self.root/f'mutant-{index}.yml';file.write_text(text)
            with self.subTest(index=index),self.assertRaises(ValueError):audit_workflow.audit(file)

    def test_audit_portable_without_original_handover_and_tamper_refusal(self):
        import audit_workflow
        with tempfile.TemporaryDirectory() as isolated:
            target=Path(isolated)/'local-auto-workflow-wiring'
            shutil.copytree(HERE,target,ignore=shutil.ignore_patterns('tmp*','__pycache__'))
            self.assertFalse((target.parent/'muse-handover').exists())
            with patch.object(audit_workflow,'ROOT',target):
                audit_workflow.audit(target/'boopadb-daily.OFF.yml')
                original=target/'evidence/v7-originals/boopadb-promote.yml'
                original.write_text(original.read_text()+'\n# changed\n')
                with self.assertRaisesRegex(ValueError,'Bundled reviewed original'):
                    audit_workflow.audit(target/'boopadb-daily.OFF.yml')

    def test_actual_cli_options_exist(self):
        for script,sub,flags in [(d.RESOLVER,'resolve',['--workdir','--baseline-pin','--baseline-pin-sha256','--producer-pin']),
              (d.RESOLVER,'finalize-context',['--selection','--inventory','--output']),
              (d.RELEASE/'run_candidate.py',None,['--dest','--context','--baseline-pin','--baseline-sha256','--relation-inputs','--tracker-root','--generation-config']),
              (d.RELEASE/'validation_job.py',None,['--artifact','--dest','--context','--baseline-pin','--baseline-sha256','--relation-inputs','--tracker-root']),
              (d.RELEASE/'generator/inventory_snapshot.py',None,['--tracker-root','--output'])]:
            command=[sys.executable,str(script)]+([sub] if sub else [])+['--help']
            result=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            for flag in flags:self.assertIn(flag,result.stdout)

if __name__=='__main__':unittest.main()
