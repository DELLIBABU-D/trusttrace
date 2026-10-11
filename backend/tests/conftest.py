"""Each test session uses a fresh temporary database and upload folder (never the real data/ folder)."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

_tmp = tempfile.mkdtemp(prefix="trusttrace-test-")
os.environ["TT_DATA_DIR"] = _tmp
os.environ.pop("TT_DATABASE_URL", None)
os.environ.pop("TT_AUTO_APPROVE_ORGS", None)
os.environ["TT_VERIFICATION_SYNC"] = "1"  # run verification jobs inside the request so tests are deterministic
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import manage  # noqa: E402

manage.init_db()

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.routers import auth as auth_router  # noqa: E402

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPEG_DATA_URL = "data:image/jpeg;base64," + __import__("base64").b64encode(b"\xff\xd8\xff\xe0" + b"\x00" * 64).decode()


@pytest.fixture(scope="session")
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    auth_router._hits.clear()
    yield


@pytest.fixture
def otp_box(monkeypatch):
    box: dict[str, str] = {}
    monkeypatch.setattr(auth_router, "deliver_otp", lambda phone, code: box.__setitem__(phone, code))
    return box
