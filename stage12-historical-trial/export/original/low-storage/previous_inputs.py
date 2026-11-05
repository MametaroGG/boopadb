"""Fixed legacy predecessor verification with explicit GET-only or local reads.

No credentials, implicit network, publication authority, or original completion
manifest is created. Compact evidence is only a receipt: every consumer must
replay the fixed archive and public ledger independently. A supplied receipt is
never an input authority. The full-tree mode is an explicit compatibility path.
"""
import argparse
from contextlib import contextmanager
import hashlib
import gzip
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tarfile
import unicodedata
import urllib.error
import urllib.request

HERE = Path(__file__).resolve().parent
ASSETS = HERE / 'previous-assets'
DESCRIPTOR_SHA256 = '80044930b7641b6262eea96ec7f42605ea947ca289a7b9763c731a48e7cf7b77'
LIVE = 'https://mametarogg.github.io/boopadb/'
TRACKER = 'https://codeload.github.com/MametaroGG/booth-vrc-price-tracker/tar.gz/'
MAX_FILE = 64 * 1024 ** 2
MAX_SITE = 1024 ** 3
MAX_ARCHIVE = 1024 ** 3
MAX_UNPACKED = 8 * 1024 ** 3
MAX_ENTRIES = 500000


def need(ok, reason):
    if not ok:
        raise ValueError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            need(key not in out, 'Duplicate JSON key')
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs,
                      parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Nonfinite JSON')))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True,
                      allow_nan=False).encode()


def safe_name(name):
    need(isinstance(name, str) and name and '\\' not in name and
         all(ord(c) >= 32 and ord(c) != 127 for c in name), 'Unsafe path')
    need(len(name.encode('utf-8')) <= 1024, 'Path byte budget exceeded')
    p = PurePosixPath(name)
    need(not p.is_absolute() and p.as_posix() == name and
         all(x not in ('', '.', '..') for x in name.split('/')), 'Noncanonical path')
    return p


@contextmanager
def regular_open(path):
    """Open by no-follow directory FDs; the returned FD is the consumed source.

    File replacement cannot redirect subsequent reads. In-place byte changes are
    caught by the digest of the bytes actually consumed, not a prior pathname hash.
    """
    absolute = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:-1]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        leaf = os.open(absolute.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        try:
            need(stat.S_ISREG(os.fstat(leaf).st_mode), 'Regular input required')
            with os.fdopen(leaf, 'rb') as stream:
                leaf = None
                yield stream
        finally:
            if leaf is not None:
                os.close(leaf)
    finally:
        os.close(fd)


def read_regular(path, limit):
    with regular_open(path) as stream:
        raw = stream.read(limit + 1)
    need(len(raw) <= limit, 'Local file too large')
    return raw


def open_directory(path):
    """Return a held no-follow directory FD; caller owns it."""
    absolute = Path(os.path.abspath(path))
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
    try:
        for part in absolute.parts[1:]:
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        return fd
    except Exception:
        os.close(fd)
        raise


def write_beneath(root_fd, name, raw):
    """Write a new regular file under held directory FDs, never follow links."""
    parts = safe_name(name).parts
    fd = os.dup(root_fd)
    try:
        for part in parts[:-1]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            nxt = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd)
            fd = nxt
        output = os.open(parts[-1], os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                         0o600, dir_fd=fd)
        with os.fdopen(output, 'wb') as stream:
            stream.write(raw)
    finally:
        os.close(fd)


