import unittest,tempfile,json,hashlib
from pathlib import Path
from plan_connector_handoff import make_plan,sha,oid,git_tree
class TestHandoff(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.r=Path(self.tmp.name);self.c=self.r/'candidate';self.c.mkdir();self.parent='a'*40
  b=b'{"x":1}';(self.c/'lists_full.json').write_bytes(b)
  m={'files':{'lists_full.json':sha(b)}};(self.c/'snapshot-manifest.json').write_text(json.dumps(m));self.files={p.name:sha(p.read_bytes()) for p in self.c.iterdir()}
  self.plan={'status':'dry-run-plan','single_commit_required':True,'delete_paths':[],'owner':'MametaroGG','repository':'boopadb','branch':'main','expected_parent_commit':self.parent,'fixture':False,'files':self.files,'candidate_manifest_sha256':self.files['snapshot-manifest.json']}
  self.old={'lists_full.json':{'sha':oid('blob',b),'mode':'100644'},'README.md':{'sha':oid('blob',b'keep'),'mode':'100644'}};self.tree={'truncated':False,'tree':[dict(path=k,type='blob',**v) for k,v in self.old.items()]}
  self.write()
 def write(self):
  (self.r/'plan').write_text(json.dumps(self.plan));(self.r/'tree').write_text(json.dumps(self.tree))
 def call(self,**kw):
  return make_plan(self.c,self.r/'plan',sha((self.r/'plan').read_bytes()),self.r/'tree',sha((self.r/'tree').read_bytes()),git_tree(self.old),self.parent,**kw)
 def tearDown(self):self.tmp.cleanup()
 def test_reuse_preserve_no_publish(self):
  x=self.call();self.assertEqual(x['reused'],['lists_full.json']);self.assertEqual(x['preserve_unrelated'],['README.md']);self.assertFalse(x['publication_authorized']);self.assertFalse(x['recurring_trigger_installed'])
 def test_changed_bytes(self):
  (self.c/'lists_full.json').write_text('changed')
  with self.assertRaisesRegex(ValueError,'hash mismatch'):self.call()
 def test_extra_file(self):
  (self.c/'private.json').write_text('secret')
  with self.assertRaisesRegex(ValueError,'inventory'):self.call()
 def test_symlink(self):
  (self.c/'evil').symlink_to(self.r/'plan')
  with self.assertRaisesRegex(ValueError,'symlink'):self.call()
 def test_truncated_tree(self):
  self.tree['truncated']=True;self.write()
  with self.assertRaisesRegex(ValueError,'incomplete'):self.call()
 def test_budget_is_not_capability(self):
  x=self.call(request_budget=10);self.assertEqual(x['over_budget'],['snapshot-manifest.json']);self.assertFalse(x['endpoint_limit_verified'])
 def test_wrong_tree_oid(self):
  self.tree['tree'][0]['sha']='0'*40;self.write()
  with self.assertRaisesRegex(ValueError,'reconstruction'):self.call()
 def test_wrong_manifest_map(self):
  p=self.c/'snapshot-manifest.json';p.write_text('{"files":{}}');self.plan['files'][p.name]=sha(p.read_bytes());self.plan['candidate_manifest_sha256']=sha(p.read_bytes());self.write()
  with self.assertRaisesRegex(ValueError,'manifest differs'):self.call()
if __name__=='__main__':unittest.main()
