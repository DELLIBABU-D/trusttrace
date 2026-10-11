"""Phase 3 endpoints: run verification, identity rechecks, consent withdrawal, duplicate review, issuer confirmation,
reference requests (recruiter) and the public reference-response form."""
from __future__ import annotations

import base64
import hashlib
import logging
import re
import secrets
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import Field, model_validator

from .. import activity, ratelimit, serialize
from ..evidence import chain as evidence
from ..fraud import reviews as alert_reviews
from ..deps import CurrentCandidate, CurrentRecruiter, Db
from ..errors import bad_request, conflict, not_found
from ..models import (Application, Assessment, AssessmentEvent, Candidate, ConsentRecord, DocumentExtraction, DuplicateAlert, FaceCheck, FaceEnrollment,
                      Interview, IssuerConfirmation, Reference, ReferenceRequest, VerificationJob, utcnow)
from ..schemas import Camel, MONTH_RE
from ..verification import duplicates, face as facemod, queue
from ..verification.crypto import decrypt_embedding

router = APIRouter(tags=["verification"])
log = logging.getLogger("trusttrace")
REFERENCE_TTL_DAYS = 14


def job_json(job: VerificationJob | None) -> dict | None:
    if not job:
        return None
    return {"id": job.id, "status": job.status, "reason": job.reason, "createdAt": serialize.iso(job.created_at),
            "startedAt": serialize.iso(job.started_at), "finishedAt": serialize.iso(job.finished_at), "error": job.error or None}


def latest_job(db, cand_id: str) -> VerificationJob | None:
    return db.query(VerificationJob).filter_by(candidate_id=cand_id).order_by(VerificationJob.created_at.desc()).first()


# ================================================================== candidate

@router.post("/candidate/verification/run", status_code=202, summary="Run all verification checks on my profile and documents")
def run_my_verification(cand: CurrentCandidate, db: Db):
    ratelimit.limit(f"verify:{cand.id}", 30, 3600, "Verification was started many times. Wait a little and try again.")
    job = queue.enqueue(db, cand.id, cand.user_id, "manual")
    activity.log(db, cand.user_id, "verification.requested", "candidate", cand.id)
    db.commit()
    return job_json(job)


@router.get("/candidate/verification/job", summary="Status of my latest verification job")
def my_job(cand: CurrentCandidate, db: Db):
    return job_json(latest_job(db, cand.id))


@router.get("/candidate/verification/identity")
def my_identity(cand: CurrentCandidate, db: Db):
    return serialize.latest_result(db, cand.id, "identity")


class IdentityCheckIn(Camel):
    stage: Literal["assessment", "interview", "manual"]
    reference_id: str = ""
    image: str = Field(min_length=100, max_length=4_000_000)


@router.post("/candidate/identity/check", summary="Identity recheck: compare a live camera frame with the enrolled face")
def identity_check(body: IdentityCheckIn, cand: CurrentCandidate, db: Db):
    ratelimit.limit(f"identity:{cand.id}", 30, 600, "Too many face checks in a short time. Wait a few minutes and try again.")
    if body.stage == "assessment" and body.reference_id:
        s = db.get(Assessment, body.reference_id)
        if not s or db.get(Application, s.application_id).candidate_id != cand.id:
            raise not_found("Assessment")
    if body.stage == "interview" and body.reference_id:
        i = db.get(Interview, body.reference_id)
        if not i or i.application.candidate_id != cand.id:
            raise not_found("Interview")

    def record(decision: str, message: str, similarity=None, quality=None):
        db.add(FaceCheck(candidate_id=cand.id, stage=body.stage, reference_id=body.reference_id, decision=decision,
                         similarity=similarity, threshold=facemod.SAME_PERSON if similarity is not None else None, quality=quality or {}))
        if body.stage == "assessment" and body.reference_id:
            db.add(AssessmentEvent(assessment_id=body.reference_id, candidate_id=cand.id, kind="face_check",
                                   detail={"decision": decision, "similarity": similarity}))
        activity.log(db, cand.user_id, "identity.recheck", "candidate", cand.id, stage=body.stage, decision=decision)
        evidence.record(db, cand.id, "identity.check", actor_role="candidate", actor_ref=cand.user_id, stage=body.stage,
                        referenceId=body.reference_id or None, decision=decision, similarity=similarity,
                        threshold=facemod.SAME_PERSON if similarity is not None else None, liveness="not_checked")
        db.commit()
        if decision in ("match", "no_match"):
            queue.enqueue(db, cand.id, cand.user_id, "identity_recheck")
        from ..skills.service import outcome_for
        return {"decision": decision, "outcome": outcome_for(decision, similarity), "message": message, "similarity": similarity,
                "threshold": facemod.SAME_PERSON, "quality": quality or {}, "liveness": "not_checked"}

    if not duplicates.has_consent(cand, "biometric"):
        return record("no_consent", "Biometric consent is not given, so the face check was skipped.")
    enrol = db.query(FaceEnrollment).filter_by(candidate_id=cand.id, status="active").order_by(FaceEnrollment.created_at.desc()).first()
    reference = decrypt_embedding(enrol.embedding_encrypted) if enrol else None
    if reference is None:
        return record("no_enrollment", "No enrolled face yet. Run verification after registering with a clear photo.")
    m = re.fullmatch(r"data:image/(jpeg|png);base64,([A-Za-z0-9+/=\s]+)", body.image)
    try:
        data = base64.b64decode(m.group(2)) if m else b""
    except ValueError:
        data = b""
    if not data:
        raise bad_request("The camera image could not be read.", "invalid_image")
    res = facemod.analyse(data)
    if res.status == "unreadable":
        raise bad_request("The camera image could not be read.", "invalid_image")
    if res.status == "unavailable":
        return record("error", res.message)
    if res.status != "ok":
        decision = {"no_face": "no_face", "multiple_faces": "multiple_faces", "poor_quality": "poor_quality"}.get(res.status, "error")
        return record(decision, res.message, quality=res.quality)
    sim = round(facemod.similarity(reference, res.embedding), 3)
    decision = "match" if sim >= facemod.SAME_PERSON else "no_match"
    msg = "Face matches the enrolled photo." if decision == "match" else "Face does not match the enrolled photo. A reviewer will be informed."
    return record(decision, msg, sim, res.quality)


