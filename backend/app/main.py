"""TrustTrace API (FastAPI). Also serves the built frontend so one command runs everything."""
from __future__ import annotations

from fastapi import APIRouter, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import errors
from .config import FRONTEND_DIST, MAX_REQUEST_BYTES
from contextlib import asynccontextmanager

from .routers import auth, candidate, digilocker, files, fraud, jobs, passport, recruiter, skills, verification
from .verification import queue as vqueue

@asynccontextmanager
async def lifespan(_app: FastAPI):
    if not vqueue.sync_mode():
        vqueue.start()  # background verification worker (also resumes unfinished jobs)
    yield


app = FastAPI(
    title="TrustTrace API",
    version="1.0.0",
    description="Candidate Trust & Fraud Intelligence Platform – hackathon prototype (verification engine, identity continuity, "
                "duplicate & pattern detection, explainable trust score, evidence chain, signed QR passport).",
    lifespan=lifespan,
    docs_url="/api/docs", redoc_url=None, openapi_url="/api/openapi.json",
)
errors.install(app)

api = APIRouter(prefix="/api")
for r in (auth.router, candidate.router, jobs.router, recruiter.router, files.router, verification.router, skills.router, fraud.router,
          passport.router, digilocker.router):
    api.include_router(r)


@api.get("/health", tags=["meta"])
def health():
    return {"ok": True}


@api.api_route("/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"], include_in_schema=False)
def api_not_found(path: str):
    return JSONResponse({"detail": "Endpoint not found.", "code": "not_found"}, status_code=404)


app.include_router(api)


CSP = ("default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
       "font-src 'self' data:; img-src 'self' data: blob:; media-src 'self' blob: mediastream:; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'; object-src 'none'")


@app.middleware("http")
async def security_headers(request: Request, call_next):
    # Refuse oversized bodies before they are read (uploads are 5 MB each; a request may carry a few files).
    length = request.headers.get("content-length")
    if request.method in ("POST", "PUT", "PATCH") and length and length.isdigit() and int(length) > MAX_REQUEST_BYTES:
        return JSONResponse({"detail": "The request is too large.", "code": "request_too_large"}, status_code=413)
    if request.method in ("POST", "PUT", "PATCH") and not length and "chunked" in request.headers.get("transfer-encoding", ""):
        return JSONResponse({"detail": "Uploads must declare their size.", "code": "length_required"}, status_code=411)
    response = await call_next(request)
    if not request.url.path.startswith("/api/docs"):
        response.headers.setdefault("Content-Security-Policy", CSP)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "same-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(self), display-capture=(self)")
    if request.url.path.startswith("/api/"):
        response.headers.setdefault("Cache-Control", "no-store")
    return response


# ---- frontend (built React app). Only frontend/dist is public; uploads live elsewhere.
if (FRONTEND_DIST / "assets").is_dir():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa(path: str):
    candidate = (FRONTEND_DIST / path).resolve()
    if path and candidate.is_file() and FRONTEND_DIST.resolve() in candidate.parents:
        return FileResponse(candidate)
    index = FRONTEND_DIST / "index.html"
    if index.is_file():
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
    return JSONResponse({"detail": "Frontend not built. Run: cd frontend && npm run build"}, status_code=404)
