#!/usr/bin/env python3
"""One-shot exact historical replay/non-serving trial. No dispatch, upload, publish or write API.

Stage12 is an explicitly NEW minimal reconstruction, not the original Stage11
sealed package or its recovered missing modules. Frozen generator and historical
source identities are retained. This single-job protocol is not a release.
Private source and per-product QA are destroyed before a small result is exposed.
"""
import argparse
import datetime as dt
import math
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time

HERE = Path(__file__).resolve().parent
DESTINATION = 'MametaroGG/boopadb'
BRANCH = 'chore/auto-update-trial-20261101'
WORKFLOW = '.github/workflows/stage12-historical-trial.yml'
ORIGINAL_ADAPTER_INVENTORY = '55e64a4fc0edcbef5e44e955f1c61622a6ba3afe97d74cb02958faf11504db39'
HISTORICAL_RUN_ID = '41920338326'
HISTORICAL_RUN_ATTEMPT = '1'
HISTORICAL_SAVED_COMMIT = '672373654eb125fea74a25ff4f0319440e0d5f14'
HISTORICAL_AS_OF = '2026-11-05'
PROFILE = '265359b2f5a2a0d15a5eed8069cdcb90da775549c467407e8d8f5723e94c56ff'
GENERATOR = '6481fb71f8be2abac0c6b8a616116c723f1f347ebf6f7e1331b820743168868b'
BASELINE = '26b1af17947886d0803fc9be62f0e72cbfc2932f7eae15c075709561dfc5a202'
PRODUCER = 'c084cb265640c00c2cfac1700e51c6d1e7e1cfbaf0032f10a9a5be66e2f8f315'
PRESENTATION = 'e7b74233a4814b738f2d5de12b22004dfc5466c32bdafe53c6f9047c380acd19'
PRESENTATION_CANONICAL = '1d98251b5d5b3ffd9e038e13b2f440f18c111db703dcc698c4a8f29031df4517'
PREVIOUS = '39075ec499ca0a91c4f9f2ab2573c02e10cb5f32f2fee2733ad99f7adff2611c'
GIB = 1024 ** 3
MAX_SMALL = 128 * 1024 ** 2
SOURCE_LIMITS = dict(compressed_bytes=GIB, uncompressed_bytes=20*GIB,
    file_bytes=64*1024**2, entries=700000, path_bytes=96*1024**2,
    source_bytes=12*GIB, min_free_bytes=GIB, min_free_inodes=10000,
    planned_write_bytes=16*GIB, planned_write_inodes=750000)

class Refused(ValueError): pass

class PhaseFailure(Refused):
    def __init__(self, phase):
        super().__init__('Trial stage refused')
        self.phase=phase


def need(value, message):
    if not value: raise Refused(message)

def encode(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()

def strict(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            need(key not in out, 'Duplicate JSON field'); out[key] = value
        return out
    def finite_float(value):
        number = float(value)
        need(math.isfinite(number), 'Nonfinite JSON number')
        return number
    return json.loads(raw, object_pairs_hook=pairs, parse_float=finite_float,
        parse_constant=lambda _: (_ for _ in ()).throw(Refused('Nonfinite JSON')))

def sha(raw): return hashlib.sha256(raw).hexdigest()

def stat_identity(st):
    return (st.st_dev,st.st_ino,st.st_mode,st.st_nlink,st.st_size,st.st_mtime_ns,st.st_ctime_ns)

def regular(path, limit=MAX_SMALL):
    path = Path(os.path.abspath(path)); fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = new
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf, 'rb') as source:
            st = os.fstat(source.fileno())
            need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1 and st.st_size <= limit,
                 'Regular unshared bounded file required')
            raw = source.read(limit + 1)
            need(len(raw) <= limit and stat_identity(os.fstat(source.fileno())) == stat_identity(st), 'Input changed during read')
            return raw
    finally: os.close(fd)

def file_sha(path, limit=None):
    # Every ancestor and the streamed leaf are opened without following links.
    path = Path(os.path.abspath(path)); fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = new
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf, 'rb') as source:
            st = os.fstat(source.fileno())
            need(stat.S_ISREG(st.st_mode) and st.st_nlink == 1, 'Unshared file required')
            digest = hashlib.sha256(); count = 0
            while raw := source.read(1024*1024):
                count += len(raw); need(limit is None or count <= limit, 'File exceeds bound'); digest.update(raw)
            need(stat_identity(os.fstat(source.fileno())) == stat_identity(st), 'File changed during hash')
        return digest.hexdigest()
    finally: os.close(fd)

