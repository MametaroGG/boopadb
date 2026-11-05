"""NEW Stage12 historical-only QA primitives. Not the missing v7 release contract.

Only the fixed historical source, public baseline and non-serving QA are
supported. No archive promotion, production freshness or release APIs exist.
The recovered validators are byte-identical and checked before each execution.
"""
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys
import types
import unicodedata

HERE = Path(__file__).resolve().parent
BASELINE_SHA256 = '26b1af17947886d0803fc9be62f0e72cbfc2932f7eae15c075709561dfc5a202'
GENERATOR_CODE_SHA256 = '6481fb71f8be2abac0c6b8a616116c723f1f347ebf6f7e1331b820743168868b'
VALIDATOR_INVENTORY_SHA256 = 'e3b8d87c570ab0ef13abddb8e24b37b75bc62776af3884499a51899547b01635'
PINNED_SELECTOR_SHA256 = '6ad80d4287951edb54af3e23d89a749d11484bbb4bb7803894ad36b7ad7ddcbb'
PINNED_HERO_SHA256 = '946f4226d75e00017404735bf295100ffd35dfafac78dd6cdea0652a07f85d68'
HISTORICAL_TRACKER_COMMIT = '672373654eb125fea74a25ff4f0319440e0d5f14'
HISTORICAL_DATE = '2026-11-05'
PREVIOUS_RELEASE = '39075ec499ca0a91c4f9f2ab2573c02e10cb5f32f2fee2733ad99f7adff2611c'
RELATION_KEYS = (
    'relations_bundle_manifest_sha256', 'relations_approval_sha256',
    'relation_search_bundle_manifest_sha256', 'relation_search_approval_sha256',
    'supplement_bundle_manifest_sha256', 'supplement_approval_sha256',
)
CONTEXT_KEYS = {'synthetic', 'tracker_commit', 'generator_commit', 'run_id',
    'run_attempt', 'generation', 'prev_release_digest', 'expected_date', 'inventory_digest'}
MAX_FILE_BYTES = 128 * 1024**2


def require(condition, message):
    if not condition:
        raise ValueError(message)


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False,
                      separators=(',', ':'), allow_nan=False).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _identity(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_nlink, st.st_size,
            st.st_mtime_ns, st.st_ctime_ns)


def _directory(path):
    """Open every ancestor without following links, independent of cwd races."""
    path = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in path.parts[1:]:
            new = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = new
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_bytes(path, limit=MAX_FILE_BYTES):
    path = Path(os.path.abspath(path))
    fd = _directory(path.parent)
    try:
        leaf = os.open(path.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(leaf, 'rb') as source:
            before = os.fstat(source.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                    0 <= before.st_size <= limit, 'Regular unshared bounded file required')
            raw = source.read(limit + 1)
            require(len(raw) == before.st_size and
                    _identity(before) == _identity(os.fstat(source.fileno())), 'File changed during read')
            return raw
    finally:
        os.close(fd)


def digest(path):
    return sha(read_bytes(path))


def strict(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, 'Duplicate JSON key')
            value[key] = item
        return value
    def invalid(_):
        raise ValueError('Nonfinite JSON refused')
    def finite(value):
        number = float(value)
        require(math.isfinite(number), 'Nonfinite JSON number refused')
        return number
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid, parse_float=finite)


def load_strict_json(path):
    return strict(read_bytes(path))


def write_json(path, value):
    raw = encode(value) + b'\n'
    path = Path(path)
    fd = _directory(path.parent)
    try:
        leaf = os.open(path.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=fd)
        with os.fdopen(leaf, 'wb') as out:
            out.write(raw)
    finally:
        os.close(fd)


def _path(name):
    require(type(name) is str and name and '\\' not in name and '\x00' not in name,
            'Canonical relative path required')
    p = PurePosixPath(name)
    require(not p.is_absolute() and '..' not in p.parts and '.git' not in p.parts
            and p.as_posix() == name and name not in ('.', ''), 'Unsafe path')
    require(not any(ord(c) < 32 or ord(c) == 127 for c in name), 'Control character in path')
    require(unicodedata.normalize('NFC', name) == name, 'Noncanonical Unicode path')
    return name


def _tree(root):
    root = Path(os.path.abspath(root))
    fd = _directory(root)
    os.close(fd)
    files, directories, seen = {}, [], set()
    for folder, dirs, names in os.walk(root, followlinks=False):
        for name in sorted(dirs + names):
            p = Path(folder) / name
            rel = _path(p.relative_to(root).as_posix())
            folded = unicodedata.normalize('NFC', rel).casefold()
            require(folded not in seen, 'Normalized/case path collision')
            seen.add(folded)
            mode = p.lstat().st_mode
            require(stat.S_ISREG(mode) or stat.S_ISDIR(mode), 'Nonregular tree member')
            if stat.S_ISDIR(mode):
                directories.append(rel)
            else:
                files[rel] = read_bytes(p)
    require(files, 'Nonempty tree required')
    require(all(any(n.startswith(d + '/') for n in files) for d in directories), 'Empty tree directory')
    return files


