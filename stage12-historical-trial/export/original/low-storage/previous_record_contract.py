"""Exact pure record checks extracted from the reviewed snapshot contract."""
import json, math, re
from pathlib import Path
from datetime import date

def strict_json(raw):
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out: raise ValueError('Duplicate JSON key: '+k)
            out[k] = v
        return out
    def bad(value): raise ValueError('Nonfinite JSON constant: '+value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad)

def iso(value):
    if not isinstance(value, str): raise ValueError('Date must be string')
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value: raise ValueError('Noncanonical date')
    return parsed

def commit_value(value):
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{40}', value):
        raise ValueError('Exact lowercase commit required')
    return value

def inspect_records(files, minimum, as_of, max_age_days):
    minimum=iso(minimum); as_of=iso(as_of)
    if type(max_age_days) is not int or max_age_days<0: raise ValueError('Invalid age budget')
    latest=None; ids=set(); placeholders=[]
    for name in sorted(files):
        raw = files[name]
        if Path(name).name=='.gitkeep' and not raw:
            placeholders.append(name); continue
        if Path(name).suffix!='.json': raise ValueError('Unsupported non-JSON input: '+name)
        record = strict_json(raw)
        if not name.startswith('data/'): continue
        if name == 'data/collection_receipt.json':
            # C1 collector metadata, never a product. Keep the exact bytes in
            # the capture/inventory/staged output. Authenticated run, eligibility
            # and ledger binding remain the resolver's responsibility; this
            # adapter only validates the narrow metadata format, not authority.
            if (not isinstance(record, dict) or 'id' in record or 'variations' in record or
                    record.get('schema') != 'boopa-collection-receipt-v1' or
                    record.get('repository') != 'MametaroGG/booth-vrc-price-tracker' or
                    record.get('scope') != 'bounded-filtered-search-observation' or
                    record.get('whole_catalog_complete') is not False):
                raise ValueError('Invalid collector receipt metadata')
            for key in ('run_id', 'run_attempt'):
                if not isinstance(record.get(key), str) or not re.fullmatch('[1-9][0-9]{0,19}', record[key]):
                    raise ValueError('Invalid collector receipt identity')
            if record.get('reservation_id') != record['run_id']+'-'+record['run_attempt']:
                raise ValueError('Invalid collector receipt reservation')
            commit_value(record.get('source_commit'))
            if (record.get('status') not in ('completed', 'paused') or
                    record.get('failed') is not False or
                    record.get('reservation_completed') is not True or
                    type(record.get('continueCollection')) is not bool):
                raise ValueError('Invalid collector receipt outcome')
            if ((record['status'] == 'completed' and 'reason' in record) or
                    (record['status'] == 'paused' and record.get('reason') not in ('deadline', 'day-boundary'))):
                raise ValueError('Invalid collector receipt stop reason')
            for key in ('started_at_ms', 'stopped_at_ms', 'deadline_ms', 'blocked_until_ms', 'pending_retry_count'):
                if type(record.get(key)) is not int or record[key] < 0:
                    raise ValueError('Invalid collector receipt counters')
            metrics = record.get('metrics')
            keys = ('searchPages', 'searchFailures', 'itemSuccess', 'itemFailures', 'unavailable',
                    'retries', 'duplicatesAvoided', 'chargedHttpAttempts', 'dailyChargedRequests')
            if not isinstance(metrics, dict) or any(type(metrics.get(k)) is not int or metrics[k] < 0 for k in keys):
                raise ValueError('Invalid collector receipt metrics')
            continue
        if name in ('data/crawl_state.json','data/request_budget.json'):
            if not isinstance(record,dict) or 'id' in record or 'variations' in record:
                raise ValueError('Invalid tracker state')
            continue
        if not isinstance(record,dict): raise ValueError('Invalid product')
        ident=record.get('id')
        if not isinstance(ident,str) or not re.fullmatch('[1-9][0-9]*',ident) or ident in ids:
            raise ValueError('Invalid/duplicate ID')
        if name != 'data/'+ident[:3]+'/'+ident+'.json': raise ValueError('ID/path mismatch')
        ids.add(ident); variations=record.get('variations')
        if not isinstance(variations,dict): raise ValueError('Invalid variations')
        representative=[]
        for series in variations.values():
            if not isinstance(series,list): raise ValueError('Invalid history')
            for row in series:
                if not isinstance(row,dict): raise ValueError('Invalid row')
                day=iso(row.get('date')); price=row.get('price')
                if type(price) not in (int,float) or not math.isfinite(price) or price<0 or day>as_of:
                    raise ValueError('Invalid observation')
            if len(series)>len(representative): representative=series
        if representative:
            day=max(iso(row['date']) for row in representative)
            latest=day if latest is None else max(latest,day)
    if not ids or latest is None: raise ValueError('No dated products')
    if latest<minimum or (as_of-latest).days>max_age_days: raise ValueError('Stale/regressing snapshot')
    return latest.isoformat(), placeholders
