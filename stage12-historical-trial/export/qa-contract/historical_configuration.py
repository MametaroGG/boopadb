"""NEW fixed-generator configuration gate for the exact historical trial only."""
from pathlib import Path
import historical_contract as h
import historical_reuse as reuse

CONFIG_FIELDS = {'relations_bundle', 'relations_approval', 'relation_search_bundle',
    'relation_search_approval', 'supplement_bundle', 'supplement_approval', 'daily_coverage_file',
    'daily_target_date', 'projection_work', 'projection_package_sha256', 'presentation_proof', 'presentation_sha256'}
RELATIONS = (
    ('relations_bundle', 'relations_approval', 'relations_bundle_manifest_sha256', 'relations_approval_sha256'),
    ('relation_search_bundle', 'relation_search_approval', 'relation_search_bundle_manifest_sha256', 'relation_search_approval_sha256'),
    ('supplement_bundle', 'supplement_approval', 'supplement_bundle_manifest_sha256', 'supplement_approval_sha256'),
)
BUNDLE_PATHS = ('bundles/relation-bundle', 'bundles/relation-search-bundle', 'bundles/relation-supplement-bundle')
PRESENTATION_SHA256 = 'e7b74233a4814b738f2d5de12b22004dfc5466c32bdafe53c6f9047c380acd19'
PRESENTATION_CANONICAL = '1d98251b5d5b3ffd9e038e13b2f440f18c111db703dcc698c4a8f29031df4517'


def canonical_digest(value):
    return h.sha(h.encode(value))


def manifest_inventory(manifest):
    h.require(type(manifest) is dict and manifest, 'Nonempty relation manifest required')
    if 'files' in manifest:
        h.require(set(manifest) <= {'schema', 'status', 'version', 'files', 'public_release_commit', 'sourceVersion'}
                  and type(manifest.get('schema')) is int and manifest['schema'] == 1,
                  'Unsupported relation manifest wrapper')
        inventory = manifest['files']
    else:
        inventory = manifest
    return h.typed('ledger', inventory)


def configuration(path, relation_inputs, context, reuse_policy=None, baseline_pin=None,
                  baseline_sha256=None, *, expected_sha256=None):
    """Verify actual configured bytes, never public summaries or claimed QA.

    expected_sha256 binds private materialized config bytes when supplied by the
    orchestration request. Its outer request hash remains a separate boundary.
    """
    h.require(reuse_policy is not None and baseline_pin is not None and baseline_sha256 is not None,
              'Pinned historical reuse inputs required')
    reuse.verify(reuse_policy, context, baseline_pin, baseline_sha256, relation_inputs)
    path = Path(path).absolute()
    raw = h.read_bytes(path)
    if expected_sha256 is not None:
        h.require(h.sha(raw) == expected_sha256, 'Generation configuration bytes changed')
    obj = h.strict(raw)
    h.require(type(obj) is dict and set(obj) == CONFIG_FIELDS, 'Exact complete generation configuration required')
    if set(context) != {'synthetic'}:
        h.check_context(context)
    h.require(context.get('synthetic') is False, 'Synthetic configuration is outside historical scope')
    h.require(all(obj[k] is None for k in ('daily_coverage_file', 'daily_target_date', 'projection_work',
                                           'projection_package_sha256')),
              'Historical trial forbids new daily completeness or price projection inputs')
    def resolve(value):
        h.require(type(value) is str and value, 'Configured input path required')
        p = Path(value)
        return p.absolute() if p.is_absolute() else (path.parent / p).absolute()
    resolved = dict(obj)
    for key in CONFIG_FIELDS - {'daily_target_date', 'projection_package_sha256', 'presentation_sha256'}:
        if obj[key] is not None:
            resolved[key] = resolve(obj[key])
    root = Path(relation_inputs).absolute().parent
    relations = h.load_strict_json(relation_inputs)
    for expected_bundle, (bundle_key, approval_key, manifest_key, approval_binding) in zip(BUNDLE_PATHS, RELATIONS):
        bundle, approval_path = resolved[bundle_key], resolved[approval_key]
        h.require(bundle is not None and approval_path is not None, 'All three actual relation bundles/approvals required')
        h.require(bundle.resolve() == (root / expected_bundle).resolve() and
                  approval_path.resolve() == (root / relations[approval_binding]).resolve(),
                  'Configured relation path differs from fixed historical input')
        approval = h.load_strict_json(approval_path)
        manifest = h.load_strict_json(root / relations[manifest_key])
        inventory = manifest_inventory(manifest)
        h.require(type(approval) is dict and type(approval.get('schema')) is int and approval['schema'] == 1 and
                  approval.get('status') == 'approved' and approval.get('activate') is True and
                  inventory == approval.get('files'), 'Relation approval/manifest disagreement')
        h.require({name: h.sha(blob) for name, blob in h.base._tree(bundle).items()} == inventory,
                  'Actual relation bundle differs from manifest or includes unlisted files')
    h.require(obj['presentation_proof'] is not None and obj['presentation_sha256'] == PRESENTATION_CANONICAL,
              'Fixed historical presentation proof and digest are mandatory')
    if obj['presentation_proof'] is not None:
        proof_raw = h.read_bytes(resolved['presentation_proof'])
        h.require(h.sha(proof_raw) == PRESENTATION_SHA256 and obj['presentation_sha256'] == PRESENTATION_CANONICAL and
                  canonical_digest(h.strict(proof_raw)) == PRESENTATION_CANONICAL,
                  'Fixed historical presentation proof changed')
    h.verify_generator(root.parent / 'low-storage/generator')
    # Recheck the complete public closure after the generation paths are read.
    reuse.verify(reuse_policy, context, baseline_pin, baseline_sha256, relation_inputs)
    h.require(h.read_bytes(path) == raw, 'Configuration changed during validation')
    return resolved
