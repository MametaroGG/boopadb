"""NEW exact public-input projection verifier for a non-serving historical trial.

This does not verify authorship, replace the unavailable e121 authorization, or
create execution/publication permission. The private source grant and baseline
are reviewed locally by design/verify_private_provenance.py, never transported.
"""
from pathlib import Path
import historical_contract as h

BINDING_SHA256 = '81c454f9d7afe9ff791efa1408b12d0c790f1a02b06f877df3376732b0bb7e2f'
BINDING_KEYS = {'baseline_projection', 'baseline_sha256', 'execution_permission', 'files_sha256',
    'generator_projection', 'grant_sha256', 'implementation_inventory_sha256', 'original_authorization_sha256',
    'package_inventory_sha256', 'publication_permission', 'relations_binding', 'repository',
    'runtime_map_sha256', 'schema', 'scope', 'source_reference', 'synthetic'}


def verify(path, context, baseline_path, baseline_sha256, relation_inputs):
    path = Path(path).absolute()
    policy_raw = h.read_bytes(path)
    policy = h.strict(policy_raw)
    h.require(type(policy) is dict and set(policy) == {'schema', 'binding_path', 'binding_sha256'} and
              policy['schema'] == 'boopa-public-reuse-policy-v4' and policy['binding_path'] == 'binding.json' and
              policy['binding_sha256'] == BINDING_SHA256, 'Unknown or changed public reuse policy')
    root = path.parent
    binding_path = root / 'binding.json'
    h.require(h.digest(binding_path) == BINDING_SHA256, 'Public reuse binding bytes changed')
    binding = h.load_strict_json(binding_path)
    h.require(type(binding) is dict and set(binding) == BINDING_KEYS and
              binding['schema'] == 'boopa-public-reuse-binding-v4' and
              binding['scope'] == 'unchanged-three-historical-relations-reuse' and
              binding['repository'] == 'MametaroGG/boopadb' and binding['synthetic'] is False and
              binding['execution_permission'] is False and binding['publication_permission'] is False,
              'Historical reuse scope or permission flags changed')
    h.require(type(context) is dict and context.get('synthetic') is False, 'Real historical context required')
    h.require(baseline_sha256 == h.BASELINE_SHA256 == binding['baseline_sha256'] == h.digest(baseline_path),
              'Historical baseline commitment changed')
    h.require(Path(baseline_path).resolve() == (root / 'baseline_pin.json').resolve() and
              Path(relation_inputs).resolve() == (root / 'relation-inputs.json').resolve(),
              'Different baseline or relation input namespace')
    expected = binding['files_sha256']
    h.typed('ledger', expected)
    h.require(len(expected) == 97 and 'policy.json' not in expected and 'binding.json' not in expected,
              'Unknown public input closure')
    actual = {n: h.sha(b) for n, b in h.base._tree(root).items()}
    h.require(actual == {**expected, 'policy.json': h.sha(policy_raw), 'binding.json': BINDING_SHA256},
              'Public input bytes/closure changed')
    # Policy itself is fixed bytes, not just semantically equivalent JSON.
    h.require(policy_raw == ("{\n  \"binding_path\": \"binding.json\",\n  \"binding_sha256\": \"" + BINDING_SHA256 +
              "\",\n  \"schema\": \"boopa-public-reuse-policy-v4\"\n}\n").encode(), 'Public policy bytes changed')
    pin = h.load_typed('baseline-pin', baseline_path)
    relations = h.load_strict_json(relation_inputs)
    h.require(type(relations) is dict and set(relations) == set(h.RELATION_KEYS), 'Six relation input paths required')
    actual_relations = {k: h.digest(root / h.base._path(relations[k])) for k in h.RELATION_KEYS}
    h.require(actual_relations == binding['relations_binding'] == pin['relations_binding'],
              'Actual relation bytes differ from baseline and reuse binding')
    return {'schema': 'boopa-stage12-historical-inputs-verified-v1',
            'policy_sha256': h.sha(policy_raw), 'binding_sha256': BINDING_SHA256,
            'baseline_sha256': baseline_sha256, 'grant_sha256': binding['grant_sha256'],
            'original_authorization_sha256': binding['original_authorization_sha256'],
            'original_authorization_verified': False, 'private_grant_authorship_verified': False,
            'input_files': len(actual), 'relations_binding': actual_relations,
            'execution_permission': False, 'publication_permission': False,
            'production_eligible': False, 'historical_only': True}
