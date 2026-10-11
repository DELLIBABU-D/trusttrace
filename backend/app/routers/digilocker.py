"""DigiLocker endpoints: consent + OAuth (live) or the labelled simulation, pulling one issued education document, and
comparing it with the uploaded certificate (the comparison itself runs inside the education verification check)."""
from __future__ import annotations

import secrets
import urllib.parse

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import Field

from .. import activity, config, ratelimit, serialize
from ..deps import CurrentCandidate, Db
from ..errors import ApiError, bad_request, not_found
from ..evidence import chain as evidence
from ..models import Candidate, DigiLockerLink, utcnow
from ..schemas import Camel
from ..verification import digilocker as dlk
from ..verification import queue as vqueue

router = APIRouter(tags=["DigiLocker"])


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _doc_json(d) -> dict | None:
    if not d:
        return None
    return {"id": d.id, "mode": d.mode, "simulated": d.mode != "live", "title": d.title, "issuer": d.issuer, "doctype": d.doctype,
            "issuedOn": d.issued_on, "mime": d.mime, "sha256": d.sha256, "hmacVerified": d.hmac_verified, "fetchedAt": serialize.iso(d.fetched_at),
            "fields": {k: (v or {}).get("value") for k, v in (d.fields or {}).items() if isinstance(v, dict)}}


@router.get("/candidate/digilocker", summary="DigiLocker status: mode, connection, issued documents, pulled copy and comparison")
def status(cand: CurrentCandidate, db: Db):
    mode = config.digilocker_mode()
    link = dlk.active_link(db, cand.id)
    expired = bool(link and (not link.token_expires_at or link.token_expires_at < utcnow()))
    edu = serialize.latest_result(db, cand.id, "education")
    return {"mode": mode, "enabled": mode != "off", "simulated": mode == "simulated",
            "connected": bool(link) and not expired, "sessionExpired": expired,
            "issued": [{**i, "likelyEducation": bool(dlk.EDU_HINTS.search(" ".join([i.get("name", ""), i.get("doctype", ""), i.get("description", "")])))}
                       for i in (link.issued if link else [])],
            "document": _doc_json(dlk.current_document(db, cand.id)),
            "comparison": edu.get("digilocker"),
            "consentText": "You will be sent to DigiLocker to choose which education document to share with TrustTrace. TrustTrace stores "
                           "only the document you pick and its fields, to compare it with the certificate you uploaded. You can remove it at any time."}


class StartIn(Camel):
    consent: bool


@router.post("/candidate/digilocker/start", summary="Start DigiLocker consent (returns the URL to open)")
def start(body: StartIn, request: Request, cand: CurrentCandidate, db: Db):
    if not body.consent:
        raise bad_request("Please agree to share the document first.", "consent_required")
    ratelimit.limit(f"digilocker:{cand.id}", 10, 3600, "Too many DigiLocker attempts. Try again later.")
    try:
        url = dlk.start(db, cand, _base(request))
    except dlk.DigiLockerError as exc:
        raise bad_request(str(exc), "digilocker_unavailable") from exc
    activity.log(db, cand.user_id, "digilocker.started", "candidate", cand.id, mode=config.digilocker_mode())
    db.commit()
    return {"authorizeUrl": url, "mode": config.digilocker_mode()}


@router.get("/digilocker/callback", include_in_schema=True, summary="OAuth redirect target registered with DigiLocker")
def callback(request: Request, db: Db, state: str = "", code: str | None = None, error: str | None = None, error_description: str | None = None):
    ratelimit.per_ip(request, "digilocker-callback", 30, 600, "Too many requests.")
    target = "/candidate/verification/education"
    try:
        link = dlk.complete(db, state, code, error, _base(request))
    except (dlk.DigiLockerError, ValueError) as exc:
        db.rollback()
        return RedirectResponse(f"{target}?digilocker=error&message={urllib.parse.quote(str(exc)[:200])}", status_code=302)
    if link.status == "connected":
        cand = db.get(Candidate, link.candidate_id)
        evidence.record(db, cand.id, "digilocker.connected", actor_role="candidate", actor_ref=cand.user_id, mode=link.mode,
                        documents=len(link.issued))
    db.commit()
    return RedirectResponse(f"{target}?digilocker={'connected' if link.status == 'connected' else 'denied'}", status_code=302)


# ---- the SIMULATED consent page (only in simulated mode) -------------------------------------------------------------

def _sim_link(db, state: str) -> DigiLockerLink:
    link = db.query(DigiLockerLink).filter_by(state=state, mode="simulated", status="pending").one_or_none()
    if config.digilocker_mode() != "simulated" or not link or link.expires_at < utcnow():
        raise not_found("Simulated DigiLocker request")
    return link


@router.get("/digilocker/simulated/{state}", summary="SIMULATED DigiLocker consent screen data (testing only)")
def sim_view(state: str, db: Db):
    link = _sim_link(db, state)
    cand = db.get(Candidate, link.candidate_id)
    docs = dlk.SimulatedProvider(db, cand).issued("")
    return {"simulated": True, "documents": [{"name": d["name"], "issuer": d["issuer"], "doctype": d["doctype"]} for d in docs]}


class SimDecisionIn(Camel):
    allow: bool


@router.post("/digilocker/simulated/{state}", summary="SIMULATED DigiLocker allow/deny (testing only)")
def sim_decide(state: str, body: SimDecisionIn, db: Db):
    _sim_link(db, state)
    q = {"state": state, **({"code": "SIM-" + secrets.token_urlsafe(12)} if body.allow else {"error": "access_denied"})}
    return {"redirect": f"/api/digilocker/callback?{urllib.parse.urlencode(q)}"}


# ---- pull / remove ---------------------------------------------------------------------------------------------------

class FetchIn(Camel):
    uri: str = Field(min_length=1, max_length=300)


@router.post("/candidate/digilocker/fetch", summary="Pull one issued document from DigiLocker and re-run the education check")
def fetch(body: FetchIn, cand: CurrentCandidate, db: Db):
    ratelimit.limit(f"digilocker-fetch:{cand.id}", 20, 3600, "Too many DigiLocker downloads. Try again later.")
    try:
        doc = dlk.fetch_document(db, cand, body.uri)
    except dlk.DigiLockerError as exc:
        raise ApiError(409, "digilocker_error", str(exc)) from exc
    evidence.record(db, cand.id, "digilocker.document_pulled", actor_role="candidate", actor_ref=cand.user_id, mode=doc.mode,
                    doctype=doc.doctype, issuer=doc.issuer, uriSha256=evidence.sha256(doc.uri), sha256=doc.sha256, hmacVerified=doc.hmac_verified)
    activity.log(db, cand.user_id, "digilocker.document_pulled", "candidate", cand.id, mode=doc.mode)
    db.commit()
    job = vqueue.enqueue(db, cand.id, cand.user_id, "digilocker_document")
    return {"document": _doc_json(doc), "job": {"id": job.id, "status": job.status} if job else None}


@router.delete("/candidate/digilocker", summary="Disconnect DigiLocker and delete the token, list and pulled copies")
def remove(cand: CurrentCandidate, db: Db):
    n = dlk.disconnect(db, cand.id)
    evidence.record(db, cand.id, "digilocker.disconnected", actor_role="candidate", actor_ref=cand.user_id, removed=n)
    db.commit()
    vqueue.enqueue(db, cand.id, cand.user_id, "digilocker_removed")
    return {"ok": True, "removed": n}
