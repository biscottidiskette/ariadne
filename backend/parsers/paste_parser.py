import json
from parsers.ioc_parser import extract_iocs


def parse_paste(raw_content: str) -> dict:
    iocs = extract_iocs(raw_content, context="Pasted content")
    lines = raw_content.strip().split('\n')
    line_count = len(lines)
    content_lower = raw_content.lower()
    detected_hints = []

    if 'eventid' in content_lower or 'event id' in content_lower:
        detected_hints.append('Windows events')
    if 'process' in content_lower and 'pid' in content_lower:
        detected_hints.append('process activity')
    if any(h in content_lower for h in ['alert', 'detect', 'threat']):
        detected_hints.append('security alerts')
    if 'sigma' in content_lower and 'detection:' in content_lower:
        detected_hints.append('Sigma rule')
    if any(h in content_lower for h in ['powershell', 'cmd.exe', 'wscript']):
        detected_hints.append('command execution')
    if any(h in content_lower for h in ['hklm', 'hkcu', 'registry']):
        detected_hints.append('registry activity')

    hint_str = ', '.join(detected_hints) if detected_hints else 'generic text'
    ioc_summary = f"{len(iocs)} IoCs extracted." if iocs else "No IoCs detected."

    preview_lines = lines[:20]
    if len(lines) > 20:
        preview_lines.append(f"... ({len(lines) - 20} more lines)")

    summary = (
        f"Pasted content: {line_count} lines. "
        f"Detected: {hint_str}. "
        f"{ioc_summary}\n\nContent preview:\n" + '\n'.join(preview_lines)
    )

    return {
        'parsed_content': json.dumps({
            'line_count': line_count,
            'detected_hints': detected_hints,
            'preview': '\n'.join(lines[:50]),
        }),
        'summary': summary,
        'timeline_events': [],
        'iocs': iocs,
    }
