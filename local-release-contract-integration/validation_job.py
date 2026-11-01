#!/usr/bin/env python3
"""Execute offline v7 validation gates and stage its byte-identical QA artifact.

This is machine validation, NOT independent reviewer approval or permission to
publish. No production authority, completion, or live-lineage facts are minted.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import tempfile

import release_contract as rc

PINNED_SELECTOR_SHA256 = 'b41ef07ae3982eb9a75a8b517ee92f9df6472e7a5d94d47ab3ffd2e74c761809'
PINNED_HERO_SHA256 = '946f4226d75e00017404735bf295100ffd35dfafac78dd6cdea0652a07f85d68'
EVIDENCE_NAMES = (
    'hash-ledger.json', 'run-manifest.json', 'qa-archive.json',
    'attestation.json', 'input-inventory.json', 'input-inventory-summary.json',
    'evidence-records.json',
)
GATES = [
    'typed-manifest-validation',
    'archive-digest+safe-extract+ledger-set-equality',
    'bindings+freshness',
    'population-vs-pinned-baseline',
    'validate_snapshot+search-core-recombination',
    'ui-regression-per-page-brace-matched',
    'evidence-records-vs-pin',
    'projection-contract-gate',
]


def validate_job(artifact, dest, *, context_path, baseline_pin, baseline_sha256,
                 relation_inputs, tracker_root):
    """All checks must pass before exposing a new QA artifact at ``dest``.

    The incoming artifact is copied to isolated storage before validation. The
    same captured archive bytes are staged, not regenerated or repacked. Caller
    context/pins and actual tracker/relation inputs are verified by rc.validate.
    No clock override and no bypass/synthetic-success path is provided.
    """
    artifact, dest = Path(artifact), Path(dest)
    rc.require(not dest.exists() and not dest.is_symlink(), 'QA destination must not exist')
    kwargs = dict(context_path=context_path, baseline_pin=baseline_pin,
                  baseline_sha256=baseline_sha256, relation_inputs=relation_inputs,
                  tracker_root=tracker_root)
    with tempfile.TemporaryDirectory(prefix='.validation-job-', dir=dest.parent) as directory:
        root = Path(directory)
        incoming = root / 'incoming'
        rc.copy_tree_bytes(artifact, incoming)
        site = root / 'site'
        report = rc.validate(incoming, site, **kwargs)
        # validate_snapshot executes site/scripts/embed-hero.cjs. Rehashing an
        # attacker-modified site manifest must never authorize new executable JS.
        hero = site / 'scripts/embed-hero.cjs'
        rc.require(rc.digest(hero) == PINNED_HERO_SHA256,
                   'untrusted hero executable: reviewed source hash required')
        # Existing canonical prepare_deployment.py trust boundary: the pinned
        # hero evaluates this span, so a rehashed HTML file is not sufficient.
        selector = re.search(r'// HERO_SELECTOR_START[^\n]*\n([\s\S]*?)// HERO_SELECTOR_END',
                             rc.read_bytes(site / 'index.html').decode('utf-8'))
        rc.require(selector is not None and hashlib.sha256(selector[1].encode()).hexdigest() == PINNED_SELECTOR_SHA256,
                   'untrusted hero selector: pinned baseline source required')
        run = rc.load_typed('run-manifest', incoming / 'work/run-manifest.json')
        rc.run_validator('validate_snapshot.py', '--root', site,
                         '--expected-date', run['expected_date'],
                         '--manifest', site / 'snapshot-manifest.json')
        # Reload external pins through the same checked input boundary. A pin
        # replacement while checks were running is not silently accepted.
        context, pin, _ = rc.inputs(context_path, baseline_pin, baseline_sha256, relation_inputs)
        rc.require(rc.load_strict_json(incoming / 'work/contract-context.json') == context,
                   'context changed during validation')
        archive = rc.load_typed('qa-archive', incoming / 'work/qa-archive.json')
        result = {
            'status': 'passed',
            'run_id': run['run_id'], 'tracker_commit': run['tracker_commit'],
            'generator_commit': run['generator_commit'], 'expected_date': run['expected_date'],
            'product_count': run['product_count'], 'generation': run['generation'],
            'inventory_digest': run['inventory_digest'],
            'prev_release_digest': run['prev_release_digest'],
            'qa_archive': archive['archive'], 'qa_archive_sha256': archive['sha256'],
            'baseline_pin': {key: pin[key] for key in (
                'baseline_commit', 'product_count', 'max_date', 'generation')},
            'gates': GATES,
            'synthetic': context['synthetic'], 'deployable': False,
            'scope': 'offline-v7-machine-validation-only',
            'not_established': [name for name in report['not_established']
                                if name != 'canonical-snapshot-runtime-qa'],
        }
        rc.typed('validation-results', result)
        out = root / 'qa-artifact'
        evidence = out / 'evidence'
        evidence.mkdir(parents=True)
        blob = rc.read_bytes(incoming / 'site-release.tar')
        rc.require(hashlib.sha256(blob).hexdigest() == archive['sha256'],
                   'validated archive changed before handoff')
        (out / 'site-release.tar').write_bytes(blob)
        for name in EVIDENCE_NAMES:
            (evidence / name).write_bytes(rc.read_bytes(incoming / 'work' / name))
        rc.write_json(evidence / 'validation-results.json', result)
        for name in rc.PROJECTION_FILES:
            path = incoming / 'work' / name
            if path.exists():
                (evidence / name).write_bytes(rc.read_bytes(path))
        evdir = incoming / 'work/projection-evidence'
        if evdir.exists():
            rc.copy_tree_bytes(evdir, evidence / 'projection-evidence')
        rc.require(not dest.exists() and not dest.is_symlink(), 'QA destination appeared')
        out.rename(dest)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact', required=True)
    parser.add_argument('--dest', required=True)
    parser.add_argument('--context', dest='context_path', required=True)
    parser.add_argument('--baseline-pin', required=True)
    parser.add_argument('--baseline-sha256', required=True)
    parser.add_argument('--relation-inputs', required=True)
    parser.add_argument('--tracker-root', required=True)
    print(json.dumps(validate_job(**vars(parser.parse_args())), indent=2))


if __name__ == '__main__':
    main()