# Narrow compatibility for the recovered verifier, not a replacement old module.
base = types.SimpleNamespace(_tree=_tree, _path=_path)


def typed(kind, value):
    if kind == 'ledger':
        require(type(value) is dict and value, 'Nonempty ledger required')
        seen = set()
        for name, expected in value.items():
            _path(name)
            key = unicodedata.normalize('NFC', name).casefold()
            require(key not in seen and type(expected) is str and re.fullmatch('[a-f0-9]{64}', expected),
                    'Invalid or colliding ledger entry')
            seen.add(key)
    elif kind == 'baseline-pin':
        keys = {'schema', 'baseline_commit', 'baseline_prev_release_sentinel', 'evidence',
                'generation', 'index_html_blob', 'item_html_blob', 'max_date', 'product_count', 'relations_binding'}
        require(type(value) is dict and set(value) == keys and type(value['schema']) is int and
                value['schema'] == 1, 'Unknown historical baseline schema')
        require(sha(encode(value) + b'\n') == BASELINE_SHA256, 'Unrecognized historical baseline content')
    elif kind == 'evidence-records':
        require(type(value) is dict and set(value) == {'schema', 'records'} and
                type(value['schema']) is int and value['schema'] == 1 and
                type(value['records']) is list and len(value['records']) == 1, 'Unsupported evidence schema')
        rec = value['records'][0]
        fields = {'item_id', 'kind', 'corrected_url', 'proof_sha256', 'confirmed_at', 'applies_when'}
        require(type(rec) is dict and set(rec) == fields and rec['kind'] == 'verified_thumbnail' and
                rec['item_id'] == '2625416', 'Unsupported thumbnail evidence')
        require(type(rec['proof_sha256']) is str and re.fullmatch('[a-f0-9]{64}', rec['proof_sha256']) and
                type(rec['corrected_url']) is str and rec['corrected_url'].startswith('https://') and
                type(rec['applies_when']) is str and rec['applies_when'], 'Invalid thumbnail evidence')
        stamp = dt.datetime.fromisoformat(rec['confirmed_at'].replace('Z', '+00:00'))
        require(stamp.tzinfo is not None, 'Aware thumbnail timestamp required')
    else:
        raise ValueError('Unsupported historical contract kind: ' + str(kind))
    return value


def load_typed(kind, path):
    return typed(kind, load_strict_json(path))


def check_context(c):
    require(type(c) is dict and set(c) == CONTEXT_KEYS, 'Exact historical context required')
    require(c['synthetic'] is False and c['tracker_commit'] == HISTORICAL_TRACKER_COMMIT and
            c['expected_date'] == HISTORICAL_DATE and c['generation'] == 2 and type(c['generation']) is int and
            c['prev_release_digest'] == PREVIOUS_RELEASE, 'Different historical source/context refused')
    require(type(c['generator_commit']) is str and re.fullmatch('[a-f0-9]{40}', c['generator_commit']),
            'Workflow execution SHA required separately from generator code digest')
    require(type(c['inventory_digest']) is str and re.fullmatch('[a-f0-9]{64}', c['inventory_digest']),
            'Invalid actual source inventory digest')
    require(type(c['run_id']) is str and re.fullmatch('[1-9][0-9]*', c['run_id']) and c['run_attempt'] == '1',
            'Invalid historical trial execution identity')
    return c


def checked_context(path):
    return check_context(load_strict_json(path))


def inputs(context_path, baseline_pin, baseline_sha256, relation_inputs):
    c = checked_context(context_path)
    require(baseline_sha256 == BASELINE_SHA256 == digest(baseline_pin), 'Historical baseline byte commitment mismatch')
    pin = load_typed('baseline-pin', baseline_pin)
    relation_inputs = Path(relation_inputs).absolute()
    paths = load_strict_json(relation_inputs)
    require(type(paths) is dict and set(paths) == set(RELATION_KEYS), 'All six original relation inputs required')
    bindings = {}
    for key in RELATION_KEYS:
        name = _path(paths[key])
        bindings[key] = digest(relation_inputs.parent / name)
    require(bindings == pin['relations_binding'], 'Consumed relation inputs differ from baseline pin')
    return c, pin, bindings


def verify_generator(root):
    inventory = {name: sha(blob) for name, blob in _tree(root).items()}
    require(len(inventory) == 165 and sha(encode(inventory)) == GENERATOR_CODE_SHA256,
            'Frozen historical generator changed')
    return GENERATOR_CODE_SHA256


