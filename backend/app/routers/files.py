"""Authorised document download. Files are never served from a public folder."""
from __future__ import annotations

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse

from .. import storage
from ..deps import Db
from ..errors import ApiError, not_found
from ..models import Application, Document, Job, User
from ..security import decode_token

router = APIRouter(tags=["files"])


def can_view(db, user: User, doc: Document) -> bool:
    if user.role == "candidate":
        return doc.candidate.user_id == user.id
    if user.role == "recruiter" and user.organization_id:
        # Only recruiters whose organisation received an application from this candidate.
        return db.query(Application).join(Job).filter(Application.candidate_id == doc.candidate_id,
                                                      Job.organization_id == user.organization_id).first() is not None
    return False


@router.get("/files/{doc_id}", summary="Download a document with a short-lived signed link")
def download(doc_id: str, token: str, request: Request, db: Db):
    claims = decode_token(token, "download")
    if not claims or claims.get("doc") != doc_id:
        raise ApiError(401, "link_expired", "This download link has expired. Reload the page to get a new one.")
    user, doc = db.get(User, claims["sub"]), db.get(Document, doc_id)
    if not user or not user.is_active or not doc or not can_view(db, user, doc):
        raise not_found("File")
    path = storage.path_for(doc.storage_name)
    if not path:
        raise not_found("File")
    disposition = "inline" if request.query_params.get("download") != "1" else "attachment"
    return FileResponse(path, media_type=doc.content_type, filename=doc.original_name, content_disposition_type=disposition,
                        headers={"Cache-Control": "private, no-store", "X-Content-Type-Options": "nosniff"})
