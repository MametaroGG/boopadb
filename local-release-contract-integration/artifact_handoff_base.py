"""Offline v7-shaped artifact handoff; integrity checks, NOT release authorization."""
import argparse,hashlib,io,json,os,stat,subprocess,sys,tarfile,tempfile,unicodedata
from pathlib import Path,PurePosixPath
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE/'validators'))
from validate_bindings import load_strict_json,load_typed,check_ledger
INPUT_NAMES=('attestation.json','prepared-input.json','input-inventory.json','input-inventory-summary.json')
WORK_NAMES=(*INPUT_NAMES,'hash-ledger.json','qa-archive.json')
KINDS={'attestation.json':'attestation','prepared-input.json':'prepared-input','input-inventory.json':'ledger','input-inventory-summary.json':'input-inventory-summary','hash-ledger.json':'ledger','qa-archive.json':'qa-archive'}
def sha(blob):return hashlib.sha256(blob).hexdigest()
def encode(obj):return (json.dumps(obj,sort_keys=True,ensure_ascii=False,indent=2,allow_nan=False)+'\n').encode()
def cli(script,*args):
 result=subprocess.run([sys.executable,str(HERE/'validators'/script),*map(str,args)],capture_output=True,text=True)
 if result.returncode:raise ValueError(script+': '+result.stdout+result.stderr)
 return result.stdout.strip()
def _path(name):
 p=PurePosixPath(name)
 if not name or p.is_absolute() or '..' in p.parts or '.git' in p.parts or p.as_posix()!=name or '\\' in name:raise ValueError('unsafe/noncanonical path: '+name)
 return name
def _tree(root):
 root=Path(root)
 if root.is_symlink() or not root.is_dir():raise ValueError('regular tree required')
 files={};directories=[];seen=set()
 for base,dirs,names in os.walk(root,followlinks=False):
  for name in dirs+names:
   p=Path(base)/name;rel=_path(p.relative_to(root).as_posix());fold=unicodedata.normalize('NFC',rel).casefold()
   if fold in seen:raise ValueError('path collision')
   seen.add(fold);mode=p.lstat().st_mode
   if stat.S_ISLNK(mode) or not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):raise ValueError('nonregular tree member')
   if stat.S_ISDIR(mode):directories.append(rel)
   else:files[rel]=p.read_bytes()
 if not files:raise ValueError('empty tree')
 if any(not any(n.startswith(d+'/') for n in files) for d in directories):raise ValueError('empty directory')
 return files
def _bindings(work,expected_inventory_digest,expected_commit,expected_date):
 work=Path(work);objects={}
 if work.is_symlink() or not work.is_dir():raise ValueError('regular work directory required')
 for name in INPUT_NAMES:
  p=work/name
  if p.is_symlink() or not p.is_file():raise ValueError('required regular work file missing: '+name)
  cli('validate_bindings.py',KINDS[name],p);objects[name]=load_typed(KINDS[name],p)
 inv=objects['input-inventory.json'];actual=sha((work/'input-inventory.json').read_bytes())
 if actual!=expected_inventory_digest:raise ValueError('input inventory byte commitment mismatch')
 att=objects['attestation.json'];prepared=objects['prepared-input.json'];summary=objects['input-inventory-summary.json']
 for obj in (att,prepared,summary):
  if obj['inventory_digest']!=actual:raise ValueError('inventory binding mismatch')
 for obj in (att,prepared):
  if obj['tracker_commit']!=expected_commit or obj['expected_date']!=expected_date:raise ValueError('commit/date binding mismatch')
 if att['completion_scope']!='immutable-captured-snapshot-integrity':raise ValueError('unsupported attestation scope')
 if att['inventory_count']!=len(inv) or summary['inventory_count']!=len(inv) or summary['files']!=len(inv):raise ValueError('inventory count mismatch')
 nonjson=sorted(n for n in inv if not n.endswith('.json'))
 if sorted(summary['non_json_files'])!=nonjson:raise ValueError('non-JSON inventory mismatch')
 return objects

