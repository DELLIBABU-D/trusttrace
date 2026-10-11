"""Registration, login, logout, session lookup and mobile OTP."""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from .. import activity, serialize, storage
from ..evidence import chain as evidence
from ..config import AUTO_APPROVE_ORGS, OTP_MAX_ATTEMPTS, OTP_TTL_MINUTES
from ..deps import CurrentUser, Db, current_session
from ..errors import ApiError, bad_request, conflict
from ..models import (AuthSession, Candidate, ConsentRecord, Document, Education, Employment, OtpChallenge, Organization, User, utcnow)
from ..schemas import CandidateRegisterIn, LoginIn, OtpIn, RecruiterRegisterIn, TokenOut
from ..security import hash_secret, issue_access_token, needs_rehash, new_otp_code, verify_secret

router = APIRouter(tags=["auth"])
log = logging.getLogger("trusttrace")
CONSENT_POLICY_VERSION = "2026-10"

# --- rate limiting: see app/ratelimit.py ------------------------------------------------------------
from .. import ratelimit  # noqa: E402

_hits = ratelimit._hits  # kept for tests that reset limits
_rate_limit = ratelimit.limit
_client = ratelimit.client_ip


# --- OTP delivery ---------------------------------------------------------------------------------
def deliver_otp(phone: str, code: str) -> None:
    """No SMS provider is configured, so the code is printed in the server console (development delivery).
    Replace this function with an SMS gateway call for production."""
    log.info("[TrustTrace OTP] code sent to mobile ending %s (development console delivery)", phone[-2:])  # never log the code
    print(f"\n  >>> TrustTrace OTP for mobile ending {phone[-4:]}: {code}  (valid {OTP_TTL_MINUTES} minutes)\n", flush=True)


def _start_session(db, user: User, request: Request) -> str:
    session = AuthSession(user_id=user.id, expires_at=utcnow(), user_agent=request.headers.get("user-agent", "")[:300])
    db.add(session)
    db.flush()
    token, exp = issue_access_token(user.id, user.role, session.id)
    session.expires_at = exp
    user.last_login_at = utcnow()
    return token


@router.post("/auth/otp", summary="Send a one-time code to a mobile number")
def request_otp(body: OtpIn, request: Request, db: Db):
    _rate_limit(f"otp:{body.phone}", 3, 600, "Too many codes requested for this number. Try again in 10 minutes.")
    ratelimit.per_ip(request, "otp-ip", 10, 3600, "Too many codes requested. Try again later.")
    code = new_otp_code()
    db.query(OtpChallenge).filter(OtpChallenge.phone == body.phone, OtpChallenge.used_at.is_(None)).update({"used_at": utcnow()})
    db.add(OtpChallenge(phone=body.phone, code_hash=hash_secret(code), expires_at=utcnow() + timedelta(minutes=OTP_TTL_MINUTES)))
    db.commit()
    deliver_otp(body.phone, code)
    return {"sent": True, "expiresInMinutes": OTP_TTL_MINUTES}


def _consume_otp(db, phone: str, code: str) -> None:
    ch = (db.query(OtpChallenge).filter(OtpChallenge.phone == phone, OtpChallenge.used_at.is_(None))
          .order_by(OtpChallenge.created_at.desc()).first())
    if not ch or ch.expires_at < utcnow():
        raise bad_request("The OTP has expired or wasn't requested. Tap Verify OTP to get a new code.", "otp_invalid")
    if ch.attempts >= OTP_MAX_ATTEMPTS:
        raise bad_request("Too many wrong attempts. Request a new OTP.", "otp_locked")
    ch.attempts += 1
    if not verify_secret(ch.code_hash, code):
        db.commit()
        raise bad_request("The OTP is incorrect.", "otp_invalid", {"otp": "The OTP is incorrect."})
    ch.used_at = utcnow()


@router.post("/auth/login", response_model=TokenOut, summary="Sign in as a candidate or recruiter")
def login(body: LoginIn, request: Request, db: Db):
    _rate_limit(f"login:{_client(request)}:{body.email}", 10, 900, "Too many sign-in attempts. Wait 15 minutes and try again.")
    _rate_limit(f"login-account:{body.email}", 30, 900, "Too many sign-in attempts for this account. Wait 15 minutes and try again.")
    ratelimit.per_ip(request, "login-ip", 50, 900, "Too many sign-in attempts from this network. Wait 15 minutes and try again.")
    user = db.query(User).filter_by(email=body.email).one_or_none()
    if not verify_secret(user.password_hash if user else None, body.password) or not user or not user.is_active:
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")
    if user.role != body.role:
        other = "recruiter" if user.role == "recruiter" else "candidate"
        raise ApiError(401, "wrong_role", f"This is a {other} account. Choose the {other.title()} tab to sign in.")
    if needs_rehash(user.password_hash):
        user.password_hash = hash_secret(body.password)
    token = _start_session(db, user, request)
    activity.log(db, user.id, "auth.login")
    if user.role == "candidate" and user.candidate:
        from ..fraud import devices, patterns
        devices.record(db, request, user.candidate.id, "login")
        db.flush()
        patterns.scan(db, user.candidate)
    db.commit()
    return {"token": token, "user": serialize.session_user(user)}


@router.post("/auth/logout", summary="End the current session")
def logout(db: Db, session: Annotated[AuthSession, Depends(current_session)]):
    session.revoked_at = utcnow()
    activity.log(db, session.user_id, "auth.logout")
    db.commit()
    return {"ok": True}