def write(path, value):
    path = Path(path); raw = encode(value) + b'\n'
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'wb') as out: out.write(raw)
    return sha(raw)

def tree(root):
    root = Path(root)
    for parent in (root, *root.parents): need(not parent.is_symlink(), 'Linked tree refused')
    files, dirs = {}, set()
    for path in root.rglob('*'):
        need(not path.is_symlink(), 'Linked tree member refused')
        name = path.relative_to(root).as_posix()
        if path.is_dir(): dirs.add(name)
        else:
            need(path.is_file(), 'Nonregular tree member refused')
            files[name] = file_sha(path)
    expected_dirs = {str(p) for name in files for p in Path(name).parents if str(p) != '.'}
    need(dirs == expected_dirs, 'Unexpected tree directory')
    return files

def verify_adapter(expected):
    raw = regular(HERE/'ADAPTER-INVENTORY.json')
    need(re.fullmatch('[a-f0-9]{64}', expected or '') and sha(raw) == expected, 'Adapter inventory commitment changed')
    inventory = strict(raw); actual = tree(HERE); actual.pop('ADAPTER-INVENTORY.json')
    need(set(inventory) == {'schema', 'files', 'source_stage11_adapter_sha256', 'reconstruction_mode'} and inventory['schema'] == 'boopa-stage12-historical-trial-adapter-v1' and inventory['source_stage11_adapter_sha256'] == ORIGINAL_ADAPTER_INVENTORY and inventory['reconstruction_mode'] == 'new-minimal-historical-only-implementation'
         and inventory['files'] == actual, 'Exact adapter closure changed')
    return inventory

def verify_export(export):
    export = Path(export); raw = regular(export/'HISTORICAL-TRIAL-INVENTORY.json')
    need(re.fullmatch('[a-f0-9]{64}', PROFILE) and sha(raw) == PROFILE, 'Reviewed Stage12 export inventory changed or not sealed')
    inventory = strict(raw); actual = tree(export); actual.pop('HISTORICAL-TRIAL-INVENTORY.json')
    keys = {'schema','files','source_stage11_export_sha256','reconstruction_mode','generator_code_sha256',
            'historical_replay','current_source_eligible','production_eligible','publication_authorized','external_writes_enabled'}
    need(set(inventory) == keys and inventory['schema'] == 'boopa-stage12-historical-trial-export-v1' and
         inventory['reconstruction_mode'] == 'new-minimal-historical-only-implementation' and
         inventory['source_stage11_export_sha256'] == 'a293abc248f545e89a1fa44a3ac3136a9b5b127b9336b91621e212f9bed06af4' and
         inventory['files'] == actual and inventory['generator_code_sha256'] == GENERATOR and
         inventory['historical_replay'] is True, 'Exact new export closure required')
    need(all(inventory[k] is False for k in ('current_source_eligible','production_eligible','publication_authorized','external_writes_enabled')),
         'Export cannot authorize current eligibility, execution or publication')
    generator = tree(export/'original/low-storage/generator')
    need(len(generator) == 165 and sha(encode(generator)) == GENERATOR, 'Frozen 165-file generator changed')
    return inventory

def load_modules(export):
    low = Path(export)/'original/low-storage'; contract = Path(export)/'qa-contract'
    sys.path[:0] = [str(low), str(contract)]
    import historical_configuration
    import stream_source, stream_source_transport, low_claim, resource_preflight
    spec = importlib.util.spec_from_file_location('_stage12_resolver', low/'source-resolver/resolve_automatic_inputs.py')
    resolver = importlib.util.module_from_spec(spec); spec.loader.exec_module(resolver)
    for mod, expected in ((historical_configuration, contract), (stream_source, low), (stream_source_transport, low), (low_claim, low)):
        need(Path(mod.__file__).resolve().parent == expected.resolve(), 'Wrong dependency origin')
    return historical_configuration, resolver, stream_source, stream_source_transport, low_claim, resource_preflight

def same_historical_source(left, right):
    # The historical authenticator validates the complete fixed proof schema.
    # Only actual evaluation time may advance; no observation or identity changes.
    from historical_source import public_labels
    public_labels(left); public_labels(right)
    return encode({k:v for k,v in left.items() if k != 'evaluated_at'}) == encode({k:v for k,v in right.items() if k != 'evaluated_at'})


def clean_env(home):
    return {'PATH': os.environ.get('PATH','/usr/local/bin:/usr/bin:/bin'), 'HOME': str(home),
            'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'}

