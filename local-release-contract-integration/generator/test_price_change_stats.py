import copy,unittest
from datetime import datetime,timezone
from build_full import price_change_stats,daily_records_sha256,DAILY_RECORDS_HASH_ALGORITHM,DailyPriceAccumulator

NOW=datetime(2026,10,30,0,0,tzinfo=timezone.utc)
def record(ident='1',series=None,**variations):
 return {'id':ident,'variations':{'main':series or [{'date':'2026-10-29','price':100},{'date':'2026-10-30','price':80}],**variations}}
def receipt(records,**overrides):
 return dict(schema=1,date='2026-10-30',timezone='Asia/Tokyo',history_timezone='Asia/Tokyo',complete=True,product_ids=[r['id'] for r in records],records_sha256=daily_records_sha256(records),records_hash_algorithm=DAILY_RECORDS_HASH_ALGORITHM,**overrides)
class PriceChangeStats(unittest.TestCase):
 def metric(self,records,coverage=True,**kwargs):return price_change_stats(records,77,coverage=receipt(records) if coverage is True else coverage,now=NOW,**kwargs)
 def test_cumulative_preserved_and_missing_not_zero(self):
  result=self.metric([record()],None);self.assertEqual(result['cumulative']['unique_products'],77);self.assertIsNone(result['daily']['unique_products']);self.assertEqual(result['daily']['reason'],'missing-coverage')
 def test_true_zero_only_with_complete_coverage(self):
  r=[record(series=[{'date':'2026-10-30','price':100}])];self.assertEqual(self.metric(r)['daily']['unique_products'],0)
 def test_unique_products_not_transitions_or_variants(self):
  series=[{'date':'2026-10-29T15:00:00Z','price':100},{'date':'2026-10-30T00:00:00Z','price':80},{'date':'2026-10-29T23:00:00Z','price':90}]
  r=[record(series=series,other=series),record('2')];self.assertEqual(self.metric(r)['daily']['unique_products'],2)
 def test_shorter_variation_not_counted(self):
  r=[record(series=[{'date':'2026-10-28','price':100},{'date':'2026-10-29','price':100},{'date':'2026-10-30','price':100}],short=[{'date':'2026-10-29','price':100},{'date':'2026-10-30','price':50}])];self.assertEqual(self.metric(r)['daily']['unique_products'],0)
 def test_duplicate_identical_observations_deterministic(self):
  s=[{'date':'2026-10-30','price':80},{'date':'2026-10-29','price':100},{'date':'2026-10-30','price':80}];r=[record(series=s)];self.assertEqual(self.metric(r)['daily']['unique_products'],1);r[0]['variations']['main'].reverse();self.assertEqual(self.metric(r)['daily']['unique_products'],1)
 def test_conflicting_duplicate_unknown(self):
  r=[record(series=[{'date':'2026-10-30','price':100},{'date':'2026-10-30','price':80}])];self.assertEqual(self.metric(r)['daily']['reason'],'conflicting-observation')
 def test_midnight_jst(self):
  r=[record(series=[{'date':'2026-10-29T14:59:59Z','price':100},{'date':'2026-10-29T15:00:00Z','price':80}])];self.assertEqual(self.metric(r)['daily']['unique_products'],1)
  r=[record(series=[{'date':'2026-10-29T14:00:00Z','price':100},{'date':'2026-10-29T14:59:59Z','price':80}])];self.assertEqual(self.metric(r)['daily']['reason'],'missing-observation-day')
 def test_default_day_is_jst_not_utc(self):
  result=price_change_stats([],0,now=datetime(2026,10,29,15,0,tzinfo=timezone.utc));self.assertEqual(result['daily']['date'],'2026-10-30')
 def test_missing_timezone_unknown(self):
  r=[record()];c=receipt(r);del c['history_timezone'];self.assertEqual(self.metric(r,c)['daily']['reason'],'unverified-history-timezone')
 def test_aware_timestamps_do_not_require_date_only_provenance(self):
  r=[record(series=[{'date':'2026-10-29T00:00:00Z','price':100},{'date':'2026-10-30T00:00:00Z','price':80}])];c=receipt(r);del c['history_timezone'];self.assertEqual(self.metric(r,c)['daily']['unique_products'],1)
 def test_stale_partial_unbound_coverage_unknown(self):
  r=[record()]
  for key,value in [('date','2026-10-29'),('complete',False),('product_ids',[]),('records_sha256','bad'),('schema',True),('timezone','UTC')]:
   c=receipt(r);c[key]=value
   with self.subTest(key=key):self.assertIsNone(self.metric(r,c)['daily']['unique_products'])
 def test_missing_history_unknown(self):
  r=[{'id':'1','variations':{}}];self.assertEqual(self.metric(r)['daily']['reason'],'missing-price-history')
 def test_record_order_hash_independent(self):
  r=[record(),record('2')];self.assertEqual(daily_records_sha256(r),daily_records_sha256(r[::-1]))
 def test_duplicate_product_ids_unknown(self):
  r=[record(),record()];self.assertEqual(self.metric(r)['daily']['reason'],'duplicate-or-invalid-product-id')
 def test_updated_at_authentic_generation_not_observation(self):
  self.assertEqual(self.metric([record()])['daily']['updated_at'],NOW.isoformat())
 def test_invalid_price_or_naive_timestamp_unknown(self):
  for value in [True,None,'80']:
   r=[record(series=[{'date':'2026-10-30','price':value}])];self.assertEqual(self.metric(r)['daily']['reason'],'invalid-price')
  r=[record(series=[{'date':'2026-10-30T00:00:00','price':80}])];self.assertEqual(self.metric(r)['daily']['reason'],'unverified-history-timezone')