def verify_request_identity(request):
    """Call before any gate; request is already exact-byte bound by its caller."""
    keys = {'schema', 'workflow_execution_sha', 'generator_code_sha256', 'site', 'visibility_ledger',
            'source_dir', 'source_request', 'source_result', 'previous', 'context', 'context_path',
            'generation_config', 'generation_config_sha256', 'relation_inputs', 'baseline_pin',
            'baseline_sha256', 'reuse_policy', 'gate_work'}
    require(type(request) is dict and set(request) == keys and
            request['schema'] == 'boopa-stage12-historical-qa-request-v1',
            'Unknown or incomplete historical QA request schema')
    require(type(request['generation_config_sha256']) is str and
            re.fullmatch('[a-f0-9]{64}', request['generation_config_sha256']), 'Invalid configuration byte digest')
    for name in ('site', 'visibility_ledger', 'source_dir', 'context_path', 'generation_config',
                 'relation_inputs', 'baseline_pin', 'reuse_policy', 'gate_work'):
        require(type(request[name]) is str and request[name] and Path(request[name]).is_absolute(),
                'Absolute private QA input path required')
    require(all(type(request[name]) is dict for name in ('source_request', 'source_result', 'previous')),
            'Private source and predecessor records required')
    require(request['baseline_sha256'] == BASELINE_SHA256, 'Wrong historical request baseline')
    check_context(request['context'])
    require(request['workflow_execution_sha'] == request['context']['generator_commit'] and
            request['generator_code_sha256'] == GENERATOR_CODE_SHA256,
            'Execution SHA and fixed generator identity mismatch')
    require(checked_context(request['context_path']) == request['context'], 'Request/context file mismatch')


def evidence(pin, work):
    typed('baseline-pin', pin)
    work = Path(work)
    require(not any((work / name).exists() or (work / name).is_symlink() for name in
                    ('projection-package.json', 'projection-declaration.json', 'projection-evidence')),
            'Historical trial cannot apply price projection')
    return typed('evidence-records', {'schema': 1, 'records': [dict(
        pin['evidence']['thumbnail_correction_2625416'], kind='verified_thumbnail')]})


def verify_validators():
    require(digest(HERE / 'VALIDATOR-INVENTORY.json') == VALIDATOR_INVENTORY_SHA256,
            'Validator inventory commitment changed')
    expected = load_typed('ledger', HERE / 'VALIDATOR-INVENTORY.json')
    actual = {'validators/' + n: sha(b) for n, b in _tree(HERE / 'validators').items()}
    require(actual == expected, 'Recovered validator bytes or closure changed')
    return expected


def validate_executables(site):
    site = Path(site)
    require(digest(site / 'scripts/embed-hero.cjs') == PINNED_HERO_SHA256, 'Untrusted hero executable')
    text = read_bytes(site / 'index.html').decode('utf-8')
    matches = re.findall(r'// HERO_SELECTOR_START[^\n]*\n([\s\S]*?)// HERO_SELECTOR_END', text)
    require(len(matches) == 1 and sha(matches[0].encode()) == PINNED_SELECTOR_SHA256,
            'Untrusted or ambiguous hero selector')


def run_validator(name, *args):
    require(name in {'gate_ui.py', 'check_projection.py', 'validate_snapshot.py'}, 'Unsupported historical validator')
    verify_validators()
    if name == 'validate_snapshot.py':
        values = list(map(str, args))
        require(values.count('--root') == 1, 'Explicit snapshot root required')
        validate_executables(values[values.index('--root') + 1])
    env = {'PATH': os.environ.get('PATH', '/usr/local/bin:/usr/bin:/bin'),
           'LANG': 'C.UTF-8', 'PYTHONDONTWRITEBYTECODE': '1'}
    result = subprocess.run([sys.executable, '-B', str(HERE / 'validators' / name), *map(str, args)],
                            capture_output=True, text=True, env=env, timeout=180)
    require(result.returncode == 0, 'Historical validator failed: ' + name + '\n' + result.stdout + result.stderr)
    verify_validators()
    return result.stdout.strip()


def contract_gates(site, work, tracker_root, pin):
    site, work = Path(site), Path(work)
    actual = {name: sha(blob) for name, blob in _tree(site).items()}
    require(load_typed('ledger', work / 'hash-ledger.json') == actual, 'Site ledger does not match actual bytes')
    require(load_typed('evidence-records', work / 'evidence-records.json') == evidence(pin, work),
            'Thumbnail evidence differs from fixed baseline')
    want = pin['evidence']['thumbnail_correction_2625416']
    when = dt.datetime.fromisoformat(want['confirmed_at'].replace('Z', '+00:00'))
    require(when.tzinfo is not None and when <= dt.datetime.now(dt.timezone.utc), 'Future/naive thumbnail evidence')
    for name in ('index.html', 'item.html'):
        require(want['corrected_url'] in read_bytes(site / name).decode('utf-8'), 'Pinned thumbnail absent')
    run_validator('gate_ui.py', site)
    # Genuine unchanged all-route applied-signal scanner; no no-op substitute.
    run_validator('check_projection.py', '--gate', '--work-dir', work, '--site-dir', site,
                  '--raw-dir', Path(tracker_root) / 'data', '--evaluation-time', dt.datetime.now(dt.timezone.utc).isoformat())
    require({name: sha(blob) for name, blob in _tree(site).items()} == actual, 'Site changed across contract gates')
