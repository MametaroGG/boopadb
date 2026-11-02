#!/usr/bin/env python3
"""Offline v7 build-artifact contract adapter, never a release authorization.

No fetching, publishing, approval creation, collector completion inference, or
historical clock override. The caller supplies reviewed pins and run context.
"""
import argparse
import datetime as dt
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / 'validators'))
from validate_bindings import load_strict_json, load_typed, validate_typed
import artifact_handoff_base as base

RELATION_KEYS = (
    'relations_bundle_manifest_sha256', 'relations_approval_sha256',
    'relation_search_bundle_manifest_sha256', 'relation_search_approval_sha256',
    'supplement_bundle_manifest_sha256', 'supplement_approval_sha256',
)
CONTEXT_KEYS = {
    'synthetic', 'tracker_commit', 'generator_commit', 'run_id', 'run_attempt',
    'generation', 'prev_release_digest', 'expected_date', 'inventory_digest',
}
BASE_WORK = {*base.INPUT_NAMES, 'hash-ledger.json', 'qa-archive.json',
             'run-manifest.json', 'evidence-records.json', 'contract-context.json'}
PROJECTION_FILES = {'projection-package.json', 'projection-declaration.json'}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_bytes(path):
    path = Path(path)
    require(path.is_file() and not path.is_symlink(), 'regular input file required: ' + str(path))
    return path.read_bytes()


def digest(path):
    return hashlib.sha256(read_bytes(path)).hexdigest()


def write_json(path, value):
    Path(path).write_bytes(base.encode(value))


def typed(kind, value):
    validate_typed(kind, value)
    return value


def run_validator(name, *args):
    return base.cli(name, *args)


def checked_context(path):
    c = load_strict_json(path)
    require(isinstance(c, dict) and set(c) == CONTEXT_KEYS, 'exact explicit context fields required')
    require(type(c['synthetic']) is bool, 'synthetic must be a boolean')
    for key in ('tracker_commit', 'generator_commit'):
        require(isinstance(c[key], str) and re.fullmatch('[0-9a-f]{40}', c[key]), 'invalid ' + key)
    for key in ('prev_release_digest', 'inventory_digest'):
        require(isinstance(c[key], str) and re.fullmatch('[0-9a-f]{64}', c[key]), 'invalid ' + key)
    for key in ('run_id', 'run_attempt'):
        require(isinstance(c[key], str) and re.fullmatch('[0-9]+', c[key]) and int(c[key]) > 0, 'invalid ' + key)
    require(type(c['generation']) is int and c['generation'] > 0, 'invalid generation')
    require(isinstance(c['expected_date'], str) and dt.date.fromisoformat(c['expected_date']).isoformat() == c['expected_date'], 'invalid date')
    return c


def inputs(context_path, baseline_pin, baseline_sha256, relation_inputs):
    c = checked_context(context_path)
    require(digest(baseline_pin) == baseline_sha256, 'baseline pin byte commitment mismatch')
    pin = load_typed('baseline-pin', baseline_pin)
    require(c['synthetic'] or not (pin.get('synthetic') is True or pin.get('fixture') is True),
            'synthetic baseline pin cannot validate production context')
    relation_inputs = Path(relation_inputs)
    paths = load_strict_json(relation_inputs)
    require(isinstance(paths, dict) and set(paths) == set(RELATION_KEYS), 'all six actual relation inputs required')
    bindings = {}
    for key in RELATION_KEYS:
        require(isinstance(paths[key], str) and paths[key], 'actual relation path required: ' + key)
        path = Path(paths[key])
        if not path.is_absolute():
            path = relation_inputs.parent / path
        bindings[key] = digest(path)
    require(bindings == {key: pin['relations_binding'][key] for key in RELATION_KEYS}, 'actual consumed relation inputs differ from baseline pin')
    # Carry pin's descriptive metadata unchanged so the existing v7 workflow's
    # whole-object equality gate also succeeds; the six hashes above are computed
    # from actual consumed files, never merely copied from the pin.
    bindings = {**pin['relations_binding'], **bindings}
    return c, pin, bindings


def tracker_inventory(work, tracker_root):
    """Recheck the actual data/meta source bytes; never infer completed collection."""
    inventory = load_typed('ledger', Path(work) / 'input-inventory.json')
    tracker_root = Path(tracker_root)
    actual = {}
    for directory in ('data', 'meta'):
        root = tracker_root / directory
        require(root.is_dir() and not root.is_symlink(), 'tracker data/meta required')
        # Empty subdirectories are immaterial to the producer's source inventory.
        for directory_path, dirs, names in os.walk(root, followlinks=False):
            for name in dirs:
                require(not (Path(directory_path) / name).is_symlink(), 'source directory symlink')
            for name in names:
                path = Path(directory_path) / name
                rel = path.relative_to(tracker_root).as_posix()
                base._path(rel)
                actual[rel] = digest(path)
    require(actual == inventory, 'actual tracker source differs from input inventory')


