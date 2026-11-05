"""New Stage12 historical-only QA contract; original frozen source/visibility checks retained."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from datetime import datetime, timezone
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'generator'))
from verified_source import VerifiedSource, strict_json, open_directory, exact_read
from visibility_contract import verify_visibility_output
from visibility_policy import VisibilityPolicy
import source_identity
import charts_contract as checked_charts
import snapshot_contract as checked_snapshot
for module in (checked_charts, checked_snapshot):
    if Path(module.__file__).resolve().parent != HERE / "generator":
        raise ValueError("Wrong checked-source dependency origin")
# Retained static/runtime validators are dependencies, not replaced or weakened.
sys.path.insert(0,str(HERE.parents[1]/'qa-contract'))
import historical_contract as rc
from reconcile_sets import reconcile


def digest(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def public_ids(site):
    rows=[]
    for n in range(24):rows.extend(strict_json((site/f'search_index_{n}.json').read_bytes()))
    values=[row[0] for row in rows]
    rc.require(len(values)==len(set(values)), 'Duplicate output IDs')
    return values


def run(request_path, expected_sha256, output):
    request_path=Path(request_path);fd=open_directory(request_path.parent)
    try:raw=exact_read(fd,request_path.name,128*1024**2)
    finally:__import__('os').close(fd)
    rc.require(hashlib.sha256(raw).hexdigest()==expected_sha256,'Private validation request changed')
    request=rc.strict(raw);rc.verify_request_identity(request);site=Path(request['site']);src=Path(request['source_dir']);context=request['context']
    with VerifiedSource(src/'prepared',request['source_result']['completion_sha256']) as source:
        inv=(src/'evidence/input-inventory.json').read_bytes();att=(src/'evidence/attestation.json').read_bytes()
        source_proof=source_identity.verify(source,request['source_request'],inv,att,{name:'100644' for name in strict_json(inv)})
        rc.require(source.manifest['fixture'] is context['synthetic'] and source.manifest['tracker_commit']==context['tracker_commit'] and source.manifest['expected_date']==context['expected_date'] and hashlib.sha256(inv).hexdigest()==context['inventory_digest'],'Context/source mismatch')
        snapshot_raw=(site/'snapshot-manifest.json').read_bytes();snapshot_sha=hashlib.sha256(snapshot_raw).hexdigest();snap=strict_json(snapshot_raw)
        rc.require(snap.get('fixture') is context['synthetic'] and snap['input_manifest_sha256']==source.completion_sha256,'Snapshot source mismatch')
        actual={name:hashlib.sha256(value).hexdigest() for name,value in rc.base._tree(site).items()}
        rc.require(actual=={**snap['files'],'snapshot-manifest.json':snapshot_sha},'Site hash closure mismatch')
        ledger_path=Path(request['visibility_ledger']);ledger_raw=ledger_path.read_bytes();ledger_sha=hashlib.sha256(ledger_raw).hexdigest();ledger=strict_json(ledger_raw)
        verify_visibility_output(site,ledger_path,snap['visibility'],source.root,dict(source.hashes),verified_source=source)
        previous=request['previous']
        rc.require(previous['previous_release_digest']==context['prev_release_digest'],'Previous lineage mismatch')
        result=reconcile(previous['visible_ids'],public_ids(site),ledger['backend_ids'],ledger['visible_ids'],ledger['confirmed_hidden_ids'],previous_backend=previous['backend_ids'])
        rc.require(context['expected_date']>=previous['expected_date'],'Source observation date regressed')
        # Derive raw + individual metadata receipts for every new canonical ID.
        receipts=[]
        for ident in result['new_backend_ids']:
            raw_name='data/'+ident[:3]+'/'+ident+'.json';meta_name='tracker_meta/'+ident[:3]+'/'+ident+'.json'
            rc.require(source.read_json(source.root/raw_name)['id']==ident and source.read_json(source.root/meta_name)['id']==ident,'New ID lacks exact raw/metadata provenance')
            receipts.append({'id':ident,'raw_path':raw_name,'raw_sha256':source.hashes[raw_name],'meta_path':meta_name,'meta_sha256':source.hashes[meta_name]})
        rc.require(snap['validation']['rows']==len(ledger['visible_ids']) and snap['validation']['max_date']==context['expected_date'],'Output population/date mismatch')
        # Reuse original relation/evidence and UI contract. Applied projection is
        # explicitly unsupported here until its parser accepts checked raw reads.
        config=Path(request['generation_config']);import historical_configuration as run_candidate
        resolved=run_candidate.configuration(config,request['relation_inputs'],context,reuse_policy=request.get('reuse_policy'),baseline_pin=request['baseline_pin'],baseline_sha256=request['baseline_sha256'],expected_sha256=request['generation_config_sha256'])
        rc.require(resolved['projection_work'] is None,'Low-storage v1 cannot apply projection with unchecked raw readers')
        _,pin,_=rc.inputs(request['context_path'],request['baseline_pin'],request['baseline_sha256'],request['relation_inputs'])
        work=Path(request['gate_work']);work.mkdir()
        rc.write_json(work/'evidence-records.json',rc.evidence(pin,work));rc.write_json(work/'hash-ledger.json',actual)
        rc.contract_gates(site,work,source.root,pin)
        # Before any site-provided executable is run, preserve the existing pins.
        validation_job=rc
        rc.require(digest(site/'scripts/embed-hero.cjs')==validation_job.PINNED_HERO_SHA256,'Untrusted hero executable')
        import re
        match=re.search(r'// HERO_SELECTOR_START[^\n]*\n([\s\S]*?)// HERO_SELECTOR_END',(site/'index.html').read_text())
        rc.require(match and hashlib.sha256(match[1].encode()).hexdigest()==validation_job.PINNED_SELECTOR_SHA256,'Untrusted hero selector')
        rc.run_validator('validate_snapshot.py','--root',site,'--expected-date',context['expected_date'],'--manifest',site/'snapshot-manifest.json')
        source.verify_all()
        rc.require({name:hashlib.sha256(value).hexdigest() for name,value in rc.base._tree(site).items()}==actual and ledger_path.read_bytes()==ledger_raw,'Candidate or ledger changed across independent verification')
        report={'schema':'boopa-stage12-historical-machine-qa-v1','workflow_execution_sha':request['workflow_execution_sha'],'generator_code_sha256':request['generator_code_sha256'],'status':'passed','source':source_proof,'validation_only':True,'previous_validation_only':previous['validation_only'],'previous_evidence_mode':previous['previous_evidence_mode'],'previous_facts_sha256':hashlib.sha256(json.dumps(previous,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest(),'previous_release_digest':previous['previous_release_digest'],'transition':result,'new_id_receipts':receipts,'candidate_snapshot_sha256':snapshot_sha,'visibility_ledger_sha256':ledger_sha,'context':context,'publication_authorized':False,'production_eligible':False,'deployable':False,'legacy_v7_artifact_compatible':False}
    Path(output).write_text(json.dumps(report,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n')
    return report

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--request',required=True);p.add_argument('--sha256',required=True);p.add_argument('--output',required=True);a=p.parse_args();print(json.dumps(run(a.request,a.sha256,a.output),sort_keys=True,separators=(',',':'),allow_nan=False))
