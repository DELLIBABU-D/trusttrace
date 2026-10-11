"""Encryption of face embeddings at rest (Fernet = AES-128-CBC + HMAC-SHA256).

The key is derived from the server secret (TT_SECRET_KEY or backend/data/secret.key). Losing that secret makes
stored embeddings unreadable, which simply means candidates are re-enrolled from their selfie.
"""
from __future__ import annotations

import base64
import hashlib

import numpy as np
from cryptography.fernet import Fernet, InvalidToken

from ..config import secret_key


def _fernet() -> Fernet:
    digest = hashlib.sha256(b"trusttrace-face-embedding-v1:" + secret_key().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_embedding(vec: np.ndarray) -> bytes:
    return _fernet().encrypt(np.asarray(vec, dtype=np.float32).tobytes())


def decrypt_embedding(blob: bytes) -> np.ndarray | None:
    try:
        return np.frombuffer(_fernet().decrypt(blob), dtype=np.float32).copy()
    except (InvalidToken, ValueError):
        return None


def _text_fernet() -> Fernet:
    digest = hashlib.sha256(b"trusttrace-secret-text-v1:" + secret_key().encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_text(text: str) -> str:
    return _text_fernet().encrypt(text.encode()).decode() if text else ""


def decrypt_text(blob: str) -> str:
    try:
        return _text_fernet().decrypt(blob.encode()).decode() if blob else ""
    except (InvalidToken, ValueError):
        return ""