def run_private(command, work, *, timeout=3600, result_path=None):
    """Run reviewed code with no credentials; never forward stdout or stderr."""
    work = Path(work); work.mkdir(mode=0o700)
    with (work/'stdout').open('xb') as out, (work/'stderr').open('xb') as err:
        child = subprocess.Popen(command, stdout=out, stderr=err, env=clean_env(work), start_new_session=True)
        try: code = child.wait(timeout=timeout)
        except BaseException:
            os.killpg(child.pid, signal.SIGKILL); child.wait(); raise
    need(code == 0, 'Private stage refused')
    need((work/'stdout').stat().st_size <= MAX_SMALL and (work/'stderr').stat().st_size <= MAX_SMALL, 'Private log bound exceeded')
    if result_path is None: return None
    value = strict(regular(work/'stdout'))
    need(regular(result_path) == encode(value)+b'\n', 'Captured stage output differs from result file')
    return value

def context(proof, result, run_id, execution_sha):
    s = proof['selection']
    return dict(synthetic=False, tracker_commit=s['tracker_commit'], generator_commit=execution_sha,
        run_id=run_id, run_attempt='1', generation=s['generation'], prev_release_digest=s['prev_release_digest'],
        expected_date=s['expected_date'], inventory_digest=result['inventory_sha256'])

def summarize(report, source_result, elapsed, runtime):
    """Explicit numeric/hash/status projection, never generic recursive redaction."""
    need(report['status'] == 'passed' and report['validation_only'] is True and
         all(report[k] is False for k in ('publication_authorized','production_eligible','deployable','legacy_v7_artifact_compatible')),
         'Non-serving independent QA required')
    need(report.get('context',{}).get('synthetic') is False, 'Real source context required')
    resource_keys={'free_bytes_before','free_inodes_before','effective_available_memory_bytes','required_memory_bytes','required_storage_bytes','cpu_count'}
    need(type(runtime) is dict and set(runtime) <= resource_keys and all(type(v) is int and v >= 0 for v in runtime.values()),
         'Only numeric runtime measurements may leave private work')
    transition = report['transition']
    counts = {'backend_products': source_result['backend_product_count'],
        'visible_products': transition['candidate_visible_count'],
        'previous_visible_products': transition['previous_visible_count'],
        'new_backend_products': len(transition['new_backend_ids']),
        'new_visible_products': len(transition['new_visible_ids']),
        'removed_visible_products': len(transition['hidden_ids'])}
    need(all(type(v) is int and v >= 0 for v in counts.values()), 'Invalid aggregate counts')
    need(re.fullmatch('[a-f0-9]{64}', report['candidate_snapshot_sha256']), 'Invalid snapshot digest')
    return {'schema':'boopa-stage12-historical-single-job-trial-result-v1', 'status':'passed',
        'implementation':'new-stage12-historical-only', 'historical_replay':True, 'current_source_eligible':False, 'automatic_intake_eligible':False,
        'current_selector_used':False, 'scope':'exact-historical-replay-only',
        'synthetic_context':False, 'publication_authorized':False, 'production_eligible':False,
        'deployable':False, 'cross_job_artifact_contract_verified':False,
        'browser_visual_qa':False, 'independent_source_reconstruction':True,
        'independent_previous_reconstruction':True, 'private_proofs_uploaded':False,
        'retention_days':7, 'counts':counts, 'candidate_snapshot_sha256':report['candidate_snapshot_sha256'],
        'generator_code_sha256':GENERATOR, 'profile_sha256':PROFILE,
        'elapsed_seconds':round(elapsed,3), 'runner_resources':runtime}

def orchestrate(backend):
    """Actual stage ordering; injected backends are used only by offline unit tests."""
    def step(name, operation, *args):
        try: return operation(*args)
        except PhaseFailure: raise
        except Exception: raise PhaseFailure(name) from None
    step('preflight',backend.guard); step('capacity',backend.admit)
    initial=step('source-selection',backend.resolve,'initial')
    step('input-binding',backend.bind_intake,initial); step('source-download',backend.acquire,initial)
    build_source=step('source-preparation',backend.derive,'build',initial)
    build_previous=step('previous-build',backend.previous,'build',initial)
    candidate=step('generator',backend.generate,initial,build_source)
    step('candidate-copy',backend.handoff,candidate); step('discard-build-source',backend.discard_build_source)
    current=step('source-before-qa',backend.resolve,'before-qa'); step('source-identity',backend.same_source,initial,current)
    qa_source=step('source-independent-qa',backend.derive,'qa',current)
    step('source-reconstruction-match',backend.same_completion,build_source,qa_source)
    qa_previous=step('previous-independent-qa',backend.previous,'qa',current)
    step('previous-reconstruction-match',backend.same_previous,build_previous,qa_previous)
    report=step('independent-qa',backend.validate,current,qa_source,qa_previous)
    final=step('source-final',backend.resolve,'final'); step('source-final-identity',backend.same_source,initial,final)
    step('final-input-check',backend.guard); step('candidate-final-check',backend.verify_candidate_unchanged)
    return step('result-redaction',backend.result,report,qa_source)

