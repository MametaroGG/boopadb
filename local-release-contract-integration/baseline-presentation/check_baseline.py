"""Read-only baseline evidence preservation regression; no generation authority."""
import hashlib, json, pathlib, re, shutil, sys, tempfile
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'local-release-contract-integration/generator'))
from projection_integration import apply_presentation
from current_price_projection import digest
proof_path=ROOT/'local-price-baseline-review/presentation-proof.exact.json'
proof=json.loads(proof_path.read_text())
sha='1d98251b5d5b3ffd9e038e13b2f440f18c111db703dcc698c4a8f29031df4517'
assert digest(proof)==sha
source=ROOT/'local-release-contract-integration/tests/fixtures'
blobs={'index.html':'cebee521935ebe0cb72723d0faa443fa6d422c9d','item.html':'aa523fc3ea5b5b654b1110a5a80fe742027359b2'}
pattern=r'<script id="price-presentation-proof">const PRICE_PRESENTATION = (.*?);</script>'
with tempfile.TemporaryDirectory(prefix='baseline-presentation-') as td:
 target=pathlib.Path(td)
 for name,expected in blobs.items():
  data=(source/name).read_bytes()
  assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==expected
  original=re.search(pattern,data.decode(),re.S)[1]
  assert original.encode()==proof_path.read_bytes()
  shutil.copyfile(source/name,target/name)
 apply_presentation(target,proof,sha)
 for name in blobs:
  rendered=(target/name).read_text()
  assert json.loads(re.search(pattern,rendered,re.S)[1])==proof
  assert all(m not in rendered for m in ('createCurrentPriceProjection','CurrentPrices','current-price-projection'))
  assert 'comparisonSuppressed' in rendered and 'comparisonMarkup' in rendered
  assert 'historySaleLabel' in rendered and 'ppStats' in rendered
 assert not (target/'current-price-projection.json').exists()
 try:apply_presentation(target,proof,'0'*64)
 except ValueError:pass
 else:raise AssertionError('mismatched digest accepted')
assert all(e['variant_coverage']=='unknown' and 'current_variants' not in e for e in proof['entries'].values())
print('PASS exact public blobs and embedded bytes; canonical binding; unchanged consumer apply; 4 entries preserved; no projection minted; mismatch refused')
print('NOT RUN: complete current-generation build, browser QA, publication, authority authentication')
