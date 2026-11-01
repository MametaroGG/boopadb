"""R2: canonical flat inventory compatibility, without authority or byte changes."""
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import release_contract as rc
import run_candidate
import test_pipeline


class ManifestShapeTests(unittest.TestCase):
    def test_flat_exact_mapping(self):
        obj = {'sub/a.js': 'a' * 64, 'b.json': 'b' * 64}
        self.assertIs(run_candidate.manifest_inventory(obj), obj)

    def test_wrapped_exact_mapping(self):
        files = {'sub/a.js': 'a' * 64}
        obj = dict(schema=1, status='existing-pinned-status', version='original',
                   files=files, public_release_commit='c' * 40, sourceVersion='original-source')
        self.assertIs(run_candidate.manifest_inventory(obj), files)
        self.assertEqual(obj['status'], 'existing-pinned-status')

    def test_invalid_or_ambiguous_shapes_rejected(self):
        cases = [None, [], {}, {'files': {}}, {'files': 'a' * 64},
                 {'files': {'a.js': 'a' * 64}, 'outside.js': 'b' * 64},
                 {'schema': 1, 'a.js': 'a' * 64},
                 {'files': {'a.js': 'a' * 64}, 'nested': {'files': {'b.js': 'b' * 64}}}]
        for value in cases:
            with self.subTest(value=value):
                with self.assertRaises(Exception):
                    run_candidate.manifest_inventory(value)

    def test_invalid_hashes_rejected_flat_and_wrapped(self):
        for sha in ('x' * 64, 'a' * 63, 'A' * 64, None, 1, True, {}, []):
            for wrap in (False, True):
                value = {'a.js': sha}
                if wrap: value = {'files': value}
                with self.subTest(sha=sha, wrapped=wrap):
                    with self.assertRaises(Exception): run_candidate.manifest_inventory(value)

    def test_invalid_paths_rejected_flat_and_wrapped(self):
        for name in ('', '/absolute', '../outside', 'a/../outside', 'a\\b', 'a//b', './a', '.git/config'):
            for wrap in (False, True):
                value = {name: 'a' * 64}
                if wrap: value = {'files': value}
                with self.subTest(path=name, wrapped=wrap):
                    with self.assertRaises(Exception): run_candidate.manifest_inventory(value)

    def test_normalization_collision_rejected(self):
        with self.assertRaises(Exception):
            run_candidate.manifest_inventory({'A.js': 'a' * 64, 'a.js': 'b' * 64})


class CanonicalManifestConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_pipeline.PipelineTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.flat_paths = []
        for _, _, manifest_key, _ in run_candidate.RELATIONS:
            wrapped_path = Path(self.fixture.relation_inputs[manifest_key])
            original = rc.load_strict_json(wrapped_path)
            path = self.fixture.root / (manifest_key + '-flat.json')
            rc.write_json(path, original['files'])
            self.fixture.relation_inputs[manifest_key] = str(path)
            self.fixture.pin['relations_binding'][manifest_key] = rc.digest(path)
            self.flat_paths.append(path)
        self.flush()

    def flush(self):
        f = self.fixture
        rc.write_json(f.relations_path, f.relation_inputs)
        rc.write_json(f.pin_path, f.pin)
        rc.write_json(f.config_path, f.config)
        rc.write_json(f.context_path, f.context)

    def configure(self):
        f = self.fixture
        # Match the real runner: exact original-byte baseline binding still runs
        # before the new flat/wrapped parser. No digest is recomputed as an alias.
        rc.inputs(f.context_path, f.pin_path, rc.digest(f.pin_path), f.relations_path)
        return run_candidate.configuration(f.config_path, f.relations_path, f.context)

    def test_flat_maps_match_75_10_4_canonical_approval_inventories(self):
        self.assertEqual([len(rc.load_strict_json(p)) for p in self.flat_paths], [75, 10, 4])
        self.configure()

    def test_raw_manifest_and_approval_bytes_preserved(self):
        paths = self.flat_paths + [Path(self.fixture.config[a]) for _, a, _, _ in run_candidate.RELATIONS]
        before = {str(p): p.read_bytes() for p in paths}
        self.configure()
        self.assertEqual(before, {str(p): p.read_bytes() for p in paths})
        for path, (_, _, manifest_key, _) in zip(self.flat_paths, run_candidate.RELATIONS):
            self.assertEqual(rc.digest(path), self.fixture.pin['relations_binding'][manifest_key])

    def test_actual_end_to_end_flat_generation_and_validation(self):
        f = self.fixture
        result = run_candidate.run(f.root / 'flat-run', **f.kwargs())
        self.assertEqual(result['status'], 'passed')
        self.assertTrue(result['synthetic'])
        self.assertFalse(result['deployable'])
        self.assertEqual(rc.digest(f.root / 'flat-run/build-artifact/site-release.tar'),
                         rc.digest(f.root / 'flat-run/qa-artifact/site-release.tar'))

    def test_manifest_approval_map_mismatch_refused(self):
        path = self.flat_paths[0]
        files = rc.load_strict_json(path); files[next(iter(files))] = '0' * 64
        rc.write_json(path, files)
        self.fixture.pin['relations_binding'][run_candidate.RELATIONS[0][2]] = rc.digest(path)
        self.flush()
        with self.assertRaisesRegex(ValueError, 'manifest and approval inventories differ'): self.configure()

    def test_matching_wrong_hash_still_refuses_actual_bundle_bytes(self):
        f = self.fixture
        path = self.flat_paths[0]
        files = rc.load_strict_json(path); files[next(iter(files))] = '0' * 64
        rc.write_json(path, files)
        _, approval_key, manifest_key, binding_key = run_candidate.RELATIONS[0]
        approval_path = Path(f.config[approval_key])
        approval = rc.load_strict_json(approval_path); approval['files'] = files
        rc.write_json(approval_path, approval)
        f.pin['relations_binding'][manifest_key] = rc.digest(path)
        f.pin['relations_binding'][binding_key] = rc.digest(approval_path)
        self.flush()
        with self.assertRaisesRegex(ValueError, 'actual bundle bytes differ'): self.configure()

    def test_invalid_flat_path_refused_even_with_matching_approval(self):
        f = self.fixture
        files = {'../outside': 'a' * 64}
        path = self.flat_paths[0]; rc.write_json(path, files)
        _, approval_key, manifest_key, binding_key = run_candidate.RELATIONS[0]
        approval_path = Path(f.config[approval_key])
        approval = rc.load_strict_json(approval_path); approval['files'] = files
        rc.write_json(approval_path, approval)
        f.pin['relations_binding'][manifest_key] = rc.digest(path)
        f.pin['relations_binding'][binding_key] = rc.digest(approval_path)
        self.flush()
        with self.assertRaises(Exception): self.configure()

    def test_original_byte_pin_still_rejects_changed_manifest(self):
        self.flat_paths[0].write_bytes(self.flat_paths[0].read_bytes() + b' ')
        with self.assertRaisesRegex(ValueError, 'actual consumed relation inputs differ'): self.configure()

    def test_flat_production_still_rejects_local_test_only_approvals(self):
        f = self.fixture
        f.context['synthetic'] = False
        f.pin.pop('synthetic')
        self.flush()
        with self.assertRaisesRegex(ValueError, 'local/synthetic relation approval'): self.configure()

    def test_daily_null_pair_still_omits_optional_receipt(self):
        result = self.configure()
        self.assertIsNone(result['daily_coverage_file'])
        self.assertIsNone(result['daily_target_date'])

if __name__ == '__main__': unittest.main()
