"""Pinned, offline public-catalog visibility. Source records are never modified.

Only a last-known HTTP 404/410 marker is exclusion evidence. This is not proof
that an item is permanently private. Missing metadata and transient failures do
not imply withdrawal. Invalid or conflicting withdrawal evidence stops a build.
"""
import hashlib
import json
import math
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
_ID = re.compile(r'[1-9][0-9]*', re.ASCII)
_SHA = re.compile(r'[0-9a-f]{64}', re.ASCII)
_DATE = re.compile(r'\d{4}-\d{2}-\d{2}', re.ASCII)


def canonical_id(value):
    return isinstance(value, str) and _ID.fullmatch(value) is not None


def canonical_date(value):
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        raise ValueError('Canonical YYYY-MM-DD visibility date required')
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError('Noncanonical visibility date')
    return parsed


def strict_json(raw):
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out:
                raise ValueError('Duplicate metadata key: ' + key)
            out[key] = value
        return out

    def nonfinite(value):
        raise ValueError('Nonfinite metadata constant: ' + value)

    return json.loads(raw, object_pairs_hook=pairs, parse_constant=nonfinite)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(',', ':'), allow_nan=False).encode('utf-8')


class VisibilityPolicy:
    """Read metadata once and retain only hashes, IDs and exclusion evidence.

    expected_hashes uses the frozen manifest's tracker_meta/... paths. Without
    that map the standalone build binds its own exact metadata reads. Records
    returned by iter_metadata are the same bytes used for each evidence hash.
    """
    def __init__(self, meta_root, expected_hashes=None, generation_time=None, verified_source=None):
        self.verified_source = verified_source
        self.root = Path(meta_root)
        self.now = generation_time or datetime.now(timezone.utc)
        if not isinstance(self.now, datetime) or self.now.tzinfo is None:
            raise ValueError('Aware visibility generation timestamp required')
        self.today = self.now.astimezone(JST).date()
        self.expected_hashes = expected_hashes
        if expected_hashes is not None:
            if not isinstance(expected_hashes, dict) or any(
                    not isinstance(path, str) or not path.startswith('tracker_meta/') or
                    not isinstance(sha, str) or not _SHA.fullmatch(sha)
                    for path, sha in expected_hashes.items()):
                raise ValueError('Invalid pinned metadata hash inventory')
        self.metadata_hashes = {}
        self.metadata_ids = set()
        self.markers = {}
        self.backend_ids = set()
        self.hidden_ids = set()
        self._loaded = False

    def iter_metadata(self):
        if self._loaded:
            raise ValueError('Metadata may only be consumed once')
        self._loaded = True
        if self.root.is_symlink() or not self.root.is_dir():
            raise ValueError('Existing nonlinked metadata directory required')
        paths = self.verified_source.paths('tracker_meta') if self.verified_source else self.root.rglob('*')
        for path in sorted(paths):
            if not self.verified_source and path.is_symlink():
                raise ValueError('Linked metadata input: ' + str(path))
            if not self.verified_source and path.is_dir():
                continue
            if not self.verified_source and not path.is_file():
                raise ValueError('Nonregular metadata input: ' + str(path))
            relative = path.relative_to(self.root)
            name = 'tracker_meta/' + relative.as_posix()
            raw = self.verified_source.read_bytes(path) if self.verified_source else path.read_bytes()
            sha = hashlib.sha256(raw).hexdigest()
            if self.expected_hashes is not None and self.expected_hashes.get(name) != sha:
                raise ValueError('Unbound metadata input: ' + name)
            self.metadata_hashes[name] = sha
            if path.name == '.gitkeep' and not raw:
                continue
            if path.suffix != '.json':
                raise ValueError('Unsupported metadata input: ' + name)
            # Root JSON files are collector bookkeeping, not product records.
            if len(relative.parts) == 1:
                continue
            try:
                record = strict_json(raw)
            except (ValueError, UnicodeDecodeError) as exc:
                raise ValueError('Invalid metadata ' + name + ': ' + str(exc)) from exc
            ident = path.stem
            if not canonical_id(ident) or ident in self.metadata_ids:
                raise ValueError('Invalid/duplicate metadata path ID: ' + name)
            self.metadata_ids.add(ident)
            if not isinstance(record, dict):
                raise ValueError('Metadata record must be an object: ' + name)
            if 'id' in record and (not canonical_id(record['id']) or record['id'] != ident):
                raise ValueError('Metadata ID/path mismatch: ' + name)
            flag = record.get('unavailable', False)
            if type(flag) is not bool:
                raise ValueError('Nonboolean unavailable marker: ' + name)
            if flag:
                status = record.get('status')
                if type(status) is not int or not 100 <= status <= 599:
                    raise ValueError('Invalid unavailable HTTP status: ' + name)
                if status in (404, 410):
                    if record.get('id') != ident:
                        raise ValueError('Missing canonical unavailable item ID: ' + name)
                    fetched = canonical_date(record.get('fetched_at'))
                    if fetched > self.today:
                        raise ValueError('Future unavailable marker: ' + name)
                    # A success body and an unavailable tombstone cannot be
                    # asserted by the same producer record.
                    if record.get('name'):
                        raise ValueError('Conflicting unavailable metadata body: ' + name)
                    self.markers[ident] = dict(id=ident, path=name, sha256=sha,
                                               status=status, fetched_at=fetched.isoformat())
            elif record.get('status') in (404, 410):
                raise ValueError('Conflicting unavailable flag/status: ' + name)
            if record.get('name') and record.get('id') != ident:
                raise ValueError('Missing canonical metadata ID: ' + name)
            yield ident, record
        if self.expected_hashes is not None and set(self.metadata_hashes) != set(self.expected_hashes):
            raise ValueError('Pinned metadata inventory differs from consumed input')

    def observe_product(self, record):
        """Return visibility after checking a source record against its marker."""
        ident = record.get('id')
        if not canonical_id(ident) or ident in self.backend_ids:
            raise ValueError('Invalid/duplicate backend visibility ID')
        self.backend_ids.add(ident)
        marker = self.markers.get(ident)
        if marker is None:
            return True
        variations = record.get('variations')
        if not isinstance(variations, dict):
            raise ValueError('Invalid history for unavailable item: ' + ident)
        for series in variations.values():
            if not isinstance(series, list):
                raise ValueError('Invalid history for unavailable item: ' + ident)
            for observation in series:
                if not isinstance(observation, dict):
                    raise ValueError('Invalid observation for unavailable item: ' + ident)
                stamp = observation.get('date')
                # The pinned tracker format uses JST calendar days. Do not
                # infer ordering from a naive timestamp or a malformed row.
                observed_day = canonical_date(stamp)
                price = observation.get('price')
                if type(price) not in (int, float) or not math.isfinite(price) or price < 0:
                    raise ValueError('Invalid price for unavailable item: ' + ident)
                if observed_day.isoformat() > marker['fetched_at']:
                    raise ValueError('Newer price observation conflicts with unavailable marker: ' + ident)
        self.hidden_ids.add(ident)
        return False

    def public_payload(self):
        # A metadata-only tombstone must also suppress stale bookmark/history
        # and remote fallback entries. Backend partition counts stay separate.
        return dict(schema=1, hidden_ids=sorted(self.markers))

    def write_evidence(self, directory, source_min_date, source_max_date):
        """Private exact-set ledger; no names or source records are serialized."""
        visible = self.backend_ids - self.hidden_ids
        inventory_sha = hashlib.sha256(json_bytes(self.metadata_hashes)).hexdigest()
        counts = dict(backend_total=len(self.backend_ids), visible_total=len(visible),
                      confirmed_hidden_total=len(self.hidden_ids))
        ledger = dict(schema=1, policy='last-known-http-unavailable-v1',
                      evidence_scope='pinned-metadata-and-retained-backend-products',
                      generated_at=self.now.isoformat(),
                      metadata_binding='frozen-input-manifest' if self.expected_hashes is not None else 'exact-standalone-read',
                      metadata_inventory_sha256=inventory_sha,
                      backend_ids=sorted(self.backend_ids), visible_ids=sorted(visible),
                      confirmed_hidden_ids=sorted(self.hidden_ids),
                      confirmed_hidden_evidence=[self.markers[i] for i in sorted(self.hidden_ids)],
                      known_unavailable_ids=sorted(self.markers),
                      known_unavailable_evidence=[self.markers[i] for i in sorted(self.markers)],
                      metadata_only_unavailable_total=len(set(self.markers) - self.backend_ids),
                      source_min_date=source_min_date, source_max_date=source_max_date,
                      counts=counts)
        raw = json_bytes(ledger)
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / 'visibility-ledger.json'
        path.write_bytes(raw)
        return dict(schema=1, **counts, source_min_date=source_min_date,
                    source_max_date=source_max_date,
                    ledger_sha256=hashlib.sha256(raw).hexdigest(),
                    metadata_inventory_sha256=inventory_sha)
