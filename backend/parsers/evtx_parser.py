import json
from typing import Optional
from parsers.ioc_parser import extract_iocs
from parsers.chainsaw_parser import _map_event_type


def parse_evtx(file_bytes: bytes) -> dict:
    try:
        import Evtx.Evtx as evtx
        import io
    except ImportError:
        return _error_result("python-evtx not installed")

    records = []
    timeline_events = []
    all_iocs = []

    try:
        with evtx.Evtx(io.BytesIO(file_bytes)) as log:
            for record in log.records():
                try:
                    xml_str = record.xml()
                    parsed = _parse_evtx_record(xml_str)
                    if parsed:
                        records.append(parsed)
                        if parsed.get('timestamp'):
                            timeline_events.append({
                                'event_time':  parsed['timestamp'],
                                'event_type':  _map_event_type(parsed.get('event_id')),
                                'description': f"Event ID {parsed.get('event_id', 'unknown')} on {parsed.get('computer', 'unknown')}",
                                'host':        parsed.get('computer'),
                                'actor':       parsed.get('subject_user') or parsed.get('target_user'),
                                'process':     parsed.get('process_name'),
                            })
                        iocs = extract_iocs(xml_str, context=f"EVTX Event ID {parsed.get('event_id')}")
                        all_iocs.extend(iocs)
                except Exception:
                    continue
    except Exception as e:
        return _error_result(f"Failed to read EVTX file: {e}")

    from collections import Counter
    event_ids = [str(r.get('event_id')) for r in records if r.get('event_id')]
    computers = list(set(r.get('computer') for r in records if r.get('computer')))
    eid_counts = Counter(event_ids)
    top_eids = eid_counts.most_common(5)

    summary_parts = [f"EVTX file: {len(records)} events parsed across {len(computers)} host(s)."]
    if computers:
        summary_parts.append(f"Hosts: {', '.join(computers[:5])}.")
    if top_eids:
        summary_parts.append(f"Top event IDs: {', '.join(f'EID {e}({c})' for e, c in top_eids)}.")
    if all_iocs:
        ioc_types = Counter(i['ioc_type'] for i in all_iocs)
        summary_parts.append(f"IoCs: {', '.join(f'{c} {t}' for t, c in ioc_types.most_common(4))}.")

    return {
        'parsed_content':  json.dumps(records[:500]),
        'summary':         ' '.join(summary_parts),
        'timeline_events': timeline_events[:1000],
        'iocs':            all_iocs,
    }


def _parse_evtx_record(xml_str: str) -> Optional[dict]:
    try:
        from lxml import etree
        root = etree.fromstring(xml_str.encode('utf-8'))
        ns = {'e': 'http://schemas.microsoft.com/win/2004/08/events/event'}

        def get(xpath):
            result = root.xpath(xpath, namespaces=ns)
            if result:
                return result[0].text if hasattr(result[0], 'text') else str(result[0])
            return None

        def get_data(name):
            result = root.xpath(f'//e:Data[@Name="{name}"]', namespaces=ns)
            return result[0].text if result else None

        return {
            'timestamp':    get('//e:TimeCreated/@SystemTime'),
            'event_id':     get('//e:EventID'),
            'computer':     get('//e:Computer'),
            'channel':      get('//e:Channel'),
            'provider':     get('//e:Provider/@Name'),
            'subject_user': get_data('SubjectUserName'),
            'target_user':  get_data('TargetUserName'),
            'logon_type':   get_data('LogonType'),
            'process_name': get_data('NewProcessName') or get_data('ProcessName'),
            'command_line': get_data('CommandLine'),
            'ip_address':   get_data('IpAddress'),
            'workstation':  get_data('WorkstationName'),
        }
    except Exception:
        return None


def _error_result(message: str) -> dict:
    return {'parsed_content': '{}', 'summary': f"Parse error: {message}", 'timeline_events': [], 'iocs': []}
