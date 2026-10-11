"""Candidate-only endpoints. Every query is scoped to the signed-in candidate."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, File, Request, Response, UploadFile
from sqlalchemy.orm import selectinload

from .. import activity, ratelimit, serialize, storage
from ..evidence import chain as evidence
from ..deps import CurrentCandidate, Db, Paging, paginate
from ..errors import ApiError, bad_request, conflict, not_found
from ..models import (Application, Assessment, Document, Education, Employment, Interview, Message, Reference, User, VerificationRun, utcnow)
from ..schemas import AssessmentSubmitIn, ProfileUpdateIn
from ..verification import queue as vqueue

router = APIRouter(prefix="/candidate", tags=["candidate"])


def _my_application(db, cand, app_id: str) -> Application:
    a = db.get(Application, app_id)
    if not a or a.candidate_id != cand.id:  # same response for "missing" and "not yours"
        raise not_found("Application")
    return a


@router.get("/dashboard")
def dashboard(cand: CurrentCandidate, db: Db):
    from .jobs import visible_jobs  # local import avoids a cycle

    apps = db.query(Application).filter_by(candidate_id=cand.id).all()
    app_ids = [a.id for a in apps]
    applied_job_ids = {a.job_id for a in apps}
    pending = db.query(Assessment).filter(Assessment.application_id.in_(app_ids), Assessment.status != "submitted").count() if app_ids else 0
    interviews = db.query(Interview).filter(Interview.application_id.in_(app_ids), Interview.status == "scheduled").count() if app_ids else 0
    scores = [a.trust_report.score for a in apps if a.trust_report and a.trust_report.score is not None]
    skills = {s.lower() for s in cand.skills or []}
    jobs = [j for j in visible_jobs(db).limit(50).all() if j.id not in applied_job_ids]
    jobs.sort(key=lambda j: -len(skills & {s.lower() for s in j.skills or []}))
    return {
        "appliedJobs": len(apps), "assessmentsPending": pending, "interviewsScheduled": interviews,
        "trustScore": scores[-1] if scores else None, "verification": serialize.verification_items(db, cand),
        "recommendedJobs": [serialize.job(j, applied=False) for j in jobs[:4]],
    }


@router.get("/profile")
def get_profile(cand: CurrentCandidate):
    return serialize.profile(cand, cand.user_id)


@router.put("/profile")
def update_profile(body: ProfileUpdateIn, cand: CurrentCandidate, db: Db):
    user = cand.user
    if body.email != user.email and db.query(User).filter(User.email == body.email, User.id != user.id).first():
        raise conflict("Another account already uses this email.", "email_taken")
    if body.phone != user.phone:
        cand.phone_verified_at = None  # a new number has not been verified by OTP
    user.full_name, user.email, user.phone = body.full_name, body.email, body.phone
    cand.location, cand.headline = body.location, body.headline
    cand.linkedin_url, cand.github_url, cand.skills = body.linkedin_url, body.github_url, body.skills
    if body.education is not None:
        if not body.education:
            raise bad_request("Keep at least one education entry.", fields={"education": "Required"})
        cand.education = [Education(position=i, degree=e.degree, institution=e.institution, start_year=int(e.start_year), end_year=int(e.end_year), score=e.score)
                          for i, e in enumerate(body.education)]
    if body.experience is not None:
        cand.employment = [Employment(position=i, company=e.company, title=e.title, start_month=e.start, end_month=e.end, current=e.current)
                           for i, e in enumerate(body.experience)]
    if body.references is not None:
        cand.references = [Reference(position=i, name=r.name, relationship_=r.relationship, company=r.company, email=r.email, phone=r.phone)
                           for i, r in enumerate(body.references)]
    cand.updated_at = utcnow()
    activity.log(db, user.id, "candidate.profile_updated", "candidate", cand.id)
    db.flush()
    from ..verification.pipeline import profile_dict
    evidence.record(db, cand.id, "profile.updated", actor_role="candidate", actor_ref=user.id,
                    claimsSha256=evidence.sha256(evidence.canonical(evidence._clean(profile_dict(cand)))))
    db.commit()
    vqueue.enqueue(db, cand.id, user.id, "profile_changed")
    db.refresh(cand)
    return serialize.profile(cand, cand.user_id)


# ---------------------------------------------------------------- applications

@router.get("/applications")
def applications(cand: CurrentCandidate, db: Db, page: Paging, response: Response):
    q = (db.query(Application).filter_by(candidate_id=cand.id).options(selectinload(Application.events))
         .order_by(Application.applied_at.desc()))
    return [serialize.application(a) for a in paginate(q, page, response)]


@router.get("/applications/{app_id}")
def application(app_id: str, cand: CurrentCandidate, db: Db):
    return serialize.application(_my_application(db, cand, app_id))


# ---------------------------------------------------------------- documents

@router.get("/documents")
def documents(cand: CurrentCandidate):
    return [serialize.document(d, cand.user_id) for d in serialize.current_docs(cand) if d.kind != "selfie"]


def _store(db, cand, kind: str, f: storage.StoredFile, replaces: Document | None = None) -> Document:
    """Save a new document; single-copy kinds replace the previous one (kept for audit, file deleted)."""
    doc = Document(candidate_id=cand.id, kind=kind, original_name=f.original_name, storage_name=f.storage_name, content_type=f.content_type,
                   size_bytes=f.size, sha256=f.sha256, uploaded_by=cand.user_id)
    db.add(doc)
    db.flush()
    replaced = [replaces] if replaces else []
    if kind in storage.SINGLE_KINDS:
        for old in serialize.current_docs(cand):
            if old.kind == kind and old.id != doc.id:
                old.replaced_by_id, old.replaced_at = doc.id, utcnow()
                storage.delete(old.storage_name)
                replaced.append(old)
    activity.log(db, cand.user_id, "document.uploaded", "document", doc.id, kind=kind, sha256=f.sha256)
    evidence.record(db, cand.id, "document.replaced" if replaced else "document.uploaded", actor_role="candidate", actor_ref=cand.user_id,
                    documentId=doc.id, kind=kind, sha256=f.sha256, size=f.size,
                    replaces=[{"documentId": o.id, "sha256": o.sha256} for o in replaced] or None)
    return doc


@router.post("/documents", status_code=201, summary="Upload documents (multipart; field name = document kind)")
async def upload_documents(request: Request, cand: CurrentCandidate, db: Db):
    ratelimit.limit(f"upload:{cand.id}", 40, 3600, "Too many uploads in the last hour. Try again later.")
    form = await request.form(max_files=10, max_fields=20)
    items = [(k, v) for k, v in form.multi_items() if hasattr(v, "read")]
    if not items:
        raise bad_request("Choose at least one file to upload.", "no_files")
    if len(items) > 10:
        raise bad_request("Upload at most 10 files at a time.")
    unknown = [k for k, _ in items if k not in storage.DOCUMENT_KINDS]
    if unknown:
        raise bad_request(f"Unknown document type '{unknown[0]}'.", "invalid_document_kind")
    saved: list[tuple[str, storage.StoredFile]] = []
    try:
        for kind, upload in items:
            saved.append((kind, await storage.save_upload(kind, upload)))
    except ApiError:
        for _, f in saved:  # all-or-nothing
            storage.delete(f.storage_name)
        raise
    docs = [_store(db, cand, kind, f) for kind, f in saved]
    db.commit()
    vqueue.enqueue(db, cand.id, cand.user_id, "document_changed")
    db.refresh(cand)
    return [serialize.document(d, cand.user_id) for d in docs]


@router.put("/documents/{doc_id}", summary="Replace one document with a new file")
async def replace_document(doc_id: str, cand: CurrentCandidate, db: Db, file: Annotated[UploadFile, File()]):
    ratelimit.limit(f"upload:{cand.id}", 40, 3600, "Too many uploads in the last hour. Try again later.")
    old = db.get(Document, doc_id)
    if not old or old.candidate_id != cand.id or old.replaced_by_id:
        raise not_found("Document")
    f = await storage.save_upload(old.kind, file)
    doc = _store(db, cand, old.kind, f, replaces=old if old.kind not in storage.SINGLE_KINDS else None)
    if old.kind not in storage.SINGLE_KINDS:
        old.replaced_by_id, old.replaced_at = doc.id, utcnow()
        storage.delete(old.storage_name)
    db.commit()
    vqueue.enqueue(db, cand.id, cand.user_id, "document_changed")
    return serialize.document(doc, cand.user_id)


@router.delete("/documents/{doc_id}", summary="Remove an optional certificate")
def delete_document(doc_id: str, cand: CurrentCandidate, db: Db):
    doc = db.get(Document, doc_id)
    if not doc or doc.candidate_id != cand.id or doc.replaced_by_id:
        raise not_found("Document")
    if doc.kind != "certificate":
        raise bad_request("Required documents can be replaced but not removed.", "document_required")
    storage.delete(doc.storage_name)
    db.delete(doc)
    activity.log(db, cand.user_id, "document.deleted", "document", doc_id)
    evidence.record(db, cand.id, "document.deleted", actor_role="candidate", actor_ref=cand.user_id, documentId=doc_id, kind=doc.kind, sha256=doc.sha256)
    db.commit()
    vqueue.enqueue(db, cand.id, cand.user_id, "document_changed")
    return {"ok": True}


# ---------------------------------------------------------------- verification (results arrive in Phase 3/4)

@router.get("/verification")
def verification(cand: CurrentCandidate, db: Db):
    return serialize.verification_items(db, cand)


@router.get("/verification/history")
def verification_history(cand: CurrentCandidate, db: Db, page: Paging, response: Response):
    q = db.query(VerificationRun).filter_by(candidate_id=cand.id).order_by(VerificationRun.started_at.desc())
    return [{"id": r.id, "at": serialize.iso(r.finished_at or r.started_at), "check": serialize.CHECK_LABELS.get(r.check, r.check.title()),
             "result": r.status, "detail": r.error or r.detail}
            for r in paginate(q, page, response)]


def _doc_verification(db, cand, kinds: tuple[str, ...], check: str) -> dict:
    doc = next((d for d in serialize.current_docs(cand) if d.kind in kinds), None)
    res = serialize.latest_result(db, cand.id, check)
    run_doc_matches = doc is not None and res.get("documentId") == doc.id
    previewable = doc is not None and doc.content_type.startswith("image/")
    out = {
        "documentId": doc.id if doc else None,
        "previewUrl": serialize.download_url(doc, cand.user_id) if previewable else None,
        "downloadUrl": serialize.download_url(doc, cand.user_id) if doc else None,
        "fileName": doc.original_name if doc else None,
        "extracted": [], "confidence": None, "comparison": [], "matchScore": None, "summary": None,
        "status": "pending" if doc else "not_started",
    }
    if run_doc_matches or (doc is None and res.get("at")):
        out.update({k: res.get(k) for k in ("extracted", "confidence", "comparison", "matchScore", "summary", "findings", "issuer", "digilocker",
                                             "references", "extraction", "consistency", "at", "error") if k in res})
        out["status"] = res["status"]
        out["extracted"] = out.get("extracted") or []
        out["comparison"] = out.get("comparison") or []
    elif doc:
        out["summary"] = "Document received. Run verification to read and compare it."
        out["references"] = res.get("references")
    return out


@router.get("/verification/education")
def education_verification(cand: CurrentCandidate, db: Db):
    return _doc_verification(db, cand, ("marksheet", "education_certificate"), "education")


@router.get("/verification/employment")
def employment_verification(cand: CurrentCandidate, db: Db):
    return _doc_verification(db, cand, ("experience_letter",), "employment")


# ---------------------------------------------------------------- assessments / interviews / messages / passport

def _my_app_ids(db, cand) -> list[str]:
    return [a.id for a in db.query(Application.id).filter_by(candidate_id=cand.id)]


# Assessments and interviews moved to routers/skills.py (Phase 4).


@router.get("/messages")
def messages(cand: CurrentCandidate, db: Db, page: Paging, response: Response):
    q = db.query(Message).filter_by(recipient_id=cand.user_id).order_by(Message.at.desc())
    return [serialize.message(msg) for msg in paginate(q, page, response)]


@router.post("/messages/{mid}/read")
def mark_read(mid: str, cand: CurrentCandidate, db: Db):
    msg = db.get(Message, mid)
    if not msg or msg.recipient_id != cand.user_id:
        raise not_found("Message")
    msg.read_at = msg.read_at or utcnow()
    db.commit()
    return serialize.message(msg)


# GET /candidate/passport lives in routers/passport.py (Phase 6).
