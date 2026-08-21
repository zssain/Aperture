"""Security primitives: Argon2id password hashing, session tokens, and a per-account
login rate limiter.

Timing-equivalence: :data:`DUMMY_PASSWORD_HASH` lets the login path run an Argon2
verification even when the account does not exist, so unknown-user and wrong-password
responses are indistinguishable in timing as well as body/status.
"""

import hashlib
import secrets
import time
from collections import defaultdict, deque
from collections.abc import Callable
from dataclasses import dataclass, field

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

_hasher = PasswordHasher()  # Argon2id by default

# Precomputed once per process. Verifying a password against it costs the same as a
# real verification, equalising timing for unknown accounts.
DUMMY_PASSWORD_HASH = _hasher.hash("aperture-timing-equaliser")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, VerificationError):
        return False


def generate_session_token() -> str:
    """A high-entropy, URL-safe opaque session token (never stored in the clear)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """SHA-256 hex of a session token — what we store and look up by."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class RateLimitExceededError(Exception):
    def __init__(self, retry_after_seconds: int) -> None:
        super().__init__("login rate limit exceeded")
        self.retry_after_seconds = retry_after_seconds


@dataclass
class _Bucket:
    attempts: deque[float] = field(default_factory=deque)
    locked_until: float = 0.0
    lockouts: int = 0


class LoginRateLimiter:
    """In-memory per-account limiter: N attempts per window, exponential lockout.

    Keyed by the submitted email so known and unknown accounts throttle identically.
    Process-local — adequate for a single API process; a shared store would be needed
    across replicas (noted as a limitation for this stage).
    """

    def __init__(
        self,
        max_attempts: int = 5,
        window_seconds: float = 60.0,
        base_lockout_seconds: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._max = max_attempts
        self._window = window_seconds
        self._base_lockout = base_lockout_seconds
        self._clock = clock
        self._buckets: dict[str, _Bucket] = defaultdict(_Bucket)

    def hit(self, key: str) -> None:
        """Record an attempt; raise :class:`RateLimitExceededError` if over the limit."""
        now = self._clock()
        bucket = self._buckets[key]
        if now < bucket.locked_until:
            raise RateLimitExceededError(int(bucket.locked_until - now) + 1)
        while bucket.attempts and now - bucket.attempts[0] > self._window:
            bucket.attempts.popleft()
        bucket.attempts.append(now)
        if len(bucket.attempts) > self._max:
            bucket.lockouts += 1
            lockout = self._base_lockout * (2 ** (bucket.lockouts - 1))
            bucket.locked_until = now + lockout
            bucket.attempts.clear()
            raise RateLimitExceededError(int(lockout))

    def reset(self, key: str) -> None:
        self._buckets.pop(key, None)

    def clear(self) -> None:
        self._buckets.clear()


login_rate_limiter = LoginRateLimiter()
