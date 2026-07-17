from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from dataclasses import dataclass


_SCRYPT_NAME = "scrypt"
_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def _derive_password(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=n,
        r=r,
        p=p,
        maxmem=64 * 1024 * 1024,
    )


def hash_password(password: str, salt: bytes | None = None) -> str:
    if not password:
        raise ValueError("密码不能为空。")
    actual_salt = salt or secrets.token_bytes(16)
    digest = _derive_password(password, actual_salt, _SCRYPT_N, _SCRYPT_R, _SCRYPT_P)
    return (
        f"{_SCRYPT_NAME}${_SCRYPT_N}${_SCRYPT_R}${_SCRYPT_P}$"
        f"{actual_salt.hex()}${digest.hex()}"
    )


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, n_text, r_text, p_text, salt_hex, digest_hex = encoded_hash.split("$", 5)
        if algorithm != _SCRYPT_NAME:
            return False
        n, r, p = int(n_text), int(r_text), int(p_text)
        if (n, r, p) != (_SCRYPT_N, _SCRYPT_R, _SCRYPT_P):
            return False
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        actual = _derive_password(password, salt, n, r, p)
    except (TypeError, ValueError, OverflowError):
        return False
    return hmac.compare_digest(actual, expected)


@dataclass(frozen=True)
class AuthDecision:
    status: str
    retry_after_seconds: int = 0


class LoginGuard:
    def __init__(
        self,
        username: str,
        password_hash: str,
        max_failures: int = 5,
        cooldown_seconds: int = 900,
    ) -> None:
        self.username = username
        self.password_hash = password_hash
        self.max_failures = max(1, int(max_failures))
        self.cooldown_seconds = max(1, int(cooldown_seconds))
        self._failure_count = 0
        self._locked_until = 0.0

    @property
    def failure_count(self) -> int:
        return self._failure_count

    def authenticate(self, username: str, password: str, now: float) -> AuthDecision:
        if now < self._locked_until:
            return AuthDecision(
                status="locked",
                retry_after_seconds=max(1, math.ceil(self._locked_until - now)),
            )
        if self._locked_until:
            self._failure_count = 0
            self._locked_until = 0.0

        password_matches = verify_password(password, self.password_hash)
        if hmac.compare_digest(str(username), self.username) and password_matches:
            self._failure_count = 0
            return AuthDecision(status="authenticated")

        self._failure_count += 1
        if self._failure_count >= self.max_failures:
            self._locked_until = now + self.cooldown_seconds
            return AuthDecision(status="locked", retry_after_seconds=self.cooldown_seconds)
        return AuthDecision(status="denied")


@dataclass(frozen=True)
class SessionClock:
    max_idle_seconds: int = 8 * 60 * 60

    def is_expired(self, last_activity: float, now: float) -> bool:
        return now - last_activity > self.max_idle_seconds