if __name__=='__main__':unittest.main()

class BuildDailyIntegration(unittest.TestCase):
 def test_build_preserves_cumulative_and_defaults_daily_unknown(self):
  import tempfile,json,contextlib,io
  from pathlib import Path
  from build_full import build
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);data=root/'data';meta=root/'meta';out=root/'out';(data/'shard').mkdir(parents=True);meta.mkdir()
   r=record();r['name']='Fixture';(data/'shard/1.json').write_text(json.dumps(r))
   with contextlib.redirect_stderr(io.StringIO()):build(data,meta,out,generation_time=NOW)
   stats=json.loads((out/'lists_full.json').read_text())['stats']
   self.assertEqual(stats['changed'],1);self.assertEqual(stats['price_changes']['cumulative']['unique_products'],1);self.assertIsNone(stats['price_changes']['daily']['unique_products'])
   with contextlib.redirect_stderr(io.StringIO()):build(data,meta,out,daily_coverage=receipt([r]),generation_time=NOW)
   stats=json.loads((out/'lists_full.json').read_text())['stats'];self.assertEqual(stats['changed'],1);self.assertEqual(stats['price_changes']['daily']['unique_products'],1)

class DailyEntrypoints(unittest.TestCase):
 def test_invalid_receipt_private_copy_and_unknown(self):
  import tempfile,hashlib
  from pathlib import Path
  from build_full import read_daily_coverage
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'receipt';p.write_bytes(b'{malformed');obj,digest=read_daily_coverage(p,root/'private')
   self.assertEqual(digest,hashlib.sha256(b'{malformed').hexdigest());self.assertEqual((root/'private/daily-coverage-receipt.json').read_bytes(),b'{malformed')
   self.assertIsNone(price_change_stats([record()],1,coverage=obj,now=NOW)['daily']['unique_products'])
 def test_daily_cannot_exceed_cumulative(self):
  r=[record()];self.assertEqual(price_change_stats(r,0,coverage=receipt(r),now=NOW)['daily']['reason'],'inconsistent-cumulative-count')
 def test_build_full_cli_argument_pipe(self):
  import tempfile
  from pathlib import Path
  from unittest.mock import patch
  import build_full
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);p=root/'receipt';p.write_text('{}')
   with patch('sys.argv',['build_full','--data-dir',d,'--tracker-meta-dir',d,'--output-dir',str(root/'out'),'--daily-coverage-file',str(p),'--daily-target-date','2026-10-30']),patch.object(build_full,'build') as build:
    build_full.main()
   self.assertEqual(build.call_args.kwargs,dict(daily_coverage={},daily_target_date='2026-10-30'))
   self.assertEqual(len(list(root.glob('.out-daily-input-*/daily-coverage-receipt.json'))),1)
 def test_build_site_cli_argument_pipe(self):
  from unittest.mock import patch
  from pathlib import Path
  import build_site
  with patch('sys.argv',['build_site','--input-root','input','--completion-manifest','complete','--static-root','static','--output-dir','out','--daily-coverage-file','receipt','--daily-target-date','2026-10-30']),patch.object(build_site,'build',return_value={}) as build:
   build_site.main()
  self.assertEqual(build.call_args.kwargs,dict(daily_coverage_file=Path('receipt'),daily_target_date='2026-10-30'))
 def test_build_site_actual_receipt_pipeline_private_ids(self):
  import tempfile,json,hashlib,contextlib,io
  from pathlib import Path
  import build_site
  with tempfile.TemporaryDirectory() as d:
   root=Path(d);source=root/'input';(source/'data/s').mkdir(parents=True);(source/'tracker_meta/s').mkdir(parents=True);records=[]
   for i in range(1,5):
    r=record(str(i));r['name']='Fixture '+str(i);records.append(r);(source/f'data/s/{i}.json').write_text(json.dumps(r));(source/f'tracker_meta/s/{i}.json').write_text(json.dumps({'id':str(i),'name':r['name'],'image':'https://example.invalid/a.jpg','likes':10,'shop':{'name':'Fixture','subdomain':'fixture'}}))
   (source/'charts.json').write_text('[]')
   manifest=root/'completion';manifest.write_text(json.dumps(dict(schema=1,status='complete',collection_id='DAILY-TEST',fixture=True,expected_date='2026-10-30',files={p.relative_to(source).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in source.rglob('*.json')})))
   receiptfile=root/'receipt';receiptfile.write_text(json.dumps(receipt(records)));out=root/'candidate'
   with contextlib.redirect_stderr(io.StringIO()),contextlib.redirect_stdout(io.StringIO()):result=build_site.build(source,manifest,Path(__file__).parent/'pinned-static',out,daily_coverage_file=receiptfile,daily_target_date='2026-10-30')
   self.assertEqual(json.loads((out/'lists_full.json').read_text())['stats']['price_changes']['daily']['unique_products'],4)
   self.assertEqual(result['daily_coverage_receipt_sha256'],hashlib.sha256(receiptfile.read_bytes()).hexdigest())
   self.assertNotIn('product_ids',json.dumps(result));self.assertFalse(any('daily-coverage' in p.name for p in out.rglob('*')))
   self.assertEqual(len(list(root.glob('.candidate-candidate-*/daily-private/daily-coverage-receipt.json'))),1)


