"""Synthetic contract tests only; not approval of any real supplemental claim."""
import hashlib,json,tempfile,unittest,struct,zlib
from pathlib import Path
from preserve_relation_supplement import validate,configure,check_import,SCHEMA,LOGO_PATH,validate_png

def encode(v):return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
class SupplementTest(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.bundle=self.root/'bundle';self.bundle.mkdir();(self.bundle/'relation-supplement').mkdir()
  self.relations={'status':'approved-bundle','activate':True,'version':'a'*64}
  self.items={'123':{'tools':[],'references':[{'kind':'booth_reference','id':'456','name':'Synthetic reference','status':'reviewed_reference','sourceAge':'historical_capture_unknown','evidenceSha256':'b'*64}]}}
  self.write()
 def tearDown(self):self.tmp.cleanup()
 def write(self):
  base={'schema':SCHEMA,'sourceVersion':'a'*64,'items':self.items};version=sha(encode(base));d={**base,'version':version};raw=encode(d)
  m={'schema':SCHEMA,'sourceVersion':'a'*64,'version':version,'itemIds':list(self.items),'files':{'items.json':{'bytes':len(raw),'sha256':sha(raw)}}}
  (self.bundle/'relation-supplement/items.json').write_bytes(raw);(self.bundle/'relation-supplement/manifest.json').write_bytes(encode(m));(self.bundle/'relationship-supplement.js').write_bytes(b'/* synthetic inert fixture */')
  self.approval={'schema':1,'status':'approved','activate':True,'scope':'local-test-only','version':version,'sourceVersion':'a'*64,'files':{p.relative_to(self.bundle).as_posix():sha(p.read_bytes()) for p in self.bundle.rglob('*') if p.is_file()}}
  self.path=self.root/'approval.json';self.path.write_bytes(encode(self.approval))
 def html(self):return '<script src="relationship-supplement.js?v='+self.approval['files']['relationship-supplement.js'][:16]+'"></script>'
 def test_exact_approved_bundle_configured(self):
  output=self.root/'out';output.mkdir();(output/'index.html').write_text(self.html());result=configure(output,self.bundle,self.path,self.relations)
  self.assertTrue(result['activate']);self.assertEqual(result['scope'],'local-test-only');validate(output,result,self.relations)
 def test_no_approval_strips_only_known_import(self):
  output=self.root/'out';output.mkdir();p=output/'index.html';p.write_text(self.html()+'<script src="other.js"></script>');self.assertEqual(configure(output,None,None,self.relations),'disabled');self.assertEqual(p.read_text(),'<script src="other.js"></script>')
 def test_corruption_and_source_mismatch_rejected(self):
  with self.assertRaisesRegex(ValueError,'matching'):validate(self.bundle,self.approval,{**self.relations,'version':'c'*64})
  (self.bundle/'relationship-supplement.js').write_text('corrupt')
  with self.assertRaisesRegex(ValueError,'integrity'):validate(self.bundle,self.approval,self.relations)
 def test_invalid_reference_and_unreviewed_tool_rejected_even_rehashed(self):
  self.items['123']['references'][0]['id']='123';self.write()
  with self.assertRaisesRegex(ValueError,'reference'):validate(self.bundle,self.approval,self.relations)
  self.items['123']['references']=[];self.items['123']['tools']=[{'kind':'external_tool','toolKey':'guessed','status':'reviewed_required'}];self.write()
  with self.assertRaisesRegex(ValueError,'tool'):validate(self.bundle,self.approval,self.relations)
 def test_forged_internal_inventory_and_content_version_rejected(self):
  p=self.bundle/'relation-supplement/manifest.json';m=json.loads(p.read_bytes());m['files']['items.json']['bytes']+=1;p.write_bytes(encode(m));self.approval['files'][p.relative_to(self.bundle).as_posix()]=sha(p.read_bytes())
  with self.assertRaisesRegex(ValueError,'internal'):validate(self.bundle,self.approval,self.relations)
  self.write();p=self.bundle/'relation-supplement/items.json';d=json.loads(p.read_bytes());d['items']['123']['references'][0]['name']='changed';p.write_bytes(encode(d));self.approval['files'][p.relative_to(self.bundle).as_posix()]=sha(p.read_bytes())
  with self.assertRaisesRegex(ValueError,'content-derived'):validate(self.bundle,self.approval,self.relations)
 def test_current_source_date_required(self):
  ref=self.items['123']['references'][0];ref['sourceAge']='seller_reviewed_at';self.write()
  with self.assertRaisesRegex(ValueError,'observation'):validate(self.bundle,self.approval,self.relations)
  ref['observedAt']='2026-10-29';self.write();validate(self.bundle,self.approval,self.relations)
 def add_logo(self):
  def chunk(kind,b):return struct.pack('>I',len(b))+kind+b+struct.pack('>I',zlib.crc32(kind+b)&0xffffffff)
  png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',1,1,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(b'\0\xff\xff\xff\xff'))+chunk(b'IEND',b'')
  p=self.bundle/LOGO_PATH;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(png);self.approval['files'][LOGO_PATH]=sha(png)
  ui=self.bundle/'relationship-ui-draft.js';ui.write_text('const media=\'<img src="'+LOGO_PATH+'?v='+sha(png)[:16]+'">\';')
  self.relations['files']={'relationship-ui-draft.js':sha(ui.read_bytes())}
 def test_optional_logo_bound_to_approved_renderer_and_hash(self):
  self.add_logo();validate(self.bundle,self.approval,self.relations)
  del self.approval['files'][LOGO_PATH]
  with self.assertRaisesRegex(ValueError,'requires approved logo'):validate(self.bundle,self.approval,self.relations)
 def test_logo_query_mismatch_rejected_even_with_rehashed_renderer(self):
  self.add_logo();ui=self.bundle/'relationship-ui-draft.js';ui.write_text(ui.read_text().replace('?v=','?v=bad'));self.relations['files']['relationship-ui-draft.js']=sha(ui.read_bytes())
  with self.assertRaisesRegex(ValueError,'Logo reference'):validate(self.bundle,self.approval,self.relations)
 def test_non_png_or_corrupt_logo_rejected_even_when_rehashed(self):
  self.add_logo();p=self.bundle/LOGO_PATH
  for b in (b'<svg><script>bad</script></svg>',p.read_bytes()+b'extra',p.read_bytes()[:-1]+b'X'):
   p.write_bytes(b);self.approval['files'][LOGO_PATH]=sha(b)
   with self.assertRaises(ValueError):validate(self.bundle,self.approval,self.relations)
 def test_stale_or_duplicate_import_rejected(self):
  check_import(self.html(),self.approval)
  for html in (self.html().replace('?v=','?v=bad'),self.html()*2):
   with self.assertRaisesRegex(ValueError,'import'):check_import(html,self.approval)
if __name__=='__main__':unittest.main()
