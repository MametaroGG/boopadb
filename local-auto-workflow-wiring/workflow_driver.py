#!/usr/bin/env python3
"""Fail-closed local wiring for an UNINSTALLED/OFF automatic-input workflow.

Only resolve invokes read-only HTTP via the separate reviewed resolver. No
publication, authorization, review record, credentials, or collector receipts
are created here. No imports execute remote calls.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
RESOLVER = ROOT / 'local-auto-input-contract/resolve_automatic_inputs.py'
RELEASE = ROOT / 'local-release-contract-integration'
CONFIG_KEYS = {'schema', 'baseline_pin', 'baseline_sha256', 'producer_pin',
               'relation_inputs', 'generation_config'}
CONTEXT_KEYS = {'synthetic', 'tracker_commit', 'generator_commit', 'run_id',
                'run_attempt', 'generation', 'prev_release_digest',
                'expected_date', 'inventory_digest'}

def require(ok, reason):
    if not ok:
        raise ValueError(reason)

def load(path):
    def pairs(values):
        result = {}
        for key, value in values:
            require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    return json.loads(Path(path).read_bytes(), object_pairs_hook=pairs)

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def match(value, pattern):
    return isinstance(value, str) and re.fullmatch(pattern, value) is not None

def write_new(path, obj):
    with Path(path).open('x') as stream:
        json.dump(obj, stream, indent=2, sort_keys=True)
        stream.write('\n')

def run(script, *args):
    subprocess.run([sys.executable, str(script), *map(str, args)], check=True)

def head(path):
    return subprocess.check_output(['git', '-C', str(path), 'rev-parse', 'HEAD'],
                                   text=True, env={**os.environ, 'GIT_NO_REPLACE_OBJECTS': '1'}).strip()

def configuration(path):
    path = Path(path)
    require(not path.is_symlink(), 'Configuration cannot be a symlink')
    path = path.resolve()
    require(path.is_relative_to(ROOT), 'Configuration must be inside generator checkout')
    c = load(path)
    require(isinstance(c, dict) and set(c) == CONFIG_KEYS and type(c['schema']) is int and c['schema'] == 1,
            'Explicit exact production configuration required')
    require(match(c['baseline_sha256'], '[0-9a-f]{64}'), 'Real baseline SHA256 required')
    for key in ('baseline_pin', 'producer_pin', 'relation_inputs', 'generation_config'):
        value = c[key]
        require(isinstance(value, str) and value and not Path(value).is_absolute(),
                key + ' must be a relative checked-out file path')
        require(not re.search(r'PROPOSAL|EXAMPLE|PLACEHOLDER|DRAFT-ADAPTATION|REQUIRED|TODO', value),
                'Unreviewed proposal/example/placeholder refused: ' + key)
        p = path.parent / value
        require(not p.is_symlink() and p.resolve().is_relative_to(ROOT) and p.is_file(),
                'Missing or out-of-checkout configured file: ' + key)
        c[key] = p.resolve()
    require(sha(c['baseline_pin']) == c['baseline_sha256'], 'Baseline pin bytes mismatch')
    c['config_sha256'] = sha(path)
    return c

def identity():
    require(os.environ.get('GITHUB_ACTIONS') == 'true', 'Actual GitHub Actions identity required')
    require(match(os.environ.get('GITHUB_SHA'), '[0-9a-f]{40}'), 'Generator SHA must be immutable')
    for key in ('GITHUB_RUN_ID', 'GITHUB_RUN_ATTEMPT'):
        require(match(os.environ.get(key), '[1-9][0-9]*'), key + ' must be positive decimal')
    require(head(ROOT) == os.environ['GITHUB_SHA'], 'Generator checkout HEAD differs from workflow SHA')

def selection(path):
    p = load(path)
    require(p.get('schema') == 'boopa-resolved-inputs-v1', 'Wrong resolver output schema')
    s = p.get('selection', {})
    require(s.get('selection_authority') == 'authenticated-github-read-and-live-lineage',
            'Authenticated resolver output required; offline-only receipt refused')
    require(match(s.get('tracker_commit'), '[0-9a-f]{40}'), 'Malformed selected tracker SHA')
    require(match(s.get('prev_release_digest'), '[0-9a-f]{64}'), 'Malformed predecessor digest')
    require(type(s.get('generation')) is int and s['generation'] > 0, 'Malformed generation')
    require(match(s.get('expected_date'), r'\d{4}-\d{2}-\d{2}'), 'Malformed expected date')
    dt.date.fromisoformat(s['expected_date'])
    require(s.get('whole_catalog_complete') is False and
            s.get('collection_scope') == 'bounded-filtered-search-observation', 'Bounded collection scope required')
    return p

def preflight(config):
    identity()
    c = configuration(config)
    for script in (RESOLVER, RELEASE / 'run_candidate.py', RELEASE / 'validation_job.py',
                   RELEASE / 'generator/inventory_snapshot.py'):
        require(script.is_file(), 'Missing integrated executable: ' + str(script))
    # The same inventory check runs again immediately before generation.
    sys.path.insert(0, str(RELEASE))
    import run_candidate
    run_candidate.verify_generator()
    return c

def resolve(config, work):
    c = preflight(config)
    work = Path(work)
    require(not work.exists(), 'Resolve work destination must be new')
    work.mkdir(parents=True)
    run(RESOLVER, 'resolve', '--workdir', work / 'selection',
        '--baseline-pin', c['baseline_pin'], '--baseline-pin-sha256', c['baseline_sha256'],
        '--producer-pin', c['producer_pin'])
    p = selection(work / 'selection/resolved-inputs.json')
    require(p.get('producer_pin_sha256') == sha(c['producer_pin']), 'Resolved producer pin differs from configured reviewed pin')
    write_new(work / 'config-binding.json', {'config_sha256': c['config_sha256']})
    output = os.environ.get('GITHUB_OUTPUT')
    require(output is not None, 'GITHUB_OUTPUT required')
    with open(output, 'a') as stream:
        stream.write('tracker_commit=' + p['selection']['tracker_commit'] + '\n')

def prepare(config, work, tracker):
    c = preflight(config)
    work, tracker = Path(work), Path(tracker)
    p = selection(work / 'selection/resolved-inputs.json')
    require(p.get('producer_pin_sha256') == sha(c['producer_pin']), 'Resolved producer pin differs from configured reviewed pin')
    require(load(work / 'config-binding.json') == {'config_sha256': c['config_sha256']},
            'Configuration differs across selection/handoff')
    require(head(tracker) == p['selection']['tracker_commit'], 'Tracker checkout differs from selected immutable SHA')
    inventory = work / 'input-inventory.json'
    run(RELEASE / 'generator/inventory_snapshot.py', '--tracker-root', tracker, '--output', inventory)
    context = work / 'context.json'
    require(not context.exists(), 'Context must be new')
    run(RESOLVER, 'finalize-context', '--selection', work / 'selection/resolved-inputs.json',
        '--inventory', inventory, '--output', context)
    obj = load(context)
    require(set(obj) == CONTEXT_KEYS and obj['synthetic'] is False, 'Exact nine-key production context required')
    expected = dict(synthetic=False, tracker_commit=p['selection']['tracker_commit'],
                    generator_commit=os.environ['GITHUB_SHA'], run_id=os.environ['GITHUB_RUN_ID'],
                    run_attempt=os.environ['GITHUB_RUN_ATTEMPT'], generation=p['selection']['generation'],
                    prev_release_digest=p['selection']['prev_release_digest'],
                    expected_date=p['selection']['expected_date'], inventory_digest=sha(inventory))
    require(obj == expected, 'Final context differs from actual checkout/inventory/workflow identity')
    return c

def common(c, work, tracker):
    return ['--context', Path(work) / 'context.json', '--baseline-pin', c['baseline_pin'],
            '--baseline-sha256', c['baseline_sha256'], '--relation-inputs', c['relation_inputs'],
            '--tracker-root', tracker]

def build(config, work, tracker):
    c = prepare(config, work, tracker)
    run(RELEASE / 'run_candidate.py', '--dest', Path(work) / 'candidate',
        *common(c, work, tracker), '--generation-config', c['generation_config'])
    # Only transfer resolver proof + config binding, not its signed URLs/API cache.
    handoff = Path(work) / 'selection-handoff'
    handoff.mkdir()
    (handoff / 'selection').mkdir()
    shutil.copyfile(Path(work) / 'selection/resolved-inputs.json', handoff / 'selection/resolved-inputs.json')
    shutil.copyfile(Path(work) / 'config-binding.json', handoff / 'config-binding.json')

def validate(config, work, tracker, artifact, dest):
    c = prepare(config, work, tracker)
    run(RELEASE / 'validation_job.py', '--artifact', artifact, '--dest', dest,
        *common(c, work, tracker))
    require(not (Path(dest) / 'evidence/qa-review-record.json').exists(),
            'Machine validation must not mint independent human QA approval')

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('stage', choices=['preflight', 'resolve', 'build', 'validate'])
    p.add_argument('--config', required=True)
    p.add_argument('--work', default='auto-work')
    p.add_argument('--tracker', default='source')
    p.add_argument('--artifact', default='incoming')
    p.add_argument('--dest', default='qa-artifact')
    a = p.parse_args()
    try:
        if a.stage == 'preflight': preflight(a.config)
        elif a.stage == 'resolve': resolve(a.config, a.work)
        elif a.stage == 'build': build(a.config, a.work, a.tracker)
        else: validate(a.config, a.work, a.tracker, a.artifact, a.dest)
    except Exception as exc:
        # Deliberately omit error text, URLs, config bytes and credentials. Actual
        # generator command logs remain separate; this record never claims QA.
        work = Path(a.work)
        if not work.is_symlink():
            work.mkdir(parents=True, exist_ok=True)
            output = work / 'failure-diagnostics.json'
            if not output.exists():
                write_new(output, {'status': 'failed', 'stage': a.stage,
                    'run_id': os.environ.get('GITHUB_RUN_ID'),
                    'run_attempt': os.environ.get('GITHUB_RUN_ATTEMPT'),
                    'error_class': type(exc).__name__, 'published': False})
        raise

if __name__ == '__main__':
    main()
