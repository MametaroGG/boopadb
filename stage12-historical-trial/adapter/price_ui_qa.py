#!/usr/bin/env python3
"""Additional independent raw-price/bootstrap/static-function QA for Stage11.

Consumes the separately reconstructed checked source after sealed candidate QA.
No network, browser, publication, or historical completion substitution. Output
contains counts only; samples, per-item facts and logs remain private temporary data.
"""
import argparse
import ast
import datetime as dt
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import trial_adapter as t

DATA_PAGES={'bookmarks.html','drops.html','free.html','history.html','index.html','item.html','new.html','ranking.html','rising.html','sale.html','updates.html'}
EMPTY_PAGES={'app.html','privacy.html','terms.html'}
FIELDS={'on_sale':('cur','base','lowest','pct','at_lowest','date'),'drops':('from','to','date','lowest','at_lowest','on_sale','sale_event'),'active':('cur','base','lowest','at_lowest','on_sale'),'newest':('cur','base','lowest','at_lowest','on_sale')}
CAPS={'on_sale':12,'drops':10,'active':9,'newest':10}
REQUEST_KEYS={'export','adapter_sha256','source_dir','completion_sha256','site','ledger','context','snapshot_sha256','ledger_sha256'}
need=t.need

def same_json(left,right):
    """JSON numeric values may be int/float, but booleans are never numbers."""
    if type(left) in (int,float) and type(right) in (int,float):return left==right
    if type(left) is not type(right):return False
    if type(left)is dict:return set(left)==set(right) and all(same_json(left[k],right[k]) for k in left)
    if type(left)is list:return len(left)==len(right) and all(same_json(a,b) for a,b in zip(left,right))
    return left==right

def filtered_charts(charts,hidden,proof,source_digest):
    need(type(charts)is list and all(type(c)is dict and type(c.get('id'))is str for c in charts),'Invalid source charts')
    ids=[c['id'] for c in charts];need(len(ids)==len(set(ids)),'Duplicate source chart IDs')
    expected={'schema':1,'input_chart_ids':ids,'hidden_chart_ids':[i for i in ids if i in hidden],
        'visible_chart_ids':[i for i in ids if i not in hidden],'input_charts_sha256':source_digest}
    need(type(proof)is dict and type(proof.get('schema'))is int and same_json(proof,expected),'Chart visibility source binding differs')
    return [c for c in charts if c['id'] not in hidden]

def price_facts(raw):
    series=[s for s in (raw.get('variations') or {}).values() if isinstance(s,list) and s]
    if not series:return None
    ordered=sorted(max(series,key=len),key=lambda r:r['date']);prices=[r['price'] for r in ordered];drop=None
    for previous,current in zip(reversed(ordered[:-1]),reversed(ordered[1:])):
        if previous['price']!=current['price']:
            if current['price']<previous['price']:drop={'from':previous['price'],'to':current['price'],'date':current['date'],'sale_event':bool(current.get('is_sale'))}
            break
    return {'cur':prices[-1],'base':max(prices),'lowest':min(prices),'on_sale':bool(ordered[-1].get('is_sale')),
        'at_lowest':all(sorted(s,key=lambda r:r['date'])[-1]['price']==min(r['price'] for r in s) for s in series),
        'first_date':ordered[0]['date'],'last_date':ordered[-1]['date'],'drop':drop,
        'changed':any(a!=b for a,b in zip(prices,prices[1:]))}