class HistoricalBackend:
    def __init__(self, export, adapter_sha, root, env, token, source_hint):
        self.export = Path(export).absolute(); self.root = Path(root); self.env = env
        self.adapter_sha = adapter_sha; self.token = token; self.hint = source_hint
        need(source_hint == (HISTORICAL_RUN_ID,HISTORICAL_RUN_ATTEMPT), 'Exact historical run only')
        self.started = time.monotonic(); self.original = self.export/'original'; self.low = self.original/'low-storage'
        verify_adapter(adapter_sha); verify_export(export)
        self.configuration, self.resolver_module, self.stream, self.stream_transport, self.claim, self.resources = load_modules(export)
        sys.path.insert(0, str(HERE)); import transport
        need(Path(transport.__file__).resolve() == HERE/'transport.py', 'Wrong transport origin')
        self.transport = transport.GET()
        self.api_headers = {'Authorization':'Bearer '+token, 'Accept':'application/vnd.github+json',
            'X-GitHub-Api-Version':'2022-11-28', 'User-Agent':'boopadb-stage12-trial'}
        self.input_root = self.root/'inputs'; self.input_root.mkdir(mode=0o700)
        need(sha(regular(HERE/'inputs/producer-pin.installed.json')) == PRODUCER and
             sha(regular(HERE/'inputs/presentation-proof.exact.json')) == PRESENTATION, 'Bound trial input changed')
        config = strict(regular(self.original/'generation-config.reuse-only.json'))
        for key in ('relations_bundle','relations_approval','relation_search_bundle','relation_search_approval','supplement_bundle','supplement_approval'):
            config[key] = str(self.original/config[key])
        config['presentation_proof'] = str(HERE/'inputs/presentation-proof.exact.json')
        config['presentation_sha256'] = PRESENTATION_CANONICAL
        self.config = self.input_root/'generation-config.json'; self.config_sha = write(self.config, config)
        self.baseline = self.original/'approved-inputs/baseline_pin.json'
        self.relations = self.original/'approved-inputs/relation-inputs.json'
        self.policy = self.original/'approved-inputs/policy.json'
        self.producer = HERE/'inputs/producer-pin.installed.json'
        self.archive = self.root/'source.tar.gz'; self.contexts = {}; self.requests = {}; self.selections = {}

    def api(self, suffix):
        status, _, body = self.transport('https://api.github.com/repos/'+DESTINATION+suffix, self.api_headers)
        need(status == 200, 'Destination read unavailable'); return strict(body)

    def execution(self):
        e = self.env
        fixed = dict(GITHUB_ACTIONS='true', GITHUB_REPOSITORY=DESTINATION,
            GITHUB_REF='refs/heads/'+BRANCH, GITHUB_EVENT_NAME='push', GITHUB_RUN_ATTEMPT='1',
            GITHUB_RUN_NUMBER='1', GITHUB_WORKFLOW_REF=DESTINATION+'/'+WORKFLOW+'@refs/heads/'+BRANCH)
        need(all(e.get(k) == v for k,v in fixed.items()) and e.get('GITHUB_WORKFLOW_SHA') == e.get('GITHUB_SHA') and
            re.fullmatch('[a-f0-9]{40}', e.get('GITHUB_SHA','')) and re.fullmatch('[1-9][0-9]*', e.get('GITHUB_RUN_ID','')),
            'First one-shot trial Actions context required')
        run = self.api('/actions/runs/'+e['GITHUB_RUN_ID'])
        need(str(run.get('id')) == e['GITHUB_RUN_ID'] and run.get('repository',{}).get('full_name') == DESTINATION and
            run.get('head_repository',{}).get('full_name') == DESTINATION and run.get('head_sha') == e['GITHUB_SHA'] and
            run.get('path') == WORKFLOW and run.get('head_branch') == BRANCH and run.get('event') == 'push' and
            type(run.get('run_attempt')) is int and run['run_attempt'] == 1 and type(run.get('run_number')) is int and run['run_number'] == 1 and
            run.get('status') == 'in_progress' and run.get('conclusion') is None, 'Actual trial identity differs')
        history = self.api('/actions/workflows/'+WORKFLOW.rsplit('/',1)[-1]+'/runs?per_page=100&page=1')
        need(type(history.get('total_count')) is int and history['total_count'] == 1 and
            len(history.get('workflow_runs',[])) == 1 and history['workflow_runs'][0].get('id') == run['id'],
            'One-use workflow history already consumed')
        jobs = self.api('/actions/runs/'+e['GITHUB_RUN_ID']+'/attempts/1/jobs?per_page=100&page=1')
        need(type(jobs.get('total_count')) is int and jobs['total_count'] == 1 and len(jobs.get('jobs',[])) == 1, 'Single trial job required')
        job = jobs['jobs'][0]
        need(type(job.get('id')) is int and job['id']>0 and job.get('name') == 'trial' and type(job.get('run_id')) is int and job['run_id'] == run['id'] and type(job.get('run_attempt')) is int and job['run_attempt'] == 1 and
             job.get('head_sha') == e['GITHUB_SHA'] and job.get('status') == 'in_progress' and job.get('conclusion') is None,
             'Actual trial job differs')
        return run

    def guard(self):
        verify_adapter(self.adapter_sha); verify_export(self.export)
        need(sha(regular(self.config)) == self.config_sha, 'Materialized config changed')
        self.execution()
        self.configuration.configuration(self.config, self.relations, {'synthetic':False},
            reuse_policy=self.policy, baseline_pin=self.baseline, baseline_sha256=BASELINE, expected_sha256=self.config_sha)

    def admit(self):
        components = {
            'one_prepared_source':dict(additional_bytes=16*GIB, additional_inodes=750000, basis='Exactly one build or independent QA source; build removed before QA'),
            'source_archive':dict(additional_bytes=GIB, additional_inodes=1, basis='Bounded immutable archive, one private read-only inode'),
            'candidate_and_copy':dict(additional_bytes=2*GIB, additional_inodes=20000, basis='Separate regular-file candidate handoff, no hardlinks'),
            'proofs_indexes_logs':dict(additional_bytes=2*GIB, additional_inodes=2000, basis='Requests, source metadata, previous facts and captured private logs'),
            'previous_source':dict(additional_bytes=0, additional_inodes=0, basis='Independent stream replay without raw-tree materialization')}
        result = self.resources.preflight(self.root, components, .25, required_memory_bytes=10*GIB, require_cgroup=False)
        write(self.root/'resource-preflight.json', result)
        obs=result['observed']; self.metrics={'free_bytes_before':obs['free_bytes'], 'free_inodes_before':obs['free_inodes'],
            'effective_available_memory_bytes':result['effective_available_memory_bytes'],
            'required_memory_bytes':result['required_memory_bytes'], 'required_storage_bytes':result['required_additional']['bytes'],
            'cpu_count':os.cpu_count()}

    def historical_scope(self, proof):
        from historical_source import public_labels
        public_labels(proof)  # Exact schema, original identities/clocks and non-current flags.

    def resolve(self, label):
        from historical_source import HistoricalResolver
        resolver=HistoricalResolver(self.resolver_module,self.token,request=self.transport,now=dt.datetime.now(dt.timezone.utc))
        destination=self.root/('resolve-'+label)
        proof=resolver.resolve(destination,self.baseline,BASELINE,self.producer)
        self.historical_scope(proof)
        need(proof['selection']['prev_release_digest'] == PREVIOUS,
             'Serving predecessor changed; fixed legacy historical trial no longer applies')
        self.selections[id(proof)]=(destination,resolver)
        self.last_historical_proof=proof
        return proof

    def bind_intake(self, proof):
        self.historical_scope(proof); self.intake=proof
        # This is the original observation envelope, NOT a new freshness check.
        # Actual source receipt and evaluated_at bytes are not rewritten.
        from historical_source import original_claim
        self.original_claim=original_claim()
        write(self.root/'private-intake.json', {'schema':'boopa-stage12-historical-private-intake-v1','source':proof,
            'source_claim':self.original_claim,'generator_code_sha256':GENERATOR,'profile_sha256':PROFILE,
            'config_sha256':self.config_sha,'adapter_inventory_sha256':self.adapter_sha,
            'historical_replay':True,'current_source_eligible':False,'automatic_intake_eligible':False,
            'publication_authorized':False,'production_eligible':False})

    def request(self, proof):
        location,resolver=self.selections[id(proof)]; commit=proof['selection']['tracker_commit']
        prefix=self.resolver_module.PREFIX
        commit_obj=resolver.api(prefix+'/git/commits/'+commit); root_obj=resolver.api(prefix+'/git/trees/'+commit)
        receipt=regular(location/'tracker-proof/data/collection_receipt.json'); producer=regular(self.producer)
        binding={'repository':self.resolver_module.REPOSITORY,'saved_commit':commit,'root_tree':commit_obj['tree']['sha'],
            'commit_evidence_sha256':sha(encode(commit_obj)), 'root_evidence_sha256':sha(encode(root_obj)),
            'receipt_sha256':sha(receipt),'source_commit':proof['source_commit'],'run_id':proof['run_id'],
            'run_attempt':proof['run_attempt'],'producer_pin_sha256':sha(producer),'authority':'local-historical-validation-only'}
        return {'binding':binding,'archive_path':str(self.archive),'commit':commit_obj,'root':root_obj,
            'producer_raw_hex':producer.hex(),'derive_claim':self.original_claim,'limits':SOURCE_LIMITS}

    def acquire(self, proof):
        request=self.request(proof); binding=self.stream.Binding(**request['binding']); binding.validate()
        with self.stream_transport.open_source(binding, SOURCE_LIMITS['compressed_bytes']) as source, self.archive.open('xb') as out:
            while raw:=source.read(1024*1024): out.write(raw)
            need(source.complete, 'Incomplete archive transport')
        self.archive_sha=file_sha(self.archive,SOURCE_LIMITS['compressed_bytes']); self.archive.chmod(0o400)

    def derive(self, label, proof):
        need(file_sha(self.archive,SOURCE_LIMITS['compressed_bytes']) == self.archive_sha, 'Archive changed between independent passes')
        request=self.request(proof); request_path=self.root/(label+'-source-request.json'); digest=write(request_path,request)
        output=self.root/(label+'-source')
        result=run_private([sys.executable,'-B',str(self.low/'source_stage.py'),'--request',str(request_path),
            '--sha256',digest,'--output',str(output)], self.root/(label+'-source-process'), result_path=output/'source-result.json')
        need(result['saved_commit'] == proof['selection']['tracker_commit'] and result['source_date'] == proof['selection']['expected_date'] and
             result['archive_consumed_sha256'] == self.archive_sha, 'Independent source derivation mismatch')
        self.requests[label]=request; self.contexts[label]=context(proof,result,self.env['GITHUB_RUN_ID'],self.env['GITHUB_SHA'])
        write(self.root/(label+'-context.json'),self.contexts[label]); return result

    def previous(self, label, proof):
        request_path=self.root/(label+'-previous-request.json')
        digest=write(request_path,{'previous_release_digest':proof['selection']['prev_release_digest']})
        output=self.root/(label+'-previous.json')
        return run_private([sys.executable,'-B',str(HERE/'trial_adapter.py'),'previous-stage','--export',str(self.export),
            '--adapter-sha256',self.adapter_sha,'--request',str(request_path),'--request-sha256',digest,'--output',str(output)],
            self.root/(label+'-previous-process'), result_path=output)

    def generate(self, proof, source):
        config=self.configuration.configuration(self.config,self.relations,self.contexts['build'],
            reuse_policy=self.policy,baseline_pin=self.baseline,baseline_sha256=BASELINE,expected_sha256=self.config_sha)
        need(config['projection_work'] is None and config['daily_coverage_file'] is None and config['daily_target_date'] is None,
             'No new projection or daily completeness claim allowed')
        build=self.root/'build'; build.mkdir(mode=0o700); site=build/'site'
        prepared=self.root/'build-source/prepared'
        command=[sys.executable,'-B',str(self.low/'generator/build_site.py'),'--input-root',str(prepared),
            '--completion-manifest',str(prepared/'completion.json'),'--verified-completion-sha256',source['completion_sha256'],
            '--static-root',str(self.low/'generator/pinned-static'),'--output-dir',str(site)]
        for bundle,approval,_,_ in self.configuration.RELATIONS:
            for key in (bundle,approval): command+=['--'+key.replace('_','-'),str(config[key])]
        command+=['--presentation-proof',str(config['presentation_proof']),'--presentation-sha256',config['presentation_sha256']]
        run_private(command,self.root/'generation-process',timeout=5400)
        ledgers=list(build.glob('.site-candidate-*/visibility-private/visibility-ledger.json'))
        need(len(ledgers) == 1, 'Exact private ledger required')
        need(not (site/'release-manifest.json').exists(), 'Trial may not create a release manifest')
        return site,ledgers[0]

    def handoff(self,candidate):
        site,ledger=candidate; self.candidate_tree=tree(site); self.ledger_sha=file_sha(ledger,MAX_SMALL)
        need(len(self.candidate_tree) <= 8192 and sum(p.stat().st_size for p in site.rglob('*') if p.is_file()) <= GIB,
             'Candidate exceeds trial copy budget')
        snap=strict(regular(site/'snapshot-manifest.json'))
        need(snap.get('fixture') is False and self.candidate_tree == {**snap['files'],'snapshot-manifest.json':sha(regular(site/'snapshot-manifest.json'))},
             'Candidate snapshot hash closure changed')
        self.qa_site=self.root/'qa-site'; self.qa_site.mkdir(mode=0o700)
        for name,digest in self.candidate_tree.items():
            target=self.qa_site/name; target.parent.mkdir(parents=True,exist_ok=True)
            raw=regular(site/name,64*1024**2); need(sha(raw)==digest,'Candidate changed during copy')
            with target.open('xb') as out: out.write(raw)
            target.chmod(0o400)
        self.qa_ledger=self.root/'qa-visibility-ledger.json'
        with self.qa_ledger.open('xb') as out: out.write(regular(ledger))
        self.qa_ledger.chmod(0o400); self.verify_candidate_unchanged()

    def discard_build_source(self):
        shutil.rmtree(self.root/'build-source'); shutil.rmtree(self.root/'build')
        need(not (self.root/'build-source').exists(), 'Build source retained before QA reconstruction')

    def same_source(self,left,right):
        self.historical_scope(left); self.historical_scope(right)
        need(same_historical_source(left,right) and left['original_as_of']==right['original_as_of'],
             'Pinned historical source or live lineage changed across replay')

    def same_completion(self,left,right):
        for key in ('completion_sha256','inventory_sha256','attestation_sha256','saved_commit','root_tree','source_date','archive_consumed_sha256','backend_ids_sha256'):
            need(left[key]==right[key], 'Independent source reconstruction differs')
        need(self.contexts['build']==self.contexts['qa'], 'Independent context differs')

    def same_previous(self,left,right): need(encode(left)==encode(right), 'Independent published predecessor replay differs')

    def validate(self,proof,source,previous):
        self.verify_candidate_unchanged()
        request={'schema':'boopa-stage12-historical-qa-request-v1','workflow_execution_sha':self.env['GITHUB_SHA'],'generator_code_sha256':GENERATOR,
            'site':str(self.qa_site),'visibility_ledger':str(self.qa_ledger),'source_dir':str(self.root/'qa-source'),
            'source_request':self.requests['qa'],'source_result':source,'previous':previous,
            'context':self.contexts['qa'],'context_path':str(self.root/'qa-context.json'),
            'generation_config':str(self.config),'generation_config_sha256':self.config_sha,'relation_inputs':str(self.relations),'baseline_pin':str(self.baseline),
            'baseline_sha256':BASELINE,'reuse_policy':str(self.policy),'gate_work':str(self.root/'qa-gates')}
        path=self.root/'qa-request.json'; digest=write(path,request); output=self.root/'private-qa.json'
        report=run_private([sys.executable,'-B',str(self.low/'verify_candidate.py'),'--request',str(path),'--sha256',digest,
            '--output',str(output)],self.root/'qa-process',timeout=5400,result_path=output)
        need(report['context']==self.contexts['qa'] and report['candidate_snapshot_sha256']==self.candidate_tree['snapshot-manifest.json'] and
             report['visibility_ledger_sha256']==self.ledger_sha,'QA handoff identity differs')
        extra={'export':str(self.export),'adapter_sha256':self.adapter_sha,
            'source_dir':str(self.root/'qa-source'),'completion_sha256':source['completion_sha256'],
            'site':str(self.qa_site),'ledger':str(self.qa_ledger),'context':self.contexts['qa'],
            'snapshot_sha256':self.candidate_tree['snapshot-manifest.json'],'ledger_sha256':self.ledger_sha}
        extra_path=self.root/'qa-price-ui-request.json'; extra_digest=write(extra_path,extra)
        extra_output=self.root/'qa-price-ui-result.json'
        try:
            self.price_ui=run_private([sys.executable,'-B',str(HERE/'price_ui_qa.py'),'--request',str(extra_path),
                '--sha256',extra_digest,'--output',str(extra_output)],self.root/'qa-price-ui-process',
                timeout=5400,result_path=extra_output)
            need(self.price_ui['status']=='passed' and self.price_ui['publication_authorized'] is False and
                 self.price_ui['production_eligible'] is False and self.price_ui['browser_visual_qa'] is False,
                 'Additional independent QA refused')
        except Exception: raise PhaseFailure('qa-price-ui') from None
        return report

    def verify_candidate_unchanged(self):
        need(tree(self.qa_site)==self.candidate_tree and file_sha(self.qa_ledger,MAX_SMALL)==self.ledger_sha,'Candidate changed across QA')

    def result(self,report,source):
        result=summarize(report,source,time.monotonic()-self.started,self.metrics)
        keys=('all_public_prices_checked','history_free_products','list_price_fields_checked','shop_rows_checked',
            'bootstrap_price_fields_checked','bootstrap_variation_positions_checked','data_pages_checked','empty_pages_checked',
            'static_function_pages','static_function_assertions','hidden_ids_checked','average_variants_checked')
        counts={key:self.price_ui[key] for key in keys}
        need(all(type(value)is int and value>=0 for value in counts.values()),'Additional QA must expose counts only')
        need(counts['all_public_prices_checked']==result['counts']['visible_products'],'Independent QA populations differ')
        result['additional_qa_checks']=counts
        result['displayed_average_verified']=counts['average_variants_checked']>0
        proof=self.last_historical_proof; self.historical_scope(proof)
        from historical_source import public_labels
        result['historical_source']=public_labels(proof)
        return result


