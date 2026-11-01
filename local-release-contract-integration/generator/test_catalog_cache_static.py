import hashlib,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import build_site,build_prototype
from static_assets import STATIC_HASHES
class CatalogStatic(unittest.TestCase):
 def test_module_is_pinned_copied_and_referenced(self):
  with tempfile.TemporaryDirectory() as d:
   target=Path(d);build_site.copy_statics(build_site.HERE/'pinned-static',target)
   self.assertEqual(hashlib.sha256((target/'catalog-cache.js').read_bytes()).hexdigest(),STATIC_HASHES['catalog-cache.js'])
   self.assertIn('catalog-cache.js?v='+STATIC_HASHES['catalog-cache.js'],build_prototype.TEMPLATE)
   self.assertIn('await spCatalogReader.refresh()',build_prototype.TEMPLATE)
   self.assertIn('catalog-images.js?v=20261029-core-v1',build_prototype.TEMPLATE)
   self.assertEqual(hashlib.sha256((target/'catalog-images.js').read_bytes()).hexdigest(),STATIC_HASHES['catalog-images.js'])
 def test_git_source_route_uses_reviewed_module_pin_not_nonexistent_old_commit_file(self):
  calls=[]
  def git(args,**kwargs):calls.append(args[-1]);return b'old-static-fixture'
  with tempfile.TemporaryDirectory() as d,patch('build_site.subprocess.check_output',side_effect=git):
   target=Path(d)/'out';target.mkdir();build_site.copy_statics(Path(d)/'git-source',target)
   self.assertEqual(hashlib.sha256((target/'catalog-cache.js').read_bytes()).hexdigest(),STATIC_HASHES['catalog-cache.js'])
   self.assertFalse(any(s.endswith((':catalog-cache.js',':catalog-images.js')) for s in calls))
   self.assertEqual(hashlib.sha256((target/'catalog-images.js').read_bytes()).hexdigest(),STATIC_HASHES['catalog-images.js'])