def assets():
    raw = read_regular(ASSETS / 'descriptor.json', 65536)
    need(sha(raw) == DESCRIPTOR_SHA256, 'Fixed predecessor descriptor changed')
    descriptor = strict_json(raw)
    raw = read_regular(ASSETS / 'site-ledger.json', 2 ** 20)
    need(sha(raw) == descriptor['site_ledger_sha256'], 'Fixed public ledger changed')
    ledger = strict_json(raw)
    need(isinstance(ledger, dict) and 24 < len(ledger) < 8192, 'Invalid public ledger')
    for name, digest in ledger.items():
        safe_name(name)
        need(re.fullmatch('[a-f0-9]{64}', digest) is not None, 'Invalid public digest')
    return descriptor, ledger


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class PublicGET:
    """Bounded, credential-free GETs to exact fixed archive and ledger URLs.

    Construction is explicit. No cookies, proxies, netrc, authorization headers,
    redirect following, environment discovery, upload, or mutation operation.
    """
    def __init__(self):
        descriptor, ledger = assets()
        self.allowed = {LIVE + name for name in ledger} | {LIVE + 'release-manifest.json'}
        self.archive_url = TRACKER + descriptor['tracker_commit']
        self.allowed.add(self.archive_url)
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

    @contextmanager
    def open(self, url):
        need(url in self.allowed, 'Public GET URL refused')
        request = urllib.request.Request(url, method='GET', headers={
            'Accept-Encoding': 'identity', 'Cache-Control': 'no-cache',
            'User-Agent': 'boopadb-previous-read'})
        try:
            response = self.opener.open(request, timeout=30)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            need(response.geturl() == url, 'Implicit redirect refused')
            headers = list(response.headers.items())
            need(len({k.lower() for k, _ in headers}) == len(headers), 'Duplicate response header')
            limit = MAX_ARCHIVE if url == self.archive_url else MAX_FILE
            for key, value in headers:
                if key.lower() == 'content-length':
                    need(value.isdigit() and int(value) <= limit, 'Oversized declared body')
                if key.lower() == 'content-encoding':
                    need(value.lower() == 'identity', 'HTTP content encoding refused')
            need(response.status not in range(300, 400), 'Public redirect refused')
            yield response.status, response


class LocalFixture:
    """Explicit read-only local archive/site replay. Never falls back to network.

    The legacy-absence marker is caller-declared fixture context, not fresh HTTP
    evidence. Output remains validation-only and cannot claim live selection.
    """
    validation_only = True

    def __init__(self, archive, site, *, legacy_absent):
        need(legacy_absent is True, 'Explicit legacy fixture context required')
        self.archive = Path(archive)
        self.site = Path(site)
        descriptor, self.ledger = assets()
        self.archive_url = TRACKER + descriptor['tracker_commit']
        need(not (self.site / 'release-manifest.json').exists() and
             not (self.site / 'release-manifest.json').is_symlink(), 'Unexpected modern fixture sentinel')
        # Complete exact file set, including extra files/links. Content is checked
        # on the FD which is actually consumed below, not trusted from this walk.
        actual = set()
        need(self.site.is_dir() and not self.site.is_symlink(), 'Invalid site fixture root')
        expected_dirs = {str(parent) for name in self.ledger
                         for parent in PurePosixPath(name).parents if str(parent) != '.'}
        for path in self.site.rglob('*'):
            need(not path.is_symlink(), 'Linked site fixture')
            relative = path.relative_to(self.site).as_posix()
            if path.is_dir():
                need(relative in expected_dirs, 'Extra site fixture directory')
            else:
                need(path.is_file(), 'Nonregular site fixture')
                actual.add(relative)
        need(actual == set(self.ledger), 'Site fixture file set differs')

    @contextmanager
    def open(self, url):
        if url == LIVE + 'release-manifest.json':
            need(not (self.site / 'release-manifest.json').exists() and
                 not (self.site / 'release-manifest.json').is_symlink(), 'Modern fixture appeared')
            yield 404, io.BytesIO(b'')
        elif url == self.archive_url:
            with regular_open(self.archive) as stream:
                yield 200, stream
        else:
            need(url.startswith(LIVE) and url[len(LIVE):] in self.ledger, 'Fixture URL refused')
            with regular_open(self.site / url[len(LIVE):]) as stream:
                yield 200, stream