class ConsentIn(Camel):
    purpose: Literal["biometric", "document_processing"]
    granted: bool


@router.post("/candidate/consents", summary="Give or withdraw consent. Withdrawing deletes the related derived data.")
def set_consent(body: ConsentIn, request: Request, cand: CurrentCandidate, db: Db):
    db.add(ConsentRecord(candidate_id=cand.id, purpose=body.purpose, granted=body.granted, policy_version="2026-10",
                         ip_address=request.client.host if request.client else "", user_agent=request.headers.get("user-agent", "")[:300]))
    deleted = 0
    if not body.granted and body.purpose == "biometric":
        # derived biometric data: face templates and stored similarity results. The photo itself is hidden from recruiters
        # while consent is withdrawn and removed with `manage.py erase-candidate`.
        deleted = db.query(FaceEnrollment).filter_by(candidate_id=cand.id).delete()
        deleted += db.query(FaceCheck).filter_by(candidate_id=cand.id).delete()
    if not body.granted and body.purpose == "document_processing":
        doc_ids = [d.id for d in cand.documents]
        if doc_ids:
            deleted = db.query(DocumentExtraction).filter(DocumentExtraction.document_id.in_(doc_ids)).delete(synchronize_session=False)
        from ..verification import digilocker as dlk
        deleted += dlk.disconnect(db, cand.id)  # DigiLocker copies are processed documents too
    activity.log(db, cand.user_id, "consent.changed", "candidate", cand.id, purpose=body.purpose, granted=body.granted, deleted=deleted)
    evidence.record(db, cand.id, "consent.changed", actor_role="candidate", actor_ref=cand.user_id, purpose=body.purpose, granted=body.granted,
                    derivedRecordsDeleted=deleted)
    db.commit()
    db.refresh(cand)
    queue.enqueue(db, cand.id, cand.user_id, "consent_changed")
    return serialize.profile(cand, cand.user_id)


# ================================================================== recruiter

def _org_app(db, rec, app_id: str) -> Application:
    a = db.get(Application, app_id)
    if not a or a.job.organization_id != rec.organization_id:
        raise not_found("Application")
    return a


@router.post("/recruiter/applicants/{app_id}/verification/run", status_code=202, summary="Run verification for this applicant")
def run_applicant_verification(app_id: str, rec: CurrentRecruiter, db: Db):
    ratelimit.limit(f"verify-rec:{rec.id}", 120, 3600, "Too many verification runs started. Wait a little and try again.")
    a = _org_app(db, rec, app_id)
    job = queue.enqueue(db, a.candidate_id, rec.id, "manual")
    activity.log(db, rec.id, "verification.requested", "application", a.id)
    db.commit()
    return job_json(job)


@router.get("/recruiter/applicants/{app_id}/verification/job")
def applicant_job(app_id: str, rec: CurrentRecruiter, db: Db):
    return job_json(latest_job(db, _org_app(db, rec, app_id).candidate_id))


class AlertReviewIn(Camel):
    status: Literal["not_duplicate", "confirmed_duplicate", "open"]
    note: str = Field(min_length=10, max_length=2000)


