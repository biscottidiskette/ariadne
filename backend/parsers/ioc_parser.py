import re
from typing import Optional

IPV4_PATTERN = re.compile(
    r'\b(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}'
    r'(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\b'
)
DOMAIN_PATTERN = re.compile(
    r'\b(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)'
    r'+[a-zA-Z]{2,}\b'
)
MD5_PATTERN    = re.compile(r'\b[a-fA-F0-9]{32}\b')
SHA1_PATTERN   = re.compile(r'\b[a-fA-F0-9]{40}\b')
SHA256_PATTERN = re.compile(r'\b[a-fA-F0-9]{64}\b')
URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]{3,}')
WIN_PATH_PATTERN = re.compile(
    r'[A-Za-z]:\\(?:[^\\/:*?"<>|\r\n]+\\)*[^\\/:*?"<>|\r\n]*'
)
REG_KEY_PATTERN = re.compile(
    r'(?:HKEY_LOCAL_MACHINE|HKEY_CURRENT_USER|HKEY_CLASSES_ROOT|'
    r'HKEY_USERS|HKEY_CURRENT_CONFIG|HKLM|HKCU|HKU|HKCR)'
    r'(?:\\[^\s,;"\']+)+'
)

EXCLUDED_IPS = {'127.0.0.1', '0.0.0.0', '255.255.255.255', '169.254.0.1'}
EXCLUDED_DOMAINS = {
    'microsoft.com', 'windows.com', 'windowsupdate.com', 'localhost', 'local'
}


def extract_iocs(text: str, context: Optional[str] = None) -> list[dict]:
    found = []
    seen = set()

    def add(ioc_type: str, value: str, ctx: Optional[str] = None):
        key = (ioc_type, value.lower())
        if key not in seen:
            seen.add(key)
            found.append({'ioc_type': ioc_type, 'value': value, 'context': ctx or context})

    for match in URL_PATTERN.findall(text):
        add('url', match.rstrip('.,;)'))

    for match in REG_KEY_PATTERN.findall(text):
        add('registry_key', match)

    for match in WIN_PATH_PATTERN.findall(text):
        if len(match) > 5:
            add('file_path', match)

    for match in SHA256_PATTERN.findall(text):
        add('hash_sha256', match.lower())

    for match in SHA1_PATTERN.findall(text):
        if not any(match.lower() in ioc['value'] for ioc in found if ioc['ioc_type'] == 'hash_sha256'):
            add('hash_sha1', match.lower())

    for match in MD5_PATTERN.findall(text):
        if not any(match.lower() in ioc['value'] for ioc in found if ioc['ioc_type'] in ('hash_sha256', 'hash_sha1')):
            add('hash_md5', match.lower())

    for match in IPV4_PATTERN.findall(text):
        if match not in EXCLUDED_IPS:
            add('ip', match)

    for match in DOMAIN_PATTERN.findall(text):
        match_lower = match.lower()
        if any(match == ioc['value'] for ioc in found if ioc['ioc_type'] == 'ip'):
            continue
        if any(match_lower.endswith(excl) for excl in EXCLUDED_DOMAINS):
            continue
        if len(match) < 5:
            continue
        add('domain', match_lower)

    return found
