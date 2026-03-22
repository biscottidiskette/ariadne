import json
from parsers.ioc_parser import extract_iocs


def parse_edr(raw_content: str) -> dict:
    try:
        data = json.loads(raw_content)
    except json.JSONDecodeError:
        try:
            lines = [l.strip() for l in raw_content.strip().split('\n') if l.strip()]
            data = [json.loads(l) for l in lines]
        except json.JSONDecodeError:
            return _parse_plain_text_edr(raw_content)

    if isinstance(data, dict):
        data = [data]

    alerts = []
    all_iocs = []
    timeline_events = []

    for item in data:
        alert = _normalize_alert(item)
        if alert:
            alerts.append(alert)
            if alert.get('timestamp'):
                timeline_events.append({
                    'event_time':  alert['timestamp'],
                    'event_type':  'process_creation',
                    'description': alert.get('description') or f"EDR Alert: {alert.get('technique', 'unknown')}",
                    'host':        alert.get('hostname'),
                    'actor':       alert.get('username'),
                    'process':     alert.get('process_name'),
                })
        iocs = extract_iocs(json.dumps(item), context="EDR alert")
        all_iocs.extend(iocs)

    hosts = list(set(a.get('hostname') for a in alerts if a.get('hostname')))
    techniques = list(set(a.get('technique') for a in alerts if a.get('technique')))

    summary_parts = [f"EDR: {len(alerts)} alert(s)."]
    if hosts:
        summary_parts.append(f"Hosts: {', '.join(hosts[:5])}.")
    if techniques:
        summary_parts.append(f"Techniques: {', '.join(techniques[:5])}.")
    if all_iocs:
        summary_parts.append(f"{len(all_iocs)} IoCs extracted.")

    return {
        'parsed_content':  json.dumps(alerts),
        'summary':         ' '.join(summary_parts),
        'timeline_events': timeline_events,
        'iocs':            all_iocs,
    }


def _normalize_alert(item: dict) -> dict:
    if 'detect_id' in item or 'detection_id' in item:
        return {
            'vendor': 'crowdstrike',
            'alert_id': item.get('detect_id') or item.get('detection_id'),
            'timestamp': item.get('created_timestamp') or item.get('first_behavior'),
            'severity': item.get('max_severity_displayname', '').lower(),
            'description': item.get('description'),
            'hostname': item.get('device', {}).get('hostname') if isinstance(item.get('device'), dict) else None,
            'username': item.get('user_name'),
            'process_name': item.get('filename'),
            'command_line': item.get('cmdline'),
            'technique': item.get('technique'),
            'tactic': item.get('tactic'),
            'sha256': item.get('sha256'),
        }
    if 'threatInfo' in item or 'agentRealtimeInfo' in item:
        threat = item.get('threatInfo', {})
        agent = item.get('agentRealtimeInfo', {})
        return {
            'vendor': 'sentinelone',
            'alert_id': item.get('id'),
            'timestamp': threat.get('createdAt'),
            'severity': threat.get('confidenceLevel', '').lower(),
            'description': threat.get('threatName'),
            'hostname': agent.get('agentComputerName'),
            'username': threat.get('processUser'),
            'process_name': threat.get('maliciousProcessArguments'),
            'command_line': threat.get('maliciousProcessArguments'),
            'technique': threat.get('mitigationStatus'),
            'sha256': threat.get('sha256'),
        }
    return {
        'vendor': 'generic',
        'alert_id': item.get('id') or item.get('alert_id'),
        'timestamp': item.get('timestamp') or item.get('created_at') or item.get('time'),
        'severity': item.get('severity') or item.get('risk_level'),
        'description': item.get('description') or item.get('name') or item.get('title'),
        'hostname': item.get('hostname') or item.get('host') or item.get('computer'),
        'username': item.get('username') or item.get('user'),
        'process_name': item.get('process') or item.get('process_name') or item.get('image'),
        'command_line': item.get('command_line') or item.get('cmdline'),
        'technique': item.get('technique') or item.get('mitre_technique'),
        'sha256': item.get('sha256') or item.get('hash'),
    }


def _parse_plain_text_edr(raw_content: str) -> dict:
    iocs = extract_iocs(raw_content, context="EDR plain text")
    return {
        'parsed_content': json.dumps({'raw': raw_content[:2000]}),
        'summary': f"EDR plain text output: {len(raw_content)} chars. {len(iocs)} IoCs extracted.",
        'timeline_events': [],
        'iocs': iocs,
    }
