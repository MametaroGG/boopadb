"""Common current price projection across generated HTML and fetched records.
Candidate-only transformer; fail closed on unknown template anchors.
"""
from pathlib import Path
import json,re,hashlib
HERE=Path(__file__).parent
LIB=(HERE/'current-price-projection.cjs').read_text().split("if(typeof module")[0]

def transform(text,config,page_name=None):
 if 'id="current-price-projection"' in text:raise ValueError('projection already applied')
 js=LIB+'\nwindow.CurrentPrices=createCurrentPriceProjection('+json.dumps(config,ensure_ascii=False,separators=(',',':')).replace('<',r'\u003c')+');\n'
 if text.count('</head>')!=1 or text.count('</body>')!=1:raise ValueError('required document anchors missing')
 text=text.replace('</head>','<script id="current-price-projection">'+js+'</script>\n</head>',1)
 # Bootstrap payload is generated in the same candidate; historical arrays are
 # left intact by walk and only the chosen chart key is reordered for display.
 m=re.search(r'const P\s*=\s*',text)
 if m:
  _,end=json.JSONDecoder().raw_decode(text[m.end():]);pos=m.end()+end
  if text[pos:pos+1]!=';':raise ValueError('unrecognized bootstrap terminator')
  text=text[:pos+1]+'\nObject.assign(P,CurrentPrices.walk(P,{trustedLegacy:true}));'+text[pos+1:]
 # Old and visibility-aware templates are explicit alternatives. Unknown or
 # duplicated variants still fail closed; never remove the visibility filter.
 variants = [
  ("if(!Array.isArray(rows))throw new Error('catalog format');return rows;", "if(!Array.isArray(rows))throw new Error('catalog format');return rows.map(r=>CurrentPrices.row(r));", "if(!Array.isArray(rows))throw new Error('catalog format');return visibleItems(rows);", "if(!Array.isArray(rows))throw new Error('catalog format');return visibleItems(rows).map(r=>CurrentPrices.row(r));"),
  ('const rec = recordFromItem(await r.json());', 'const rec = await CurrentPrices.rawRecord(await r.json(),recordFromItem,globalThis.crypto);', 'const rec = recordFromItem(raw);', 'const rec = await CurrentPrices.rawRecord(raw,recordFromItem,globalThis.crypto);'),
  ('return _shopShardCache[idx][sub] || null;', "const rows=_shopShardCache[idx][sub] || null;return Array.isArray(rows)?rows.map(r=>CurrentPrices.row(r,'shop')):rows;", 'return _shopShardCache[idx][sub] ? visibleItems(_shopShardCache[idx][sub]) : null;', "const rows=_shopShardCache[idx][sub] || null;return Array.isArray(rows)?visibleItems(rows).map(r=>CurrentPrices.row(r,'shop')):rows;")
 ]
 if page_name in ('index.html','item.html') or 'function renderProdPage' in text:
  for anchor in ['FULL_LISTS = f; FULL_OK = true;','function renderProdPage(x){','function renderPPBody(x){']:
   if text.count(anchor)!=1:raise ValueError('required exact main anchor missing or duplicated: '+anchor)
  for old,_,visible,_ in variants:
   if text.count(old)+text.count(visible)!=1:raise ValueError('required main projection anchor missing or ambiguous: '+old)
 text=text.replace('FULL_LISTS = f; FULL_OK = true;','f=CurrentPrices.walk(f); FULL_LISTS = f; FULL_OK = true;')
 for old,projected,visible,visible_projected in variants:
  text=text.replace(old,projected).replace(visible,visible_projected)
 if 'async function loadFull(){' in text:
  old='if (r.ok) return await r.json();'
  visible='if (r.ok) return filterVisibleLists(await r.json());'
  if text.count(old)+text.count(visible)!=1:raise ValueError('required subpage full-list anchor missing or ambiguous')
  text=text.replace(old,'if (r.ok) return CurrentPrices.walk(await r.json());').replace(visible,'if (r.ok) return filterVisibleLists(CurrentPrices.walk(await r.json()));')
 text=text.replace('function renderProdPage(x){','function renderProdPage(x){\n  x=CurrentPrices.record(x);')
 text=text.replace('function renderPPBody(x){','function renderPPBody(x){\n  x=CurrentPrices.record(x);')
 for anchor,param in [('function saleCard(s, i){','s'),('function saleCardVariantOriginal(s, i){','s'),('function plainCard(x, i){','x'),('function mosaicCell(s, i){','s'),('function capCard(s){','s'),('function rkCluster(s){','s'),('function heroSlideHTML(x, i){','x'),('function fillCardPrice(rec){','rec')]:
  if anchor in text:text=text.replace(anchor,anchor+'\n '+param+'=CurrentPrices.display('+param+');')
 if page_name in ('index.html','item.html'):
  if sum(text.count(a) for a in ['function saleCard(s, i){','function saleCardVariantOriginal(s, i){'])!=1:raise ValueError('required sale card presentation hook missing or ambiguous')
 text=text.replace('return spCatalogCache.hits;', 'return spCatalogCache.hits.map(x=>CurrentPrices.record(x));')
 text=text.replace("const raw=Array.from({length:24},(_,i)=>spCatalogParts.get(i)).flat();", "const raw=Array.from({length:24},(_,i)=>spCatalogParts.get(i)).flat().map(r=>CurrentPrices.row(r));")
 text=text.replace('function bmInfo(b){','function bmInfo(b){\n const projected=CurrentPrices.current(b.id);if(projected)return projected;')
 text=text.replace('const cur = lookup.get(String(b.id));','const cur = CurrentPrices.current(b.id)||lookup.get(String(b.id));')
 text=text.replace('const lk = lookup.get(String(h.id));','const lk = CurrentPrices.current(h.id)||lookup.get(String(h.id));')
 text=text.replace('const now = PROD.get(String(h.id));','const now = CurrentPrices.current(h.id)||PROD.get(String(h.id));')
 # Only the category-card response, not arbitrary fetch callbacks or analytics.
 anchor='fetch("cat_cards.json?v=20251026-1").then(r => { if (!r.ok) throw new Error("cat"); return r.json(); }).then(data => {'
 if anchor in text:text=text.replace(anchor,anchor+'\n data=CurrentPrices.walk(data);')
 # Same-shop raw fallback must use the same hash gate, not longest-series price.
 anchor='if (dd && dd.variations) {'
 if anchor in text:
  if text.count(anchor)!=1:raise ValueError('ambiguous same-shop raw fallback')
  text=text.replace('let cur = null, sale = false;','let cur = null, sale = false, projected = null;')
  text=text.replace(anchor,"if(dd && CurrentPrices.entry(nid)){projected=await CurrentPrices.rawRecord(dd,recordFromItem,globalThis.crypto);cur=projected.cur;sale=projected.sale;}else "+anchor)
  anchor='cur, base: cur, pct: 0, sale });'
  if text.count(anchor)!=1:raise ValueError('missing same-shop raw result anchor')
  text=text.replace(anchor,'cur, base: cur, pct: 0, sale, ...(projected||{}) });')
 text=text.replace('</body>','<script>'+ (HERE/'current-price-lifecycle.js').read_text()+'</script>\n</body>',1)
 return text

