"""Phase 6 endpoints: evidence chain (recruiter audit timeline + verification) and the TrustTrace QR passport.

Public endpoints (no login): the passport verification check and the signing public key. Both are rate limited and
return only what is inside the signed passport plus its status."""
from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import Field

from .. import activity, ratelimit
from ..deps import CurrentCandidate, CurrentRecruiter, Db
from ..errors import not_found
from ..evidence import chain, passport
from ..models import Application, PassportRecord
from ..schemas import Camel

router = APIRouter(tags=["evidence chain & passport"])


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _org_app(db, rec, app_id: str) -> Application:
    a = db.get(Application, app_id)
    if not a or a.job.organization_id != rec.organization_id:
        raise not_found("Application")
    return a


def _anchors(db, cand_id: str) -> list[tuple[int, str, str]]:
    return [(p.chain_seq, p.chain_hash, f"passport {p.public_id}") for p in db.query(PassportRecord).filter_by(candidate_id=cand_id)]


# ---------------------------------------------------------------- evidence chain (recruiter)

@router.get("/recruiter/applicants/{app_id}/evidence", summary="Audit timeline (hash chain) for this candidate, with a fresh integrity check")
def evidence_timeline(app_id: str, rec: CurrentRecruiter, db: Db):
    a = _org_app(db, rec, app_id)
    return {"events": chain.timeline(db, a.candidate_id, rec.organization_id),
            "verification": chain.verify(db, a.candidate_id, anchors=_anchors(db, a.candidate_id)),
            "note": "Each event's details are hashed (SHA-256) and linked to the previous event with an HMAC. Changing, removing or "
                    "re-ordering stored events is detected. A local hash chain cannot stop someone with full control of the server "
                    "and its keys from rewriting everything; issued passports pin the chain head as an extra check."}


# ---------------------------------------------------------------- passport (recruiter)

def _recruiter_view(db, a: Application, request: Request) -> dict:
    from ..fraud import scoring
    record = scoring.refresh(db, a, "report_view")
    breakdown = getattr(record, "live", record.breakdown)
    rows = db.query(PassportRecord).filter_by(application_id=a.id).order_by(PassportRecord.issued_at.desc()).all()
    active = next((p for p in rows if p.status == "active"), None)
    db.commit()
    return {"eligibility": passport.eligibility(db, a, breakdown),
            "active": passport.passport_json(active, _base(request)) if active else None,
            "history": [{"passportId": p.public_id, "status": p.status, "reason": p.status_reason or None,
                         "issuedAt": p.issued_at.isoformat() + "Z", "expiresAt": p.expires_at.isoformat() + "Z",
                         "changedAt": p.status_changed_at.isoformat() + "Z" if p.status_changed_at else None} for p in rows]}


@router.get("/recruiter/applicants/{app_id}/passport", summary="Passport eligibility, the active passport and its history")
def recruiter_passport(app_id: str, request: Request, rec: CurrentRecruiter, db: Db):
    return _recruiter_view(db, _org_app(db, rec, app_id), request)


@router.post("/recruiter/applicants/{app_id}/passport", status_code=201,
             summary="Issue (or regenerate) a signed passport. Only when the eligibility rules are met.")
def issue_passport(app_id: str, request: Request, rec: CurrentRecruiter, db: Db):
    a = _org_app(db, rec, app_id)
    p = passport.issue(db, a, rec.id)
    activity.log(db, rec.id, "passport.issued", "application", a.id, passportId=p.public_id)
    db.commit()
    return _recruiter_view(db, a, request)


class RevokeIn(Camel):
    reason: str = Field(min_length=10, max_length=500)


@router.post("/recruiter/applicants/{app_id}/passport/revoke", summary="Revoke the active passport (reason required)")
def revoke_passport(app_id: str, body: RevokeIn, request: Request, rec: CurrentRecruiter, db: Db):
    a = _org_app(db, rec, app_id)
    p = passport.active_for(db, a.id)
    if not p:
        raise not_found("Active passport")
    passport.revoke(db, p, rec.id, body.reason.strip())
    activity.log(db, rec.id, "passport.revoked", "application", a.id, passportId=p.public_id)
    db.commit()
    return _recruiter_view(db, a, request)


# ---------------------------------------------------------------- passport (candidate)

@router.get("/candidate/passport", summary="My TrustTrace passports (one per application where a recruiter issued one)")
def my_passports(request: Request, cand: CurrentCandidate, db: Db):
    rows = db.query(PassportRecord).filter_by(candidate_id=cand.id).order_by(PassportRecord.issued_at.desc()).all()
    v = chain.verify(db, cand.id, anchors=_anchors(db, cand.id))
    return {"passports": [passport.passport_json(p, _base(request)) | {"jobTitle": p.claims.get("role"), "organisation": p.claims.get("iss")}
                          for p in rows],
            "candidateRef": passport.candidate_ref(cand.id), "candidateName": cand.user.full_name,
            "chain": {"intact": v["intact"], "events": v["events"]}}


# ---------------------------------------------------------------- public verification

@router.get("/passport/public-key", summary="Public key that verifies passport signatures (Ed25519)")
def public_key():
    return passport.public_key_info()


@router.get("/passport/verify/{ref}", summary="Public: verify a passport by its ID (TTP-…) or full signed token (TT1.…)")
def verify_passport(ref: str, request: Request, db: Db):
    ratelimit.per_ip(request, "passport-verify", 60, 60, "Too many verification requests. Try again in a minute.")
    return passport.verify_ref(db, ref)
