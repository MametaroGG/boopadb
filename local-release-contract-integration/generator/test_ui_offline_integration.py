"""Synthetic snippet tests only; never imports scanner or uses browser/network."""
import json,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parent
SOURCE=(ROOT/'build_prototype.py').read_text()
def runjs(body):
 p=subprocess.run(['node','-e',body],capture_output=True,text=True,check=True)
 return json.loads(p.stdout)
class UIIntegration(unittest.TestCase):
 def test_ppstats_and_price_heading(self):
  self.assertIn('id="ppStats"',SOURCE)
  self.assertIn('statsEl.innerHTML = statsHTML(seriesOf(x, keys[0]))',SOURCE)
  self.assertNotIn('<span class="pp-varprice">${yen(curP)}</span>',SOURCE)
  self.assertIn('<div class="pstats">${statsHTML(ser)}</div>',SOURCE)
 def test_bookmark_wrapping(self):
  self.assertIn('bookmark-price-layout-v1',SOURCE)
  self.assertIn('.bmstrip{display:flex;flex-wrap:wrap;',SOURCE)
  self.assertIn('.bmvals .price .free{white-space:normal;',SOURCE)
 def test_history_sale_label_languages(self):
  line=next(l for l in SOURCE.splitlines() if l.startswith('function historySaleLabel()'))
  self.assertEqual(SOURCE.count('function historySaleLabel()'),1)
  self.assertEqual(runjs("let LANG='ja';"+line+"const a=historySaleLabel();LANG='en';console.log(JSON.stringify([a,historySaleLabel()]));"),['セール観測','Sale observed'])
 def test_metadata_image_original_timestamps_and_no_overwrite(self):
  code=SOURCE[SOURCE.index('const META_BASE ='):SOURCE.index('async function fillImgs(){')]
  js="""let now=0,calls=0,response=null;
Date.now=()=>now;
const fetch=async()=>{calls++;return {ok:response!==null,json:async()=>response}};
"""+code+"""
(async()=>{
 let a=await fetchMeta('2625416'),b=await fetchMeta('5846349');
 if(a.image_verified_at!=='2026-10-31T00:54:24.326165+00:00'||b.image_verified_at!=='2026-10-30T14:12:49Z')throw Error('timestamp');
 if(!a.image.includes('/i/2625416/')||!b.image.includes('/i/5846349/'))throw Error('image');
 await fetchMeta('2625416');if(calls!==2)throw Error('cache');
 now=59999;await fetchMeta('2625416');if(calls!==2)throw Error('early retry');
 now=60000;response={image:'existing',price:99};let c=await fetchMeta('2625416');
 if(calls!==3||c.image!=='existing'||c.price!==99||c.image_verified_at)throw Error('overwrite');
 console.log(JSON.stringify(true));
})().catch(e=>{console.error(e);process.exitCode=1});"""
  self.assertTrue(runjs(js))
 def test_lazy_history_dedup_and_merge(self):
  code=SOURCE[SOURCE.index('let detailHistoryEpoch ='):SOURCE.index('function detailHistoryStatus(')]
  js="""let calls=0;const PROD=new Map([['1',{id:'1',cur:99,name:'summary'}]]);
const fetchItemRecord=async()=>{calls++;return {id:'1',cur:1,name:'raw',variations:{SKU:[[1,2],[2,3]]},spark:[[1,2]]}};
"""+code+"""
(async()=>{let [a,b]=await Promise.all([detailHistoryRequest('1'),detailHistoryRequest('1')]);
 if(calls!==1||a!==b||a.cur!==99||!hasDetailHistory(a)||detailHistoryInflight.size!==0)throw Error('history');
 console.log(JSON.stringify(true));})().catch(e=>{console.error(e);process.exitCode=1});"""
  self.assertTrue(runjs(js))
 def test_stale_history_navigation_guard(self):
  self.assertIn("if (epoch !== detailHistoryEpoch || !prodPage.classList.contains('open')) return;",SOURCE)
  self.assertIn('function closeProduct(){\n  detailHistoryEpoch++;',SOURCE)
  self.assertIn('detailHistoryInflight.delete(id)',SOURCE)
if __name__=='__main__':unittest.main(verbosity=2)
