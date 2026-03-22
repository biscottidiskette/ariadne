import json
import csv
import io
from parsers.ioc_parser import extract_iocs


def parse_siem(raw_content: str) -> dict:
    try:
        data = json.loads(raw_content)
        return _parse_siem_json(data, raw_content)
    except json.JSONDecodeError:
        pass
    try:
        reader = csv.DictReader(io.StringIO(raw_content))
        rows = list(reader)
        if rows and len(rows[0]) > 1:
            return _parse_siem_csv(rows, raw_content)
    except Exception:
        pass
    return _parse_siem_text(raw_content)


def _parse_siem_json(data, raw_content: str) -> dict:
    if isinstance(data, dict):
        if 'results' in data:
            data = data['results']
        elif 'hits' in data:
            hits = data.get('hits', {})
            data = [h.get('_source', h) for h in hits.get('hits', [])]
        else:
            data = [data]
    if not isinstance(data, list):
        data = [data]
    records = data[:500]
    iocs = extract_iocs(json.dumps(records), context="SIEM query result")
    fields = list(records[0].keys()) if records else []
    return {
        'parsed_content': json.dumps(records),
        'summary': f"SIEM query results: {len(records)} records. Fields: {', '.join(fields[:8])}. {len(iocs)} IoCs extracted.",
        'timeline_events': _extract_timeline_from_siem(records),
        'iocs': iocs,
    }


def _parse_siem_csv(rows: list, raw_content: str) -> dict:
    iocs = extract_iocs(raw_content, context="SIEM CSV export")
    fields = list(rows[0].keys()) if rows else []
    return {
        'parsed_content': json.dumps(rows[:500]),
        'summary': f"SIEM CSV export: {len(rows)} rows. Columns: {', '.join(fields[:8])}. {len(iocs)} IoCs extracted.",
        'timeline_events': _extract_timeline_from_siem(rows),
        'iocs': iocs,
    }


def _parse_siem_text(raw_content: str) -> dict:
    iocs = extract_iocs(raw_content, context="SIEM plain text")
    return {
        'parsed_content': json.dumps({'raw': raw_content[:5000]}),
        'summary': f"SIEM plain text: {len(raw_content)} chars. {len(iocs)} IoCs extracted.",
        'timeline_events': [],
        'iocs': iocs,
    }


def _extract_timeline_from_siem(records: list) -> list:
    events = []
    time_fields = ['_time', 'timestamp', 'time', '@timestamp', 'EventTime', 'datetime']
    desc_fields = ['_raw', 'message', 'EventType', 'signature', 'name', 'description']
    host_fields = ['host', 'hostname', 'Computer', 'dest', 'src_host']
    for record in records[:200]:
        timestamp = next((record.get(f) for f in time_fields if record.get(f)), None)
        if not timestamp:
            continue
        description = next((record.get(f) for f in desc_fields if record.get(f)), 'SIEM event')
        host = next((record.get(f) for f in host_fields if record.get(f)), None)
        events.append({
            'event_time': str(timestamp),
            'event_type': 'other',
            'description': str(description)[:500],
            'host': host,
            'actor': record.get('user') or record.get('src_user'),
            'process': record.get('process') or record.get('process_name'),
        })
    return events