class HashReader:
    def __init__(self, raw, limit):
        self.raw, self.limit = raw, limit
        self.digest, self.size = hashlib.sha256(), 0

    def read(self, size=-1):
        need(type(size) is int and size >= 0, 'Unbounded archive read refused')
        chunk = self.raw.read(min(size, self.limit - self.size + 1))
        need(isinstance(chunk, bytes), 'Binary stream required')
        self.size += len(chunk)
        need(self.size <= self.limit, 'Compressed archive byte budget exceeded')
        self.digest.update(chunk)
        return chunk


def load_pure_module(name, path, expected, imports=None):
    """Execute only the pinned bytes just read, without an unchecked second read."""
    raw = read_regular(path, 2 ** 20)
    need(sha(raw) == expected, 'Reviewed helper changed')
    import types
    module = types.ModuleType(name)
    module.__file__ = str(path)
    if imports:
        import builtins
        def importing(name, globals=None, locals=None, fromlist=(), level=0):
            if name in imports and level == 0:
                return imports[name]
            return builtins.__import__(name, globals, locals, fromlist, level)
        module.__dict__['__builtins__'] = dict(vars(builtins), __import__=importing)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def record_checks(descriptor):
    return load_pure_module('previous_record_contract', HERE / 'previous_record_contract.py',
                            descriptor['record_contract_sha256'])


def chart_helpers(descriptor):
    # Resolve the helper's imports to pinned in-memory bytes without mutating
    # process-global sys.modules or reopening an unchecked module pathname.
    varutil = load_pure_module('legacy_varutil', ASSETS / 'varutil.py', descriptor['helper_sha256']['varutil.py'])
    return load_pure_module('legacy_charts', ASSETS / 'charts_contract.py',
                            descriptor['helper_sha256']['charts_contract.py'], {'varutil': varutil})


class MemoryPath:
    """Minimal immutable path facade for the three selected chart source records."""
    def __init__(self, files, name=''):
        self.files, self.name = files, name

    def __truediv__(self, part):
        return MemoryPath(self.files, self.name + ('/' if self.name else '') + str(part))

    def glob(self, pattern):
        need(self.name == 'data' and pattern == '*/*.json', 'Unexpected chart access')
        return (MemoryPath(self.files, name) for name in sorted(self.files))

    def is_file(self):
        return self.name in self.files

    def read_text(self):
        return self.files[self.name].decode('utf-8')


def build_charts(winners, descriptor):
    charts = chart_helpers(descriptor)
    source = MemoryPath({name: raw for _, name, raw in winners})
    result = charts.generate_charts(source)
    charts.validate_charts(result, source, False)
    return json.dumps(result, ensure_ascii=False).encode()


