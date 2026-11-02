"""Synthetic UTC/JST boundary tests; no new freshness allowance."""
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
GEN=Path(__file__).resolve().parents[1]/'generator'
sys.path.insert(0,str(GEN))
spec=importlib.util.spec_from_file_location('snapshot_calendar_module',GEN/'snapshot_contract.py');s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)
class CalendarTests(unittest.TestCase):
 def attest_at(self,instant,day,**kwargs):
  class Clock:
   @staticmethod
   def now(tz):return dt.datetime.fromisoformat(instant).astimezone(tz)
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp);(p/'data/123').mkdir(parents=True);(p/'meta').mkdir();(p/'data/123/123456.json').write_text(json.dumps({'id':'123456','variations':{'v':[{'date':day,'price':100}]}}));inv=p/'inventory';inv.write_bytes(s.inventory_bytes(s.snapshot(p)))
   with patch.object(s,'datetime',Clock):return s.attest(p,'a'*40,inv,'2026-10-30',fixture=True,**kwargs)
 def test_default_tracks_jst_boundaries(self):
  for instant,day in [('2026-11-02T14:59:59+00:00','2026-11-02'),('2026-11-02T15:00:00+00:00','2026-11-03'),('2026-11-02T23:59:59+00:00','2026-11-03'),('2026-11-03T00:00:00+00:00','2026-11-03')]:
   with self.subTest(instant=instant):self.assertEqual(self.attest_at(instant,day)['as_of'],day)
 def test_future_day_still_rejected(self):
  with self.assertRaisesRegex(ValueError,'Invalid observation'):self.attest_at('2026-11-02T15:00:00+00:00','2026-11-04')
 def test_stale_day_still_rejected(self):
  with self.assertRaisesRegex(ValueError,'Stale'):self.attest_at('2026-11-02T15:00:00+00:00','2026-11-01')
 def test_one_day_age_limit_unchanged(self):
  r=self.attest_at('2026-11-02T15:00:00+00:00','2026-11-02');self.assertEqual(r['max_source_age_days'],1)
 def test_explicit_as_of_unchanged(self):
  self.assertEqual(self.attest_at('2026-11-02T15:00:00+00:00','2026-11-02',as_of='2026-11-02')['as_of'],'2026-11-02')
  with self.assertRaisesRegex(ValueError,'Invalid observation'):self.attest_at('2026-11-02T15:00:00+00:00','2026-11-03',as_of='2026-11-02')
if __name__=='__main__':unittest.main()
