"""Consistent error bodies: {"detail": "<human message>", "code": "<machine code>", "fields"?: {...}}."""
from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class ApiError(HTTPException):
    def __init__(self, status: int, code: str, detail: str, fields: dict | None = None):
        super().__init__(status_code=status, detail=detail)
        self.code = code
        self.fields = fields


def bad_request(detail: str, code: str = "invalid_request", fields: dict | None = None) -> ApiError:
    return ApiError(400, code, detail, fields)


def not_found(what: str = "Resource") -> ApiError:
    return ApiError(404, "not_found", f"{what} not found.")


def forbidden(detail: str = "You don't have access to this.") -> ApiError:
    return ApiError(403, "forbidden", detail)


def conflict(detail: str, code: str = "conflict") -> ApiError:
    return ApiError(409, code, detail)


_DEFAULT_CODES = {400: "invalid_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 405: "method_not_allowed", 409: "conflict", 413: "too_large", 429: "rate_limited"}


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError):
        body = {"detail": exc.detail, "code": exc.code}
        if exc.fields:
            body["fields"] = exc.fields
        return JSONResponse(body, status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException):
        return JSONResponse({"detail": exc.detail if isinstance(exc.detail, str) else "Request failed.", "code": _DEFAULT_CODES.get(exc.status_code, "error")},
                            status_code=exc.status_code, headers=getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        fields: dict[str, str] = {}
        for err in exc.errors():
            loc = [str(p) for p in err.get("loc", []) if p not in ("body", "query", "path")]
            msg = str(err.get("msg", "Invalid value")).removeprefix("Value error, ")
            fields.setdefault(".".join(loc) or "request", msg)
        first_key, first_msg = next(iter(fields.items()))
        detail = first_msg if first_key == "request" else f"{first_key}: {first_msg}"
        return JSONResponse({"detail": detail, "code": "validation_error", "fields": fields}, status_code=422)
