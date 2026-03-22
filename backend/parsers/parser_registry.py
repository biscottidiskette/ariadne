import json
from typing import Optional
from parsers.chainsaw_parser import parse_chainsaw
from parsers.evtx_parser import parse_evtx
from parsers.edr_parser import parse_edr
from parsers.siem_parser import parse_siem
from parsers.paste_parser import parse_paste
from parsers.ioc_parser import extract_iocs


def parse_artifact(
    raw_content: str,
    artifact_type: str,
    filename: Optional[str] = None,
    file_bytes: Optional[bytes] = None,
) -> dict:
    if artifact_type in ('other', 'paste') and filename:
        artifact_type = _detect_type_from_filename(filename, raw_content)

    if artifact_type == 'evtx' and file_bytes:
        return parse_evtx(file_bytes)
    elif artifact_type == 'chainsaw':
        return parse_chainsaw(raw_content)
    elif artifact_type == 'edr':
        return parse_edr(raw_content)
    elif artifact_type == 'siem':
        return parse_siem(raw_content)
    elif artifact_type == 'ioc':
        iocs = extract_iocs(raw_content, context="IoC list upload")
        return {
            'parsed_content': json.dumps({'ioc_count': len(iocs)}),
            'summary': f"IoC list: {len(iocs)} indicators extracted.",
            'timeline_events': [],
            'iocs': iocs,
        }
    else:
        return parse_paste(raw_content)


def _detect_type_from_filename(filename: str, content: str) -> str:
    name_lower = filename.lower()
    if name_lower.endswith('.evtx'):
        return 'evtx'
    if name_lower.endswith('.json'):
        if '"detections"' in content[:500] or '"Event"' in content[:500]:
            return 'chainsaw'
        if '"threatInfo"' in content[:500] or 'detect_id' in content[:500]:
            return 'edr'
        if '"results"' in content[:500] or '"hits"' in content[:500]:
            return 'siem'
        return 'paste'
    if name_lower.endswith('.csv'):
        return 'siem'
    if name_lower.endswith(('.yml', '.yaml')):
        return 'sigma'
    return 'paste'
