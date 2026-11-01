"""Self-contained, offline smoke tests for the delivery; needs Python3 + Node only."""
import hashlib,json,tempfile,unittest
from pathlib import Path
import build_site

class DeliverySmoke(unittest.TestCase):
    def test_offline_candidate_and_tamper_refusal(self):
        with tempfile.TemporaryDirectory(prefix='boopadb-delivery-smoke-') as temp:
            root=Path(temp);source=root/'input';(source/'data'/'123').mkdir(parents=True);(source/'tracker_meta'/'123').mkdir(parents=True)
            for n in range(4):
                ident=str(123450+n)
                item={'id':ident,'name':'SMOKE FIXTURE '+ident,'variations':{'Default':[{'date':'2026-10-01','price':1000},{'date':'2026-10-28','price':500,'is_sale':True}]}}
                meta={'id':ident,'name':item['name'],'image':'https://example.invalid/image.jpg','shop':{'name':'Fixture','subdomain':'fixture'},'likes':10}
                (source/'data'/'123'/(ident+'.json')).write_text(json.dumps(item));(source/'tracker_meta'/'123'/(ident+'.json')).write_text(json.dumps(meta))
            (source/'charts.json').write_text('[]')
            manifest=root/'completion.json';manifest.write_text(json.dumps({'schema':1,'status':'complete','collection_id':'DELIVERY-SMOKE-NOT-PRODUCTION','fixture':True,'expected_date':'2026-10-28','files':{p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*.json')}}))
            output=root/'candidate';result=build_site.build(source,manifest,Path(__file__).parent/'pinned-static',output)
            for name in ('index.html','item.html','sale.html','ranking.html','drops.html','history.html','new.html','free.html','rising.html','updates.html','bookmarks.html'):
                text=(output/name).read_text()
                self.assertIn('DISCOUNT_DISPLAY_GUARD_START',text,name)
                self.assertNotRegex(text,r'<span class="(?:discst|disc|udisc|sg)">[-−]\$\{(?:\w+\.)?(?:pct|_disc)\}%</span>')
                self.assertEqual(result['files'][name],hashlib.sha256((output/name).read_bytes()).hexdigest())
            self.assertTrue(result['validation']['ok']);self.assertTrue(result['fixture']);self.assertFalse(result['deployed'])
            self.assertEqual(result['catalog_core']['rows'],4)
            self.assertEqual(len([x for x in result['files'] if x.startswith('search-core/')]),536)
            self.assertFalse((output/'reports').exists())
            self.assertEqual(build_site.load_trusted('validate_search_core').validate(output,result,required=True),result['catalog_core'])
            self.assertNotIn('src="relationship-data.js"',(output/'index.html').read_text())
            from rerender_candidate import rerender
            pin=hashlib.sha256((output/'snapshot-manifest.json').read_bytes()).hexdigest()
            approvals=[]
            for name in ('relation','relation-search'):
                approval=json.loads((Path(__file__).parent/(name+'-bundle-inventory.json')).read_text())
                approval.update(status='approved',activate=True,scope='local-test-only')
                path=root/(name+'-approval.json');path.write_text(json.dumps(approval));approvals.append(path)
            second=root/'rerendered'
            rendered=rerender(output,pin,second,Path(__file__).parent/'relation-bundle',approvals[0],True,Path(__file__).parent/'relation-search-bundle',approvals[1])
            for name in ('index.html','item.html','sale.html','ranking.html','drops.html','history.html','new.html','free.html','rising.html','updates.html','bookmarks.html'):
                text=(second/name).read_text()
                self.assertIn('DISCOUNT_DISPLAY_GUARD_START',text,name)
                self.assertNotRegex(text,r'<span class="(?:discst|disc|udisc|sg)">[-−]\$\{(?:\w+\.)?(?:pct|_disc)\}%</span>')
                self.assertEqual(rendered['files'][name],hashlib.sha256((second/name).read_bytes()).hexdigest())
            self.assertFalse(rendered['raw_rebuild_performed'])
            self.assertEqual(rendered['catalog_core'],result['catalog_core'])
            self.assertEqual({k:v for k,v in rendered['files'].items() if k.startswith('search-core/')},{k:v for k,v in result['files'].items() if k.startswith('search-core/')})
            self.assertFalse((second/'reports').exists())
            self.assertEqual(rendered['files']['lists_full.json'],result['files']['lists_full.json'])
            self.assertEqual(rendered['input_manifest_sha256'],result['input_manifest_sha256'])
            self.assertIn('relationship-search.js?v=',(second/'index.html').read_text())
            supplement_inventory=Path(__file__).parent/'relation-supplement-bundle-inventory.json'
            if supplement_inventory.exists():
                approval=json.loads(supplement_inventory.read_text());approval.update(status='approved',activate=True,scope='local-test-only')
                supplement_approval=root/'supplement-approval.json';supplement_approval.write_text(json.dumps(approval))
                supplemented=rerender(output,pin,root/'supplemented',Path(__file__).parent/'relation-bundle',approvals[0],True,Path(__file__).parent/'relation-search-bundle',approvals[1],Path(__file__).parent/'relation-supplement-bundle',supplement_approval)
                self.assertEqual(supplemented['files']['lists_full.json'],result['files']['lists_full.json'])
                self.assertEqual(supplemented['relation_supplement']['scope'],'local-test-only')
                self.assertEqual(supplemented['relation_supplement']['files'],approval['files'])
                self.assertIn('relationship-supplement.js?v=',(root/'supplemented/index.html').read_text())
            with self.assertRaisesRegex(ValueError,'external pin'):
                rerender(output,'0'*64,root/'bad-rerender',allow_fixture=True)
            (source/'charts.json').write_text('[null]')
            with self.assertRaisesRegex(RuntimeError,'integrity failure'):
                build_site.build(source,manifest,Path(__file__).parent/'pinned-static',root/'rejected')
            self.assertFalse((root/'rejected').exists())

if __name__=='__main__':unittest.main()