def main(root):
 root=Path(root);path=root/'current-price-projection.json'
 if not path.exists():return
 config=json.loads(path.read_text())
 pending={}
 for p in root.glob('*.html'):
  text=p.read_text()
  if text.strip().startswith('google-site-verification:') and '<' not in text:continue
  pending[p]=transform(text,config,p.name)
 # Both standalone and index image search fetch raw histories rather than the
 # global index: same raw hash verification, not a separate price heuristic.
 p=root/'image-search-engine.js'
 if p.exists():
  s=p.read_text();anchor="{...record,...imagePriceRecord(data),name:record.name||data.name}"
  if s.count(anchor)!=1:raise ValueError('required image raw projection anchor missing')
  s=s.replace("{...record,...imagePriceRecord(data),name:record.name||data.name}","{...record,...await CurrentPrices.rawRecord(data,d=>({id:String(d.id),...imagePriceRecord(d)}),globalThis.crypto),name:record.name||data.name}")
  s=s.replace('function imageResultCard(x, saved, detailUrl){','function imageResultCard(x, saved, detailUrl){\n x=CurrentPrices.display(x);')
  pending[p]=s
  version=hashlib.sha256(s.encode()).hexdigest()
  for name in ('index.html','item.html','image-search.html'):
   page=root/name
   if page not in pending:continue
   pending[page],count=re.subn(r'image-search-engine\.js(?:\?[^\"\']*)?', 'image-search-engine.js?v='+version,pending[page])
   if count!=1:raise ValueError('image engine import missing/ambiguous: '+name)
 for p,s in pending.items():p.write_text(s)
