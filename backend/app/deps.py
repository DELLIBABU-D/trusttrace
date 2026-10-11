"""Request dependencies: database session, current user, role guards, pagination."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query, Request, Response
from sqlalchemy.orm import Session

from .db import get_db
from .errors import ApiError, forbidden
from .models import AuthSession, Candidate, User, utcnow
from .security import decode_token

Db = Annotated[Session, Depends(get_db)]


def _bearer(request: Request) -> str | None:
    header = request.headers.get("authorization", "")
    if header.lower().startswith("bearer "):
        return header[7:].strip() or None
    return None


def _unauthorized(detail: str = "Please sign in to continue.") -> ApiError:
    err = ApiError(401, "unauthorized", detail)
    err.headers = {"WWW-Authenticate": "Bearer"}
    return err


def current_session(request: Request, db: Db) -> AuthSession:
    token = _bearer(request)
    claims = decode_token(token, "access") if token else None
    if not claims:
        raise _unauthorized()
    session = db.get(AuthSession, claims.get("jti"))
    if not session or session.revoked_at or session.expires_at < utcnow() or session.user_id != claims["sub"]:
        raise _unauthorized("Your session has ended. Please sign in again.")
    return session


def current_user(db: Db, session: Annotated[AuthSession, Depends(current_session)]) -> User:
    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(current_user)]


def require_candidate(user: CurrentUser, db: Db) -> Candidate:
    if user.role != "candidate":
        raise forbidden("This area is for candidates.")
    cand = db.query(Candidate).filter_by(user_id=user.id).one_or_none()
    if not cand:
        raise forbidden("Candidate profile missing.")
    return cand


def require_recruiter(user: CurrentUser) -> User:
    if user.role != "recruiter" or not user.organization_id:
        raise forbidden("This area is for recruiters.")
    if user.organization and user.organization.status == "suspended":
        raise forbidden("Your organisation is suspended. Contact the TrustTrace administrator.")
    return user


CurrentCandidate = Annotated[Candidate, Depends(require_candidate)]
CurrentRecruiter = Annotated[User, Depends(require_recruiter)]


@dataclass
class Page:
    limit: int
    offset: int


def pagination(limit: Annotated[int, Query(ge=1, le=100)] = 50, offset: Annotated[int, Query(ge=0)] = 0) -> Page:
    return Page(limit, offset)


Paging = Annotated[Page, Depends(pagination)]


def paginate(query, page: Page, response: Response):
    """Apply limit/offset and expose the total in X-Total-Count (lists stay plain JSON arrays)."""
    response.headers["X-Total-Count"] = str(query.order_by(None).count())
    return query.limit(page.limit).offset(page.offset).all()
