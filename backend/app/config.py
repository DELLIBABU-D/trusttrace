"""Runtime settings. Everything can be overridden with environment variables; nothing secret is hardcoded."""
from __future__ import annotations

import os
import secrets
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = BACKEND_DIR.parent
DATA_DIR = Path(os.environ.get("TT_DATA_DIR", BACKEND_DIR / "data"))
UPLOAD_DIR = DATA_DIR / "uploads"          # private: never served as static files
FRONTEND_DIST = PROJECT_DIR / "frontend" / "dist"

DATABASE_URL = os.environ.get("TT_DATABASE_URL", f"sqlite:///{(DATA_DIR / 'trusttrace.db').as_posix()}")
TOKEN_TTL_HOURS = int(os.environ.get("TT_TOKEN_TTL_HOURS", "12"))
DOWNLOAD_LINK_TTL_MINUTES = 10
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
OTP_TTL_MINUTES = 10
OTP_MAX_ATTEMPTS = 5
# Recruiter organisations start as "pending". Set TT_AUTO_APPROVE_ORGS=1 only for local demos.
AUTO_APPROVE_ORGS = os.environ.get("TT_AUTO_APPROVE_ORGS", "0") == "1"


def secret_key() -> str:
    """JWT signing key: TT_SECRET_KEY, or a random key generated once and kept in data/secret.key."""
    env = os.environ.get("TT_SECRET_KEY")
    if env:
        return env
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / "secret.key"
    if not path.exists():
        path.write_text(secrets.token_urlsafe(48))
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return path.read_text().strip()


# ---------------------------------------------------------------- Phase 6
PASSPORT_TTL_DAYS = int(os.environ.get("TT_PASSPORT_TTL_DAYS", "90"))
# Base URL printed in passport QR codes, e.g. https://trusttrace.example. Defaults to the URL the request came in on.
PUBLIC_URL = os.environ.get("TT_PUBLIC_URL", "").rstrip("/")
MAX_REQUEST_BYTES = int(os.environ.get("TT_MAX_REQUEST_MB", "12")) * 1024 * 1024


def _private_file(name: str, make) -> bytes:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / name
    if not path.exists():
        path.write_bytes(make())
        try:
            path.chmod(0o600)
        except OSError:
            pass
    return path.read_bytes()


def evidence_key() -> bytes:
    """HMAC key for the evidence chain: TT_EVIDENCE_KEY, or a random key generated once in data/evidence.key.
    Kept separate from the JWT key so rotating login sessions never breaks the chain."""
    env = os.environ.get("TT_EVIDENCE_KEY")
    if env:
        return env.encode()
    return _private_file("evidence.key", lambda: secrets.token_urlsafe(48).encode()).strip()


def passport_signing_key_pem() -> bytes:
    """Ed25519 private key (PEM) that signs passports: TT_PASSPORT_KEY_FILE, or one generated once in data/passport_ed25519.pem."""
    env = os.environ.get("TT_PASSPORT_KEY_FILE")
    if env:
        return Path(env).read_bytes()

    def make() -> bytes:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        return Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                          serialization.NoEncryption())
    return _private_file("passport_ed25519.pem", make)

# ---------------------------------------------------------------- DigiLocker (Requester / MeriPehchaan partner API)
# live      : real DigiLocker; needs an approved partner app (client id + secret) and a registered redirect URI.
# simulated : a built-in, clearly-labelled stand-in for demos (records from manage.py load-digilocker-records).
# off       : hide the feature.
DIGILOCKER_CLIENT_ID = os.environ.get("TT_DIGILOCKER_CLIENT_ID", "")
DIGILOCKER_CLIENT_SECRET = os.environ.get("TT_DIGILOCKER_CLIENT_SECRET", "")
DIGILOCKER_REDIRECT_URI = os.environ.get("TT_DIGILOCKER_REDIRECT_URI", "")  # default: <public url>/api/digilocker/callback
DIGILOCKER_BASE = os.environ.get("TT_DIGILOCKER_BASE", "https://digilocker.meripehchaan.gov.in").rstrip("/")


def digilocker_mode() -> str:
    mode = os.environ.get("TT_DIGILOCKER_MODE", "").strip().lower()
    if mode in ("live", "simulated", "off"):
        return mode
    return "live" if DIGILOCKER_CLIENT_ID and DIGILOCKER_CLIENT_SECRET else "simulated"
