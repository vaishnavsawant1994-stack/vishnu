from __future__ import annotations
import hashlib, hmac, secrets, threading, time
from dataclasses import dataclass

@dataclass
class PairingOffer:
    code: str
    token: str
    expires_at: float

class PairingManager:
    """Process-scoped one-time pairing authority.

    The control API and desktop QR surface may each construct a manager, but
    they intentionally share this single in-process offer store. A QR offer is
    therefore consumed by the same authority that created it instead of by a
    duplicate pairing system. Access is synchronized because the UI and server
    run on different threads.
    """

    _shared_offers: dict[str, PairingOffer] = {}
    _shared_lock = threading.RLock()

    def __init__(self, ttl_seconds: int = 300):
        self.ttl = max(30, min(int(ttl_seconds), 3600))

    @classmethod
    def _prune_locked(cls, now: float) -> None:
        expired = [token for token, offer in cls._shared_offers.items() if offer.expires_at <= now]
        for token in expired:
            cls._shared_offers.pop(token, None)

    def create(self) -> PairingOffer:
        now = time.time()
        token = secrets.token_urlsafe(32)
        code = f"{secrets.randbelow(1_000_000):06d}"
        offer = PairingOffer(code, token, now + self.ttl)
        with self._shared_lock:
            self._prune_locked(now)
            self._shared_offers[token] = offer
        return offer

    def consume(self, token: str, code: str) -> bool:
        now = time.time()
        with self._shared_lock:
            self._prune_locked(now)
            offer = self._shared_offers.pop(str(token), None)
        if not offer or now > offer.expires_at:
            return False
        return hmac.compare_digest(offer.code, str(code))

    def invalidate(self, token: str) -> bool:
        with self._shared_lock:
            return self._shared_offers.pop(str(token), None) is not None

def hash_secret(secret: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", secret.encode(), salt.encode(), 250_000).hex()

def verify_secret(secret: str, salt: str, expected: str) -> bool:
    return hmac.compare_digest(hash_secret(secret, salt), expected)

def new_bearer_secret() -> tuple[str,str,str]:
    token=secrets.token_urlsafe(48)
    salt=secrets.token_hex(16)
    return token,salt,hash_secret(token,salt)