def previous_stage(args):
    verify_adapter(args.adapter_sha256); verify_export(args.export)
    raw=regular(args.request); need(sha(raw)==args.request_sha256,'Previous request changed'); request=strict(raw)
    need(request=={'previous_release_digest':PREVIOUS},'Exact fixed predecessor required')
    low=Path(args.export).resolve()/'original/low-storage'; sys.path.insert(0,str(low))
    import previous_inputs
    need(Path(previous_inputs.__file__).resolve().parent==low,'Wrong previous helper origin')
    receipt,_,_=previous_inputs.verify(previous_inputs.PublicGET(),PREVIOUS)
    need(receipt['original_previous_manifest_recovered'] is False and receipt['expected_date']=='2026-10-31' and
         receipt['publication_authorized'] is False,'Legacy evidence was relabeled')
    write(args.output,receipt); print(encode(receipt).decode())


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    for name in ('inspect','run','previous-stage'):
        p=sub.add_parser(name); p.add_argument('--export',type=Path,required=True); p.add_argument('--adapter-sha256',required=True)
        if name=='run':
            p.add_argument('--output',type=Path,required=True)
        if name=='previous-stage':
            p.add_argument('--request',type=Path,required=True); p.add_argument('--request-sha256',required=True); p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(argv)
    if args.command=='previous-stage': previous_stage(args); return 0
    verify_adapter(args.adapter_sha256); verify_export(args.export)
    if args.command=='inspect':
        print(encode({'status':'local-package-integrity-passed','files':len(verify_export(args.export)['files'])+1,'generator_files':165,
            'real_data_generation_performed':False,'source_eligibility_established':False,'historical_replay':True,'current_source_eligible':False,'automatic_intake_eligible':False,'publication_authorized':False}).decode()); return 0
    output=Path(args.output).absolute(); need(not output.exists() and not output.is_symlink(),'Fresh result directory required')
    for parent in output.parents: need(not parent.is_symlink(),'Linked result parent')
    output.parent.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ); token=os.environ.pop('GITHUB_TOKEN',None)
    need(type(token)is str and token and not any(c.isspace() for c in token),'Explicit existing Actions token required')
    # All historical/private evidence lives outside the eventual upload directory.
    with tempfile.TemporaryDirectory(prefix='stage12-historical-private-',dir=output.parent) as temporary:
        # The sealed resolver starts Node itself. Scrub the parent environment
        # too, so that child cannot inherit any credential or interpreter option.
        sanitized=clean_env(temporary); os.environ.clear(); os.environ.update(sanitized)
        backend=HistoricalBackend(args.export,args.adapter_sha256,Path(temporary),env,token,(HISTORICAL_RUN_ID,HISTORICAL_RUN_ATTEMPT))
        result=orchestrate(backend)
    # Temp cleanup must succeed before exporting the result. Nothing else leaves.
    output.mkdir(mode=0o700); write(output/'trial-result.json',result)
    need(set(p.name for p in output.iterdir())=={'trial-result.json'},'Unexpected public output')
    print(encode(result).decode()); return 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except PhaseFailure as error:
        print(encode({'status':'refused','phase':error.phase,'historical_replay':True,'current_source_eligible':False,'automatic_intake_eligible':False,'publication_authorized':False,'production_eligible':False}).decode(),file=sys.stderr)
        raise SystemExit(1)
    except (Exception, KeyboardInterrupt):
        print('Historical non-serving replay refused; no current eligibility or publication authorized.',file=sys.stderr)
        raise SystemExit(1)
