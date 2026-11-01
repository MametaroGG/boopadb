#!/usr/bin/env python3
"""Offline YAML/shell/pinned-action interface audit; PyYAML is test-only."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import tempfile
import yaml

ROOT=Path(__file__).resolve().parent

def check(ok,message):
    if not ok:raise ValueError(message)

def audit(path):
    text=Path(path).read_text()
    # BaseLoader retains the GitHub Actions key `on` (YAML 1.2) as a string,
    # instead of Python's default YAML 1.1 coercion to boolean True.
    workflow=yaml.load(text,Loader=yaml.BaseLoader)
    check(set(workflow['on'])=={'workflow_dispatch'},'Schedule/event activation refused')
    check(workflow['permissions']=={'contents':'read','actions':'read'},'Unexpected token permissions')
    check(workflow['concurrency']['cancel-in-progress']=='false','Serialization changed')
    check(set(workflow['jobs'])=={'build','validate'},'Unexpected publication/additional job')
    check(workflow['jobs']['validate']['needs']=='build','Independent validation ordering lost')
    check('DRAFT-ADAPTATION' not in text,'Unimplemented adaptation placeholder')
    pins=json.loads((ROOT/'ACTION-PINS.json').read_text())['actions']
    count=0
    for name,job in workflow['jobs'].items():
        check(job['if']=='${{ false }}','Workflow must remain explicitly OFF')
        for step in job['steps']:
            if 'run' in step:
                check('${{' not in step['run'],'Expression interpolation into shell refused')
                subprocess.run(['bash','-n'],input=step['run'],text=True,check=True)
            if 'uses' not in step:continue
            action,commit=step['uses'].split('@')
            check(action in pins and commit==pins[action]['commit'],'Action does not match verified official immutable ref')
            check(re.fullmatch('[0-9a-f]{40}',commit),'Mutable action tag')
            evidence=ROOT/pins[action]['evidence']
            check(hashlib.sha256(evidence.read_bytes()).hexdigest()==pins[action]['evidence_sha256'],'Action ref evidence changed')
            declared=yaml.load((ROOT/'evidence'/(action.split('/')[-1]+'-action.yml')).read_text(),Loader=yaml.BaseLoader)
            check(set(step.get('with',{}))<=set(declared['inputs']),'Unsupported actual pinned action input')
            if action=='actions/checkout':check(step['with']['persist-credentials']=='false','Persisted git credentials refused')
            if action=='actions/upload-artifact':
                check(step['with']['overwrite']=='false','Immutable artifact overwrite refused')
                check(step['with']['retention-days']=='90','v7 retention weakened')
            if action=='actions/download-artifact':
                check('artifact-ids' in step['with'] and 'name' not in step['with'],'Download must use exact same-run artifact ID')
            count+=1
    build=workflow['jobs']['build']['steps']
    idx={step.get('id'):i for i,step in enumerate(build) if 'id' in step}
    tracker=next(i for i,step in enumerate(build) if step.get('with',{}).get('repository'))
    generate=next(i for i,step in enumerate(build) if 'run_stage.sh build' in step.get('run',''))
    check(idx['resolve']<tracker<generate<idx['build_artifact'],'Resolver/checkout/generation/artifact order changed')
    provenance=json.loads((ROOT/'V7-SOURCE.json').read_text())
    check(provenance.get('schema')==1 and len(provenance['sources'])==3,'Incomplete original v7 provenance')
    for entry in provenance['sources']:
        # Bundled byte-exact originals are the portable runtime reference. The
        # original location is provenance, never a required consumer-local path.
        bundled=ROOT/entry['bundled_path']
        check(hashlib.sha256(bundled.read_bytes()).hexdigest()==entry['sha256'],
              'Bundled reviewed original v7 source modified')
        original=ROOT.parent/entry['original_path']
        if original.is_file():
            check(hashlib.sha256(original.read_bytes()).hexdigest()==entry['sha256'],
                  'Available reviewed original v7 source modified')
    subprocess.run(['bash','-n',str(ROOT/'run_stage.sh')],check=True)
    return {'status':'passed','yaml':'parsed','shell_blocks':'bash -n passed',
            'immutable_action_references':count,'actual_pinned_action_input_compatibility':'passed',
            'original_v7_daily_qa_promote_bytes':'verified against pinned bundled originals','schedule':'OFF',
            'jobs':'literal false','installed':False,'published':False}

if __name__=='__main__':
    print(json.dumps(audit(ROOT/'boopadb-daily.OFF.yml'),indent=2))