def tar_members(source):
    """Bound headers before reading payload, including PAX extension headers.

    Python's high-level TarFile can allocate an attacker-declared PAX payload
    before returning a member. This narrow USTAR/PAX reader bounds that step and
    rejects unsupported extensions rather than delegating their interpretation.
    """
    total = 0
    def take(stream, size):
        nonlocal total
        total += size
        need(total <= 9 * 1024 ** 3, 'Decompressed archive budget exceeded')
        result = stream.read(size)
        need(len(result) == size, 'Truncated tar stream')
        return result
    def pax_records(body):
        out, cursor = {}, 0
        while cursor < len(body):
            space = body.find(b' ', cursor)
            need(space > cursor and body[cursor:space].isdigit(), 'Invalid PAX record')
            length = int(body[cursor:space])
            need(length > space - cursor + 1 and cursor + length <= len(body), 'Invalid PAX length')
            row = body[space + 1:cursor + length]
            need(row.endswith(b'\n') and b'=' in row, 'Invalid PAX value')
            key, value = row[:-1].decode('utf-8').split('=', 1)
            need(key not in out and key in ('comment', 'path'), 'Unsupported/duplicate PAX key')
            out[key] = value
            cursor += length
        return out
    global_pax, pending = {}, None
    with gzip.GzipFile(fileobj=source, mode='rb') as stream:
        headers = 0
        while True:
            block = take(stream, 512)
            if not any(block):
                need(pending is None and not any(take(stream, 512)), 'Invalid tar end marker')
                while True:
                    tail = stream.read(1024 ** 2)
                    if not tail:
                        break
                    total += len(tail)
                    need(total <= 9 * 1024 ** 3 and not any(tail), 'Nonzero/oversized tar trailer')
                break
            headers += 1
            need(headers <= MAX_ENTRIES + 10000, 'Tar header budget exceeded')
            entry = tarfile.TarInfo.frombuf(block, 'utf-8', 'strict')
            need(0 <= entry.size <= MAX_FILE, 'Tar member byte budget exceeded')
            if entry.type in (tarfile.XHDTYPE, tarfile.XGLTYPE):
                need(entry.size <= 65536, 'PAX header byte budget exceeded')
                body = take(stream, entry.size)
                padding = (-entry.size) % 512
                if padding:
                    need(not any(take(stream, padding)), 'Nonzero tar padding')
                values = pax_records(body)
                if entry.type == tarfile.XGLTYPE:
                    need(not global_pax and pending is None and set(values) <= {'comment'}, 'Unsupported global PAX')
                    global_pax = values
                else:
                    need(pending is None and set(values) <= {'path'}, 'Unsupported local PAX')
                    pending = values
                continue
            need(entry.isdir() or entry.isreg(), 'Unsupported tar entry type')
            entry.pax_headers = {**global_pax, **(pending or {})}
            if pending and 'path' in pending:
                entry.name = pending['path']
            pending = None
            # tarfile's yielded directory names omit the one canonical trailing
            # separator used by Git's archives. No other normalization is allowed.
            if entry.isdir() and entry.name.endswith('/'):
                entry.name = entry.name[:-1]
            body = take(stream, entry.size)
            padding = (-entry.size) % 512
            if padding:
                need(not any(take(stream, padding)), 'Nonzero tar padding')
            yield entry, body