def core_bindings(site, work, c, pin, bindings):
    objects = base._bindings(work, c['inventory_digest'], c['tracker_commit'], c['expected_date'])
    snap = load_typed('snapshot-manifest', Path(site) / 'snapshot-manifest.json')
    att = objects['attestation.json']
    prepared = objects['prepared-input.json']
    for name, obj in (('attestation', att), ('prepared-input', prepared), ('snapshot', snap)):
        require(type(obj.get('fixture')) is bool, name + ' explicit fixture boolean required')
        require(obj['fixture'] == c['synthetic'], name + ' fixture/context boundary mismatch')
    rows = snap['validation']['rows']
    require(rows > 0 and rows >= pin['product_count'] * 0.98, 'population regression vs pinned baseline')
    require(snap['validation']['max_date'] == c['expected_date'], 'snapshot/date binding mismatch')
    date = dt.date.fromisoformat(c['expected_date'])
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    require(date <= today and (today - date).days <= 1, 'future or stale snapshot')
    require(date >= dt.date(2026, 10, 30) and c['expected_date'] >= pin['max_date'], 'source date regression')
    require(c['generation'] > pin['generation'], 'generation must succeed pinned baseline')
    # Exact next-live-generation and current predecessor are checked by the
    # selection adapter/promote; this adapter never invents a live state.
    require(bindings == pin['relations_binding'], 'relation binding mismatch')
    return rows, len(objects['input-inventory.json'])


def manifests(c, rows, count, bindings, site_files):
    release = {
        'schema': 1, 'generation': c['generation'], 'source_date': c['expected_date'],
        'product_count': rows, 'tracker_commit': c['tracker_commit'],
        'generator_commit': c['generator_commit'], 'run_id': c['run_id'],
        'inventory_digest': c['inventory_digest'], 'prev_release_digest': c['prev_release_digest'],
    }
    run = {
        'run_id': c['run_id'], 'run_attempt': c['run_attempt'],
        'tracker_commit': c['tracker_commit'], 'generator_commit': c['generator_commit'],
        'expected_date': c['expected_date'], 'product_count': rows, 'site_files': site_files,
        'generation': c['generation'], 'inventory_digest': c['inventory_digest'],
        'inventory_count': count, 'prev_release_digest': c['prev_release_digest'],
        'relations_binding': bindings,
    }
    return typed('release-manifest', release), typed('run-manifest', run)


def copy_tree_bytes(source, target):
    files = base._tree(source)
    target.mkdir()
    for name, blob in files.items():
        out = target / name
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(blob)
    return files


def copy_projection(source_work, target_work):
    """Only explicit v7 package files; never unwrap review-only builder output."""
    source_work, target_work = Path(source_work), Path(target_work)
    present = [name for name in PROJECTION_FILES if (source_work / name).exists()]
    evdir = source_work / 'projection-evidence'
    if not present and not evdir.exists():
        return
    require(len(present) == 2 and evdir.is_dir(), 'incomplete projection inputs')
    package = load_strict_json(source_work / 'projection-package.json')
    require(isinstance(package, dict) and 'records' in package and 'package' not in package,
            'review-only envelope is not a projection package')
    require(not any(key in package for key in ('authority_verified', 'artifact_stage', 'deployable')),
            'untrusted/review-only projection package refused')
    load_typed('projection-declaration', source_work / 'projection-declaration.json')
    for name in sorted(PROJECTION_FILES):
        (target_work / name).write_bytes(read_bytes(source_work / name))
    files = copy_tree_bytes(evdir, target_work / 'projection-evidence')
    for name, blob in files.items():
        require(re.fullmatch('[0-9a-f]{64}', name) and hashlib.sha256(blob).hexdigest() == name,
                'projection artifact must use exact content-addressed filename')


def evidence(pin, work):
    want = pin['evidence']['thumbnail_correction_2625416']
    records = [dict(want, kind='verified_thumbnail')]
    package = Path(work) / 'projection-package.json'
    if package.exists():
        pkg = load_strict_json(package)
        declaration = load_typed('projection-declaration', Path(work) / 'projection-declaration.json')
        require(isinstance(pkg.get('records'), dict), 'projection records mapping required')
        for item in sorted(pkg['records']):
            records.append({'item_id': item, 'kind': 'current_price_projection',
                            'package_sha256': declaration['package_sha256'], 'as_of': declaration['as_of']})
    return typed('evidence-records', {'schema': 1, 'records': records})


