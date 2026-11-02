#!/usr/bin/env python3
"""Supplemental exact-byte reuse gate. A reviewed checkout is the trust boundary.

This module checks commitments, not authorship. The owner grant must be verified
by the authorized human reviewer BEFORE the policy/trust digest is committed.
No policy or grant is supplied with this implementation. Missing means reject.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
KEYS=('relations_bundle_manifest_sha256','relations_approval_sha256',
      'relation_search_bundle_manifest_sha256','relation_search_approval_sha256',
      'supplement_bundle_manifest_sha256','supplement_approval_sha256')
RUNTIME_FILES={'local-release-contract-integration/'+n for n in ('reuse_authorization.py','release_contract.py','run_candidate.py','validation_job.py','artifact_handoff_base.py')} | {'local-auto-workflow-wiring/workflow_driver.py','local-auto-workflow-wiring/run_stage.sh'}
RUNTIME_FILES |= {'local-release-contract-integration/validators/'+p.name for p in (HERE/'validators').glob('*.py')}
RUNTIME_FILES |= {'local-auto-input-contract/resolve_automatic_inputs.py','local-auto-input-contract/select-input.cjs','local-auto-input-contract/proposed/src/collection-receipt.js'}
POLICY_KEYS={'schema','trust_path','trust_sha256','grant_path','baseline_path',
             'baseline_sha256','relation_inputs_path','implementation_inventory_path'}
TRUST_KEYS={'schema','scope','synthetic','repository','baseline_sha256','relations_binding',
            'implementation_inventory_sha256','runtime_files_sha256','grant_sha256','grant_reference'}

def need(ok, why):
    if not ok: raise ValueError(why)

def raw(p):
    p=Path(p); need(p.is_file() and not p.is_symlink(),'regular non-symlink file required')
    return p.read_bytes()

def sha(p): return hashlib.sha256(raw(p)).hexdigest()

def load(p):
    def pairs(items):
        d={}
        for k,v in items:
            need(k not in d,'duplicate JSON key'); d[k]=v
        return d
    return json.loads(raw(p),object_pairs_hook=pairs)

def digest_ok(x): return isinstance(x,str) and re.fullmatch('[0-9a-f]{64}',x) is not None

def resolve(parent,value,root):
    need(isinstance(value,str) and value and not Path(value).is_absolute(),'relative configured path required')
    p=parent/value
    need(p.resolve().is_relative_to(root.resolve()),'configured input escapes reviewed checkout')
    # Check every component, not just the final file.
    cursor=p
    while cursor != root.parent and cursor != cursor.parent:
        need(not cursor.is_symlink(),'symlink in configured input'); cursor=cursor.parent
    need(p.is_file(),'configured input absent')
    return p.resolve()

def policy(path):
    original=Path(path)
    cursor=original.absolute()
    while cursor != cursor.parent:
        need(not cursor.is_symlink(),'policy path cannot contain symlink')
        cursor=cursor.parent
    path=original.resolve(); need(path.is_relative_to(ROOT),'policy outside reviewed checkout')
    p=load(path)
    need(isinstance(p,dict) and set(p)==POLICY_KEYS and p['schema']=='boopa-reuse-policy-v1','exact reuse policy required')
    for k in ('trust_sha256','baseline_sha256'): need(digest_ok(p[k]),'malformed policy digest')
    paths={k:resolve(path.parent,p[k],ROOT) for k in POLICY_KEYS if k.endswith('_path')}
    need(sha(paths['trust_path'])==p['trust_sha256'],'untrusted authorization bytes')
    need(sha(paths['baseline_path'])==p['baseline_sha256'],'historical baseline bytes changed')
    return p,paths

def verify(path,context,baseline_path,baseline_sha256,relation_inputs):
    p,paths=policy(path); t=load(paths['trust_path'])
    need(isinstance(t,dict) and set(t)==TRUST_KEYS and t['schema']=='boopa-production-reuse-v1','exact trusted reuse record required')
    need(t['scope']=='production-exact-historical-relations-reuse','wrong reuse scope')
    need(t['repository']=='MametaroGG/boopadb','wrong reuse repository')
    need(type(t['synthetic']) is bool and t['synthetic']==context['synthetic'],'reuse fixture/context mismatch')
    for k in ('baseline_sha256','implementation_inventory_sha256','grant_sha256'): need(digest_ok(t[k]),'malformed trusted digest')
    need(isinstance(t['grant_reference'],str) and bool(t['grant_reference'].strip()),'verified owner grant reference required')
    need(bool(raw(paths['grant_path']).strip()) and sha(paths['grant_path'])==t['grant_sha256'],'owner grant evidence changed')
    need(p['baseline_sha256']==baseline_sha256==t['baseline_sha256']==sha(baseline_path),'historical baseline binding mismatch')
    need(Path(baseline_path).resolve()==paths['baseline_path'],'different baseline path')
    need(Path(relation_inputs).resolve()==paths['relation_inputs_path'],'different relation inputs path')
    baseline=load(baseline_path); rel=load(relation_inputs)
    need(isinstance(rel,dict) and set(rel)==set(KEYS),'all six original relation inputs required')
    bindings={k:sha(resolve(Path(relation_inputs).parent,rel[k],ROOT)) for k in KEYS}
    need(bindings==t['relations_binding']=={k:baseline['relations_binding'][k] for k in KEYS},'historical relation bytes changed')
    need(sha(paths['implementation_inventory_path'])==t['implementation_inventory_sha256'],'implementation commitment mismatch')
    # Committed inventory must be the executing generator inventory, not a decoy.
    need(paths['implementation_inventory_path']==(HERE/'GENERATOR-INVENTORY.json').resolve(),'wrong executing implementation inventory')
    need(isinstance(t['runtime_files_sha256'],dict) and set(t['runtime_files_sha256'])==RUNTIME_FILES,'exact runtime implementation pins required')
    need(all(digest_ok(v) and sha(ROOT/k)==v for k,v in t['runtime_files_sha256'].items()),'runtime implementation changed')
    inventory=load(paths['implementation_inventory_path'])
    actual={f.relative_to(HERE).as_posix():sha(f) for f in (HERE/'generator').rglob('*') if f.is_file() and '__pycache__' not in f.parts}
    need(actual==inventory,'actual generator implementation changed')
    return {'authorization_sha256':p['trust_sha256'],'policy_sha256':sha(path),
            'grant_sha256':t['grant_sha256'],'implementation_inventory_sha256':t['implementation_inventory_sha256']}

def envelope(path,context,baseline_path,baseline_sha256,relation_inputs,archive):
    binding=verify(path,context,baseline_path,baseline_sha256,relation_inputs)
    return {'schema':'boopa-reuse-envelope-v1','context':context,'archive_sha256':sha(archive),**binding}

def check_envelope(path,context,baseline_path,baseline_sha256,relation_inputs,archive,evidence):
    expected=envelope(path,context,baseline_path,baseline_sha256,relation_inputs,archive)
    need(load(evidence)==expected,'reuse handoff binding mismatch')
    return expected

def source_checks(source_run,source_checkout,context,trust):
    run=load(source_run)
    need(run.get('repository',{}).get('full_name')=='MametaroGG/boopadb','wrong source repository')
    need(run.get('status')=='completed' and run.get('conclusion')=='success','source run not successful terminal')
    need(str(run.get('id'))==context.get('run_id') and str(run.get('run_attempt'))==context.get('run_attempt') and run.get('head_sha')==context.get('generator_commit'),'source run/context mismatch')
    source=Path(source_checkout).resolve()
    head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    need(head==run['head_sha'],'source checkout differs from authenticated source run')
    # Verify source committed inventory against trusted reviewed implementation,
    # and bytes in checkout against its inventory; no artifact-provided code runs.
    inv=source/'local-release-contract-integration/GENERATOR-INVENTORY.json'
    need(sha(inv)==trust['implementation_inventory_sha256'],'source run implementation not authorized')
    need(set(trust['runtime_files_sha256'])==RUNTIME_FILES and all(sha(source/k)==v for k,v in trust['runtime_files_sha256'].items()),'source runtime implementation not authorized')
    sr=inv.parent
    actual={f.relative_to(sr).as_posix():sha(f) for f in (sr/'generator').rglob('*') if f.is_file() and '__pycache__' not in f.parts}
    need(actual==load(inv),'source generator inventory mismatch')


def handoff(artifact,policy_path,source_run,source_checkout,review_record=None):
    artifact=Path(artifact); ev=artifact/'evidence'; obj=load(ev/'reuse-envelope.json')
    context=obj.get('context',{})
    need(context.get('synthetic') is False,'synthetic reuse cannot enter QA/promotion')
    p,paths=policy(policy_path); trust=load(paths['trust_path'])
    source_checks(source_run,source_checkout,context,trust)
    # Trusted current checkout independently runs all commitment checks.
    check_envelope(policy_path,context,paths['baseline_path'],p['baseline_sha256'],paths['relation_inputs_path'],artifact/'site-release.tar',ev/'reuse-envelope.json')
    manifest=load(ev/'run-manifest.json')
    for k in ('run_id','run_attempt','tracker_commit','generator_commit','expected_date','generation','inventory_digest','prev_release_digest'):
        need(manifest.get(k)==context.get(k),'run manifest/context mismatch: '+k)
    return review_binding(ev/'reuse-envelope.json',review_record)

def review_binding(evidence,review_record=None):
    obj=load(evidence)
    result={'reuse_envelope_sha256':sha(evidence),'authorization_sha256':obj['authorization_sha256']}
    if review_record is not None:
        need(load(review_record).get('relation_reuse_binding_sha256')==result['reuse_envelope_sha256'],'independent QA reuse binding mismatch')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__); s=p.add_subparsers(dest='command',required=True)
    q=s.add_parser('verify-handoff')
    for k in ('artifact','policy','source-run','source-checkout'): q.add_argument('--'+k,required=True)
    q.add_argument('--review-record'); q.add_argument('--output')
    a=p.parse_args(); result=handoff(a.artifact,a.policy,a.source_run,a.source_checkout,a.review_record)
    data=json.dumps(result,sort_keys=True)+'\n'
    if a.output:
        with open(a.output,'x') as f: f.write(data)
    print(data,end='')
if __name__=='__main__': main()
