from __future__ import annotations

from dataclasses import dataclass
import ipaddress
import socket
from threading import RLock

from zeroconf import IPVersion, ServiceInfo, Zeroconf


SERVICE_TYPE = '_vishnu._tcp.local.'
SERVICE_PREFIX = 'Vishnu-'


def _local_ipv4_addresses() -> list[bytes]:
    values: set[str] = set()
    hostname = socket.gethostname()
    try:
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_STREAM):
            values.add(str(info[4][0]))
    except OSError:
        pass
    try:
        probe = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            probe.connect(('192.0.2.1', 9))
            values.add(str(probe.getsockname()[0]))
        finally:
            probe.close()
    except OSError:
        pass
    usable: list[bytes] = []
    for raw in sorted(values):
        try:
            address = ipaddress.ip_address(raw)
        except ValueError:
            continue
        if address.version != 4 or address.is_loopback or address.is_unspecified or address.is_multicast:
            continue
        usable.append(socket.inet_aton(raw))
    return usable


@dataclass(frozen=True)
class DiscoveryDescriptor:
    service_id: str
    service_name: str
    port: int
    cert_sha256: str


class LocalDeviceAdvertiser:
    """Advertise only the minimal TLS device gateway on the local link.

    The advertisement contains no pairing token, device bearer, owner secret, or
    user data. The QR remains the trust anchor through the certificate fingerprint.
    """

    def __init__(self, *, service_id: str, port: int, cert_sha256: str):
        self.descriptor = DiscoveryDescriptor(
            service_id=str(service_id),
            service_name=f'{SERVICE_PREFIX}{service_id}',
            port=int(port),
            cert_sha256=str(cert_sha256).lower(),
        )
        self._zeroconf: Zeroconf | None = None
        self._info: ServiceInfo | None = None
        self._lock = RLock()

    @property
    def running(self) -> bool:
        with self._lock:
            return self._zeroconf is not None

    def start(self) -> DiscoveryDescriptor:
        with self._lock:
            if self._zeroconf is not None:
                return self.descriptor
            addresses = _local_ipv4_addresses()
            if not addresses:
                raise RuntimeError('No usable local-network address is available for Vishnu device discovery')
            hostname = (socket.gethostname().strip() or 'vishnu').replace(' ', '-').replace('.', '-')
            info = ServiceInfo(
                SERVICE_TYPE,
                f'{self.descriptor.service_name}.{SERVICE_TYPE}',
                addresses=addresses,
                port=self.descriptor.port,
                properties={
                    b'protocol': b'2',
                    b'id': self.descriptor.service_id.encode('ascii'),
                    b'fp': self.descriptor.cert_sha256.encode('ascii'),
                },
                server=f'{hostname}.local.',
            )
            zc = Zeroconf(ip_version=IPVersion.V4Only)
            try:
                zc.register_service(info, allow_name_change=False)
            except Exception:
                zc.close()
                raise
            self._zeroconf = zc
            self._info = info
            return self.descriptor

    def stop(self) -> None:
        with self._lock:
            zc, info = self._zeroconf, self._info
            self._zeroconf = None
            self._info = None
        if zc is None:
            return
        try:
            if info is not None:
                zc.unregister_service(info)
        finally:
            zc.close()
