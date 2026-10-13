from __future__ import annotations

from dataclasses import dataclass
import time
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse


PAIRING_SCHEME = 'vishnu'
PAIRING_HOST = 'pair'
PAIRING_VERSION = '1'


@dataclass(frozen=True)
class PairingPayload:
    base_url: str
    token: str
    code: str
    expires_at: float


def normalize_vishnu_origin(value: str, *, allow_local_http: bool = False) -> str:
    raw = str(value or '').strip()
    parsed = urlparse(raw)
    if parsed.username is not None or parsed.password is not None:
        raise ValueError('Do not embed credentials in the Vishnu URL')
    if not parsed.hostname:
        raise ValueError('Vishnu URL must include a hostname')
    local = parsed.hostname in {'127.0.0.1', 'localhost', '::1'}
    if parsed.scheme != 'https' and not (allow_local_http and local and parsed.scheme == 'http'):
        raise ValueError('Vishnu URL must use HTTPS except for explicitly allowed localhost development')
    if parsed.fragment:
        raise ValueError('Vishnu URL must not contain a fragment')
    port = f':{parsed.port}' if parsed.port is not None else ''
    host = f'[{parsed.hostname}]' if ':' in parsed.hostname and not parsed.hostname.startswith('[') else parsed.hostname
    return urlunparse((parsed.scheme, f'{host}{port}', '', '', '', '')).rstrip('/')


def build_pairing_uri(
    *,
    base_url: str,
    token: str,
    code: str,
    expires_at: float,
    allow_local_http: bool = False,
) -> str:
    origin = normalize_vishnu_origin(base_url, allow_local_http=allow_local_http)
    clean_token = str(token or '').strip()
    clean_code = str(code or '').strip()
    expiry = float(expires_at)
    if not 16 <= len(clean_token) <= 256:
        raise ValueError('Pairing token length is invalid')
    if len(clean_code) != 6 or not clean_code.isdigit():
        raise ValueError('Pairing code must contain exactly six digits')
    if expiry <= time.time():
        raise ValueError('Pairing offer is expired')
    query = urlencode({
        'v': PAIRING_VERSION,
        'base': origin,
        'token': clean_token,
        'code': clean_code,
        'expires': f'{expiry:.6f}',
    }, quote_via=quote)
    return f'{PAIRING_SCHEME}://{PAIRING_HOST}?{query}'


def parse_pairing_uri(
    uri: str,
    *,
    allow_local_http: bool = False,
    now: float | None = None,
) -> PairingPayload:
    parsed = urlparse(str(uri or '').strip())
    if parsed.scheme != PAIRING_SCHEME or parsed.hostname != PAIRING_HOST or parsed.path not in {'', '/'}:
        raise ValueError('This is not a Vishnu pairing QR code')
    if parsed.fragment:
        raise ValueError('Pairing QR code must not contain a fragment')
    values = parse_qs(parsed.query, keep_blank_values=True, strict_parsing=True)
    allowed = {'v', 'base', 'token', 'code', 'expires'}
    if set(values) != allowed or any(len(items) != 1 for items in values.values()):
        raise ValueError('Pairing QR code fields are invalid')
    if values['v'][0] != PAIRING_VERSION:
        raise ValueError('Unsupported Vishnu pairing QR version')
    origin = normalize_vishnu_origin(values['base'][0], allow_local_http=allow_local_http)
    token = values['token'][0].strip()
    code = values['code'][0].strip()
    if not 16 <= len(token) <= 256:
        raise ValueError('Pairing token length is invalid')
    if len(code) != 6 or not code.isdigit():
        raise ValueError('Pairing code must contain exactly six digits')
    try:
        expiry = float(values['expires'][0])
    except (TypeError, ValueError) as exc:
        raise ValueError('Pairing expiry is invalid') from exc
    current = time.time() if now is None else float(now)
    if expiry <= current:
        raise ValueError('This pairing QR code has expired')
    return PairingPayload(base_url=origin, token=token, code=code, expires_at=expiry)
