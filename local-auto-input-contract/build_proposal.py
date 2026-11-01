"""Regenerate only local proposal/pins from immutable read-only evidence."""
from pathlib import Path
import hashlib,json,difflib
R=Path(__file__).parent

def obj(kind,b):return hashlib.sha1(kind.encode()+b' '+str(len(b)).encode()+b'\0'+b).hexdigest()
def tree(entries):
 entries=sorted(entries,key=lambda e:(e['path']+('/' if e['type']=='tree' else '')).encode())
 b=b''.join((e['mode'].lstrip('0')+' '+e['path']).encode()+b'\0'+bytes.fromhex(e['sha']) for e in entries)
 return obj('tree',b)
root=json.loads((R/'evidence/tree-root.json').read_text())['tree']
for dirname,updates in [('src',['scraper.js','collection-receipt.js']),('scripts',['push-data.sh']),('test',['workflow.test.js'])]:
 data=json.loads((R/f'evidence/tree-{dirname}.json').read_text())
 direct=[e for e in data['tree'] if '/' not in e['path']]
 assert tree(direct)==data['sha']
 entries={e['path']:e.copy() for e in direct}
 for name in updates:entries[name]={'path':name,'mode':'100644','type':'blob','sha':obj('blob',(R/'proposed'/dirname/name).read_bytes())}
 for entry in root:
  if entry['path']==dirname:entry['sha']=tree(list(entries.values()))
root.append({'path':'write-save-receipt.cjs','mode':'100644','type':'blob','sha':obj('blob',(R/'proposed/write-save-receipt.cjs').read_bytes())})
expected={e['path']:{k:e[k] for k in ['mode','type','sha']} for e in root if e['path'] not in ['data','meta','.github']}
inline='''import json, pathlib, subprocess
expected = '''+repr(expected)+'''
raw = subprocess.check_output(['git','ls-tree','-z','HEAD'])
actual = {}
for row in raw.split(b'\\0'):
    if not row: continue
    info, name = row.decode().split('\\t',1)
    mode, kind, sha = info.split()
    if name not in ('data','meta','.github'):
        actual[name] = dict(mode=mode,type=kind,sha=sha)
if actual != expected: raise SystemExit('Unreviewed collector source tree; stop before executing repository code')
subprocess.run(['git','diff','--exit-code','--quiet','HEAD','--','.',':!data',':!meta',':!.github'],check=True)
others = subprocess.check_output(['git','ls-files','--others','-z']).split(b'\\0')
for entry in others:
    if entry and entry.decode().split('/',1)[0] not in ('data','meta','.github','node_modules'):
        raise SystemExit('Untracked source/config file; stop before executing repository code')
if pathlib.Path('.npmrc').exists(): raise SystemExit('Unreviewed npm configuration')
'''
(R/'source-gate.INLINE.py').write_text(inline)
def gate(name,record=False):
 text='      - name: '+name+'\n        timeout-minutes: 1\n        run: |\n          python3 -I - <<\'PY\'\n'
 text+=''.join('          '+line+'\n' for line in inline.splitlines())+'          PY\n'
 if record:text+='          echo "COLLECTOR_SOURCE_COMMIT=$(git rev-parse HEAD)" >> "$GITHUB_ENV"\n'
 return text+'\n'
workflow=(R/'evidence/.github__workflows__daily_scrape.yml').read_text()
# Five new 1-minute guards/receipt steps fit the original 359-minute envelope.
workflow=workflow.replace('        timeout-minutes: 20\n', '        timeout-minutes: 15\n', 1)
workflow=workflow.replace('      - name: Setup Node.js',gate('Verify reviewed source before dependencies')+'      - name: Setup Node.js')
workflow=workflow.replace('      - name: Run Scraper',gate('Verify reviewed source before collection',True)+'      - name: Run Scraper')
workflow=workflow.replace('      - name: Report scraper failure',gate('Verify reviewed source after save')+'      - name: Report scraper failure')
snippet=(R/'workflow-receipt.PROPOSAL.yml').read_text();snippet=snippet[snippet.index('      - name:'):]
snippet=snippet.replace('REVIEWED_FULL_COMMIT_SHA_REQUIRED','ea165f8d65b6e75b540449e92b4886f43607fa02')
snippet=snippet.replace('        # An approved immutable action SHA is intentionally NOT invented here.','        # Verified upstream upload-artifact v4.6.2 commit; local proposal only.')
workflow+='\n'+snippet
(R/'proposed/.github/workflows/daily_scrape.yml').write_text(workflow)
files=['src/scraper.js','src/collection-receipt.js','src/collection-runtime.js','src/continuation.js','scripts/push-data.sh','write-save-receipt.cjs']
contents={n:(R/'proposed'/n).read_bytes() if (R/'proposed'/n).exists() else (R/'evidence'/n.replace('/','__')).read_bytes() for n in files}
pin=dict(schema='boopa-producer-pin-v1',repository='MametaroGG/booth-vrc-price-tracker',
 workflow_sha256=hashlib.sha256(workflow.encode()).hexdigest(),
 files_sha256={n:hashlib.sha256(b).hexdigest() for n,b in contents.items()},source_root_entries=expected)
(R/'producer-pin.PROPOSAL.json').write_text(json.dumps(pin,indent=2,sort_keys=True)+'\n')
chunks=[]
for n in ['src/scraper.js','scripts/push-data.sh','src/collection-receipt.js','write-save-receipt.cjs','.github/workflows/daily_scrape.yml','test/workflow.test.js']:
 old_path=R/'evidence'/n.replace('/','__');old=old_path.read_text() if old_path.exists() else ''
 new=(R/'proposed'/n).read_text()
 chunks.extend(difflib.unified_diff(old.splitlines(True),new.splitlines(True),fromfile='a/'+n if old else '/dev/null',tofile='b/'+n))
(R/'producer-receipt.PROPOSAL.patch').write_text(''.join(chunks))
