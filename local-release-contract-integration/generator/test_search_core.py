import contextlib,hashlib,io,json,tempfile,unittest
from pathlib import Path
from build_site import load_trusted

class SearchCore(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
  for i in range(24):
   row=[str(i+1),'title-'+str(i),i,100,0,0,1,'category',i,'image-'+str(i),20261029,1,'shop','tag']
   (self.root/f'search_index_{i}.json').write_text(json.dumps([row]))
  with contextlib.redirect_stdout(io.StringIO()):
   self.report=load_trusted('build-search-core').build(self.root,write_report=False)
  self.manifest={'catalog_core':self.report['catalog_core'],'files':{p.relative_to(self.root).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in self.root.rglob('*.json')}}
  self.validate=load_trusted('validate_search_core').validate
 def tearDown(self):self.tmp.cleanup()
 def rewrite(self,name,data):
  p=self.root/name;p.write_text(json.dumps(data));self.manifest['files'][name]=hashlib.sha256(p.read_bytes()).hexdigest()
 def test_exact_recombination_and_no_reports(self):
  self.assertEqual(self.validate(self.root,self.manifest,required=True),self.report['catalog_core'])
  self.assertFalse((self.root/'reports').exists())
  with contextlib.redirect_stdout(io.StringIO()):load_trusted('build-search-core').build(self.root,check=True,write_report=False)
 def test_core_price_tamper_even_with_rehashed_manifest_rejected(self):
  name='search-core/core_0.json';rows=json.loads((self.root/name).read_text());rows['data'][2][0]=999;self.rewrite(name,rows)
  with self.assertRaisesRegex(ValueError,'recombination'):self.validate(self.root,self.manifest,required=True)
 def test_image_tamper_even_with_rehashed_manifest_rejected(self):
  name='search-core/images_1.json';self.rewrite(name,{'1':'wrong-image'})
  with self.assertRaisesRegex(ValueError,'recombination'):self.validate(self.root,self.manifest,required=True)
 def test_missing_bucket_rejected(self):
  (self.root/'search-core/images_1.json').unlink()
  with self.assertRaisesRegex(ValueError,'536'):self.validate(self.root,self.manifest,required=True)
 def test_extra_namespace_file_rejected(self):
  self.rewrite('search-core/extra.json',{})
  with self.assertRaisesRegex(ValueError,'536'):self.validate(self.root,self.manifest,required=True)
 def test_missing_declaration_rejected(self):
  del self.manifest['catalog_core']
  with self.assertRaisesRegex(ValueError,'declaration'):self.validate(self.root,self.manifest,required=True)
 def test_incorrect_count_rejected(self):
  self.manifest['catalog_core']['rows']=23
  with self.assertRaisesRegex(ValueError,'declaration'):self.validate(self.root,self.manifest,required=True)
 def test_image_bucket_ownership_rejected(self):
  self.rewrite('search-core/images_1.json',{'2':'image-1'})
  with self.assertRaisesRegex(ValueError,'bucket'):self.validate(self.root,self.manifest,required=True)

 def test_boolean_part_count_rejected(self):
  self.manifest['catalog_core']['part_rows'][0]=True
  with self.assertRaisesRegex(ValueError,'integer types'):self.validate(self.root,self.manifest,required=True)
 def test_validation_count_mismatch_rejected(self):
  self.manifest['validation']={'rows':23}
  with self.assertRaisesRegex(ValueError,'validation row count'):self.validate(self.root,self.manifest,required=True)

 def test_boolean_for_numeric_price_rejected(self):
  name='search-core/core_0.json';rows=json.loads((self.root/name).read_text());rows['data'][2][0]=False;self.rewrite(name,rows)
  with self.assertRaisesRegex(ValueError,'recombination'):self.validate(self.root,self.manifest,required=True)
 def test_float_for_integer_flag_rejected(self):
  name='search-core/core_0.json';rows=json.loads((self.root/name).read_text());rows['data'][5][0]=0.0;self.rewrite(name,rows)
  with self.assertRaisesRegex(ValueError,'recombination'):self.validate(self.root,self.manifest,required=True)

 def test_unknown_compact_format_rejected(self):
  name='search-core/core_0.json';obj=json.loads((self.root/name).read_text());obj['format']='unknown';self.rewrite(name,obj)
  with self.assertRaisesRegex(ValueError,'schema'):self.validate(self.root,self.manifest,required=True)
 def test_malformed_dictionary_reference_rejected(self):
  for bad in [-1,999,False,0.0,'0']:
   name='search-core/core_0.json';obj=json.loads((self.root/name).read_text());obj['data'][7][0]=bad;self.rewrite(name,obj)
   with self.assertRaisesRegex(ValueError,'reference'):self.validate(self.root,self.manifest,required=True)
 def test_empty_tag_array_rejected(self):
  name='search-core/core_0.json';obj=json.loads((self.root/name).read_text());obj['data'][13][0]=[];self.rewrite(name,obj)
  with self.assertRaisesRegex(ValueError,'tag references'):self.validate(self.root,self.manifest,required=True)
 def test_deterministic_compact_regeneration(self):
  before={p.name:p.read_bytes() for p in (self.root/'search-core').glob('*')}
  with contextlib.redirect_stdout(io.StringIO()):load_trusted('build-search-core').build(self.root,write_report=False)
  self.assertEqual(before,{p.name:p.read_bytes() for p in (self.root/'search-core').glob('*')})
 def test_codec_expansion_budgets(self):
  codec=load_trusted('compact_codec')
  row=['1','title',0,0,0,0,1,'category',0,'',20261030,0,'shop','tag']
  for kind in ['string','dictionary-total','references','joined-tag','joined-total','rows','dict-count']:
   obj=codec.encode([row])
   if kind=='string':obj['tags']=['😀'*32769]
   elif kind=='dictionary-total':obj['tags']=[str(i)+'x'*65530 for i in range(65)]
   elif kind=='references':obj['data'][13][0]=[0]*4097
   elif kind=='joined-tag':obj['tags']=['😀'*16384];obj['data'][13][0]=[0,0]
   elif kind=='joined-total':
    obj=codec.encode([row]*513);obj['tags']=['x'*65536];obj['data'][13]=[[0]]*513
   elif kind=='rows':obj['data']=[[c[0]]*100001 for c in obj['data']]
   elif kind=='dict-count':obj['tags']=['x']*1000001
   with self.subTest(kind=kind),self.assertRaises(ValueError):codec.decode(obj)
 def test_utf16_boundary(self):
  codec=load_trusted('compact_codec');row=['1','title',0,0,0,0,1,'category',0,'',20261030,0,'shop','😀'*32768]
  self.assertTrue(codec.exact(codec.decode(codec.encode([row])),[row]))
 def test_legacy_image_free_migration_validation(self):
  for i in range(24):
   original=json.loads((self.root/f'search_index_{i}.json').read_text());original[0][9]='';self.rewrite(f'search-core/core_{i}.json',original)
  self.manifest['catalog_core']['format']='image-free-v1'
  self.assertEqual(self.validate(self.root,self.manifest,required=True)['format'],'image-free-v1')
 def test_unknown_manifest_format_rejected(self):
  self.manifest['catalog_core']['format']='unknown'
  with self.assertRaisesRegex(ValueError,'format'):self.validate(self.root,self.manifest,required=True)