@router.get("/auth/me", summary="The signed-in user")
def me(user: CurrentUser):
    return serialize.session_user(user)


@router.post("/auth/register/recruiter", response_model=TokenOut, status_code=201, summary="Create a recruiter account and organisation")
def register_recruiter(body: RecruiterRegisterIn, request: Request, db: Db):
    ratelimit.per_ip(request, "register", 10, 3600, "Too many registrations from this network. Try again later.")
    if db.query(User).filter_by(email=body.email).first():
        raise conflict("An account with this email already exists. Sign in instead.", "email_taken")
    org = Organization(name=body.organisation, company_size=body.company_size, status="approved" if AUTO_APPROVE_ORGS else "pending",
                       approved_at=utcnow() if AUTO_APPROVE_ORGS else None)
    db.add(org)
    db.flush()
    user = User(role="recruiter", email=body.email, password_hash=hash_secret(body.password), full_name=body.full_name,
                phone=body.phone, organization_id=org.id)
    db.add(user)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise conflict("An account with this email already exists. Sign in instead.", "email_taken") from exc
    token = _start_session(db, user, request)
    activity.log(db, user.id, "recruiter.registered", "organization", org.id, status=org.status)
    db.commit()
    db.refresh(user)
    return {"token": token, "user": serialize.session_user(user)}


@router.post("/candidates/register", response_model=TokenOut, status_code=201, summary="Register a candidate (multipart: payload JSON + idDocument file)")
async def register_candidate(request: Request, db: Db, payload: Annotated[str, Form()], idDocument: Annotated[UploadFile, File()]):  # noqa: N803
    ratelimit.per_ip(request, "register", 10, 3600, "Too many registrations from this network. Try again later.")
    try:
        body = CandidateRegisterIn.model_validate(json.loads(payload))
    except (json.JSONDecodeError, ValidationError) as exc:
        if isinstance(exc, ValidationError):
            err = exc.errors()[0]
            field = ".".join(str(p) for p in err["loc"])
            msg = str(err["msg"]).removeprefix("Value error, ")
            raise bad_request(f"{field}: {msg}" if field else msg, "validation_error", {field or "payload": msg}) from exc
        raise bad_request("Registration data could not be read.") from exc
    if db.query(User).filter_by(email=body.email).first():
        raise conflict("An account with this email already exists. Sign in instead.", "email_taken")
    # Validate both files first, so a bad file doesn't use up the OTP.
    id_file = await storage.save_upload("id_document", idDocument)
    try:
        selfie_file = storage.save_data_url("selfie", body.selfie, "enrolment-photo.jpg")
    except ApiError:
        storage.delete(id_file.storage_name)
        raise
    try:
        _consume_otp(db, body.phone, body.otp)
    except ApiError:
        storage.delete(id_file.storage_name)
        storage.delete(selfie_file.storage_name)
        raise

    user = User(role="candidate", email=body.email, password_hash=hash_secret(body.password), full_name=body.full_name, phone=body.phone)
    db.add(user)
    db.flush()
    cand = Candidate(user_id=user.id, date_of_birth=body.date_of_birth, phone_verified_at=utcnow(), skills=[])
    db.add(cand)
    db.flush()
    for i, e in enumerate(body.education):
        db.add(Education(candidate_id=cand.id, position=i, degree=e.degree, institution=e.institution, start_year=int(e.start_year), end_year=int(e.end_year), score=e.score))
    for i, e in enumerate(body.experience):
        db.add(Employment(candidate_id=cand.id, position=i, company=e.company, title=e.title, start_month=e.start, end_month=e.end, current=e.current))
    ip, ua = _client(request), request.headers.get("user-agent", "")[:300]
    for purpose in ("biometric", "document_processing"):
        db.add(ConsentRecord(candidate_id=cand.id, purpose=purpose, granted=True, policy_version=CONSENT_POLICY_VERSION, ip_address=ip, user_agent=ua))
    reg_docs = []
    for kind, f in (("id_document", id_file), ("selfie", selfie_file)):
        reg_docs.append(Document(candidate_id=cand.id, kind=kind, original_name=f.original_name, storage_name=f.storage_name, content_type=f.content_type,
                                 size_bytes=f.size, sha256=f.sha256, uploaded_by=user.id))
        db.add(reg_docs[-1])
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        storage.delete(id_file.storage_name)
        storage.delete(selfie_file.storage_name)
        raise conflict("An account with this email already exists. Sign in instead.", "email_taken") from exc
    token = _start_session(db, user, request)
    activity.log(db, user.id, "candidate.registered", "candidate", cand.id)
    evidence.record(db, cand.id, "candidate.registered", actor_role="candidate", actor_ref=user.id, phoneVerified=True,
                    consents=["biometric", "document_processing"], consentPolicy=CONSENT_POLICY_VERSION,
                    claimsSha256=evidence.sha256(evidence.canonical({"education": [e.model_dump(mode="json") for e in body.education],
                                                                    "experience": [e.model_dump(mode="json") for e in body.experience]})))
    for d in reg_docs:
        evidence.record(db, cand.id, "document.uploaded", actor_role="candidate", actor_ref=user.id, documentId=d.id, kind=d.kind,
                        sha256=d.sha256, size=d.size_bytes)
    from ..fraud import devices, patterns
    devices.record(db, request, cand.id, "register")
    db.flush()
    patterns.scan(db, cand)
    db.commit()
    from ..verification import queue as vqueue
    vqueue.enqueue(db, cand.id, user.id, "registration")
    return {"token": token, "user": serialize.session_user(user)}
