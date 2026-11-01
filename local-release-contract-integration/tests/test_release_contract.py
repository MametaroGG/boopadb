"""Synthetic contract integration tests; never production approval/collection proof.

Unchanged v7 baseline HTML is copied solely to exercise the existing UI gate.
Small raw inputs, relation inputs, pin population and run context are explicitly
synthetic. Original evidence timestamps are never renewed.
"""
import copy
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


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + '\n')
    return path


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def canonical_sha(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(',', ':')).encode()).hexdigest()


class ReleaseContractTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.site = self.root / 'site'
        self.work = self.root / 'work'
        self.tracker = self.root / 'tracker'
        self.site.mkdir(); self.work.mkdir()
        self.date = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
        for page in ('index.html', 'item.html'):
            shutil.copyfile(ROOT / 'tests/fixtures' / page, self.site / page)
        self.raw = {
            'id': '100', 'name': 'SYNTHETIC contract fixture',
            'variation_keys': {'v1': 'KeyA', 'v2': 'KeyB'},
            'variations': {
                'KeyA': [{'date': '2026-10-29', 'price': 3000},
                         {'date': '2026-10-30', 'price': 2500}],
                'KeyB': [{'date': '2026-10-30', 'price': 6000}],
            },
        }
        write(self.tracker / 'data/100/100.json', self.raw)
        write(self.tracker / 'meta/100/100.json', {'fixture': True, 'date': self.date})
        self.inventory = {p.relative_to(self.tracker).as_posix(): sha(p)
                          for p in sorted(self.tracker.rglob('*.json'))}
        write(self.work / 'input-inventory.json', self.inventory)
        digest = sha(self.work / 'input-inventory.json')
        self.att = {
            'expected_date': self.date, 'tracker_commit': '1' * 40,
            'completion_scope': 'immutable-captured-snapshot-integrity',
            'inventory_digest': digest, 'inventory_count': len(self.inventory),
            'fixture': True,
        }
        write(self.work / 'attestation.json', self.att)
        write(self.work / 'prepared-input.json', self.att)
        write(self.work / 'input-inventory-summary.json', {
            'files': len(self.inventory), 'non_json_files': [],
            'inventory_digest': digest, 'inventory_count': len(self.inventory)})
        self.snapshot = {'schema': 1, 'fixture': True,
                         'validation': {'rows': 1, 'max_date': self.date}}
        write(self.site / 'snapshot-manifest.json', self.snapshot)
        self.pin = json.loads((ROOT / 'tests/fixtures/baseline_pin.json').read_text())
        self.pin.update(product_count=1, max_date='2026-10-30', synthetic=True)
        self.relations = {}
        self.pin['relations_binding'] = {}
        for field in ('relations_bundle_manifest_sha256', 'relations_approval_sha256',
                      'relation_search_bundle_manifest_sha256', 'relation_search_approval_sha256',
                      'supplement_bundle_manifest_sha256', 'supplement_approval_sha256'):
            relative = 'relations/' + field + '.json'
            path = write(self.root / relative, {'synthetic': True, 'purpose': field,
                                               'authority': 'NONE - TEST FIXTURE'})
            self.relations[field] = relative
            self.pin['relations_binding'][field] = sha(path)
        self.pin_path = write(self.root / 'pin.json', self.pin)
        self.relations_path = write(self.root / 'relation-inputs.json', self.relations)
        self.context = {
            'synthetic': True, 'tracker_commit': '1' * 40, 'generator_commit': '2' * 40,
            'run_id': '9990001', 'run_attempt': '1', 'generation': 2,
            'prev_release_digest': self.pin['baseline_prev_release_sentinel'],
            'expected_date': self.date, 'inventory_digest': digest,
        }
        self.context_path = write(self.root / 'context.json', self.context)
        self.artifact = self.root / 'artifact'

    def kwargs(self):
        return dict(context_path=self.context_path, baseline_pin=self.pin_path,
                    baseline_sha256=sha(self.pin_path), relation_inputs=self.relations_path,
                    tracker_root=self.tracker)

    def prepare(self):
        return rc.prepare(self.site, self.work, self.artifact, **self.kwargs())

    def validate(self):
        return rc.validate(self.artifact, self.root / 'checked-site', **self.kwargs())

    def test_synthetic_full_contract_roundtrip(self):
        original = {p.name: sha(p) for p in self.site.iterdir() if p.is_file()}
        self.prepare()
        self.validate()
        self.assertEqual(original, {p.name: sha(p) for p in self.site.iterdir() if p.is_file()})
        self.assertFalse((self.site / 'release-manifest.json').exists())
        run = json.loads((self.artifact / 'work/run-manifest.json').read_text())
        release = json.loads((self.root / 'checked-site/release-manifest.json').read_text())
        for field in ('run_id', 'tracker_commit', 'generator_commit', 'generation',
                      'prev_release_digest', 'inventory_digest'):
            self.assertEqual(run[field], self.context[field])
            self.assertEqual(release[field], self.context[field])
        self.assertEqual(run['relations_binding'], self.pin['relations_binding'])
        self.assertEqual(run['site_files'], len(json.loads(
            (self.artifact / 'work/hash-ledger.json').read_text())))
        records = json.loads((self.artifact / 'work/evidence-records.json').read_text())['records']
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]['confirmed_at'],
                         self.pin['evidence']['thumbnail_correction_2625416']['confirmed_at'])

    def test_missing_relation_approval_refused(self):
        (self.root / self.relations['relations_approval_sha256']).unlink()
        with self.assertRaises(Exception): self.prepare()
        self.assertFalse(self.artifact.exists())

    def test_real_pin_descriptive_relation_metadata_supported(self):
        self.pin['relations_binding']['source'] = 'Existing v7 descriptive provenance, not another hash field'
        write(self.pin_path, self.pin)
        self.prepare()
        self.validate()
        run = json.loads((self.artifact / 'work/run-manifest.json').read_text())
        self.assertEqual(run['relations_binding'], self.pin['relations_binding'])

    def test_altered_relation_approval_refused(self):
        write(self.root / self.relations['relations_approval_sha256'], {'synthetic': 'modified'})
        with self.assertRaises(Exception): self.prepare()

    def test_missing_relation_input_mapping_refused(self):
        self.relations.pop('relations_approval_sha256')
        write(self.relations_path, self.relations)
        with self.assertRaises(Exception): self.prepare()

    def test_external_pin_digest_mismatch_refused(self):
        kwargs = self.kwargs(); kwargs['baseline_sha256'] = '0' * 64
        with self.assertRaises(Exception):
            rc.prepare(self.site, self.work, self.artifact, **kwargs)

    def test_tracker_input_tamper_refused(self):
        write(self.tracker / 'data/100/100.json', {'modified': True})
        with self.assertRaises(Exception): self.prepare()

    def test_tracker_unlisted_file_refused(self):
        write(self.tracker / 'data/101/101.json', {'synthetic': True})
        with self.assertRaises(Exception): self.prepare()

    def test_external_context_commit_mismatch_refused(self):
        self.context['tracker_commit'] = '3' * 40
        write(self.context_path, self.context)
        with self.assertRaises(Exception): self.prepare()

    def test_context_generation_mismatch_on_validate_refused(self):
        self.prepare()
        self.context['generation'] = 3
        write(self.context_path, self.context)
        with self.assertRaises(Exception): self.validate()

    def test_archive_tamper_refused(self):
        self.prepare()
        archive = self.artifact / 'site-release.tar'
        archive.write_bytes(archive.read_bytes() + b'tampered')
        with self.assertRaises(Exception): self.validate()

    def test_unlisted_evidence_kind_refused(self):
        self.prepare()
        path = self.artifact / 'work/evidence-records.json'
        obj = json.loads(path.read_text())
        obj['records'].append({'item_id': '100', 'kind': 'unreviewed_other_kind'})
        write(path, obj)
        with self.assertRaises(Exception): self.validate()

    def test_thumbnail_confirmation_time_tamper_refused(self):
        self.prepare()
        path = self.artifact / 'work/evidence-records.json'
        obj = json.loads(path.read_text())
        obj['records'][0]['confirmed_at'] = dt.datetime.now(dt.timezone.utc).isoformat()
        write(path, obj)
        with self.assertRaises(Exception): self.validate()

    def test_undeclared_projection_on_other_route_refused(self):
        (self.site / 'sale.html').write_text('<script>window.CurrentPrices={};</script>')
        with self.assertRaises(Exception): self.prepare()

    def test_ui_gate_remains_mandatory(self):
        (self.site / 'index.html').write_text('<html>marker-only replacement</html>')
        with self.assertRaises(Exception): self.prepare()

    def test_production_context_refuses_fixture_inputs(self):
        self.context['synthetic'] = False
        write(self.context_path, self.context)
        with self.assertRaises(Exception): self.prepare()
        self.assertFalse(self.artifact.exists())

    def test_synthetic_context_requires_fixture_flags(self):
        self.att['fixture'] = False
        write(self.work / 'attestation.json', self.att)
        with self.assertRaises(Exception): self.prepare()

    def test_production_context_cannot_relabel_synthetic_pin(self):
        self.context['synthetic'] = False
        write(self.context_path, self.context)
        self.att['fixture'] = False
        write(self.work / 'attestation.json', self.att)
        write(self.work / 'prepared-input.json', self.att)
        self.snapshot['fixture'] = False
        write(self.site / 'snapshot-manifest.json', self.snapshot)
        with self.assertRaises(Exception): self.prepare()

    def test_cli_prepare_validate_roundtrip(self):
        common = ['--context', str(self.context_path), '--baseline-pin', str(self.pin_path),
                  '--baseline-sha256', sha(self.pin_path), '--relation-inputs', str(self.relations_path),
                  '--tracker-root', str(self.tracker)]
        command = [sys.executable, str(ROOT / 'release_contract.py')]
        prepared = subprocess.run(command + ['prepare', '--site', str(self.site), '--work', str(self.work),
                                  '--dest', str(self.artifact)] + common,
                                  capture_output=True, text=True)
        self.assertEqual(prepared.returncode, 0, prepared.stdout + prepared.stderr)
        checked = subprocess.run(command + ['validate', '--artifact', str(self.artifact),
                                 '--dest', str(self.root / 'checked-cli')] + common,
                                 capture_output=True, text=True)
        self.assertEqual(checked.returncode, 0, checked.stdout + checked.stderr)
        for output in (prepared.stdout, checked.stdout):
            report = json.loads(output)
            self.assertTrue(report['synthetic'])
            self.assertFalse(report['deployable'])
            self.assertIn('independent-review-authority', report['not_established'])

    def test_snapshot_date_mismatch_refused(self):
        self.snapshot['validation']['max_date'] = '2026-10-29'
        write(self.site / 'snapshot-manifest.json', self.snapshot)
        with self.assertRaises(Exception): self.prepare()

    def test_population_regression_refused(self):
        self.pin['product_count'] = 100
        write(self.pin_path, self.pin)
        with self.assertRaises(Exception): self.prepare()

    def test_destination_reuse_refused(self):
        self.prepare()
        with self.assertRaises(Exception): self.prepare()

    def install_projection(self, expired):
        artifact_bytes = b'SYNTHETIC official-dom-bytes-for-item-100'
        source_hash = hashlib.sha256(artifact_bytes).hexdigest()
        evdir = self.work / 'projection-evidence'; evdir.mkdir()
        (evdir / source_hash).write_bytes(artifact_bytes)
        package = {'schema': 1, 'records': {'100': {
            'raw_record_sha256': canonical_sha(self.raw),
            'snapshot': {'snapshot_id': '100-synthetic-official-1', 'item_id': '100',
                         'observed_at': '2026-10-31T00:00:00Z',
                         'current_variants_complete': True, 'source_content_sha256': source_hash,
                         'variants': [{'id': 'v1', 'name': 'A', 'price': 2500, 'active': True},
                                      {'id': 'v2', 'name': 'B', 'price': 6000, 'active': True}]},
            'evidence': [{'evidence_id': 'synthetic-ev1', 'item_id': '100', 'variant_id': 'v1',
                          'snapshot_id': '100-synthetic-official-1', 'price': 2500,
                          'kind': 'official_scoped_promotion', 'review_status': 'verified',
                          'source_content_sha256': source_hash,
                          'valid_from': '2026-10-31T00:00:00Z',
                          'valid_through': '2026-10-31T00:00:00Z',
                          'seller_declared_start': '2026-10-01T00:00:00+09:00',
                          'seller_declared_end': '2026-11-30T00:00:00+09:00',
                          'regular_price': 5000}],
            'legacy_variant_id': 'v2', 'expires_at': '2026-10-31T12:00:00Z',
        }}}
        if not expired:
            # This is newly created artificial test data, NOT renewed historical
            # or official evidence. Runtime UTC is used solely to cover transport.
            now = dt.datetime.now(dt.timezone.utc)
            observed = (now - dt.timedelta(minutes=1)).isoformat()
            expires = (now + dt.timedelta(hours=1)).isoformat()
            rec = package['records']['100']
            rec['snapshot']['observed_at'] = observed
            rec['expires_at'] = expires
            rec['evidence'][0]['valid_from'] = observed
            rec['evidence'][0]['valid_through'] = observed
            rec['evidence'][0]['seller_declared_start'] = observed
            rec['evidence'][0]['seller_declared_end'] = expires
        write(self.work / 'projection-package.json', package)
        payload = {'schema': 1, 'entries': {'100': {'cur': 2500}}}
        if not expired:
            import check_projection
            selector = check_projection.load_selector(
                ROOT / 'validators/selected_price_selector.py', check_projection.PINNED_SELECTOR_SHA256)
            entries, _ = check_projection.verify_package(
                package, canonical_sha(package), dt.datetime.now(dt.timezone.utc),
                self.tracker / 'data', evdir, selector)
            payload['entries'] = entries
        write(self.site / 'current-price-projection.json', payload)
        write(self.work / 'projection-declaration.json', {
            'applied': True, 'package_sha256': canonical_sha(package),
            'as_of': '2026-10-31T06:00:00Z' if expired else dt.datetime.now(dt.timezone.utc).isoformat(),
            'payload_sha256': canonical_sha(payload), 'applied_items': ['100']})
        for page in ('index.html', 'item.html'):
            p = self.site / page
            p.write_text(p.read_text() + '<script>window.CurrentPrices=createCurrentPriceProjection('
                         + json.dumps(payload, separators=(',', ':')) + ');</script>')

    def test_current_synthetic_projection_full_contract_roundtrip(self):
        self.install_projection(expired=False)
        before = sha(self.work / 'projection-package.json')
        self.prepare()
        self.validate()
        self.assertEqual(before, sha(self.artifact / 'work/projection-package.json'))
        self.assertEqual(sha(self.site / 'current-price-projection.json'),
                         sha(self.root / 'checked-site/current-price-projection.json'))

    def test_projection_artifact_byte_tamper_on_validate_refused(self):
        self.install_projection(expired=False)
        self.prepare()
        path = next((self.artifact / 'work/projection-evidence').iterdir())
        path.write_bytes(path.read_bytes() + b'TAMPERED')
        with self.assertRaises(Exception): self.validate()

    def test_review_only_evidence_envelope_refused(self):
        self.install_projection(expired=False)
        path = self.work / 'projection-package.json'
        package = json.loads(path.read_text())
        write(path, {'package': package, 'authority_verified': False,
                     'artifact_stage': 'untrusted-review-only', 'deployable': False})
        with self.assertRaises(Exception): self.prepare()
        self.assertFalse(self.artifact.exists())

    def test_expired_projection_unchanged_times_refused(self):
        self.install_projection(expired=True)
        before = sha(self.work / 'projection-package.json')
        with self.assertRaises(Exception) as exc: self.prepare()
        self.assertRegex(str(exc.exception), '(?i)(stale|expired)')
        self.assertEqual(before, sha(self.work / 'projection-package.json'))
        self.assertFalse(self.artifact.exists())


if __name__ == '__main__':
    unittest.main()
