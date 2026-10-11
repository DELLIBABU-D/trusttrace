"""Privacy-conscious device/network identifiers.

The browser sends a random per-browser ID (X-TT-Device, created on first visit and explained in the registration
consent text). The server keeps only an HMAC of it and of the client IP address, keyed with the server secret, so the
raw values can't be recovered or matched against other systems. Recorded for candidates only, at register/login/apply.
"""
from __future__ import annotations

import hashlib
import hmac
import re

from fastapi import Request
from sqlalchemy.orm import Session

from ..config import secret_key
from ..models import DeviceSighting

_DEVICE_RE = re.compile(r"^[A-Za-z0-9-]{16,64}$")


def _h(kind: str, value: str) -> str:
    return hmac.new(secret_key().encode(), f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()[:32]


def record(db: Session, request: Request | None, candidate_id: str, action: str) -> None:
    if request is None:
        return
    raw = request.headers.get("x-tt-device", "")
    device = _h("device", raw) if _DEVICE_RE.match(raw) else ""
    ip = request.client.host if request.client else ""
    # Only public addresses are used for the shared-network rule: loopback/LAN addresses are shared by everyone on the
    # same machine or office network and would raise meaningless alerts.
    from ..ratelimit import is_local
    network = _h("net", ip) if ip and not is_local(ip) else ""
    if device or network:
        db.add(DeviceSighting(candidate_id=candidate_id, device_hash=device, network_hash=network, action=action))
