"""Actual canonical CLI generation + full v7 machine validation, synthetic only."""
import datetime as dt
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import release_contract as rc
import run_candidate


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.tracker = self.root / 'tracker'
        shutil.copytree(ROOT / 'tests/fixtures/tracker', self.tracker)
        # Create fresh synthetic history dates in a NEW tree, not renewed real
        # evidence; no price evidence package is used in this baseline case.
        today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
        records = []
        for path in (self.tracker / 'data').rglob('*.json'):
            record = rc.load_strict_json(path)
            for series in record.get('variations', {}).values():
                records.extend(dt.date.fromisoformat(row['date']) for row in series)
        shift = today - max(records)
        for path in (self.tracker / 'data').rglob('*.json'):
            record = rc.load_strict_json(path)
            for series in record.get('variations', {}).values():
                for row in series:
                    row['date'] = (dt.date.fromisoformat(row['date']) + shift).isoformat()
            rc.write_json(path, record)
        run_candidate.verify_generator()
        subprocess.run([sys.executable, str(ROOT / 'generator/inventory_snapshot.py'),
                        '--tracker-root', str(self.tracker), '--output', str(self.root / 'expected-inventory.json')], check=True, capture_output=True)
        self.relation_inputs = {}
        self.config = {key: None for key in run_candidate.CONFIG_FIELDS}
        self.pin = rc.load_strict_json(ROOT / 'tests/fixtures/baseline_pin.json')
        self.pin.update(synthetic=True, product_count=4, max_date='2026-10-30')
        self.pin['relations_binding'] = {'source': 'SYNTHETIC test inputs; no publication authority'}
        stems = ('relation', 'relation-search', 'relation-supplement')
        for stem, (bundle_key, approval_key, manifest_key, binding_key) in zip(stems, run_candidate.RELATIONS):
            manifest = ROOT / 'generator' / (stem + '-bundle-inventory.json')
            approval = rc.load_strict_json(manifest)
            approval.update(status='approved', activate=True, scope='local-test-only', synthetic=True)
            approval_path = self.root / (stem + '-test-approval.json')
            rc.write_json(approval_path, approval)
            self.config[bundle_key] = str(ROOT / 'generator' / (stem + '-bundle'))
            self.config[approval_key] = str(approval_path)
            self.relation_inputs[manifest_key] = str(manifest)
            self.relation_inputs[binding_key] = str(approval_path)
            self.pin['relations_binding'][manifest_key] = rc.digest(manifest)
            self.pin['relations_binding'][binding_key] = rc.digest(approval_path)
        self.context = dict(synthetic=True, tracker_commit='1'*40, generator_commit='2'*40,
                            run_id='9999991', run_attempt='1', generation=2,
                            prev_release_digest=self.pin['baseline_prev_release_sentinel'],
                            expected_date=today.isoformat(), inventory_digest=rc.digest(self.root / 'expected-inventory.json'))
        self.context_path = self.root / 'context.json'; rc.write_json(self.context_path, self.context)
        self.pin_path = self.root / 'pin.json'; rc.write_json(self.pin_path, self.pin)
        self.relations_path = self.root / 'relations.json'; rc.write_json(self.relations_path, self.relation_inputs)
        self.config_path = self.root / 'generation.json'; rc.write_json(self.config_path, self.config)

    def kwargs(self):
        return dict(context_path=self.context_path, baseline_pin=self.pin_path,
                    baseline_sha256=rc.digest(self.pin_path), relation_inputs=self.relations_path,
                    tracker_root=self.tracker, generation_config=self.config_path)

    def test_actual_generator_to_qa_artifact(self):
        dest = self.root / 'run'
        result = run_candidate.run(dest, **self.kwargs())
        self.assertEqual(result['status'], 'passed')
        self.assertTrue(result['synthetic'])
        self.assertFalse(result['deployable'])
        self.assertEqual(rc.digest(dest / 'build-artifact/site-release.tar'), rc.digest(dest / 'qa-artifact/site-release.tar'))
        self.assertTrue((dest / 'qa-artifact/evidence/validation-results.json').is_file())
        self.assertFalse((dest / 'qa-artifact/evidence/qa-review-record.json').exists())
        self.assertFalse((dest / 'FAILED.txt').exists())
        self.assertEqual(len(rc.load_strict_json(dest / 'commands.json')), 4)
        snap = rc.load_strict_json(dest / 'site/snapshot-manifest.json')
        for feature in ('relations', 'relation_search', 'relation_supplement'):
            self.assertEqual(snap[feature]['status'], 'approved-bundle')
            self.assertEqual(snap[feature]['scope'], 'local-test-only')

    def test_production_rejects_local_test_approvals(self):
        self.context['synthetic'] = False; rc.write_json(self.context_path, self.context)
        self.pin.pop('synthetic'); rc.write_json(self.pin_path, self.pin)
        dest = self.root / 'must-not-run'
        with self.assertRaisesRegex(ValueError, 'local/synthetic relation approval'):
            run_candidate.run(dest, **self.kwargs())
        self.assertFalse(dest.exists())

    def test_generation_actual_approval_must_match_contract(self):
        other = self.root / 'other-approval.json'
        shutil.copyfile(self.config['relations_approval'], other)
        self.config['relations_approval'] = str(other); rc.write_json(self.config_path, self.config)
        with self.assertRaisesRegex(ValueError, 'generator approval differs'):
            run_candidate.run(self.root / 'must-not-run', **self.kwargs())

if __name__ == '__main__': unittest.main()