def average_facts(raw):
    """Independent full-observation statistics, before thinning and after outlier policy."""
    result={}
    for name,series in (raw.get('variations') or {}).items():
        if not isinstance(series,list) or len(series)<2:continue
        rows=sorted(series,key=lambda r:r['date']);positive=sorted((i for i,r in enumerate(rows) if r['price']>0),key=lambda i:rows[i]['price']);excluded=set()
        for split in range(5,len(positive)):
            if rows[positive[split]]['price']>=20*rows[positive[split-1]]['price'] and len({rows[i]['date'] for i in positive[:split]})>=5:
                excluded.update(positive[split:]);break
        if any(r['price']==0 or 0<r['price']<1000000 for r in rows):
            excluded.update(i for i,r in enumerate(rows) if r['price']>=1000000)
        ordinary=[r['price'] for i,r in enumerate(rows) if i not in excluded]
        values=ordinary or [r['price'] for r in rows]
        result[name]={'sum':sum(values),'count':len(values)}
    return result

def list_price_fields(name,facts):
    values={k:facts[k] for k in ('cur','base','lowest','on_sale','at_lowest')}
    if name=='free':
        need(facts['cur']==0 and facts['base']>=100,'Invalid free membership')
        values.update(at_lowest=True,pct=100,date=facts['last_date'])
    elif name=='on_sale':
        need(facts['on_sale'] and facts['cur']<facts['base'] and facts['base']>=500,'Invalid sale membership')
        values.pop('on_sale');values.update(pct=round((facts['base']-facts['cur'])/facts['base']*100),date=facts['last_date'])
    elif name=='drops':
        need(facts['drop'] is not None,'Missing latest downward change')
        values.pop('cur');values.pop('base');values.update(facts['drop']);values['at_lowest']=facts['drop']['to']<=facts['lowest']
    return values

def check_list_item(name,item,prices):
    need(isinstance(item,dict) and item.get('id') in prices,'Unbound list price source')
    values=list_price_fields(name,prices[item['id']])
    for key,value in values.items():need(key in item and same_json(item[key],value),'Missing or incorrect list price field')
    return len(values)

def check_shop_row(row,prices,with_badge):
    need(isinstance(row,list) and len(row)==(8 if with_badge else 6) and row[0] in prices,'Unbound shop source')
    values=prices[row[0]];expected=[values['cur'],values['base'],int(values['on_sale'])]
    if with_badge:expected.append(int(values['at_lowest']))
    need(same_json(row[3:7 if with_badge else 6],expected),'Shop price fields differ')

def check_search_row(row,facts):
    need(isinstance(row,list) and len(row)>10,'Malformed search row')
    if facts is None:
        need(same_json(row[2:7],[None,None,None,0,0]) and same_json(row[10],0),'History-free price differs')
    else:
        need(same_json(row[2:7],[facts['cur'],facts['base'],facts['lowest'],int(facts['on_sale']),int(facts['at_lowest'])])
             and same_json(row[10],int(facts['first_date'].replace('-',''))),'Public raw-derived price differs')

def classify_payload(name,payload):
    if name in EMPTY_PAGES:
        need(payload=={},'Informational payload not empty');return 'empty'
    need(name in DATA_PAGES,'Unexpected bootstrap-bearing page')
    need(isinstance(payload,dict) and set(payload)=={'stats','visibility','on_sale','drops','active','newest','charts'},'Incomplete data bootstrap')
    return 'data'

def compare_bootstrap(payload,lists,maps):
    need(same_json(payload['stats'],lists['stats']) and same_json(payload['visibility'],lists['visibility']),'Bootstrap stats/visibility differs')
    count=0
    for name,fields in FIELDS.items():
        items=payload[name];need(isinstance(items,list),'Bootstrap collection not array');seen=set()
        wanted=lists[name][:CAPS[name]]
        need(all(type(x)is dict for x in items) and [x.get('id') for x in items]==[x['id'] for x in wanted],'Bootstrap ordered prefix differs')
        for item in items:
            need(isinstance(item,dict) and item.get('id') in maps[name] and item['id'] not in seen,'Unbound or duplicate bootstrap item')
            seen.add(item['id']);prior=maps[name][item['id']]
            for key in fields:
                need(key in item and key in prior and same_json(item[key],prior[key]),'Bootstrap price differs');count+=1
    return count

