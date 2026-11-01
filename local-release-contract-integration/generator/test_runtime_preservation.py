"""Offline guard negatives; run in the fresh v4+addon tool directory."""
import hashlib,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from prepare_deployment import prepare,PAGES
from build_site import BASELINE,STATICS

class RuntimePreservation(unittest.TestCase):
 def test_changed_or_missing_public_runtime_has_no_plan(self):
  with tempfile.TemporaryDirectory() as tmp:
   root=Path(tmp);candidate=root/'candidate';candidate.mkdir()
   required=set(STATICS)|{x+'.html' for x in PAGES}|{'lists_full.json','shop_digest.json','cat_cards.json'}
   required|={f'{p}_{i}.json' for p in ('search_index','shop_items') for i in range(24)}
   required|={f'relations_children_{i}.json' for i in range(8)}
   names=['relationship-data.js','relationship-ui-draft.js','relationship-search.js','relationship-supplement.js','relation-supplement/items.json','relation-supplement/assets/modular-avatar-logo.png','relation-data/items_0.json','relation-search/children_0.json']
   for name in names:
    for old in (False,True):
     files={n:'0'*64 for n in required}
     if old:files[name]=hashlib.sha256(b'old').hexdigest()
     m={'status':'validated-candidate','baseline_commit':BASELINE,'deployed':False,'fixture':True,'collection_completion':'producer-attested-not-independently-verified','collection_id':'fixture','files':files}
     (candidate/'snapshot-manifest.json').write_text(json.dumps(m))
     def git(args,**kwargs):
      if 'rev-parse' in args:return BASELINE+'\n'
      if 'ls-tree' in args:return name+'\n'
      if args[-1].endswith(':index.html'):return b'<html>synthetic target</html>'
      if args[-1].endswith(':'+name):return b'current reviewed bytes'
      raise AssertionError(args)
     with patch('prepare_deployment.subprocess.check_output',side_effect=git):
      with self.assertRaisesRegex(ValueError,'already-public relationship runtime/data'):
       prepare(candidate,root,BASELINE,root/'plan.json',allow_fixture=True)
     self.assertFalse((root/'plan.json').exists())
if __name__=='__main__':unittest.main()
