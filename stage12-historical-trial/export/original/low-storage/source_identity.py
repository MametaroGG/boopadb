"""Reauthenticate prepared data/meta against resolver-observed Git tree identities.

This is a consumption verifier, not a source selector. The caller must obtain the
commit/root evidence through the existing authenticated resolver and pass the
exact private request digest directly. No serialized completion is authority.
"""
import hashlib
import json
from pathlib import PurePosixPath
from collections.abc import Mapping


def need(ok, message):
    if not ok:
        raise ValueError(message)


def git_hash(kind, raw):
    return hashlib.sha1(kind.encode() + b' ' + str(len(raw)).encode() + b'\0' + raw).hexdigest()


def tree_hash(entries):
    """Exact recursive Git ordering, including directory slash sort semantics."""
    directories = {'': {}}
    for path, (mode, digest) in entries.items():
        parts = PurePosixPath(path).parts
        need(path == '/'.join(parts) and all(p not in ('', '.', '..') for p in parts), 'Noncanonical source path')
        for index in range(len(parts) - 1):
            parent = '/'.join(parts[:index]); child = '/'.join(parts[:index + 1])
            directories.setdefault(child, {})
            prior = directories[parent].setdefault(parts[index], ('40000', child))
            need(prior == ('40000', child), 'Source tree path collision')
        parent = '/'.join(parts[:-1])
        need(parts[-1] not in directories[parent], 'Duplicate source path')
        directories[parent][parts[-1]] = (mode, digest)
    def digest(name):
        rows = []
        for child, (mode, value) in directories[name].items():
            oid = digest(value) if mode == '40000' else value
            raw = child.encode('utf-8')
            rows.append((raw + (b'/' if mode == '40000' else b''), mode.encode() + b' ' + raw + b'\0' + bytes.fromhex(oid)))
        return git_hash('tree', b''.join(value for _, value in sorted(rows)))
    return digest('')


class RawView(Mapping):
    def __init__(self, source, hashes):
        self.source, self.hashes = source, hashes
    def __iter__(self): return iter(self.hashes)
    def __len__(self): return len(self.hashes)
    def __getitem__(self, name):
        mapped = 'tracker_meta/' + name[5:] if name.startswith('meta/') else name
        return self.source.read_bytes(self.source.root / mapped)


def verify(source, request, inventory_raw, attestation_raw, source_modes):
    """Bind exact consumed bytes to real source anchors and deterministic charts."""
    from snapshot_contract import inspect_records, strict_json
    from charts_contract import generate_charts, validate_charts
    binding = request['binding']; root = request['root']; commit = request['commit']
    need(commit['sha'] == binding['saved_commit'] and commit['tree']['sha'] == binding['root_tree'], 'Saved commit/tree identity changed')
    need(root['truncated'] is False, 'Truncated source tree')
    root_entries = root['tree']
    def root_oid(rows):
        values=[]
        for entry in rows:
            name=entry['path']; mode=entry['mode']; raw=name.encode()
            need('/' not in name and name not in ('','.','..'), 'Recursive source root')
            mode='40000' if mode=='040000' else mode
            need(mode in ('40000','100644','100755'), 'Unsupported source mode')
            values.append((raw+(b'/' if mode=='40000' else b''),mode.encode()+b' '+raw+b'\0'+bytes.fromhex(entry['sha'])))
        need(len({r['path'] for r in rows})==len(rows), 'Duplicate root member')
        return git_hash('tree', b''.join(v for _,v in sorted(values)))
    need(root_oid(root_entries)==binding['root_tree'], 'Root evidence not committed by saved source')
    inventory=strict_json(inventory_raw); attestation=strict_json(attestation_raw)
    hashes={('meta/'+name[13:] if name.startswith('tracker_meta/') else name):digest for name,digest in source.hashes.items() if name.startswith(('data/','tracker_meta/'))}
    need(hashes==inventory and set(source_modes)==set(hashes), 'Prepared/archive inventory or mode set differs')
    need(attestation['files']==hashes and attestation['inventory_digest']==hashlib.sha256(inventory_raw).hexdigest(), 'Attestation inventory mismatch')
    for key in ('collection_id','tracker_commit'):
        need(attestation[key]==binding['saved_commit'] and source.manifest[key]==binding['saved_commit'], 'Source identity mismatch')
    need(source.manifest['inventory_digest']==hashlib.sha256(inventory_raw).hexdigest() and source.manifest['producer_attestation_sha256']==hashlib.sha256(attestation_raw).hexdigest(), 'Completion derivation mismatch')
    objects={}
    for name in hashes:
        mode=source_modes[name]; need(mode=='100644', 'Unsupported raw source mode')
        raw=RawView(source,hashes)[name]
        objects[name]=(mode,git_hash('blob',raw))
    actual={}
    for directory in ('data','meta'):
        subset={name[len(directory)+1:]:value for name,value in objects.items() if name.startswith(directory+'/')}
        expected=[entry['sha'] for entry in root_entries if entry['path']==directory and entry['mode']=='040000' and entry['type']=='tree']
        actual[directory]=tree_hash(subset)
        need(expected==[actual[directory]], 'Prepared bytes differ from authenticated '+directory+' Git subtree')
    view=RawView(source,hashes)
    latest, placeholders=inspect_records(view,attestation['minimum_source_date'],attestation['as_of'],attestation['max_source_age_days'])
    need(latest==attestation['expected_date']==source.manifest['expected_date'] and placeholders==attestation['bound_empty_placeholders'], 'Source record/date derivation differs')
    charts=json.dumps(generate_charts(source.root,verified_source=source),ensure_ascii=False).encode()
    need(source.read_bytes(source.root/'charts.json')==charts, 'Charts not independently derived from committed source')
    validate_charts(strict_json(charts),source.root,attestation['fixture'],verified_source=source)
    need(hashlib.sha256(view['data/collection_receipt.json']).hexdigest()==binding['receipt_sha256'], 'Resolver receipt differs from consumed source')
    source.verify_all()
    return {'schema':'boopa-consumed-git-subtrees-v1','saved_commit':binding['saved_commit'],'git_subtrees':actual,'source_files':len(hashes),'completion_sha256':source.completion_sha256,'charts_sha256':hashlib.sha256(charts).hexdigest(),'authority':'resolver-bound-source-integrity-only','publication_authorized':False}