# vm sandboxes get only the exact extracted functions and a tiny test context.
# All downloaded content and source examples stay in the private stage directory.
UI_CODE=r'''
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const [root,sampleFile,ledgerFile,contextFile]=process.argv.slice(1);
const ledger=JSON.parse(fs.readFileSync(ledgerFile)),context=JSON.parse(fs.readFileSync(contextFile));
const bundle=JSON.parse(fs.readFileSync(sampleFile)),sample=bundle===null?null:bundle.item,backend=new Set(ledger.backend_ids);
function fresh(){let n=999999999000;while(backend.has(String(n)))n++;backend.add(String(n));return String(n);}
const unknown=fresh(),unknown2=fresh(),visible=ledger.visible_ids[0]||fresh();
const day=context.expected_date,prior=new Date(Date.parse(day+'T00:00:00Z')-86400000).toISOString().slice(0,10);
const next=new Date(Date.parse(day+'T00:00:00Z')+86400000).toISOString().slice(0,10);
function payload(html){const start=html.indexOf('const P = ')+10;assert(start>=10);return JSON.parse(html.slice(start,html.indexOf(';\n',start)));}
let pageCount=0,assertions=0,hiddenChecked=0;
for(const name of ['index.html','item.html','bookmarks.html']){
 const html=fs.readFileSync(path.join(root,name),'utf8'),P=payload(html);assert.equal(P.stats.total,ledger.counts.visible_total);
 const start=html.indexOf('// VISIBILITY_POLICY_START'),end=html.indexOf('// VISIBILITY_POLICY_END');assert(start>=0&&end>start);
 const box={P,document:{querySelectorAll:()=>[]},Date,PROD:new Map(),visible,unknown,unknown2,day,prior,next};
 vm.createContext(box);vm.runInContext(html.slice(start,end),box,{timeout:1000});const run=s=>vm.runInContext(s,box,{timeout:1000});
 box.ids=ledger.confirmed_hidden_ids;assert.equal(run('snapshotHiddenIds.size'),box.ids.length);
 assert.equal(run('ids.every(hiddenItem)'),true);assert.equal(run('hiddenItem(visible)'),false);
 const hidden=ledger.confirmed_hidden_ids[0];
 if(hidden){box.hidden=hidden;assert.equal(run('visibleItems([{id:hidden},{id:visible}]).length'),1);
  assert.equal(run('visibleItems([[hidden],[visible]])[0][0]'),visible);
  assert.equal(run('acceptVisibilityMeta(hidden,{id:hidden,name:"restored",fetched_at:day})'),null);assertions+=3;}
 assert.equal(run('confirmedUnavailableMeta(visible,{id:visible,unavailable:true,status:403,fetched_at:day})'),false);
 assert.equal(run('confirmedUnavailableMeta(visible,{id:visible,unavailable:true,status:404,fetched_at:day})'),true);
 assert.equal(run('visibilityAllowsLiveMarker(visible,{id:visible,unavailable:true,status:404,fetched_at:prior})'),false);
 run('noteVisibilityObservation({id:unknown,date:next})');
 assert.equal(run('visibilityAllowsLiveMarker(unknown,{id:unknown,unavailable:true,status:404,fetched_at:day})'),false);
 assert.equal(run('acceptVisibilityMeta(unknown2,{id:unknown2,unavailable:true,status:404,fetched_at:day})'),null);
 assert.equal(run('hiddenItem(unknown2)'),true);assert.equal(run('hiddenItem(visible)'),false);
 assert.equal(run('visibleItems([{id:unknown2},{id:visible}]).length'),1);
 assert.equal(run('visibleItems([[unknown2],[visible]])[0][0]'),visible);
 assertions+=12;hiddenChecked+=box.ids.length;pageCount++;
}
const html=fs.readFileSync(path.join(root,'item.html'),'utf8');
const a=html.indexOf('function thinPointsJS'),b=html.indexOf('function recordFromItem');
const c=html.indexOf('function statsHTML'),d=html.indexOf('const DAYMS');assert(a>=0&&b>a&&c>=0&&d>c);
const box={yen:x=>x===0?'Free':`¥${x.toLocaleString('en-US')}`,tr:(x,a)=>a?`${x}:${a.n}`:x,historyObservationLabel:()=> 'History',esc:x=>String(x)};
vm.createContext(box);vm.runInContext(html.slice(a,b)+html.slice(c,d),box,{timeout:1000});
let averageVariants=0;
if(sample!==null){box.data=sample;
 const avgs=vm.runInContext('Object.entries(thinVarsJS(data)).map(([name,s])=>({name,average_source:s.average_source,average:Math.round(s.average_source.sum/s.average_source.count),rendered_html:statsHTML(s)}))',box,{timeout:1000});
 assert(avgs.length>=1);
 for(const r of avgs){const raw=sample.variations[r.name];assert(Array.isArray(raw)&&raw.length>0);const expectedStats=bundle.averages[r.name];assert(expectedStats);
  assert.equal(r.average_source.sum,expectedStats.sum);assert.equal(r.average_source.count,expectedStats.count);const expected=Math.round(expectedStats.sum/expectedStats.count);assert.equal(r.average,expected);
  const currency=expected===0?'Free':`¥${expected.toLocaleString('en-US')}`;
  assert(r.rendered_html.includes(`<div class="k">pp_avg</div><div class="v">${currency}</div>`));averageVariants++;
 }
}
assert(/const all = visibleItems\(bmLoad\(\)\);/.test(fs.readFileSync(path.join(root,'bookmarks.html'),'utf8')));
assert(html.includes('if (hiddenItem(id)) { showHiddenProduct(); return; }'));assert(html.includes('fullIndex = visibleItems(raw)'));
console.log(JSON.stringify({static_function_pages:pageCount,static_function_assertions:assertions,hidden_ids_checked:hiddenChecked,average_variants_checked:averageVariants,bookmark_detail_search_guards:true,browser_visual_qa:false}));
'''

