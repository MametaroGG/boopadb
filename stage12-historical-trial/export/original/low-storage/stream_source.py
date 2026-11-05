"""Local-only source archive -> one prepared namespace prototype.

No networking or credentials. A caller supplies an already-authorized bounded GET
body or local fixture. Production authority remains disabled pending integration
with the existing resolver/producer gate and fresh independent QA acquisition.
"""
from __future__ import annotations
import builtins, contextlib, ctypes, errno, hashlib, io, json, math, os, re, resource, secrets, stat, tarfile, tempfile, time, types, unicodedata, zlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPOSITORY = 'MametaroGG/booth-vrc-price-tracker'
SCOPE = 'immutable-captured-snapshot-integrity'
CODE_PINS = {
 'snapshot_contract.py':'fe90612f3453cd61dcab45f34434cc43120aa734353d911efe68ad26d7f0eb72',
 'charts_contract.py':'a66488a48ade974180b44b21907efdc692a5102ae89b7b4ab635e2974385947b',
 'varutil.py':'ea900c3de864c631e675cd0020be99bb7c77f0f9c71dbf8bc6fa56b69ff18003'}

def sha(b): return hashlib.sha256(b).hexdigest()
def fail(message): raise ValueError(message)
def strict_json(raw):
    def pairs(items):
        out={}
        for key,value in items:
            if key in out: fail('Duplicate JSON key')
            out[key]=value
        return out
    def finite_float(value):
        result=float(value)
        if not math.isfinite(result):fail('Nonfinite JSON number')
        return result
    return json.loads(raw.decode('utf-8','strict'), object_pairs_hook=pairs,parse_float=finite_float,
                      parse_constant=lambda x:fail('Nonfinite JSON'))
def hex40(x):
    if not isinstance(x,str) or not re.fullmatch('[0-9a-f]{40}',x): fail('Invalid Git identity')
    return x
def canonical_date(x):
    if not isinstance(x,str) or date.fromisoformat(x).isoformat()!=x: fail('Invalid date')
    return date.fromisoformat(x)
def git_hash(kind, raw): return hashlib.sha1(kind+b' '+str(len(raw)).encode()+b'\0'+raw).digest()
def safe_path(name):
    if not isinstance(name,str) or not name or len(name.encode('utf-8','strict'))>1024: fail('Invalid path length')
    if name.startswith('/') or '\\' in name or any(ord(x)<32 or ord(x)==127 for x in name): fail('Unsafe path')
    parts=name.split('/')
    if len(parts)>32 or any(p in ('','.','..') or len(p.encode('utf-8'))>255 for p in parts):fail('Unsafe path components/depth')
    if unicodedata.normalize('NFC',name)!=name: fail('Noncanonical Unicode path')
    return name

def safe_root(path):
    path=Path(os.path.abspath(path))
    for p in [*reversed(path.parents),path]:
        if p.is_symlink(): fail('Linked root ancestry')
    if not path.is_dir(): fail('Missing root')
    return path

