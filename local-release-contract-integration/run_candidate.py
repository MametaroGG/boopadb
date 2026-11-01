#!/usr/bin/env python3
"""Pinned canonical generation -> v7 build/validation artifacts, offline only."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys

import release_contract as rc

HERE = Path(__file__).resolve().parent
GENERATOR = HERE / 'generator'
CONFIG_FIELDS = {
    'relations_bundle', 'relations_approval', 'relation_search_bundle',
    'relation_search_approval', 'supplement_bundle', 'supplement_approval',
    'daily_coverage_file', 'daily_target_date', 'projection_work',
    'projection_package_sha256', 'presentation_proof', 'presentation_sha256',
}
RELATIONS = (
    ('relations_bundle', 'relations_approval', 'relations_bundle_manifest_sha256', 'relations_approval_sha256'),
    ('relation_search_bundle', 'relation_search_approval', 'relation_search_bundle_manifest_sha256', 'relation_search_approval_sha256'),
    ('supplement_bundle', 'supplement_approval', 'supplement_bundle_manifest_sha256', 'supplement_approval_sha256'),
)


def verify_generator():
    pins = rc.load_strict_json(HERE / 'GENERATOR-INVENTORY.json')
    actual = {p.relative_to(HERE).as_posix(): rc.digest(p)
              for p in GENERATOR.rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    rc.require(actual == pins, 'canonical generator inventory mismatch')


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def configuration(path, relation_inputs, context):
    path = Path(path).resolve()
    obj = rc.load_strict_json(path)
    rc.require(isinstance(obj, dict) and set(obj) == CONFIG_FIELDS, 'explicit complete generation configuration required')
    def resolve(value):
        rc.require(isinstance(value, str) and value, 'configured path required')
        p = Path(value)
        return p if p.is_absolute() else path.parent / p
    resolved = dict(obj)
    for key in CONFIG_FIELDS - {'daily_target_date', 'projection_package_sha256', 'presentation_sha256'}:
        if obj[key] is not None:
            resolved[key] = resolve(obj[key])
    relation_inputs = Path(relation_inputs).resolve()
    expected_paths = rc.load_strict_json(relation_inputs)
    for bundle_key, approval_key, manifest_key, binding_key in RELATIONS:
        rc.require(resolved[bundle_key] is not None and resolved[approval_key] is not None,
                   'all three actual relation bundles/approvals required')
        actual_approval = resolved[approval_key]
        pin_path = Path(expected_paths[binding_key])
        if not pin_path.is_absolute(): pin_path = relation_inputs.parent / pin_path
        rc.require(actual_approval.resolve() == pin_path.resolve(), 'generator approval differs from contract input')
        approval = rc.load_strict_json(actual_approval)
        if not context['synthetic']:
            rc.require(not (approval.get('synthetic') is True or approval.get('fixture') is True
                            or 'local' in str(approval.get('scope', '')).lower()
                            or 'test' in str(approval.get('scope', '')).lower()),
                       'local/synthetic relation approval cannot enter production generation')
        manifest_path = Path(expected_paths[manifest_key])
        if not manifest_path.is_absolute(): manifest_path = relation_inputs.parent / manifest_path
        manifest = rc.load_strict_json(manifest_path)
        rc.require(isinstance(manifest.get('files'), dict) and manifest['files'] == approval.get('files'),
                   'consumed bundle manifest and approval inventories differ')
        for name, sha in manifest['files'].items():
            rc.base._path(name)
            rc.require(rc.digest(resolved[bundle_key] / name) == sha, 'actual bundle bytes differ from consumed manifest')
    rc.require((resolved['daily_coverage_file'] is None) == (obj['daily_target_date'] is None),
               'daily coverage and target date must be explicit together')
    if obj['daily_target_date'] is not None:
        rc.require(obj['daily_target_date'] == context['expected_date'], 'daily target/context mismatch')
    rc.require((resolved['presentation_proof'] is None) == (obj['presentation_sha256'] is None),
               'presentation proof and digest required together')
    rc.require((resolved['projection_work'] is None) == (obj['projection_package_sha256'] is None),
               'projection source and digest required together')
    return resolved


def run(dest, *, context_path, baseline_pin, baseline_sha256, relation_inputs,
        tracker_root, generation_config):
    """Run the actual pinned CLIs. Failure retains diagnostics, never QA success."""
    verify_generator()
    c, pin, bindings = rc.inputs(context_path, baseline_pin, baseline_sha256, relation_inputs)
    config = configuration(generation_config, relation_inputs, c)
    dest = Path(dest).resolve()
    rc.require(not dest.exists() and not dest.is_symlink(), 'run destination must not exist')
    dest.mkdir(parents=True)
    work = dest / 'work'; work.mkdir()
    commands = []
    def command(script, *args):
        cmd = [sys.executable, str(script), *map(str, args)]
        commands.append(cmd)
        result = subprocess.run(cmd, cwd=dest, capture_output=True, text=True,
                                env={**__import__('os').environ, 'PYTHONDONTWRITEBYTECODE': '1'})
        (dest / ('command-%02d.log' % len(commands))).write_text(result.stdout + '\n' + result.stderr)
        rc.write_json(dest / 'commands.json', commands)
        rc.require(result.returncode == 0, 'canonical command failed: ' + str(script) + ' (see command log)')
    try:
        command(GENERATOR / 'inventory_snapshot.py', '--tracker-root', Path(tracker_root).resolve(),
                '--output', work / 'input-inventory.json')
        rc.require(rc.digest(work / 'input-inventory.json') == c['inventory_digest'],
                   'generated inventory does not match explicit expected context')
        args = ['--tracker-root', Path(tracker_root).resolve(), '--tracker-commit', c['tracker_commit'],
                '--inventory', work / 'input-inventory.json', '--minimum-source-date', '2026-10-30',
                '--max-source-age-days', '1', '--output', work / 'attestation.json']
        if c['synthetic']: args.append('--fixture')
        command(GENERATOR / 'attest_snapshot.py', *args)
        att = rc.load_typed('attestation', work / 'attestation.json')
        rc.require(att['expected_date'] == c['expected_date'], 'actual source date differs from expected context')
        command(GENERATOR / 'prepare_inputs.py', '--tracker-root', Path(tracker_root).resolve(),
                '--tracker-commit', c['tracker_commit'], '--inventory', work / 'input-inventory.json',
                '--generate-charts', '--attestation', work / 'attestation.json', '--output-dir', dest / 'prepared')
        shutil.copyfile(dest / 'prepared/completion.json', work / 'prepared-input.json')
        inventory = rc.load_typed('ledger', work / 'input-inventory.json')
        rc.write_json(work / 'input-inventory-summary.json', {
            'files': len(inventory), 'inventory_count': len(inventory),
            'inventory_digest': c['inventory_digest'],
            'non_json_files': sorted(name for name in inventory if not name.endswith('.json')),
        })
        args = ['--input-root', dest / 'prepared', '--completion-manifest', dest / 'prepared/completion.json',
                '--static-root', GENERATOR / 'pinned-static', '--output-dir', dest / 'site']
        for bundle_key, approval_key, _, _ in RELATIONS:
            for key in (bundle_key, approval_key):
                args += ['--' + key.replace('_', '-'), config[key]]
        if config['daily_coverage_file'] is not None:
            args += ['--daily-coverage-file', config['daily_coverage_file'], '--daily-target-date', config['daily_target_date']]
        if config['presentation_proof'] is not None:
            args += ['--presentation-proof', config['presentation_proof'], '--presentation-sha256', config['presentation_sha256']]
        if config['projection_work'] is not None:
            source = config['projection_work']
            package = rc.load_strict_json(source / 'projection-package.json')
            rc.require(isinstance(package, dict) and 'records' in package and 'package' not in package
                       and not any(k in package for k in ('authority_verified', 'artifact_stage', 'deployable')),
                       'review-only envelope refused before generator')
            rc.require(canonical_digest(package) == config['projection_package_sha256'], 'projection package commitment mismatch')
            blobs = rc.base._tree(source / 'projection-evidence')
            args += ['--projection-package', source / 'projection-package.json',
                     '--projection-package-sha256', config['projection_package_sha256']]
            for name, blob in sorted(blobs.items()):
                rc.require(name == hashlib.sha256(blob).hexdigest(), 'invalid projection artifact content address')
                args += ['--projection-evidence', source / 'projection-evidence' / name]
        command(GENERATOR / 'build_site.py', *args)
        if config['projection_work'] is not None:
            source = config['projection_work']
            shutil.copyfile(source / 'projection-package.json', work / 'projection-package.json')
            rc.copy_tree_bytes(source / 'projection-evidence', work / 'projection-evidence')
            snapshot = rc.load_strict_json(dest / 'site/snapshot-manifest.json')
            payload = rc.load_strict_json(dest / 'site/current-price-projection.json')
            # These are transport bindings DERIVED from the completed generator,
            # not review approval or new observations/expiry.
            rc.write_json(work / 'projection-declaration.json', {
                'applied': True, 'package_sha256': config['projection_package_sha256'],
                'as_of': snapshot['current_price_projection']['as_of'],
                'payload_sha256': canonical_digest(payload), 'applied_items': sorted(payload['entries']),
            })
        common = dict(context_path=Path(context_path).resolve(), baseline_pin=Path(baseline_pin).resolve(),
                      baseline_sha256=baseline_sha256, relation_inputs=Path(relation_inputs).resolve(),
                      tracker_root=Path(tracker_root).resolve())
        contract = rc.prepare(dest / 'site', work, dest / 'build-artifact', **common)
        import validation_job
        result = validation_job.validate_job(dest / 'build-artifact', dest / 'qa-artifact', **common)
        rc.write_json(dest / 'RESULT.json', {'synthetic': c['synthetic'], 'deployable': False,
                                            'contract': contract, 'validation': result})
        return result
    except Exception as exc:
        (dest / 'FAILED.txt').write_text(str(exc) + '\n')
        raise


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dest', required=True)
    p.add_argument('--context', dest='context_path', required=True)
    p.add_argument('--baseline-pin', required=True)
    p.add_argument('--baseline-sha256', required=True)
    p.add_argument('--relation-inputs', required=True)
    p.add_argument('--tracker-root', required=True)
    p.add_argument('--generation-config', required=True)
    print(json.dumps(run(**vars(p.parse_args())), indent=2))


if __name__ == '__main__': main()
