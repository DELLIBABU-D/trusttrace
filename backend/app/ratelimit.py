"""Simple in-process rate limiting (per key, sliding window).

Limits are kept in memory: they reset on restart and are not shared between server processes (documented limitation).
Per-network limits are relaxed for loopback/private addresses, because during a local demo every browser shares 127.0.0.1;
per-account and per-phone limits always apply.
"""
from __future__ import annotations

import ipaddress
import time
from collections import deque

from fastapi import Request

from .errors import ApiError

_hits: dict[str, deque[float]] = {}
_MAX_KEYS = 50_000
LOCAL_FACTOR = 20


def client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def is_local(ip: str) -> bool:
    try:
        a = ipaddress.ip_address(ip)
    except ValueError:
        return ip in ("testclient", "unknown", "localhost")
    return a.is_loopback or a.is_private or a.is_link_local


def limit(key: str, max_hits: int, window_s: int, message: str) -> None:
    now = time.monotonic()
    if len(_hits) > _MAX_KEYS:  # bound memory: drop keys whose newest hit is older than an hour
        for k in [k for k, q in _hits.items() if not q or now - q[-1] > 3600]:
            _hits.pop(k, None)
    q = _hits.setdefault(key, deque())
    while q and now - q[0] > window_s:
        q.popleft()
    if len(q) >= max_hits:
        raise ApiError(429, "rate_limited", message)
    q.append(now)


def per_ip(request: Request, name: str, max_hits: int, window_s: int, message: str) -> None:
    ip = client_ip(request)
    limit(f"{name}:{ip}", max_hits * (LOCAL_FACTOR if is_local(ip) else 1), window_s, message)


def reset() -> None:
    _hits.clear()
