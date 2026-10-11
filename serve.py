"""Start TrustTrace (API + website) on http://localhost:5173

    pip install -r backend/requirements.txt     (first time only)
    python serve.py

- Creates or upgrades the database (backend/data/trusttrace.db) with Alembic. It never adds sample people or jobs.
- Uploaded documents are stored privately in backend/data/uploads and are only downloadable through the API.
- API documentation: http://localhost:5173/api/docs
- Settings: environment variables, or a .env file next to this script (copy .env.example). See PROJECT_STATUS.md.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))


def load_dotenv(path: Path) -> None:
    """Minimal .env support (KEY=value lines). Real environment variables always win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if key.strip() and value:
            os.environ.setdefault(key.strip(), value)


load_dotenv(ROOT / ".env")

try:
    import uvicorn  # noqa: F401
    import fastapi  # noqa: F401
    import sqlalchemy  # noqa: F401
    import alembic  # noqa: F401
    import argon2  # noqa: F401
    import jwt  # noqa: F401
    import multipart  # noqa: F401
except ImportError as exc:
    sys.exit(f"Missing Python package ({exc.name}). Install the backend requirements first:\n\n    pip install -r backend/requirements.txt\n")

if __name__ == "__main__":
    import uvicorn

    import manage

    if not (ROOT / "frontend" / "dist" / "index.html").is_file():
        sys.exit("frontend/dist is missing. Build it first: cd frontend && npm run build")
    manage.init_db()
    port = int(os.environ.get("PORT", "5173"))
    print(f"\n  TrustTrace running at http://localhost:{port}   (API docs: http://localhost:{port}/api/docs)\n  Press Ctrl+C to stop.\n")
    uvicorn.run("app.main:app", host="0.0.0.0", port=port, log_level="warning")
