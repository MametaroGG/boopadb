"""Actual validation-job gate tests, with no mocks or fake passed receipts."""
import json
from pathlib import Path
import re
import shutil
import unittest

import test_release_contract as fixtures
import validation_job


class ValidationJobTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.ReleaseContractTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_contract_only_fixture_does_not_claim_canonical_success(self):
        f = self.fixture
        f.prepare()
        out = f.root / 'qa'
        with self.assertRaises(Exception):
            validation_job.validate_job(f.artifact, out, **f.kwargs())
        self.assertFalse(out.exists())
        self.assertFalse((f.artifact / 'work/validation-results.json').exists())

    def test_actual_snapshot_gate_rejects_incomplete_site(self):
        f = self.fixture
        (f.site / 'scripts').mkdir()
        shutil.copyfile(fixtures.ROOT / 'tests/fixtures/embed-hero.cjs',
                        f.site / 'scripts/embed-hero.cjs')
        f.prepare()
        out = f.root / 'qa'
        with self.assertRaises(Exception) as caught:
            validation_job.validate_job(f.artifact, out, **f.kwargs())
        self.assertIn('validate_snapshot.py', str(caught.exception))
        self.assertFalse(out.exists())
        self.assertFalse((f.artifact / 'work/validation-results.json').exists())

    def test_rehashed_untrusted_hero_is_not_executed(self):
        f = self.fixture
        marker = f.root / 'must-not-exist'
        (f.site / 'scripts').mkdir()
        (f.site / 'scripts/embed-hero.cjs').write_text(
            "require('fs').writeFileSync(" + json.dumps(str(marker)) + ", 'executed');")
        f.prepare()  # regular site/hash ledger alone does not bless executable JS
        with self.assertRaisesRegex(Exception, 'untrusted hero executable'):
            validation_job.validate_job(f.artifact, f.root / 'qa', **f.kwargs())
        self.assertFalse(marker.exists())
        self.assertFalse((f.root / 'qa').exists())

    def test_rehashed_hero_selector_is_refused_before_runtime(self):
        f = self.fixture
        (f.site / 'scripts').mkdir()
        shutil.copyfile(fixtures.ROOT / 'tests/fixtures/embed-hero.cjs',
                        f.site / 'scripts/embed-hero.cjs')
        index = f.site / 'index.html'
        text = index.read_text()
        pattern = r'(// HERO_SELECTOR_START[^\n]*\n)'
        changed, count = re.subn(pattern,
                                 r"\1throw new Error('synthetic selector must never execute');\n",
                                 text, count=1)
        self.assertEqual(count, 1)
        index.write_text(changed)
        # Recomputed manifests are not executable authorization. prepare then
        # constructs a fresh matching ledger/archive around these altered bytes.
        f.snapshot['files'] = {
            path.relative_to(f.site).as_posix(): fixtures.sha(path)
            for path in f.site.rglob('*')
            if path.is_file() and path.name != 'snapshot-manifest.json'}
        fixtures.write(f.site / 'snapshot-manifest.json', f.snapshot)
        f.prepare()
        with self.assertRaisesRegex(Exception, '^untrusted hero selector:'):
            validation_job.validate_job(f.artifact, f.root / 'qa', **f.kwargs())
        self.assertFalse((f.root / 'qa').exists())
        self.assertFalse((f.artifact / 'work/validation-results.json').exists())


if __name__ == '__main__':
    unittest.main()
