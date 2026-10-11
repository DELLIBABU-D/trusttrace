"""Password hashing (Argon2id) and signed tokens (JWT, HS256)."""
from __future__ import annotations

import hmac
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from .config import DOWNLOAD_LINK_TTL_MINUTES, TOKEN_TTL_HOURS, secret_key

_hasher = PasswordHasher()  # argon2id, library defaults (memory-hard)
_ALG = "HS256"
# A real Argon2 hash of a random value, used so unknown-email logins cost the same time as wrong passwords.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def hash_secret(value: str) -> str:
    return _hasher.hash(value)


def verify_secret(stored_hash: str | None, value: str) -> bool:
    try:
        return _hasher.verify(stored_hash or _DUMMY_HASH, value) and stored_hash is not None
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored_hash: str) -> bool:
    return _hasher.check_needs_rehash(stored_hash)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def issue_access_token(user_id: str, role: str, session_id: str) -> tuple[str, datetime]:
    exp = _now() + timedelta(hours=TOKEN_TTL_HOURS)
    token = jwt.encode({"sub": user_id, "role": role, "jti": session_id, "typ": "access", "exp": exp, "iat": _now()}, secret_key(), algorithm=_ALG)
    return token, exp.replace(tzinfo=None)


def decode_token(token: str, typ: str) -> dict | None:
    try:
        claims = jwt.decode(token, secret_key(), algorithms=[_ALG], options={"require": ["exp", "sub", "typ"]})
    except jwt.PyJWTError:
        return None
    return claims if hmac.compare_digest(str(claims.get("typ")), typ) else None


def issue_download_token(document_id: str, user_id: str) -> str:
    exp = _now() + timedelta(minutes=DOWNLOAD_LINK_TTL_MINUTES)
    return jwt.encode({"sub": user_id, "doc": document_id, "typ": "download", "exp": exp}, secret_key(), algorithm=_ALG)


def new_otp_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"