def stream_archive(raw, descriptor, *, write_file=None):
    """One pass: consumed compressed hash + full inventory + canonical records.

    No unverified record is emitted as authority. All result objects are returned
    only after the fixed archive and independently published inventory both match.
    write_file, when requested, is confined by the caller to a private new stage.
    """
    source = HashReader(raw, descriptor['archive']['size'])
    root = 'booth-vrc-price-tracker-' + descriptor['tracker_commit']
    validator = record_checks(descriptor)
    seen, folded, regular_names, parent_names = set(), set(), set(), set()
    inventory, ids, winners = {}, set(), []
    latest, total, count, selected_bytes = None, 0, 0, 0
    for entry, body in tar_members(source):
            path = safe_name(entry.name)
            name = path.as_posix()
            normalized = unicodedata.normalize('NFC', name).casefold()
            need(name not in seen and normalized not in folded, 'Duplicate/ambiguous archive path')
            need(path.parts[0] == root, 'Wrong archive root')
            need(entry.isdir() or entry.isreg(), 'Link or special archive entry refused')
            need(not entry.issparse() and not entry.linkname, 'Sparse/linked archive entry refused')
            need(set(entry.pax_headers) <= {'comment', 'path'}, 'Unrecognized archive extension')
            need(all(parent.as_posix() not in regular_names for parent in path.parents),
                 'Archive file/directory conflict')
            need(entry.isdir() or name not in parent_names, 'Archive parent replaced by file')
            parent_names.update(parent.as_posix() for parent in path.parents)
            count += 1
            total += entry.size
            need(type(entry.size) is int and 0 <= entry.size <= MAX_FILE and
                 count <= MAX_ENTRIES and total <= MAX_UNPACKED, 'Archive budget exceeded')
            need(not entry.isdir() or entry.size == 0, 'Nonempty archive directory')
            seen.add(name)
            folded.add(normalized)
            if entry.isdir():
                continue
            regular_names.add(name)
            need(len(body) == entry.size, 'Truncated archive member')
            if len(path.parts) < 3 or path.parts[1] not in ('data', 'meta'):
                continue
            if path.name == '.gitkeep':
                need(not body, 'Nonempty source marker')
                continue
            need(path.suffix == '.json', 'Unknown previous source file')
            relative = '/'.join(('tracker_meta' if path.parts[1] == 'meta' else 'data', *path.parts[2:]))
            need(relative not in inventory, 'Duplicate reconstructed path')
            inventory[relative] = sha(body)
            selected_bytes += len(body)
            if write_file is not None:
                write_file(relative, body)
            if path.parts[1] != 'data':
                # Also validate JSON ambiguity/nonfinite values in all metadata.
                # The fixed full inventory still commits its exact original bytes.
                validator.strict_json(body)
                continue
            # Invoke the exact canonical validation function on these same bytes.
            # Its global uniqueness/date aggregation is reproduced below; a
            # single empty-history product or bookkeeping file has no dated IDs.
            try:
                day, _ = validator.inspect_records({relative: body}, '0001-01-01',
                                                    descriptor['source_date'], 3652058)
            except ValueError as error:
                if str(error) != 'No dated products':
                    raise
                day = None
            if day is not None:
                latest = max(latest or day, day)
            record = validator.strict_json(body)
            if relative in ('data/collection_receipt.json', 'data/crawl_state.json', 'data/request_budget.json'):
                continue
            ident = record['id']
            need(ident not in ids, 'Duplicate previous backend ID')
            ids.add(ident)
            best = []
            for series in record['variations'].values():
                if len(series) > len(best):
                    best = series
            if not best:
                continue
            series = sorted(best, key=lambda point: point['date'])
            distinct = len({point['price'] for point in series})
            transitions = sum(1 for i in range(1, len(series))
                              if series[i].get('is_sale') and not series[i - 1].get('is_sale'))
            if distinct >= 3 and len(series) >= 60:
                score = distinct * 2 + transitions * 3 + len(series) / 50.0
                winners.append(((score, ident), relative, body))
                winners.sort(reverse=True)
                del winners[3:]
    # Bind any remaining response bytes to the same exact compressed source pin.
    while source.read(1024 ** 2):
        pass
    need(source.size == descriptor['archive']['size'] and
         source.digest.hexdigest() == descriptor['archive']['sha256'], 'Fixed archive identity mismatch')
    need(ids and latest == descriptor['source_date'], 'Previous date/ID coverage mismatch')
    charts = build_charts(winners, descriptor)
    inventory['charts.json'] = sha(charts)
    selected_bytes += len(charts)
    if write_file is not None:
        write_file('charts.json', charts)
    anchor = descriptor['input_inventory']
    need(len(inventory) == anchor['files'] and sha(canonical(inventory)) == anchor['sha256'],
         'Reconstructed complete inventory differs from published anchor')
    return {'inventory': inventory, 'backend_ids': sorted(ids, key=int), 'source_date': latest,
            'archive_entries': count, 'archive_uncompressed_member_bytes': total,
            'reconstructed_bytes': selected_bytes, 'charts_sha256': sha(charts)}


def get_bytes(reads, name, limit=MAX_FILE, expected=None):
    safe_name(name)
    with reads.open(LIVE + name) as (status, stream):
        need(status == 200, 'Required public predecessor file unavailable')
        raw = stream.read(limit + 1)
    need(isinstance(raw, bytes) and len(raw) <= limit, 'Public response exceeded bound')
    if expected is not None:
        need(sha(raw) == expected, 'Public predecessor bytes changed')
    return raw


def no_modern(reads):
    with reads.open(LIVE + 'release-manifest.json') as (status, stream):
        need(status == 404, 'Fixed legacy path requires modern sentinel absence')
        need(len(stream.read(65537)) <= 65536, 'Oversized absence response')