def contract_gates(site, work, tracker_root, pin):
    """Existing static UI and current-time projection gates; not browser approval."""
    site, work = Path(site), Path(work)
    actual = load_typed('evidence-records', work / 'evidence-records.json')
    require(actual == evidence(pin, work), 'evidence enumeration/binding differs from actual inputs')
    want = pin['evidence']['thumbnail_correction_2625416']
    observed = dt.datetime.fromisoformat(want['confirmed_at'].replace('Z', '+00:00'))
    require(observed.tzinfo is not None and observed <= dt.datetime.now(dt.timezone.utc), 'future/naive thumbnail evidence')
    for name in ('index.html', 'item.html'):
        require(want['corrected_url'] in read_bytes(site / name).decode('utf-8'), 'pinned thumbnail missing from ' + name)
    run_validator('gate_ui.py', site)
    run_validator('check_projection.py', '--gate', '--work-dir', work,
                  '--site-dir', site, '--raw-dir', Path(tracker_root) / 'data',
                  '--evaluation-time', dt.datetime.now(dt.timezone.utc).isoformat())


def _report(c, record, site_files):
    return {
        'status': 'build-artifact-contract-validated', 'synthetic': c['synthetic'],
        'deployable': False, 'archive_sha256': record['sha256'], 'site_files': site_files,
        'gates': ['typed-bindings', 'actual-input-inventory', 'actual-relations-bindings',
                  'freshness-and-baseline-population', 'static-ui-v7', 'evidence-enumeration',
                  'current-time-projection-v7', 'archive-and-exact-ledger'],
        'not_established': ['collector-completion-authority', 'actual-checkout-commit-identity',
                            'live-lineage-currentness', 'canonical-snapshot-runtime-qa',
                            'browser-qa', 'independent-review-authority',
                            'workflow-identity-and-protection', 'deployment'],
    }


def prepare(site, work, dest, *, context_path, baseline_pin, baseline_sha256, relation_inputs, tracker_root, reuse_policy=None):
    """Create a new v7 build artifact, without changing source site/work bytes."""
    site, work, dest = map(Path, (site, work, dest))
    require(not dest.exists() and not dest.is_symlink(), 'destination must not exist')
    c, pin, bindings = inputs(context_path, baseline_pin, baseline_sha256, relation_inputs)
    if reuse_policy is not None:
        import reuse_authorization as reuse
        reuse.verify(reuse_policy, c, baseline_pin, baseline_sha256, relation_inputs)
    rows, count = core_bindings(site, work, c, pin, bindings)
    tracker_inventory(work, tracker_root)
    require(not (site / 'release-manifest.json').exists(), 'source already has release manifest; do not silently replace lineage')
    require(not any((work / n).exists() for n in ('run-manifest.json', 'evidence-records.json', 'contract-context.json')),
            'source work already has release contract; do not silently replace evidence')
    with tempfile.TemporaryDirectory(prefix='.release-contract-', dir=dest.parent) as temp:
        root = Path(temp)
        candidate = root / 'site'
        copy_tree_bytes(site, candidate)
        outwork = root / 'work'
        outwork.mkdir()
        for name in base.INPUT_NAMES:
            (outwork / name).write_bytes(read_bytes(work / name))
        copy_projection(work, outwork)
        release, _ = manifests(c, rows, count, bindings, 0)
        write_json(candidate / 'release-manifest.json', release)
        ledger = {name: hashlib.sha256(blob).hexdigest() for name, blob in base._tree(candidate).items()}
        _, run = manifests(c, rows, count, bindings, len(ledger))
        write_json(outwork / 'hash-ledger.json', ledger)
        write_json(outwork / 'run-manifest.json', run)
        write_json(outwork / 'evidence-records.json', evidence(pin, outwork))
        write_json(outwork / 'contract-context.json', c)
        contract_gates(candidate, outwork, tracker_root, pin)
        # Reuse the unchanged reviewed archive packer; extend its result with
        # the additional v7 metadata it intentionally did not implement.
        artifact = root / 'artifact'
        record = base.pack(candidate, outwork, artifact)
        for name in ('run-manifest.json', 'evidence-records.json', 'contract-context.json'):
            (artifact / 'work' / name).write_bytes(read_bytes(outwork / name))
        if (outwork / 'projection-package.json').exists():
            copy_projection(outwork, artifact / 'work')
        if reuse_policy is not None:
            write_json(artifact / 'work/reuse-envelope.json', reuse.envelope(reuse_policy, c, baseline_pin, baseline_sha256, relation_inputs, artifact / 'site-release.tar'))
        # Execute the receiving contract against the SAME archive before commit.
        result = validate(artifact, root / 'checked', context_path=context_path,
                          baseline_pin=baseline_pin, baseline_sha256=baseline_sha256,
                          relation_inputs=relation_inputs, tracker_root=tracker_root, reuse_policy=reuse_policy)
        require(not dest.exists() and not dest.is_symlink(), 'destination appeared')
        artifact.rename(dest)
    return result