def pack(site,work,dest):
 site,work,dest=map(Path,(site,work,dest))
 if dest.exists() or dest.is_symlink():raise ValueError('artifact destination must not exist')
 att=load_typed('attestation',work/'attestation.json')
 _bindings(work,att['inventory_digest'],att['tracker_commit'],att['expected_date'])
 content=_tree(site);ledger=check_ledger({n:sha(b) for n,b in content.items()})
 # Write only in isolated new staging folder; originals never altered.
 with tempfile.TemporaryDirectory(prefix='.artifact-',dir=dest.parent) as td:
  stage=Path(td);outwork=stage/'work';outwork.mkdir()
  for name in INPUT_NAMES:(outwork/name).write_bytes((work/name).read_bytes())
  (outwork/'hash-ledger.json').write_bytes(encode(ledger))
  cli('verify_inventory.py',outwork/'hash-ledger.json',site)
  archive=stage/'site-release.tar'
  with tarfile.open(archive,'w',format=tarfile.USTAR_FORMAT) as tf:
   for name,blob in sorted(content.items()):
    info=tarfile.TarInfo(name);info.size=len(blob);info.mtime=0;info.uid=info.gid=0;info.uname=info.gname='';info.mode=0o644;tf.addfile(info,io.BytesIO(blob))
  data=archive.read_bytes();record={'archive':'site-release.tar','sha256':sha(data),'bytes':len(data)}
  (outwork/'qa-archive.json').write_bytes(encode(record));cli('validate_bindings.py','qa-archive',outwork/'qa-archive.json')
  # Commit only after verifying copied commitments again.
  _bindings(outwork,att['inventory_digest'],att['tracker_commit'],att['expected_date'])
  if dest.exists() or dest.is_symlink():raise ValueError('artifact destination appeared')
  stage.rename(dest)
 return record

def validate(artifact,dest,expected_inventory_digest,expected_commit,expected_date):
 artifact,dest=map(Path,(artifact,dest))
 if dest.exists() or dest.is_symlink():raise ValueError('validation destination must not exist')
 files=_tree(artifact);required={'site-release.tar',*('work/'+n for n in WORK_NAMES)}
 if set(files)!=required:raise ValueError('artifact exact layout mismatch')
 work=artifact/'work';_bindings(work,expected_inventory_digest,expected_commit,expected_date)
 for name in ('hash-ledger.json','qa-archive.json'):cli('validate_bindings.py',KINDS[name],work/name)
 record=load_typed('qa-archive',work/'qa-archive.json');blob=files['site-release.tar']
 if record['archive']!='site-release.tar' or record['sha256']!=sha(blob) or record['bytes']!=len(blob):raise ValueError('archive byte binding mismatch')
 # Strong canonical-name preflight supplements unchanged reviewed extractor.
 with tarfile.open(fileobj=io.BytesIO(blob)) as tf:
  seen=set()
  for m in tf.getmembers():
   name=_path(m.name);key=unicodedata.normalize('NFC',name).casefold()
   if key in seen or not m.isfile():raise ValueError('duplicate or nonregular archive member')
   seen.add(key)
 cli('safe_extract.py',artifact/'site-release.tar',dest)
 cli('verify_inventory.py',work/'hash-ledger.json',dest)
 return {'status':'offline-integrity-validated','inventory_digest':expected_inventory_digest,'tracker_commit':expected_commit,'expected_date':expected_date,'site_files':len(load_typed('ledger',work/'hash-ledger.json')),'archive_sha256':record['sha256'],'scope':'typed input bindings, archive bytes, safe extraction, exact site ledger only','not_validated':['runtime/UI QA','projection eligibility','review authority','generation lineage','deployment']}

def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 a=sub.add_parser('pack');a.add_argument('--site',required=True);a.add_argument('--work',required=True);a.add_argument('--dest',required=True)
 a=sub.add_parser('validate');a.add_argument('--artifact',required=True);a.add_argument('--dest',required=True);a.add_argument('--expected-inventory-digest',required=True);a.add_argument('--expected-commit',required=True);a.add_argument('--expected-date',required=True)
 a=p.parse_args()
 result=pack(a.site,a.work,a.dest) if a.command=='pack' else validate(a.artifact,a.dest,a.expected_inventory_digest,a.expected_commit,a.expected_date)
 print(json.dumps(result,indent=2))
if __name__=='__main__':main()