class Directory:
    """Held directory capabilities; every traversal is component NOFOLLOW."""
    def __init__(self,path=None,fd=None):
        self.fd=os.dup(fd) if fd is not None else os.open('/',os.O_RDONLY|os.O_DIRECTORY)
        if fd is None:
            try:
                for part in Path(os.path.abspath(path)).parts[1:]:
                    nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=self.fd)
                    os.close(self.fd);self.fd=nxt
            except BaseException:self.close();raise
    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None
    def __enter__(self):return self
    def __exit__(self,*unused):self.close()
    def parent(self,name,create=False):
        safe_path(name);parts=name.split('/');fd=os.dup(self.fd)
        try:
            for part in parts[:-1]:
                if create:
                    try:os.mkdir(part,0o700,dir_fd=fd)
                    except FileExistsError:pass
                nxt=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                os.close(fd);fd=nxt
            return fd,parts[-1]
        except BaseException:os.close(fd);raise
    def read(self,name,maximum):
        fd,leaf=self.parent(name)
        try:
            child=os.open(leaf,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
            try:
                st=os.fstat(child)
                if not stat.S_ISREG(st.st_mode) or st.st_size>maximum:fail('Nonregular/oversized file')
                with os.fdopen(child,'rb',closefd=False) as f:raw=f.read(maximum+1)
                if len(raw)>maximum or len(raw)!=st.st_size:fail('Changed/oversized file')
                return raw
            finally:os.close(child)
        finally:os.close(fd)
    def write(self,name,raw):
        fd,leaf=self.parent(name,create=True)
        try:
            child=os.open(leaf,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600,dir_fd=fd)
            with os.fdopen(child,'wb') as f:f.write(raw)
        finally:os.close(fd)
    def mkdir(self,name):
        fd,leaf=self.parent(name,create=True)
        try:
            try:os.mkdir(leaf,0o700,dir_fd=fd)
            except FileExistsError:pass
            child=os.open(leaf,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(child)
        finally:os.close(fd)
    def inventory(self):
        files=set();dirs=set();allocated=0
        def walk(fd,prefix=''):
            nonlocal allocated
            for name in os.listdir(fd):
                rel=prefix+name;safe_path(rel);st=os.stat(name,dir_fd=fd,follow_symlinks=False);allocated+=st.st_blocks*512
                if stat.S_ISDIR(st.st_mode):
                    dirs.add(rel);child=os.open(name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
                    try:walk(child,rel+'/')
                    finally:os.close(child)
                elif stat.S_ISREG(st.st_mode):files.add(rel)
                else:fail('Nonregular prepared namespace member')
        walk(self.fd);return files,dirs,allocated

def read_anchored(root,name,maximum):
    with Directory(root) as d:return d.read(name,maximum)

def rename_noreplace(parent,source,target):
    if '/' in source or '/' in target:fail('Rename must be within held parent')
    libc=ctypes.CDLL(None,use_errno=True)
    fn=getattr(libc,'renameat2',None)
    if fn is None:fail('Atomic no-replace rename unavailable')
    fn.argtypes=(ctypes.c_int,ctypes.c_char_p,ctypes.c_int,ctypes.c_char_p,ctypes.c_uint)
    fn.restype=ctypes.c_int
    if fn(parent.fd,source.encode(),parent.fd,target.encode(),1):
        err=ctypes.get_errno();raise OSError(err,os.strerror(err))


def same_directory(left,right):
    a,b=os.fstat(left.fd),os.fstat(right.fd)
    if (a.st_dev,a.st_ino)!=(b.st_dev,b.st_ino):fail('Directory identity changed')

def verify_published(parent_path,parent,target,stage):
    # A held directory FD protects writes but is not proof that its lexical
    # name still resolves there. Bind both the requested parent and target.
    with Directory(parent_path) as reopened:same_directory(reopened,parent)
    child=os.open(target.name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent.fd)
    try:
        with Directory(fd=child) as published:same_directory(published,stage)
    finally:os.close(child)
    with Directory(target) as lexical:same_directory(lexical,stage)

def load_reviewed():
    """Hash exact helper bytes then execute those bytes, never archive helpers."""
    root=Path(__file__).parent/'reviewed';modules={}
    def local_import(name,*args,**kwargs):
        return modules[name] if name in modules else builtins.__import__(name,*args,**kwargs)
    for name in ('varutil','charts_contract','snapshot_contract'):
        raw=read_anchored(root,name+'.py',128*1024)
        if sha(raw)!=CODE_PINS[name+'.py']:fail('Reviewed helper pin mismatch')
        module=types.ModuleType('_streamed_'+name);module.__file__=str(root/(name+'.py'))
        module.__dict__['__builtins__']={**vars(builtins),'__import__':local_import}
        modules[name]=module
        exec(compile(raw,module.__file__,'exec'),module.__dict__)

    return modules

@dataclass(frozen=True)
class Limits:
    compressed_bytes:int=512*1024**2
    uncompressed_bytes:int=10*1024**3
    file_bytes:int=64*1024**2
    entries:int=500000
    path_bytes:int=64*1024**2
    source_bytes:int=8*1024**3
    min_free_bytes:int=512*1024**2
    min_free_inodes:int=10000
    # Upper-bound source allocation plus manifest/attestation/chart evidence.
    planned_write_bytes:int=0
    planned_write_inodes:int=0
    def validate(self):
        if any(type(v) is not int or v<0 for v in self.__dict__.values()): fail('Invalid resource limits')
        if not all((self.compressed_bytes,self.uncompressed_bytes,self.file_bytes,self.entries)):fail('Zero resource limit')

def preflight(parent, limits, materialize):
    limits.validate();s=os.fstatvfs(parent.fd) if isinstance(parent,Directory) else os.statvfs(safe_root(parent));free=s.f_bavail*s.f_frsize
    if materialize and (not limits.planned_write_bytes or not limits.planned_write_inodes):fail('Exact planning envelope required before materialization')
    if free<limits.min_free_bytes+limits.planned_write_bytes or s.f_favail<limits.min_free_inodes+limits.planned_write_inodes:fail('Insufficient preflight capacity')
    return {'free_bytes':free,'free_inodes':s.f_favail,'block_size':s.f_frsize}

@dataclass(frozen=True)
class Binding:
    repository:str
    saved_commit:str
    root_tree:str
    commit_evidence_sha256:str
    root_evidence_sha256:str
    receipt_sha256:str
    source_commit:str
    run_id:str
    run_attempt:str
    producer_pin_sha256:str
    authority:str='local-historical-validation-only'
    @property
    def archive_url(self):return f'https://codeload.github.com/{self.repository}/tar.gz/{self.saved_commit}'
    def validate(self):
        if self.repository!=REPOSITORY or self.authority not in ('local-historical-validation-only','synthetic-fixture-only','resolver-context-source-integrity-only'):fail('Unsupported authority/repository; production resolver integration required')
        for v in (self.saved_commit,self.root_tree,self.source_commit):hex40(v)
        for v in (self.commit_evidence_sha256,self.root_evidence_sha256,self.receipt_sha256,self.producer_pin_sha256):
            if not isinstance(v,str) or not re.fullmatch('[0-9a-f]{64}',v):fail('Missing pinned evidence digest')
        for v in (self.run_id,self.run_attempt):
            if not re.fullmatch('[1-9][0-9]{0,19}',v):fail('Invalid run binding')

class GitTree:
    def __init__(self,maximum_path_bytes=64*1024**2):self.dirs={'':{}};self.paths={};self.folded=set();self.path_bytes=0;self.maximum_path_bytes=maximum_path_bytes
    def add(self,path,mode,digest=None):
        safe_path(path);fold=path.casefold();self.path_bytes+=len(path.encode('utf-8'))
        if self.path_bytes>self.maximum_path_bytes:fail('Aggregate path memory budget exceeded')
        if path in self.paths or fold in self.folded:fail('Duplicate/normalized path')
        self.paths[path]=mode;self.folded.add(fold)
        parent,_,base=path.rpartition('/')
        if parent not in self.dirs:fail('Parent directory absent or out of order')
        if mode=='40000':self.dirs[path]={}
        self.dirs[parent][base]=(mode,digest,path)
    def digest(self,path=''):
        entries=[]
        for name,(mode,digest,child) in self.dirs[path].items():
            raw=name.encode('utf-8');digest=self.digest(child) if mode=='40000' else digest
            entries.append((raw+(b'/' if mode=='40000' else b''),mode.encode()+b' '+raw+b'\0'+digest))
        payload=b''.join(v for _,v in sorted(entries));return git_hash(b'tree',payload)

def verify_evidence(binding, commit_raw, root_raw, producer_raw):
    binding.validate()
    for raw,pin in ((commit_raw,binding.commit_evidence_sha256),(root_raw,binding.root_evidence_sha256),(producer_raw,binding.producer_pin_sha256)):
        if sha(raw)!=pin:fail('External evidence pin mismatch')
    commit,root=strict_json(commit_raw),strict_json(root_raw)
    base='https://api.github.com/repos/'+binding.repository
    if commit.get('sha')!=binding.saved_commit or commit.get('url')!=base+'/git/commits/'+binding.saved_commit or commit.get('tree',{}).get('sha')!=binding.root_tree:fail('Commit origin/tree mismatch')
    # GitHub trees queried by a commit sometimes echo the commit as sha. Never
    # accept this field alone: recompute root bytes from every immediate entry.
    if root.get('url') not in (base+'/git/trees/'+binding.root_tree,base+'/git/trees/'+binding.saved_commit) or root.get('truncated') is not False:fail('Tree origin/completeness mismatch')
    entries=root.get('tree');tree=GitTree()
    if not isinstance(entries,list):fail('Missing root entries')
    for x in entries:
        p=x.get('path');safe_path(p)
        if '/' in p:fail('Recursive root evidence not supported')
        mode=x.get('mode');typ=x.get('type');oid=hex40(x.get('sha'))
        if (mode,typ) not in (('040000','tree'),('100644','blob'),('100755','blob')):fail('Unsupported Git root mode/type')
        tree.add(p,'40000' if typ=='tree' else mode,bytes.fromhex(oid))
    # Root evidence child tree IDs are already committed, not empty trees.
    payload=[]
    for n,(mode,digest,path) in tree.dirs[''].items():
        raw=n.encode();payload.append((raw+(b'/' if mode=='40000' else b''),mode.encode()+b' '+raw+b'\0'+digest))
    if git_hash(b'tree',b''.join(v for _,v in sorted(payload))).hex()!=binding.root_tree:fail('Root tree object does not match saved commit')
    if not all(tree.paths.get(p)=='40000' for p in ('data','meta')):fail('Missing source namespaces')
    # Pin contents are opaque here: existing resolver independently verifies all
    # workflow/code gates. We never claim a pin hash by itself evaluates them.
    strict_json(producer_raw)
    return {x['path']:x for x in entries}

class StrictGzip:
    def __init__(self, source, limits):
        self.source=source;self.limits=limits;self.z=zlib.decompressobj(31)
        self.input=b'';self.buffer=b'';self.done=False;self.compressed=0;self.expanded=0;self.hash=hashlib.sha256()
    def _pump(self):
        if self.done:return
        if not self.input:
            self.input=self.source.read(65536)
            if not isinstance(self.input,bytes):fail('Byte stream required')
            self.compressed+=len(self.input);self.hash.update(self.input)
            if self.compressed>self.limits.compressed_bytes:fail('Compressed resource budget exceeded')
            if not self.input:fail('Truncated gzip stream')
        out=self.z.decompress(self.input,1024*1024);self.input=self.z.unconsumed_tail
        self.expanded+=len(out)
        if self.expanded>self.limits.uncompressed_bytes:fail('Expanded resource budget exceeded')
        self.buffer+=out
        if self.z.eof:
            if self.z.unused_data or self.input:fail('Trailing gzip content/member')
            trailing=self.source.read(1)
            if trailing:fail('Trailing compressed content')
            self.done=True
    def read(self,n):
        while len(self.buffer)<n and not self.done:self._pump()
        out=self.buffer[:n];self.buffer=self.buffer[n:];return out
    def exact(self,n):
        out=self.read(n)
        if len(out)!=n:fail('Truncated tar content')
        return out

def pax(raw):
    out={};at=0
    while at<len(raw):
        end=raw.find(b' ',at)
        if end<0:fail('Malformed PAX length')
        try:n=int(raw[at:end])
        except ValueError:fail('Malformed PAX length')
        if n<=end-at+2 or at+n>len(raw) or raw[at+n-1:at+n]!=b'\n':fail('Malformed PAX record')
        row=raw[end+1:at+n-1].decode('utf-8','strict');k,sep,v=row.partition('=')
        if not sep or k in out:fail('Duplicate/malformed PAX key')
        out[k]=v;at+=n
    return out

class Records:
    def __init__(self, claim, binding, helpers):
        self.claim=claim;self.binding=binding;self.helpers=helpers
        self.ids=set();self.latest=None;self.placeholders=[];self.candidates=[];self.top={};self.top_raw={};self.receipt=None;self.roots={}
        self.minimum=canonical_date(claim['minimum_source_date']);self.as_of=canonical_date(claim['as_of'])
        if type(claim['max_source_age_days']) is not int or claim['max_source_age_days']<0:fail('Invalid freshness budget')
    def consume(self,name,raw):
        if name.endswith('/.gitkeep') and not raw:self.placeholders.append(name);return
        if not name.endswith('.json'):fail('Unsupported source record')
        d=strict_json(raw)
        if not name.startswith('data/'):return
        if name=='data/collection_receipt.json':
            self.receipt=d
            if sha(raw)!=self.binding.receipt_sha256:fail('Receipt digest mismatch')
            if not isinstance(d,dict) or 'id' in d or 'variations' in d or d.get('schema')!='boopa-collection-receipt-v1' or d.get('repository')!=REPOSITORY or d.get('scope')!='bounded-filtered-search-observation' or d.get('whole_catalog_complete') is not False:fail('Invalid receipt')
            for key,value in (('run_id',self.binding.run_id),('run_attempt',self.binding.run_attempt),('source_commit',self.binding.source_commit),('reservation_id',self.binding.run_id+'-'+self.binding.run_attempt)):
                if d.get(key)!=value:fail('Receipt identity mismatch')
            if d.get('status') not in ('completed','paused') or d.get('failed') is not False or d.get('reservation_completed') is not True or type(d.get('continueCollection')) is not bool:fail('Receipt outcome mismatch')
            if (d['status']=='completed' and 'reason' in d) or (d['status']=='paused' and d.get('reason') not in ('deadline','day-boundary')):fail('Receipt reason mismatch')
            for k in ('started_at_ms','stopped_at_ms','deadline_ms','blocked_until_ms','pending_retry_count'):
                if type(d.get(k)) is not int or d[k]<0:fail('Invalid receipt counters')
            keys=('searchPages','searchFailures','itemSuccess','itemFailures','unavailable','retries','duplicatesAvoided','chargedHttpAttempts','dailyChargedRequests')
            if not isinstance(d.get('metrics'),dict) or any(type(d['metrics'].get(k)) is not int or d['metrics'][k]<0 for k in keys):fail('Invalid receipt metrics')
            self.roots[name]=sha(raw);return
        if name in ('data/crawl_state.json','data/request_budget.json'):
            if not isinstance(d,dict) or 'id' in d or 'variations' in d:fail('Invalid tracker state')
            self.roots[name]=sha(raw);return
        if not isinstance(d,dict):fail('Invalid product')
        ident=d.get('id')
        if not isinstance(ident,str) or not re.fullmatch('[1-9][0-9]*',ident) or ident in self.ids or name!='data/'+ident[:3]+'/'+ident+'.json':fail('Invalid duplicate product/path')
        self.ids.add(ident);variations=d.get('variations');best=[]
        if not isinstance(variations,dict):fail('Invalid variations')
        for series in variations.values():
            if not isinstance(series,list):fail('Invalid series')
            for row in series:
                if not isinstance(row,dict):fail('Invalid history row')
                day=canonical_date(row.get('date'));price=row.get('price')
                if type(price) not in (int,float) or not math.isfinite(price) or price<0 or day>self.as_of:fail('Invalid observation')
            if len(series)>len(best):best=series
        if best:
            day=max(canonical_date(r['date']) for r in best);self.latest=max(self.latest,day) if self.latest else day
            series=sorted(best,key=lambda p:p['date']);distinct=len({p['price'] for p in series})
            transitions=sum(1 for i in range(1,len(series)) if series[i].get('is_sale') and not series[i-1].get('is_sale'))
            if distinct>=3 and len(series)>=60:
                score=distinct*2+transitions*3+len(series)/50.0
                self.candidates.append((score,ident));self.candidates.sort(reverse=True);del self.candidates[3:]
                self.top[ident]=d;self.top_raw[ident]=raw;keep={i for _,i in self.candidates}
                self.top={i:v for i,v in self.top.items() if i in keep}
                self.top_raw={i:v for i,v in self.top_raw.items() if i in keep}
    def finish(self):
        if not self.ids or self.latest is None or self.latest<self.minimum or (self.as_of-self.latest).days>self.claim['max_source_age_days']:fail('Missing/stale dated products')
        if self.latest.isoformat()!=self.claim.get('expected_date') or ('bound_empty_placeholders' in self.claim and sorted(self.placeholders)!=self.claim['bound_empty_placeholders']):fail('Attestation date/placeholders mismatch')
        if self.receipt is None or set(self.roots)!={'data/collection_receipt.json','data/crawl_state.json','data/request_budget.json'}:fail('Missing receipt/ledger/crawl state')
        v=self.helpers['varutil'];charts=[]
        for _,ident in self.candidates:
            record=self.top[ident];variations=v.thin_vars_from_item(record)
            if not variations:
                raw={name:[[p['date'],p['price'],int(bool(p.get('is_sale')))] for p in sorted(series,key=lambda p:p['date'])] for name,series in record['variations'].items() if isinstance(series,list) and len(series)>=2}
                variations=v.convert_raw_variations(raw)
            charts.append({'id':ident,'name':record.get('name',''),'variations':variations})
        if not charts and not self.claim['fixture']:fail('Nonempty canonical charts required')
        chart_raw=json.dumps(charts,ensure_ascii=False).encode()
        # The canonical validator reads the immutable exact archive bytes for
        # the retained top three, not mutable staged paths or reserialized data.
        captured={'data/'+i[:3]+'/'+i+'.json':raw for i,raw in self.top_raw.items()}
        class CapturedPath:
            def __init__(self,name=''):self.name=name
            def __truediv__(self,name):return CapturedPath(self.name+'/'+name if self.name else name)
            def is_file(self):return self.name in captured
            def read_text(self):return captured[self.name].decode('utf-8','strict')
        self.helpers['charts_contract'].validate_charts(strict_json(chart_raw),CapturedPath(),self.claim['fixture'])
        return chart_raw

def namespace_files(root):
    root=safe_root(root);files=set();dirs=set()
    for base,ds,fs in os.walk(root,followlinks=False):
        for n in ds:
            p=Path(base)/n
            if p.is_symlink():fail('Linked prepared directory')
            dirs.add(p.relative_to(root).as_posix())
        for n in fs:
            p=Path(base)/n
            if not stat.S_ISREG(p.lstat().st_mode):fail('Nonregular prepared file')
            files.add(p.relative_to(root).as_posix())
    return files,dirs

def prepare(source, *, binding, commit_raw, root_raw, producer_raw, inventory_raw=None,
            attestation_raw=None, derive_claim=None, evidence_output=None, output=None, verify_existing=None, limits=Limits(),
            progress=None):
    """Return a derived completion pin only after full source authentication.

    Exactly one of output (new private directory) or verify_existing (read-only)
    must be supplied. Failed materialization leaves an uncommitted private stage;
    no completion.json or success proof is emitted and no cleanup is attempted.
    """
    with contextlib.ExitStack() as stack:
        start=time.monotonic()
        for raw,cap in ((commit_raw,4*1024**2),(root_raw,4*1024**2),(producer_raw,8*1024**2),(inventory_raw,128*1024**2),(attestation_raw,128*1024**2)):
            if raw is not None and (not isinstance(raw,bytes) or len(raw)>cap):fail('Evidence input byte budget exceeded')
        helpers=load_reviewed();root_entries=verify_evidence(binding,commit_raw,root_raw,producer_raw)
        if (output is None)==(verify_existing is None):fail('Choose materialization or read-only verification')
        deriving=inventory_raw is None and attestation_raw is None
        if deriving:
            if not isinstance(derive_claim,dict) or set(derive_claim)!={'expected_date','minimum_source_date','as_of','max_source_age_days','fixture'}:fail('Explicit derivation date/scope settings required')
            claim={'schema':1,'status':'complete','collection_id':binding.saved_commit,'tracker_commit':binding.saved_commit,'completion_scope':SCOPE,**derive_claim}
            inventory=None
        else:
            if inventory_raw is None or attestation_raw is None or derive_claim is not None:fail('Both committed inputs or explicit derivation required')
            claim=strict_json(attestation_raw);inventory=strict_json(inventory_raw)
        if not isinstance(claim,dict) or type(claim.get('schema')) is not int or claim['schema']!=1 or claim.get('status')!='complete' or type(claim.get('fixture')) is not bool or claim.get('tracker_commit')!=binding.saved_commit or claim.get('collection_id')!=binding.saved_commit or claim.get('completion_scope')!=SCOPE:fail('Attestation identity/scope mismatch')
        if not deriving and (not isinstance(inventory,dict) or claim.get('files')!=inventory or claim.get('inventory_digest')!=sha(inventory_raw) or type(claim.get('inventory_count')) is not int or claim['inventory_count']!=len(inventory)):fail('Attestation inventory mismatch')
        if binding.authority=='synthetic-fixture-only' and claim['fixture'] is not True:fail('Fixture authority mismatch')
        target=Path(output if output is not None else verify_existing)
        parent_path=safe_root(target.parent)
        parent=stack.enter_context(Directory(parent_path));before=preflight(parent,limits,output is not None)
        if evidence_output is not None:
            evidence_path=Path(os.path.abspath(evidence_output));target_path=Path(os.path.abspath(target))
            if evidence_path==target_path or target_path in evidence_path.parents or evidence_path in target_path.parents:fail('Evidence directory must be disjoint from prepared namespace')
            evidence=stack.enter_context(Directory(evidence_path))
            if os.fstat(evidence.fd).st_dev!=os.fstat(parent.fd).st_dev:fail('Evidence and prepared roots must share a filesystem')
        if output is not None:
            if target.exists() or target.is_symlink():fail('Output already exists')
            stage_name='.'+target.name+'-uncommitted-'+secrets.token_hex(12)
            os.mkdir(stage_name,0o700,dir_fd=parent.fd)
            fd=os.open(stage_name,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=parent.fd)
            try:stage=stack.enter_context(Directory(fd=fd))
            finally:os.close(fd)
        else:stage=stack.enter_context(Directory(target))
        stream=StrictGzip(source,limits);tree=GitTree(limits.path_bytes);records=Records(claim,binding,helpers)
        prefix='booth-vrc-price-tracker-'+binding.saved_commit
        count=0;seen_global=False;seen_root=False;pending=None;files={};source_bytes=0;all_bytes=0;allocated_bound=0;top_hashes={};created_dirs=set()
        while True:
            block=stream.exact(512)
            if not any(block):
                if any(stream.exact(512)):fail('Missing second tar end block')
                tail=0
                while True:
                    b=stream.read(65536)
                    if not b:break
                    tail+=len(b)
                    if any(b) or tail>1024*1024:fail('Trailing tar content/excess padding')
                if pending is not None:fail('Orphan PAX header')
                break
            t=tarfile.TarInfo.frombuf(block,'utf-8','strict');count+=1
            if count>limits.entries or t.size<0 or t.size>limits.file_bytes:fail('Entry resource limit')
            if t.type in (b'g',b'x'):
                if t.size>16384:fail('PAX resource limit')
                raw=stream.exact(t.size);padding=stream.exact((-t.size)%512)
                if any(padding):fail('Nonzero tar padding')
                attrs=pax(raw)
                if t.type==b'g':
                    if seen_global or seen_root or attrs!={'comment':binding.saved_commit}:fail('Invalid global commit header')
                    seen_global=True
                else:
                    if pending is not None or not set(attrs)<={'path','mtime'}:fail('Unsafe/duplicate PAX overrides')
                    pending=attrs
                continue
            if pending:
                t.name=pending.get('path',t.name);pending=None
            if not seen_global:fail('Missing committed archive header')
            if t.type not in (b'0',b'\0',b'5') or t.issparse() or t.linkname or t.mode&0o7000:fail('Unsafe archive type/mode/link')
            name=t.name.rstrip('/') if t.isdir() else t.name;safe_path(name)
            if name==prefix:
                if seen_root or not t.isdir() or t.size:fail('Invalid duplicate archive root')
                seen_root=True;continue
            if not seen_root or not name.startswith(prefix+'/'):fail('Wrong archive root')
            rel=name[len(prefix)+1:];safe_path(rel)
            if t.isdir():
                if t.size:fail('Nonempty directory')
                tree.add(rel,'40000');continue
            mode='100755' if t.mode&0o111 else '100644'
            used=rel.startswith('data/') or rel.startswith('meta/')
            if used and mode!='100644':fail('Executable source data')
            # The largest single member is bounded; never retain the whole archive.
            raw=stream.exact(t.size);padding=stream.exact((-t.size)%512)
            if any(padding):fail('Nonzero tar member padding')
            all_bytes+=len(raw);tree.add(rel,mode,git_hash(b'blob',raw))
            if not used:continue
            source_bytes+=len(raw);allocated_bound+=((len(raw)+before['block_size']-1)//before['block_size'])*before['block_size']
            if source_bytes>limits.source_bytes:fail('Source resource budget exceeded')
            if output is not None and (allocated_bound>limits.planned_write_bytes or len(files)+1>limits.planned_write_inodes):fail('Write envelope exceeded')
            digest=sha(raw)
            if inventory is not None and inventory.get(rel)!=digest:fail('Source differs from declared inventory: '+rel)
            records.consume(rel,raw)
            prepared='tracker_meta/'+rel[5:] if rel.startswith('meta/') else rel
            files[prepared]=digest
            if output is None:
                consumed=stage.read(prepared,limits.file_bytes)
                if consumed!=raw:fail('Existing prepared consumed bytes differ: '+rel)
            else:
                wanted=set();part=Path(prepared).parent
                while str(part)!='.':wanted.add(part.as_posix());part=part.parent
                new_dirs=wanted-created_dirs
                # Conservative directory-growth allowance plus live checks.
                # This is separate from the final exact allocation accounting.
                directory_bound=(len(created_dirs|wanted)+len(files))*before['block_size']
                if allocated_bound+directory_bound>limits.planned_write_bytes or len(files)+len(created_dirs|wanted)>limits.planned_write_inodes:fail('Source files/directories exceed planned envelope')
                vfs=os.fstatvfs(stage.fd);needed=((len(raw)+vfs.f_frsize-1)//vfs.f_frsize)*vfs.f_frsize+(len(new_dirs)+1)*vfs.f_frsize
                if vfs.f_bavail*vfs.f_frsize<limits.min_free_bytes+needed or vfs.f_favail<limits.min_free_inodes+len(new_dirs)+1:fail('Live materialization reserve exhausted')
                stage.write(prepared,raw);created_dirs.update(wanted)
            if progress and len(files)%50000==0:progress({'files':len(files),'source_bytes':source_bytes,'elapsed_seconds':time.monotonic()-start})
        # Membership, path, modes and contents are authenticated together. The
        # inventory is redundant validation, never source authority on its own.
        source_names={('meta/'+p[len('tracker_meta/'):] if p.startswith('tracker_meta/') else p) for p in files}
        if inventory is not None and source_names!=set(inventory):fail('Missing/extra source inventory member')
        actual_root=tree.digest().hex()
        if actual_root!=binding.root_tree:fail('Full archive Git root mismatch')
        for n in ('data','meta'):
            top_hashes[n]=tree.digest(n).hex()
            if top_hashes[n]!=root_entries[n]['sha']:fail('Source Git subtree mismatch')
        chart_raw=records.finish()
        if deriving:
            inventory={('meta/'+p[len('tracker_meta/'):] if p.startswith('tracker_meta/') else p):h for p,h in sorted(files.items())}
            inventory=dict(sorted(inventory.items()))
            inventory_raw=json.dumps(inventory,indent=1,sort_keys=True).encode()
            claim={'schema':1,'status':'complete','collection_id':binding.saved_commit,'fixture':claim['fixture'],'tracker_commit':binding.saved_commit,'expected_date':records.latest.isoformat(),'completion_scope':SCOPE,'scope_limit':'Not crawl/daily-coverage completion; commit must be verified by caller checkout.','inventory_digest':sha(inventory_raw),'inventory_count':len(inventory),'files':inventory,'as_of':claim['as_of'],'minimum_source_date':claim['minimum_source_date'],'max_source_age_days':claim['max_source_age_days'],'bound_empty_placeholders':sorted(records.placeholders)}
            attestation_raw=(json.dumps(claim,indent=2)+'\n').encode()
        files['charts.json']=sha(chart_raw)
        result={'schema':1,'status':'complete','fixture':claim['fixture'],'collection_id':binding.saved_commit,'tracker_commit':binding.saved_commit,'expected_date':records.latest.isoformat(),'inventory_digest':sha(inventory_raw),'inventory_count':len(inventory),'producer_attestation_sha256':sha(attestation_raw),'bound_empty_placeholders':sorted(records.placeholders),'files':files}
        completion_raw=(json.dumps(result,indent=2)+'\n').encode()
        if output is None:
            if stage.read('charts.json',limits.file_bytes)!=chart_raw:fail('Canonical chart bytes differ')
            old=stage.read('completion.json',128*1024**2)
            if strict_json(old)!=result:fail('Prepared completion semantic mismatch')
            # Preserve original complete serialization, after binding every field.
            completion_raw=old
            actual_files,actual_dirs,actual_allocation=stage.inventory()
            expected_dirs={'data','tracker_meta'}
            for f in files:
                p=Path(f).parent
                while str(p)!='.':expected_dirs.add(p.as_posix());p=p.parent
            if actual_files!=set(files)|{'completion.json'} or actual_dirs!=expected_dirs:fail('Prepared namespace contains missing/extra entries')
        else:
            actual_files,actual_dirs,actual_allocation=stage.inventory()
            block=before['block_size']
            allocation=lambda raw:((len(raw)+block-1)//block)*block
            chart_allocation=allocation(chart_raw);completion_allocation=allocation(completion_raw)
            evidence_allocation=0 if evidence_output is None else sum(allocation(b) for b in (inventory_raw,attestation_raw))
            missing_namespaces={'data','tracker_meta'}-actual_dirs
            missing_directory_allocation=len(missing_namespaces)*block
            remaining=chart_allocation+completion_allocation+evidence_allocation+missing_directory_allocation
            remaining_inodes=2+len(missing_namespaces)+(2 if evidence_output else 0)
            if actual_allocation+remaining>limits.planned_write_bytes or len(actual_files)+len(actual_dirs)+remaining_inodes>limits.planned_write_inodes:fail('Complete write envelope exceeded')
            current=os.fstatvfs(stage.fd)
            if current.f_bavail*current.f_frsize<limits.min_free_bytes+remaining or current.f_favail<limits.min_free_inodes+remaining_inodes:fail('Generated metadata reserve exhausted')
            stage.mkdir('data');stage.mkdir('tracker_meta');stage.write('charts.json',chart_raw)
            for p,h in files.items():
                if sha(stage.read(p,limits.file_bytes))!=h:fail('Staged exact bytes changed before commitment')
            # Filesystem directory allocation can differ from the allowance.
            # Recheck exact allocation and reserve again before commitment.
            actual_files,actual_dirs,actual_allocation=stage.inventory()
            current=os.fstatvfs(stage.fd)
            if actual_allocation+completion_allocation+evidence_allocation>limits.planned_write_bytes or len(actual_files)+len(actual_dirs)+1+(2 if evidence_output else 0)>limits.planned_write_inodes:fail('Complete write envelope exceeded')
            if current.f_bavail*current.f_frsize<limits.min_free_bytes+completion_allocation+evidence_allocation or current.f_favail<limits.min_free_inodes+1+(2 if evidence_output else 0):fail('Generated metadata reserve exhausted')
            stage.write('completion.json',completion_raw)
            rename_noreplace(parent,stage_name,target.name)
            verify_published(parent_path,parent,target,stage)
        if evidence_output is not None:
            with Directory(evidence_path) as reopened_evidence:same_directory(evidence,reopened_evidence)
            evidence.write('input-inventory.json',inventory_raw);evidence.write('attestation.json',attestation_raw)
        if output is not None:verify_published(parent_path,parent,target,stage)
        after=os.fstatvfs(parent.fd)
        return {'schema':'boopa-streamed-source-local-v1','status':'verified','authority':binding.authority,'production_eligible':False,'saved_commit':binding.saved_commit,'root_tree':actual_root,'git_subtrees':top_hashes,'source_file_mode':'100644','commit_evidence_sha256':binding.commit_evidence_sha256,'root_evidence_sha256':binding.root_evidence_sha256,'producer_pin_sha256':binding.producer_pin_sha256,'archive_url_constraint':binding.archive_url,'archive_consumed_sha256':stream.hash.hexdigest(),'archive_consumed_bytes':stream.compressed,'archive_expanded_bytes':stream.expanded,'archive_entries':count,'source_path_bytes':tree.path_bytes,'resource_limits':limits.__dict__,'all_regular_bytes':all_bytes,'inventory_sha256':sha(inventory_raw),'attestation_sha256':sha(attestation_raw),'source_files':len(inventory),'source_bytes':source_bytes,'prepared_data_allocated_bound':allocated_bound,'directory_growth_admission_allowance':(len(actual_dirs)+len(files))*before['block_size'],'prepared_files':len(files),'charts_sha256':sha(chart_raw),'completion_sha256':sha(completion_raw),'receipt_sha256':binding.receipt_sha256,'receipt':records.receipt,'root_source_files':records.roots,'source_date':records.latest.isoformat(),'backend_product_count':len(records.ids),'backend_ids_sha256':sha(json.dumps(sorted(records.ids,key=int),separators=(',',':')).encode()),'verification_only':output is None,'fresh_full_materialization_tested':False,'elapsed_seconds':time.monotonic()-start,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,'free_before':before,'free_after':{'bytes':after.f_bavail*after.f_frsize,'inodes':after.f_favail},'helper_pins':CODE_PINS}