def validate(artifact, dest, *, context_path, baseline_pin, baseline_sha256, relation_inputs, tracker_root, reuse_policy=None):
    """Validate/extract full contract. Success is NOT authorization to promote."""
    artifact, dest = map(Path, (artifact, dest))
    require(not dest.exists() and not dest.is_symlink(), 'destination must not exist')
    c, pin, bindings = inputs(context_path, baseline_pin, baseline_sha256, relation_inputs)
    files = base._tree(artifact)
    required = {'site-release.tar', *('work/' + name for name in BASE_WORK)}
    if reuse_policy is not None:
        required.add('work/reuse-envelope.json')
        import reuse_authorization as reuse
        reuse.check_envelope(reuse_policy, c, baseline_pin, baseline_sha256, relation_inputs, artifact / 'site-release.tar', artifact / 'work/reuse-envelope.json')
    projection_names = {name for name in files if name.startswith('work/projection-')}
    if projection_names:
        require({'work/' + name for name in PROJECTION_FILES} <= projection_names, 'incomplete projection handoff')
        for name in projection_names - {'work/' + name for name in PROJECTION_FILES}:
            require(re.fullmatch(r'work/projection-evidence/[0-9a-f]{64}', name), 'unexpected projection handoff path')
        required |= projection_names
    require(set(files) == required, 'artifact exact layout mismatch')
    work = artifact / 'work'
    require(load_strict_json(work / 'contract-context.json') == c, 'context binding mismatch')
    tracker_inventory(work, tracker_root)
    record = load_typed('qa-archive', work / 'qa-archive.json')
    require(record['archive'] == 'site-release.tar' and record['sha256'] == hashlib.sha256(files['site-release.tar']).hexdigest()
            and record['bytes'] == len(files['site-release.tar']), 'archive byte binding mismatch')
    with tempfile.TemporaryDirectory(prefix='.release-validate-', dir=dest.parent) as temp:
        root = Path(temp)
        if projection_names:
            projection_check = root / 'projection-check'
            projection_check.mkdir()
            copy_projection(work, projection_check)
        # The unchanged base validator requires its original exact layout.
        # A private projection of the artifact supplies those same bytes;
        # the full layout above and extra bindings below are also mandatory.
        original = root / 'base-artifact'
        original.mkdir()
        (original / 'work').mkdir()
        (original / 'site-release.tar').write_bytes(files['site-release.tar'])
        for name in base.WORK_NAMES:
            (original / 'work' / name).write_bytes(read_bytes(work / name))
        site = root / 'site'
        base.validate(original, site, c['inventory_digest'], c['tracker_commit'], c['expected_date'])
        rows, count = core_bindings(site, work, c, pin, bindings)
        ledger = load_typed('ledger', work / 'hash-ledger.json')
        release, run = manifests(c, rows, count, bindings, len(ledger))
        require(load_typed('release-manifest', site / 'release-manifest.json') == release, 'release manifest binding mismatch')
        require(load_typed('run-manifest', work / 'run-manifest.json') == run, 'run manifest binding mismatch')
        contract_gates(site, work, tracker_root, pin)
        require(not dest.exists() and not dest.is_symlink(), 'destination appeared')
        site.rename(dest)
    return _report(c, record, len(ledger))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'validate'):
        p = sub.add_parser(name)
        if name == 'prepare':
            p.add_argument('--site', required=True)
            p.add_argument('--work', required=True)
        else:
            p.add_argument('--artifact', required=True)
        p.add_argument('--dest', required=True)
        p.add_argument('--context', dest='context_path', required=True)
        p.add_argument('--baseline-pin', required=True)
        p.add_argument('--baseline-sha256', required=True)
        p.add_argument('--relation-inputs', required=True)
        p.add_argument('--tracker-root', required=True)
        p.add_argument('--reuse-policy')
    a = vars(parser.parse_args())
    command = a.pop('command')
    print(json.dumps(globals()[command](**a), indent=2))


if __name__ == '__main__':
    main()