def pinned_function_blocks(generator):
    values={}
    for node in ast.parse(t.regular(Path(generator)/'build_prototype.py').decode()).body:
        if isinstance(node,ast.Assign) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str):
            for name in node.targets:
                if isinstance(name,ast.Name) and name.id in ('VISIBILITY_JS','TEMPLATE'):values.setdefault(name.id,node.value.value)
    def cut(text,start,end):
        a=text.find(start);b=text.find(end,a+len(start));need(a>=0 and b>a,'Expected fixed function block missing');return text[a:b]
    return {'visibility':cut(values['VISIBILITY_JS'],'// VISIBILITY_POLICY_START','// VISIBILITY_POLICY_END'),
        'average':cut(values['TEMPLATE'],'function thinPointsJS','function recordFromItem'),
        'stats':cut(values['TEMPLATE'],'function statsHTML','const DAYMS')}

def check_pinned_functions(site,generator):
    blocks=pinned_function_blocks(generator)
    for name in ('index.html','item.html','bookmarks.html'):
        text=t.regular(Path(site)/name).decode();a=text.find('// VISIBILITY_POLICY_START');b=text.find('// VISIBILITY_POLICY_END',a)
        need(a>=0 and b>a and text[a:b]==blocks['visibility'],'Visibility executable differs from frozen generator')
    text=t.regular(Path(site)/'item.html').decode()
    for key,start,end in (('average','function thinPointsJS','function recordFromItem'),('stats','function statsHTML','const DAYMS')):
        a=text.find(start);b=text.find(end,a);need(a>=0 and b>a and text[a:b]==blocks[key],'Average executable differs from frozen generator')

