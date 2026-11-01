import json, pathlib, subprocess
expected = {'.gitattributes': {'mode': '100644', 'type': 'blob', 'sha': 'dfe0770424b2a19faf507a501ebfc23be8f54e7b'}, '.gitignore': {'mode': '100644', 'type': 'blob', 'sha': '836703e46e7f5b62c4a338b6f436c6658467e454'}, 'Boopa - BOOTH Price Tracker for VRChat.zip': {'mode': '100644', 'type': 'blob', 'sha': '8c095a39310ed80ef4c45598c46cb70b8dc5ffd9'}, 'assets': {'mode': '040000', 'type': 'tree', 'sha': '47b48dc7bf27d979b35e03c52b7b2022673bce99'}, 'booth-vrc-price-tracker.code-workspace': {'mode': '100644', 'type': 'blob', 'sha': '362d7c25bb405a5cc76d0c7518cc240999a574f4'}, 'dist': {'mode': '040000', 'type': 'tree', 'sha': '01afd779feeac8df3a5a389fe323983884fb87d4'}, 'docs': {'mode': '040000', 'type': 'tree', 'sha': '443fe1722c5902d9a65ae61471396520debeec2d'}, 'extension.crx': {'mode': '100644', 'type': 'blob', 'sha': 'b978dcc922eae497deeca803ccfe8af5bf46ad05'}, 'extension': {'mode': '040000', 'type': 'tree', 'sha': 'da7dc038a4610239e0a612dd4f5918040ceb3785'}, 'index.html': {'mode': '100644', 'type': 'blob', 'sha': 'ce0a431c77fdf0d36e59e1ea17506fa1e8eb1e51'}, 'package-lock.json': {'mode': '100644', 'type': 'blob', 'sha': '43cc06c1bf40ed032d7704ca2e43c8caa2c93339'}, 'package.json': {'mode': '100644', 'type': 'blob', 'sha': 'b4a70f1c8f4faed1ffd3e843d3315f86c341bb15'}, 'scripts': {'mode': '040000', 'type': 'tree', 'sha': '8d25af313c5ce0e38068fb126832ffdcf6c893fe'}, 'src': {'mode': '040000', 'type': 'tree', 'sha': 'f87362be086663c18704f1dc88e730273b85283d'}, 'test': {'mode': '040000', 'type': 'tree', 'sha': '9fda80fc15cd5dde6f7ab42b6d0b2133777095dc'}, 'write-save-receipt.cjs': {'mode': '100644', 'type': 'blob', 'sha': '00d22b6a011c5667a5a48db7d973e1d2e9339863'}}
raw = subprocess.check_output(['git','ls-tree','-z','HEAD'])
actual = {}
for row in raw.split(b'\0'):
    if not row: continue
    info, name = row.decode().split('\t',1)
    mode, kind, sha = info.split()
    if name not in ('data','meta','.github'):
        actual[name] = dict(mode=mode,type=kind,sha=sha)
if actual != expected: raise SystemExit('Unreviewed collector source tree; stop before executing repository code')
subprocess.run(['git','diff','--exit-code','--quiet','HEAD','--','.',':!data',':!meta',':!.github'],check=True)
others = subprocess.check_output(['git','ls-files','--others','-z']).split(b'\0')
for entry in others:
    if entry and entry.decode().split('/',1)[0] not in ('data','meta','.github','node_modules'):
        raise SystemExit('Untracked source/config file; stop before executing repository code')
if pathlib.Path('.npmrc').exists(): raise SystemExit('Unreviewed npm configuration')