class DailyReviewRegressions(unittest.TestCase):
 def test_representative_tie_order_is_bound_in_receipt(self):
  yes=[{'date':'2026-10-29','price':100},{'date':'2026-10-30','price':80}]
  no=[{'date':'2026-10-29','price':100},{'date':'2026-10-30','price':100}]
  a=[{'id':'1','variations':{'yes':yes,'no':no}}];b=[{'id':'1','variations':{'no':no,'yes':yes}}]
  self.assertNotEqual(daily_records_sha256(a),daily_records_sha256(b))
  self.assertEqual(price_change_stats(a,1,coverage=receipt(a),now=NOW)['daily']['unique_products'],1)
  self.assertEqual(price_change_stats(b,1,coverage=receipt(a),now=NOW)['daily']['reason'],'unbound-coverage')
 def test_future_timestamp_not_complete(self):
  r=[record(series=[{'date':'2026-10-29T00:00:00Z','price':100},{'date':'2026-10-30T10:00:00Z','price':80}])]
  self.assertEqual(price_change_stats(r,1,coverage=receipt(r),now=NOW)['daily']['reason'],'future-observation')


class MissingObservationDay(unittest.TestCase):
 def test_all_histories_older_is_unknown_even_with_receipt(self):
  r=[record(series=[{'date':'2026-10-28','price':100},{'date':'2026-10-29','price':80}])]
  result=price_change_stats(r,1,coverage=receipt(r),now=NOW)['daily']
  self.assertIsNone(result['unique_products']);self.assertEqual(result['reason'],'missing-observation-day')
 def test_inactive_older_product_does_not_block_observed_day(self):
  r=[record(series=[{'date':'2026-10-29','price':100}]),record('2',series=[{'date':'2026-10-30','price':80}])]
  self.assertEqual(price_change_stats(r,0,coverage=receipt(r),now=NOW)['daily']['unique_products'],0)
 def test_future_target_date_unknown(self):
  r=[record()];c=receipt(r);c['date']='2026-10-31'
  self.assertEqual(price_change_stats(r,1,target_date='2026-10-31',coverage=c,now=NOW)['daily']['reason'],'future-target-date')

class StreamingDailyStats(unittest.TestCase):
 def test_streaming_matches_batch_and_file_order(self):
  rows=[record(),record('2',series=[{'date':'2026-10-30','price':100}]),record('3',series=[{'date':'2026-10-29','price':100}])];c=receipt(rows)
  expected=price_change_stats(rows,1,coverage=c,now=NOW)
  for records in (rows,rows[::-1]):
   stream=DailyPriceAccumulator(coverage=c,now=NOW)
   for row in records:stream.add(row)
   self.assertEqual(stream.finish(1),expected)
 def test_records_not_retained(self):
  import weakref,gc
  class RawRecord(dict):pass
  row=RawRecord(record());c=receipt([row]);stream=DailyPriceAccumulator(coverage=c,now=NOW);stream.add(row);reference=weakref.ref(row);del row;gc.collect()
  self.assertIsNone(reference());self.assertEqual(len(stream.leaves),1);self.assertEqual(len(stream.leaves[0]),32)
  self.assertEqual(stream.ids,{'1'});self.assertEqual(stream.finish(1)['daily']['unique_products'],1)
 def test_streaming_digest_binding_and_algorithm_required(self):
  rows=[record()];c=receipt(rows)
  for algorithm in [None,'unversioned','sha256-sorted-record-leaves-v2']:
   changed=copy.deepcopy(c);changed['records_hash_algorithm']=algorithm
   self.assertEqual(price_change_stats(rows,1,coverage=changed,now=NOW)['daily']['reason'],'unsupported-records-hash-algorithm')
  rows[0]['variations']['main'][0]['price']=120
  self.assertEqual(price_change_stats(rows,1,coverage=c,now=NOW)['daily']['reason'],'unbound-coverage')
 def test_digest_consumes_single_pass_generator(self):
  rows=[record(),record('2')];self.assertEqual(daily_records_sha256(iter(rows)),daily_records_sha256(iter(rows[::-1])))
 def test_default_missing_coverage_retains_nothing(self):
  stream=DailyPriceAccumulator(now=NOW)
  for i in range(100):stream.add(record(str(i+1)))
  self.assertEqual(stream.ids,set());self.assertEqual(stream.leaves,[]);self.assertEqual(stream.finish(100)['daily']['reason'],'missing-coverage')