def run(request_path, expected_sha, output):
    raw=t.regular(request_path);need(t.sha(raw)==expected_sha,'QA request changed');request=t.strict(raw)
    need(type(request)is dict and set(request)==REQUEST_KEYS,'Exact QA request required')
    t.verify_adapter(request['adapter_sha256']);t.verify_export(request['export'])
    context=request['context'];need(type(context)is dict and context.get('synthetic') is False,'Real source context required')
    low=Path(request['export']).resolve()/'original/low-storage'
    sys.path.insert(0,str(low/'generator'))
    from verified_source import VerifiedSource,open_directory,verify_artifact_directory
    from varutil import thin_vars_from_item
    import verified_source,varutil
    need(Path(verified_source.__file__).resolve().parent==low/'generator' and Path(varutil.__file__).resolve().parent==low/'generator','Wrong checked-source dependency')
    site=Path(request['site']);ledger_path=Path(request['ledger'])
    snapshot_raw=t.regular(site/'snapshot-manifest.json');need(t.sha(snapshot_raw)==request['snapshot_sha256'],'Snapshot commitment changed')
    snap=t.strict(snapshot_raw);expected={**snap['files'],'snapshot-manifest.json':request['snapshot_sha256']}
    ledger_raw=t.regular(ledger_path);need(t.sha(ledger_raw)==request['ledger_sha256'],'Ledger commitment changed');ledger=t.strict(ledger_raw)
    def artifact_check():
        fd=open_directory(site)
        try:verify_artifact_directory(fd,expected)
        finally:os.close(fd)
        need(t.regular(ledger_path)==ledger_raw,'Ledger changed across price QA')
    artifact_check()
    with VerifiedSource(Path(request['source_dir'])/'prepared',request['completion_sha256']) as source:
        need(source.manifest['fixture'] is False and snap['fixture'] is False and
            source.manifest['tracker_commit']==context['tracker_commit']==snap['collection_id'] and
            source.manifest['expected_date']==context['expected_date']==snap['validation']['max_date'] and
            snap['input_manifest_sha256']==source.completion_sha256,'Checked source/context/snapshot join differs')
        source.verify_all()
        rows=[]
        for n in range(24):rows.extend(t.strict(t.regular(site/f'search_index_{n}.json')))
        ids=[r[0] for r in rows];need(len(ids)==len(set(ids)) and set(ids)==set(ledger['visible_ids']),'Public IDs differ from verified visibility')
        prices={};without_series=0;sample=None;sample_size=0
        for row in rows:
            ident=row[0];item=source.read_json(source.root/('data/'+ident[:3]+'/'+ident+'.json'))
            facts=price_facts(item);check_search_row(row,facts)
            if facts is None:without_series+=1;continue
            prices[ident]=facts
            nonempty=sum(isinstance(v,list) and len(v)>=2 for v in (item.get('variations') or {}).values())
            if sample_size<2 and nonempty>sample_size:sample=item;sample_size=nonempty
        lists=t.strict(t.regular(site/'lists_full.json'));list_checks=0
        stats={'total':len(rows),'sale_now':sum(int(f['on_sale']) for f in prices.values()),
            'free_now':sum(int(f['cur']==0 and f['base']>=100) for f in prices.values()),
            'changed':sum(int(f['changed']) for f in prices.values()),
            'min_date':ledger['source_min_date'],'max_date':ledger['source_max_date']}
        need(all(k in lists['stats'] and same_json(lists['stats'][k],v) for k,v in stats.items()),'Raw-derived public statistics differ')
        changes=lists['stats']['price_changes'];need(same_json(changes['cumulative']['unique_products'],stats['changed']) and
            changes['daily']['unique_products'] is None and changes['daily']['status']=='unavailable' and
            changes['daily']['reason']=='missing-coverage','Unsupported daily completeness claim')
        for name in ('on_sale','free','drops','active','newest','rising','popular','updates'):
            need(isinstance(lists[name],list),'Public list must be an array')
            for item in lists[name]:list_checks+=check_list_item(name,item,prices)
        shops=0
        for n in range(24):
            for items in t.strict(t.regular(site/f'shop_items_{n}.json')).values():
                for row in items:check_shop_row(row,prices,True);shops+=1
        for value in t.strict(t.regular(site/'shop_digest.json')).values():check_shop_row(value[2],prices,False);shops+=1
        maps={}
        for name in FIELDS:
            maps[name]={x['id']:x for x in lists[name]};need(len(maps[name])==len(lists[name]),'Duplicate list IDs')
        charts=filtered_charts(source.read_json(source.root/'charts.json'),set(ledger['confirmed_hidden_ids']),snap['chart_visibility'],source.hashes['charts.json']);variants={};pages=set();empty=set();scalars=0;variant_checks=0
        def thin(item):
            ident=item['id']
            if ident not in variants:variants[ident]=thin_vars_from_item(source.read_json(source.root/('data/'+ident[:3]+'/'+ident+'.json')))
            return variants[ident]
        for path in sorted(site.glob('*.html')):
            html=t.regular(path).decode()
            if 'const P = ' not in html:continue
            start=html.index('const P = ')+len('const P = ');payload=t.strict(html[start:html.index(';\n',start)])
            if classify_payload(path.name,payload)=='empty':empty.add(path.name);continue
            pages.add(path.name);scalars+=compare_bootstrap(payload,lists,maps)
            need(same_json(payload['charts'],charts),'Bootstrap charts differ from checked source')
            for item in payload['on_sale'][:12]+[r for r in payload['drops'] if r.get('date','')>='2026-10-02'][:10]:
                need(same_json(item.get('vars'),thin(item)),'Mandatory variation thinning differs');variant_checks+=1
            for name in FIELDS:
                for item in payload[name]:
                    if 'vars' in item:need(same_json(item['vars'],thin(item)),'Embedded variations differ')
        need(pages==DATA_PAGES and empty==EMPTY_PAGES,'Exact data/informational page boundary differs')
        check_pinned_functions(site,low/'generator')
        with tempfile.TemporaryDirectory(prefix='price-ui-private-',dir=Path(output).parent) as temporary:
            work=Path(temporary);t.write(work/'sample.json',None if sample is None else {'item':sample,'averages':average_facts(sample)});t.write(work/'context.json',context)
            child=subprocess.run(['node','-e',UI_CODE,str(site),str(work/'sample.json'),str(ledger_path),str(work/'context.json')],
                capture_output=True,text=True,timeout=120,env=t.clean_env(work))
            need(child.returncode==0,'Static function/displayed average checks failed')
            ui=t.strict(child.stdout.encode())
            need(set(ui)=={'static_function_pages','static_function_assertions','hidden_ids_checked','average_variants_checked',
                'bookmark_detail_search_guards','browser_visual_qa'},'Unexpected static QA output')
        source.verify_all();artifact_check();t.verify_export(request['export']);t.verify_adapter(request['adapter_sha256'])
        need(t.sha(t.regular(request_path))==expected_sha,'QA request changed during verification')
        result={'schema':'boopa-stage11-historical-independent-price-ui-qa-v1','status':'passed','publication_authorized':False,
            'historical_replay':True,'current_source_eligible':False,'automatic_intake_eligible':False,
            'production_eligible':False,'browser_visual_qa':False,'all_public_prices_checked':len(rows),
            'history_free_products':without_series,'list_price_fields_checked':list_checks,'shop_rows_checked':shops,
            'bootstrap_price_fields_checked':scalars,'bootstrap_variation_positions_checked':variant_checks,
            'data_pages_checked':len(pages),'empty_pages_checked':len(empty),**ui}
    t.write(output,result);return result

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--request',required=True);parser.add_argument('--sha256',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    try:print(t.encode(run(args.request,args.sha256,args.output)).decode())
    except Exception:
        print('Independent price/static QA refused.',file=sys.stderr);raise SystemExit(1)
