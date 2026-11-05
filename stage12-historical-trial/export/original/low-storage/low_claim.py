"""Original preparation date envelope retained at authenticated intake.

This is not current freshness authority. The current collector resolver must
still enforce receipt/run freshness and latest source on every operation.
"""
import datetime as dt
import re

def claim(proof,synthetic):
    evaluated=proof.get('evaluated_at')
    if not isinstance(evaluated,str):raise ValueError('Original evaluated timestamp required')
    when=dt.datetime.fromisoformat(evaluated.replace('Z','+00:00'))
    if when.tzinfo is None:raise ValueError('Evaluated timestamp timezone required')
    return {'expected_date':proof['selection']['expected_date'],'minimum_source_date':'2026-10-30','as_of':when.astimezone(dt.timezone(dt.timedelta(hours=9))).date().isoformat(),'max_source_age_days':1,'fixture':synthetic}

def validate(value,proof,synthetic):
    expected=claim(proof,synthetic)
    if type(value)is not dict or set(value)!=set(expected) or type(synthetic)is not bool or type(value['fixture'])is not bool or type(value['max_source_age_days'])is not int or value!=expected:raise ValueError('Original source preparation envelope changed')
    source=dt.date.fromisoformat(value['expected_date']);as_of=dt.date.fromisoformat(value['as_of'])
    if not 0<=(as_of-source).days<=1:raise ValueError('Original intake observation was stale or future')
    return value