@router.post("/recruiter/applicants/{app_id}/duplicates/{alert_id}/review", summary="Record a human review of a duplicate alert")
def review_duplicate(app_id: str, alert_id: str, body: AlertReviewIn, rec: CurrentRecruiter, db: Db):
    a = _org_app(db, rec, app_id)
    alert = db.get(DuplicateAlert, alert_id)
    if not alert or a.candidate_id not in (alert.candidate_a_id, alert.candidate_b_id):
        raise not_found("Alert")
    # per-organisation review: never changes what other organisations see or score
    alert_reviews.add(db, "duplicate", alert.id, rec.organization_id, body.status, body.note, rec.id)
    activity.log(db, rec.id, "duplicate.reviewed", "duplicate_alert", alert.id, status=body.status)
    evidence.record(db, a.candidate_id, "recruiter.alert_review", actor_role="recruiter", actor_ref=rec.id, application_id=a.id,
                    organization_id=rec.organization_id, alertKind="duplicate", alertId=alert.id, status=body.status, noteSha256=evidence.note_hash(body.note))
    from ..fraud import scoring
    scoring.refresh(db, a, "duplicate_reviewed")
    db.commit()
    return {"ok": True}


class IssuerConfirmationIn(Camel):
    result: Literal["confirmed", "denied", "no_record"]
    detail: str = Field(min_length=10, max_length=2000)
    reference: str = Field(default="", max_length=200)


@router.post("/recruiter/applicants/{app_id}/issuer-confirmation", status_code=201,
             summary="Record what the university/board said when you contacted them (recruiter attestation)")
def issuer_confirmation(app_id: str, body: IssuerConfirmationIn, rec: CurrentRecruiter, db: Db):
    a = _org_app(db, rec, app_id)
    doc = next((d for d in serialize.current_docs(a.candidate) if d.kind in ("marksheet", "education_certificate")), None)
    db.add(IssuerConfirmation(candidate_id=a.candidate_id, document_id=doc.id if doc else None, method="recruiter_attestation",
                              result=body.result, detail=f"{body.detail} (recorded by a recruiter at a verified organisation)",
                              reference=body.reference, simulated=False, recorded_by=rec.id))
    activity.log(db, rec.id, "issuer.confirmation_recorded", "application", a.id, result=body.result)
    evidence.record(db, a.candidate_id, "recruiter.issuer_confirmation", actor_role="recruiter", actor_ref=rec.id, application_id=a.id,
                    organization_id=rec.organization_id, result=body.result, documentId=doc.id if doc else None,
                    documentSha256=doc.sha256 if doc else None, detailSha256=evidence.note_hash(body.detail))
    db.commit()
    queue.enqueue(db, a.candidate_id, rec.id, "issuer_confirmation")
    return {"ok": True}


class ReferenceRequestIn(Camel):
    reference_id: str | None = None
    employment_id: str | None = None
    referee_name: str | None = Field(default=None, max_length=120)
    referee_contact: str | None = Field(default=None, max_length=254)

    @model_validator(mode="after")
    def _who(self):
        if not self.reference_id and not (self.referee_name and self.referee_contact):
            raise ValueError("Choose a reference from the profile or enter the HR contact's name and email/phone")
        return self


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


@router.post("/recruiter/applicants/{app_id}/reference-requests", status_code=201,
             summary="Create a one-time link for a referee/HR to confirm employment")
def create_reference_request(app_id: str, body: ReferenceRequestIn, request: Request, rec: CurrentRecruiter, db: Db):
    a = _org_app(db, rec, app_id)
    cand = a.candidate
    ref = db.get(Reference, body.reference_id) if body.reference_id else None
    if body.reference_id and (not ref or ref.candidate_id != cand.id):
        raise not_found("Reference")
    emp = next((e for e in cand.employment if e.id == body.employment_id), None) if body.employment_id else None
    if body.employment_id and not emp:
        raise not_found("Employment entry")
    if not emp and ref:
        emp = next((e for e in cand.employment if e.company and ref.company and e.company.lower() in ref.company.lower()), None)
    token = secrets.token_urlsafe(24)
    rr = ReferenceRequest(candidate_id=cand.id, reference_id=ref.id if ref else None, employment_id=emp.id if emp else None, application_id=a.id,
                          requested_by=rec.id, referee_name=ref.name if ref else body.referee_name, referee_contact=(ref.email or ref.phone) if ref else body.referee_contact,
                          company=emp.company if emp else (ref.company if ref else ""), claimed_title=emp.title if emp else "",
                          claimed_start=emp.start_month if emp else "", claimed_end=("present" if emp and emp.current else (emp.end_month if emp else "")),
                          token_hash=_hash(token), expires_at=utcnow() + timedelta(days=REFERENCE_TTL_DAYS))
    db.add(rr)
    activity.log(db, rec.id, "reference.requested", "application", a.id)
    db.flush()
    evidence.record(db, cand.id, "recruiter.reference_requested", actor_role="recruiter", actor_ref=rec.id, application_id=a.id,
                    organization_id=rec.organization_id, referenceRequestId=rr.id)
    db.commit()
    base = str(request.base_url).rstrip("/")
    link = f"{base}/reference/{token}"
    print(f"\n  >>> TrustTrace reference link for {rr.referee_name}: {link}\n", flush=True)  # no email service: shown to the recruiter
    return {"id": rr.id, "link": link, "expiresAt": serialize.iso(rr.expires_at), "refereeName": rr.referee_name, "refereeContact": rr.referee_contact}