def verify(reads, expected_digest, *, site_write=None, raw_write=None):
    """Fresh independent replay. Does not accept a supplied derived summary."""
    descriptor, ledger = assets()
    need(expected_digest == descriptor['release_digest'], 'Unsupported previous lineage')
    need(reads is not None and callable(getattr(reads, 'open', None)), 'Explicit GET/fixture transport required')
    no_modern(reads)
    before = get_bytes(reads, 'snapshot-manifest.json', expected=expected_digest)
    snapshot = strict_json(before)
    need(snapshot.get('fixture') is False and snapshot.get('input_inventory') == descriptor['input_inventory'] and
         snapshot.get('input_manifest_sha256') == descriptor['input_manifest_sha256'] and
         snapshot.get('validation', {}).get('max_date') == descriptor['source_date'], 'Fixed public anchors changed')
    visible, site_bytes = [], 0
    for name, digest in sorted(ledger.items()):
        body = get_bytes(reads, name, expected=digest)
        site_bytes += len(body)
        need(site_bytes <= MAX_SITE, 'Public site byte budget exceeded')
        if name == 'snapshot-manifest.json':
            need(body == before, 'Snapshot changed during capture')
        if re.fullmatch(r'search_index_(?:[0-9]|1[0-9]|2[0-3])\.json', name):
            rows = strict_json(body)
            need(isinstance(rows, list), 'Public catalog shard must be an array')
            for row in rows:
                need(isinstance(row, list) and row and isinstance(row[0], str) and
                     re.fullmatch('[1-9][0-9]*', row[0]), 'Invalid public canonical ID')
                visible.append(row[0])
        if site_write is not None:
            site_write(name, body)
    need(len(visible) == len(set(visible)) == snapshot['validation']['rows'], 'Duplicate/missing public IDs')
    with reads.open(TRACKER + descriptor['tracker_commit']) as (status, stream):
        need(status == 200, 'Fixed archive unavailable')
        previous = stream_archive(stream, descriptor, write_file=raw_write)
    need(set(visible) <= set(previous['backend_ids']), 'Previous visible IDs absent from raw source')
    need(get_bytes(reads, 'snapshot-manifest.json', expected=expected_digest) == before, 'Live predecessor changed')
    no_modern(reads)
    receipt = {
        'schema': 'boopa-fixed-previous-stream-evidence-v1',
        'previous_evidence_mode': 'verified-archive-stream-v1',
        'previous_release_digest': expected_digest,
        'previous_input_manifest_sha256': descriptor['input_manifest_sha256'],
        'previous_input_inventory_sha256': descriptor['input_inventory']['sha256'],
        'previous_input_inventory_count': descriptor['input_inventory']['files'],
        'previous_site_ledger_sha256': descriptor['site_ledger_sha256'],
        'archive_sha256': descriptor['archive']['sha256'],
        'archive_bytes': descriptor['archive']['size'],
        'tracker_commit': descriptor['tracker_commit'],
        'expected_date': previous['source_date'],
        'backend_ids': previous['backend_ids'],
        'visible_ids': sorted(visible, key=int),
        'original_previous_manifest_recovered': False,
        'validation_only': getattr(reads, 'validation_only', False) is True,
        'publication_authorized': False,
    }
    return receipt, previous, {'public_site_bytes': site_bytes, 'public_site_files': len(ledger)}


