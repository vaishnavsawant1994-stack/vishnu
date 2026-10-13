from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import ipaddress
import os
from pathlib import Path
import secrets
import socket

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID


@dataclass(frozen=True)
class LocalDeviceIdentity:
    service_id: str
    cert_path: Path
    key_path: Path
    cert_sha256: str


def _write_private(path: Path, data: bytes, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_bytes(data)
    try:
        os.chmod(temp, mode)
    except OSError:
        pass
    os.replace(temp, path)
    try:
        os.chmod(path, mode)
    except OSError:
        pass


def _service_id(path: Path) -> str:
    if path.exists():
        value = path.read_text(encoding='utf-8').strip().lower()
        if len(value) == 32 and all(ch in '0123456789abcdef' for ch in value):
            return value
    value = secrets.token_hex(16)
    _write_private(path, (value + '\n').encode('utf-8'), 0o600)
    return value


def _certificate_fingerprint(cert: x509.Certificate) -> str:
    return hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()


def _load_valid(cert_path: Path, key_path: Path) -> tuple[x509.Certificate, object] | None:
    try:
        cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
        key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
        now = datetime.now(timezone.utc)
        not_after = getattr(cert, 'not_valid_after_utc', cert.not_valid_after.replace(tzinfo=timezone.utc))
        if not_after <= now + timedelta(days=30):
            return None
        if key.public_key().public_numbers() != cert.public_key().public_numbers():
            return None
        return cert, key
    except Exception:
        return None


def ensure_local_device_identity(data_dir: Path) -> LocalDeviceIdentity:
    root = Path(data_dir) / 'local-device-gateway'
    root.mkdir(parents=True, exist_ok=True)
    service_id = _service_id(root / 'service-id')
    cert_path = root / 'gateway-cert.pem'
    key_path = root / 'gateway-key.pem'
    loaded = _load_valid(cert_path, key_path) if cert_path.exists() and key_path.exists() else None
    if loaded is None:
        key = ec.generate_private_key(ec.SECP256R1())
        now = datetime.now(timezone.utc)
        hostname = socket.gethostname().strip() or 'vishnu'
        san: list[x509.GeneralName] = [x509.DNSName('localhost'), x509.DNSName(f'{hostname}.local')]
        try:
            infos = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            seen: set[str] = set()
            for info in infos:
                raw = str(info[4][0]).split('%', 1)[0]
                if raw in seen:
                    continue
                seen.add(raw)
                address = ipaddress.ip_address(raw)
                if not address.is_unspecified:
                    san.append(x509.IPAddress(address))
        except OSError:
            pass
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'Vishnu Local Device Gateway')])
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=5))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName(san), critical=False)
            .sign(key, hashes.SHA256())
        )
        _write_private(
            key_path,
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            ),
            0o600,
        )
        _write_private(cert_path, cert.public_bytes(serialization.Encoding.PEM), 0o644)
    else:
        cert, _ = loaded
    return LocalDeviceIdentity(
        service_id=service_id,
        cert_path=cert_path,
        key_path=key_path,
        cert_sha256=_certificate_fingerprint(cert),
    )
