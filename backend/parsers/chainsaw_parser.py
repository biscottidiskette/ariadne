import json
from typing import Optional
from parsers.ioc_parser import extract_iocs


def parse_chainsaw(raw_content: str) -> dict:
    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError as e:
        return _error_result(f"Invalid JSON: {e}")

    if not isinstance(data, list):
        if isinstance(data, dict) and 'hits' in data:
            data = data['hits']
        else:
            return _error_result("Expected JSON array of Chainsaw records")

    records = []
    timeline_events = []
    all_iocs = []

    for item in data:
        try:
            record = _parse_record(item)
            if record:
                records.append(record)
                if record.get('timestamp'):
                    timeline_events.append({
                        'event_time':  record['timestamp'],
                        'event_type':  _map_event_type(record.get('event_id')),
                        'description': record.get('detection_name') or f"Event ID {record.get('event_id', 'unknown')}",
                        'host':        record.get('computer'),
                        'actor':       record.get('subject_user') or record.get('target_user'),
                        'process':     record.get('process_name'),
                    })
                iocs = extract_iocs(json.dumps(item), context=f"Chainsaw event ID {record.get('event_id')}")
                all_iocs.extend(iocs)
        except Exception:
            continue

    event_ids = [r.get('event_id') for r in records if r.get('event_id')]
    computers = list(set(r.get('computer') for r in records if r.get('computer')))
    detections = list(set(r.get('detection_name') for r in records if r.get('detection_name')))

    summary_parts = [f"Chainsaw analysis: {len(records)} matched events across {len(computers)} host(s)."]
    if computers:
        summary_parts.append(f"Hosts: {', '.join(computers[:5])}.")
    if detections:
        summary_parts.append(f"Detections: {', '.join(detections[:5])}.")
    if event_ids:
        unique_eids = list(set(str(e) for e in event_ids))
        summary_parts.append(f"Event IDs: {', '.join(unique_eids[:10])}.")
    if all_iocs:
        summary_parts.append(f"Extracted {len(all_iocs)} potential IoCs.")

    return {
        'parsed_content':  json.dumps(records[:100]),
        'summary':         ' '.join(summary_parts),
        'timeline_events': timeline_events,
        'iocs':            all_iocs,
    }


def _parse_record(item: dict) -> Optional[dict]:
    event = item.get('Event', {})
    system = event.get('System', {})
    event_data = event.get('EventData', {})
    user_data = event.get('UserData', {})
    data = {}
    if isinstance(event_data, dict):
        data.update(event_data)
    if isinstance(user_data, dict):
        data.update(user_data)
    detections = item.get('detections', [])
    detection_name = detections[0].get('name') if detections and isinstance(detections, list) and detections[0] else None
    return {
        'timestamp':      item.get('timestamp'),
        'event_id':       system.get('EventID'),
        'computer':       system.get('Computer'),
        'channel':        system.get('Channel'),
        'detection_name': detection_name,
        'subject_user':   data.get('SubjectUserName'),
        'target_user':    data.get('TargetUserName'),
        'logon_type':     data.get('LogonType'),
        'process_name':   data.get('NewProcessName') or data.get('ProcessName'),
        'command_line':   data.get('CommandLine'),
        'parent_process': data.get('ParentProcessName'),
        'ip_address':     data.get('IpAddress'),
        'workstation':    data.get('WorkstationName'),
    }


def _map_event_type(event_id) -> str:
    mapping = {
        4624: 'logon', 4625: 'logon', 4648: 'logon',
        4688: 'process_creation', 4689: 'process_creation',
        4697: 'service_install', 7045: 'service_install',
        4698: 'scheduled_task', 4702: 'scheduled_task',
        4663: 'file_write', 4656: 'file_write',
        4657: 'registry_modification',
        4776: 'logon', 4768: 'logon', 4769: 'logon',
    }
    try:
        return mapping.get(int(event_id), 'other')
    except (TypeError, ValueError):
        return 'other'


def _error_result(message: str) -> dict:
    return {'parsed_content': '{}', 'summary': f"Parse error: {message}", 'timeline_events': [], 'iocs': []}