class SimulatedResponseIn(Camel):
    confirmed: bool
    comments: str = Field(default="", max_length=1000)


@router.post("/recruiter/applicants/{app_id}/reference-requests/{rid}/simulate",
             summary="HACKATHON ONLY: record a SIMULATED referee answer (always labelled simulated, never counts as verification)")
def simulate_reference(app_id: str, rid: str, body: SimulatedResponseIn, rec: CurrentRecruiter, db: Db):
    a = _org_app(db, rec, app_id)
    rr = db.get(ReferenceRequest, rid)
    if not rr or rr.candidate_id != a.candidate_id:
        raise not_found("Reference request")
    if rr.status != "sent":
        raise conflict("This request already has a response.")
    rr.status, rr.simulated, rr.responded_at = "responded", True, utcnow()
    rr.response = {"confirmed": body.confirmed, "title": rr.claimed_title, "start": rr.claimed_start, "end": rr.claimed_end,
                   "comments": f"SIMULATED RESPONSE for testing. {body.comments}".strip(), "responderName": "Simulated referee"}
    activity.log(db, rec.id, "reference.simulated", "reference_request", rr.id)
    evidence.record(db, a.candidate_id, "reference.responded", actor_role="recruiter", actor_ref=rec.id, application_id=a.id,
                    organization_id=rec.organization_id, referenceRequestId=rr.id, confirmed=body.confirmed, simulated=True)
    db.commit()
    queue.enqueue(db, a.candidate_id, rec.id, "reference_response")
    return {"ok": True}


# ================================================================== public referee form (no login; one-time token)

def _request_for(db, token: str) -> ReferenceRequest:
    rr = db.query(ReferenceRequest).filter_by(token_hash=_hash(token)).one_or_none() if token and len(token) < 100 else None
    if not rr:
        raise not_found("Reference request")
    if rr.status == "sent" and rr.expires_at < utcnow():
        rr.status = "expired"
        db.commit()
    return rr


@router.get("/reference/{token}", summary="Referee view of a reference request (minimal details only)")
def reference_view(token: str, request: Request, db: Db):
    ratelimit.per_ip(request, "reference", 30, 600, "Too many requests. Try again in a few minutes.")
    rr = _request_for(db, token)
    cand = db.get(Candidate, rr.candidate_id)
    return {"status": rr.status, "candidateName": cand.user.full_name, "company": rr.company, "claimedTitle": rr.claimed_title,
            "claimedStart": rr.claimed_start, "claimedEnd": rr.claimed_end, "refereeName": rr.referee_name, "expiresAt": serialize.iso(rr.expires_at)}


class ReferenceResponseIn(Camel):
    confirmed: bool
    title: str = Field(default="", max_length=120)
    start: str = ""
    end: str = ""
    comments: str = Field(default="", max_length=2000)
    responder_name: str = Field(min_length=2, max_length=120)
    responder_role: str = Field(default="", max_length=120)

    @model_validator(mode="after")
    def _dates(self):
        for v in (self.start, self.end):
            if v and v != "present" and not MONTH_RE.match(v):
                raise ValueError("Dates must be months like 2023-06")
        return self


@router.post("/reference/{token}", summary="Referee submits their answer (one time)")
def reference_respond(token: str, body: ReferenceResponseIn, request: Request, db: Db):
    ratelimit.per_ip(request, "reference", 30, 600, "Too many requests. Try again in a few minutes.")
    rr = _request_for(db, token)
    if rr.status != "sent":
        raise conflict("This reference request is closed." if rr.status != "responded" else "Thank you – an answer was already submitted.")
    rr.status, rr.responded_at, rr.simulated = "responded", utcnow(), False
    rr.response = body.model_dump()
    activity.log(db, None, "reference.responded", "reference_request", rr.id, confirmed=body.confirmed)
    org_app = db.get(Application, rr.application_id) if rr.application_id else None
    evidence.record(db, rr.candidate_id, "reference.responded", actor_role="referee", application_id=rr.application_id,
                    organization_id=org_app.job.organization_id if org_app else None, referenceRequestId=rr.id, confirmed=body.confirmed,
                    simulated=False, responseSha256=evidence.sha256(evidence.canonical(evidence._clean(body.model_dump(mode="json")))))
    db.commit()
    queue.enqueue(db, rr.candidate_id, None, "reference_response")
    return {"ok": True}