def resolve(destination, expected_digest, reads=None, descriptor_path=None, *, mode='compact'):
    """Create a new local receipt/spec. Full materialization requires explicit mode.

    Old descriptor overrides are refused. The compatibility materialized spec is
    checked by the unchanged full-tree validator when consumed. Compact consumers
    MUST call verify again using their independent transport, not load this file.
    """
    need(descriptor_path is None, 'Caller-selected descriptor forbidden')
    need(mode in ('compact', 'materialized'), 'Unsupported previous representation')
    target = Path(os.path.abspath(destination))
    need(not target.exists() and not target.is_symlink(), 'New destination required')
    if isinstance(reads, LocalFixture):
        for source in (Path(os.path.abspath(reads.site)), Path(os.path.abspath(reads.archive)).parent):
            need(not target.is_relative_to(source) and not source.is_relative_to(target),
                 'Destination must be disjoint from source artifacts')
    parent_fd = open_directory(target.parent)
    stage_fd = None
    try:
        os.mkdir(target.name, mode=0o700, dir_fd=parent_fd)
        stage_fd = os.open(target.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent_fd)
    except Exception:
        os.close(parent_fd)
        raise
    identity = os.fstat(stage_fd)
    def check_destination():
        fd = open_directory(target)
        try:
            actual = os.fstat(fd)
            need((actual.st_dev, actual.st_ino) == (identity.st_dev, identity.st_ino),
                 'Destination replaced during verification')
        finally:
            os.close(fd)
    def writer(base):
        def write(name, raw):
            safe_name(name)
            write_beneath(stage_fd, base + '/' + name, raw)
        return write
    created_result = None
    created_identity = None
    try:
        receipt, previous, measurements = verify(
            reads, expected_digest,
            site_write=writer('site') if mode == 'materialized' else None,
            raw_write=writer('prepared') if mode == 'materialized' else None)
        check_destination()
        if mode == 'materialized':
            inventory = target / 'previous-files.json'
            write_beneath(stage_fd, 'previous-files.json', canonical(previous['inventory']))
            descriptor, _ = assets()
            result = {
                'previous_evidence_mode': 'published-input-inventory',
                'previous_site': str((target / 'site').absolute()),
                'previous_site_ledger': str((ASSETS / 'site-ledger.json').absolute()),
                'previous_site_ledger_sha256': descriptor['site_ledger_sha256'],
                'previous_input_root': str((target / 'prepared').absolute()),
                'previous_input_inventory': str(inventory.absolute()),
                'previous_input_inventory_sha256': descriptor['input_inventory']['sha256'],
                'previous_input_manifest_sha256': descriptor['input_manifest_sha256'],
                'previous_sentinel_path': 'snapshot-manifest.json',
                'previous_release_digest': expected_digest,
                'validation_only': receipt['validation_only'],
                'original_previous_manifest_recovered': False,
                'publication_authorized': False}
            name = 'trusted-previous-spec.json'
        else:
            result, name = receipt, 'verified-previous-evidence.json'
        output = target / name
        result_fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600, dir_fd=stage_fd)
        created_result, created_identity = name, os.fstat(result_fd)
        with os.fdopen(result_fd, 'wb') as stream:
            stream.write(canonical(result) + b'\n')
        check_destination()
        return output
    except Exception:
        # Remove only the final file this call successfully created, via its
        # held stage FD. Never clean up old sources or other stage contents.
        if created_result is not None:
            try:
                current = os.stat(created_result, dir_fd=stage_fd, follow_symlinks=False)
                if (current.st_dev, current.st_ino) == (created_identity.st_dev, created_identity.st_ino):
                    os.unlink(created_result, dir_fd=stage_fd)
            except FileNotFoundError:
                pass
        # Failure does not create a trusted spec or receipt. A partial full-tree
        # stage is deliberately retained for the caller's explicit cleanup policy.
        try:
            write_beneath(stage_fd, 'FAILED', b'Predecessor verification failed. No trusted evidence produced.\n')
        except OSError:
            pass
        raise
    finally:
        if stage_fd is not None:
            os.close(stage_fd)
        os.close(parent_fd)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--destination', required=True)
    parser.add_argument('--expected-digest', required=True)
    parser.add_argument('--local-archive', required=True)
    parser.add_argument('--local-site', required=True)
    parser.add_argument('--materialize', action='store_true')
    args = parser.parse_args()
    fixture = LocalFixture(args.local_archive, args.local_site, legacy_absent=True)
    print(resolve(args.destination, args.expected_digest, fixture,
                  mode='materialized' if args.materialize else 'compact'))
