from __future__ import annotations

from dataclasses import dataclass
import re
import time
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse


PAIRING_SCHEME = 'vishnu'
PAIRING_HOST = 'pair'
LEGACY_PAIRING_VERSION = '1'
ZERO_CONFIG_PAIRING_VERSION = '2'
_SERVICE_RE = re.compile(r'^[a-zA-Z0-9_-]{8,64}$')
_FINGERPRINT_RE = re.compile(r'^[0-9a-fA-F]{64}$')


@dataclass(frozen=True)
class PairingPayload:
    token: str
    code: str
    expires_at: float
    version: int = 1
    base_url: str | None = None
    service_id: str | None = None
    cert_sha256: str | None = None
    fallback_url: str | None = None

    @property
    def zero_config(self) -> bool:
        return self.version == 2 and bool(self.service_id and self.cert_sha256)


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


def _validated_offer(token: str, code: str, expires_at: float) -> tuple[str, str, float]:
    clean_token = str(token or '').strip()
    clean_code = str(code or '').strip()
    expiry = float(expires_at)
    if not 16 <= len(clean_token) <= 256:
        raise ValueError('Pairing token length is invalid')
    if len(clean_code) != 6 or not clean_code.isdigit():
        raise ValueError('Pairing code must contain exactly six digits')
    if expiry <= time.time():
        raise ValueError('Pairing offer is expired')
    return clean_token, clean_code, expiry


def build_pairing_uri(
    *,
    base_url: str,
    token: str,
    code: str,
    expires_at: float,
    allow_local_http: bool = False,
) -> str:
    """Build the backward-compatible direct-address pairing payload."""
    origin = normalize_vishnu_origin(base_url, allow_local_http=allow_local_http)
    clean_token, clean_code, expiry = _validated_offer(token, code, expires_at)
    query = urlencode({
        'v': LEGACY_PAIRING_VERSION,
        'base': origin,
        'token': clean_token,
        'code': clean_code,
        'expires': f'{expiry:.6f}',
    }, quote_via=quote)
    return f'{PAIRING_SCHEME}://{PAIRING_HOST}?{query}'


def build_zero_config_pairing_uri(
    *,
    service_id: str,
    cert_sha256: str,
    token: str,
    code: str,
    expires_at: float,
    fallback_url: str | None = None,
) -> str:
    """Build a discovery payload with a pinned TLS identity and no LAN address."""
    clean_service = str(service_id or '').strip()
    fingerprint = str(cert_sha256 or '').strip().lower()
    if not _SERVICE_RE.fullmatch(clean_service):
        raise ValueError('Local Vishnu service identity is invalid')
    if not _FINGERPRINT_RE.fullmatch(fingerprint):
        raise ValueError('Local Vishnu TLS fingerprint is invalid')
    clean_token, clean_code, expiry = _validated_offer(token, code, expires_at)
    values = {
        'v': ZERO_CONFIG_PAIRING_VERSION,
        'service': clean_service,
        'fp': fingerprint,
        'token': clean_token,
        'code': clean_code,
        'expires': f'{expiry:.6f}',
    }
    if fallback_url:
        values['fallback'] = normalize_vishnu_origin(fallback_url)
    query = urlencode(values, quote_via=quote)
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
    if 'v' not in values or len(values['v']) != 1:
        raise ValueError('Pairing QR code fields are invalid')
    version = values['v'][0]
    allowed = (
        {'v', 'base', 'token', 'code', 'expires'}
        if version == LEGACY_PAIRING_VERSION
        else {'v', 'service', 'fp', 'token', 'code', 'expires', 'fallback'}
        if version == ZERO_CONFIG_PAIRING_VERSION
        else set()
    )
    required = allowed - {'fallback'}
    if not allowed or not required.issubset(values) or not set(values).issubset(allowed) or any(len(items) != 1 for items in values.values()):
        if version not in {LEGACY_PAIRING_VERSION, ZERO_CONFIG_PAIRING_VERSION}:
            raise ValueError('Unsupported Vishnu pairing QR version')
        raise ValueError('Pairing QR code fields are invalid')
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
    if version == LEGACY_PAIRING_VERSION:
        origin = normalize_vishnu_origin(values['base'][0], allow_local_http=allow_local_http)
        return PairingPayload(token=token, code=code, expires_at=expiry, version=1, base_url=origin)
    service_id = values['service'][0].strip()
    fingerprint = values['fp'][0].strip().lower()
    if not _SERVICE_RE.fullmatch(service_id):
        raise ValueError('Local Vishnu service identity is invalid')
    if not _FINGERPRINT_RE.fullmatch(fingerprint):
        raise ValueError('Local Vishnu TLS fingerprint is invalid')
    fallback = values.get('fallback', [None])[0]
    fallback_origin = normalize_vishnu_origin(fallback) if fallback else None
    return PairingPayload(
        token=token,
        code=code,
        expires_at=expiry,
        version=2,
        service_id=service_id,
        cert_sha256=fingerprint,
        fallback_url=fallback_origin,
    )
