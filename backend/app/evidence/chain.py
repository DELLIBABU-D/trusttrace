"""Tamper-evident evidence chain (one hash chain per candidate).

How it works
------------
* Every important step (registration, consent, document upload/replacement, verification result, identity check,
  application, assessment, interview identity step, recruiter review, onboarding, passport issue/revocation) appends an
  EvidenceEvent.
* ``payload_hash = SHA-256(canonical JSON of the payload)``. The payload holds ids, statuses and content hashes only:
  never document text, photos, face embeddings or contact details. Free-text notes are stored as a SHA-256 of the note
  (the note itself lives in its own append-only table).
* ``event_hash = HMAC-SHA256(server evidence key, canonical header)`` where the header contains the sequence number,
  type, actor, time, payload hash and the previous event's hash. Changing any stored field, deleting an event or
  re-ordering events breaks the chain from that point on, and ``verify()`` reports exactly where.
* SQLite triggers (migration 0005) refuse UPDATE and DELETE on ``evidence_events`` through the app's connection.

Limits (stated honestly)
------------------------
A local hash chain is tamper-*evident*, not tamper-*proof*. Someone with full control of the server (database file AND
the evidence key) can drop the triggers, rewrite events and recompute every HMAC. Issued passports pin the chain head
(sequence + hash) at issue time, so a rewrite of history before that point is detected against any passport already
handed out; publishing chain heads to an external timestamping service or write-once storage would be the next step.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import config
from ..models import EvidenceEvent, utcnow

GENESIS = "0" * 64
VERSION = 1

LABELS = {
    "candidate.registered": "Candidate registered",
    "consent.changed": "Consent changed",
    "profile.updated": "Profile updated",
    "document.uploaded": "Document uploaded",
    "document.replaced": "Document replaced",
    "document.deleted": "Document removed",
    "application.submitted": "Applied to a job",
    "verification.result": "Verification result",
    "identity.check": "Face recheck",
    "assessment.submitted": "Assessment submitted",
    "interview.identity_check": "Interview identity step",
    "recruiter.status_changed": "Application status changed",
    "recruiter.decision": "Review decision",
    "recruiter.check_review": "Check concern reviewed",
    "recruiter.alert_review": "Alert reviewed",
    "recruiter.issuer_confirmation": "Issuer confirmation recorded",
    "recruiter.reference_requested": "Reference requested",
    "reference.responded": "Reference answered",
    "recruiter.report_reviewed": "Trust report marked reviewed",
    "onboarding.started": "Onboarding started",
    "digilocker.connected": "DigiLocker connected",
    "digilocker.document_pulled": "Document pulled from DigiLocker",
    "digilocker.disconnected": "DigiLocker data removed",
    "passport.issued": "Passport issued",
    "passport.revoked": "Passport revoked",
    "passport.superseded": "Passport superseded",
}


def canonical(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


def sha256(data: bytes | str) -> str:
    return hashlib.sha256(data.encode() if isinstance(data, str) else data).hexdigest()


def note_hash(text: str) -> str:
    return sha256((text or "").strip())


def _key() -> bytes:
    return config.evidence_key()


def key_id(key: bytes | None = None) -> str:
    return sha256(b"tt-evidence-key-id:" + (key or _key()))[:12]


def _clean(v):
    if isinstance(v, dict):
        return {str(k): _clean(x) for k, x in v.items() if x is not None}
    if isinstance(v, (list, tuple)):
        return [_clean(x) for x in v]
    if isinstance(v, datetime):
        return v.isoformat(timespec="seconds") + "Z"
    if isinstance(v, float):
        return round(v, 4)
    if v is None or isinstance(v, (str, int, bool)):
        return v
    return str(v)


def _ts(at: datetime) -> str:
    return at.isoformat(timespec="microseconds")


def _header(e: EvidenceEvent) -> dict:
    return {"v": VERSION, "cand": e.candidate_id, "seq": e.seq, "type": e.event_type, "app": e.application_id or "",
            "org": e.organization_id or "", "role": e.actor_role, "actor": e.actor_ref or "", "at": _ts(e.at),
            "payload": e.payload_hash, "prev": e.prev_hash}


def _mac(key: bytes, e: EvidenceEvent) -> str:
    return hmac.new(key, canonical(_header(e)), hashlib.sha256).hexdigest()


def record(db: Session, candidate_id: str, event_type: str, *, actor_role: str, actor_ref: str | None = "",
           application_id: str | None = None, organization_id: str | None = None, **payload) -> EvidenceEvent:
    """Append one event to the candidate's chain (flushes; the caller commits with its own transaction)."""
    if event_type not in LABELS:
        raise ValueError(f"unknown evidence event type {event_type}")
    body = _clean(payload)
    key = _key()
    for _ in range(5):
        last = (db.query(EvidenceEvent).filter_by(candidate_id=candidate_id).order_by(EvidenceEvent.seq.desc()).first())
        at = utcnow()
        if last and at <= last.at:  # keep time monotonic within a chain
            at = last.at + timedelta(microseconds=1)
        e = EvidenceEvent(candidate_id=candidate_id, seq=(last.seq + 1) if last else 1, event_type=event_type,
                          application_id=application_id, organization_id=organization_id, actor_role=actor_role,
                          actor_ref=actor_ref or "", payload=body, payload_hash=sha256(canonical(body)),
                          prev_hash=last.event_hash if last else GENESIS, key_id=key_id(key), at=at)
        e.event_hash = _mac(key, e)
        sp = db.begin_nested()
        try:
            db.add(e)
            db.flush()
            sp.commit()
            return e
        except IntegrityError:  # another writer took this sequence number: read the new head and retry
            sp.rollback()
    raise RuntimeError("could not append to the evidence chain")


def head(db: Session, candidate_id: str) -> EvidenceEvent | None:
    return db.query(EvidenceEvent).filter_by(candidate_id=candidate_id).order_by(EvidenceEvent.seq.desc()).first()


def verify(db: Session, candidate_id: str, anchors: list[tuple[int, str, str]] | None = None) -> dict:
    """Recompute the whole chain. ``anchors`` = [(seq, event_hash, label)] pinned elsewhere (e.g. in issued passports).

    Returns {"intact", "events", "head", "problems": [{seq, eventId, reason, detail}], "checkedAt", "keyId"}."""
    key = _key()
    kid = key_id(key)
    events = db.query(EvidenceEvent).filter_by(candidate_id=candidate_id).order_by(EvidenceEvent.seq).all()
    problems: list[dict] = []

    def bad(e: EvidenceEvent | None, reason: str, detail: str, seq: int | None = None) -> None:
        problems.append({"seq": e.seq if e else seq, "eventId": e.id if e else None, "reason": reason, "detail": detail})

    prev_hash, expected_seq = GENESIS, 1
    for e in events:
        if e.seq != expected_seq:
            bad(e, "missing_events", f"Expected event #{expected_seq} but found #{e.seq}: events were removed.")
        if e.prev_hash != prev_hash:
            bad(e, "broken_link", "This event does not point to the event before it: the order was changed or an event was removed.")
        if sha256(canonical(e.payload)) != e.payload_hash:
            bad(e, "payload_modified", "The stored details of this event were changed after it was recorded.")
        if e.key_id != kid:
            bad(e, "unknown_key", "Recorded with a different evidence key (the server key was changed or the data was copied).")
        elif not hmac.compare_digest(_mac(key, e), e.event_hash):
            bad(e, "hash_mismatch", "The event's type, time, actor or links were changed after it was recorded.")
        prev_hash, expected_seq = e.event_hash, e.seq + 1
    by_seq = {e.seq: e for e in events}
    for seq, h, label in anchors or []:
        e = by_seq.get(seq)
        if not e or e.event_hash != h:
            bad(e, "anchor_mismatch", f"History up to event #{seq} differs from what {label} recorded when it was issued.", seq)
    last = events[-1] if events else None
    return {"intact": not problems, "events": len(events), "keyId": kid, "checkedAt": utcnow().isoformat(timespec="seconds") + "Z",
            "head": {"seq": last.seq, "hash": last.event_hash, "at": last.at.isoformat(timespec="seconds") + "Z"} if last else None,
            "problems": problems[:50]}


def describe(e: EvidenceEvent) -> str:
    p = e.payload or {}
    t = e.event_type
    if t == "candidate.registered":
        return "Account created" + (" · mobile verified by OTP" if p.get("phoneVerified") else "") + (f" · consents: {', '.join(p.get('consents') or [])}" if p.get("consents") else "")
    if t == "consent.changed":
        return f"{str(p.get('purpose', '')).replace('_', ' ')} consent {'given' if p.get('granted') else 'withdrawn'}"
    if t in ("document.uploaded", "document.replaced"):
        return f"{str(p.get('kind', '')).replace('_', ' ')} · SHA-256 {str(p.get('sha256', ''))[:12]}… · {p.get('size', 0)} bytes"
    if t == "document.deleted":
        return f"{str(p.get('kind', '')).replace('_', ' ')} removed by the candidate"
    if t == "application.submitted":
        return f"Applied: {p.get('jobTitle', '')}"
    if t == "verification.result":
        codes = p.get("findingCodes") or []
        return f"{p.get('check', '')}: {str(p.get('status', '')).replace('_', ' ')}" + (f" · findings: {', '.join(codes[:5])}" if codes else "") + \
            (f" · document SHA-256 {str(p.get('documentSha256'))[:12]}…" if p.get("documentSha256") else "")
    if t == "identity.check":
        return f"{p.get('stage', '')}: {str(p.get('decision', '')).replace('_', ' ')}" + (f" · similarity {p['similarity']}" if p.get("similarity") is not None else "")
    if t == "assessment.submitted":
        return f"{p.get('title', 'Assessment')}: {p.get('score')}/{p.get('maxScore')} · {p.get('reviewSignals', 0)} integrity review signal(s)"
    if t == "interview.identity_check":
        return f"Entry check: {str(p.get('outcome', '')).replace('_', ' ')}"
    if t == "recruiter.status_changed":
        return f"Status → {str(p.get('status', '')).replace('_', ' ')}"
    if t == "recruiter.decision":
        return f"Decision: {p.get('decision', '')} (reason recorded)"
    if t == "recruiter.check_review":
        return f"{p.get('check', '')}: {p.get('status', '')} (note recorded)"
    if t == "recruiter.alert_review":
        return f"{p.get('alertKind', '')} alert: {str(p.get('status', '')).replace('_', ' ')} (note recorded)"
    if t == "recruiter.issuer_confirmation":
        return f"Issuer said: {str(p.get('result', '')).replace('_', ' ')}"
    if t == "reference.responded":
        return ("Referee confirmed" if p.get("confirmed") else "Referee did not confirm") + (" (SIMULATED)" if p.get("simulated") else "")
    if t == "recruiter.report_reviewed":
        return f"Reviewed at score {p.get('score')} (version {str(p.get('scoreRecordId', ''))[:8]})"
    if t.startswith("passport."):
        return f"Passport {p.get('publicId', '')}" + (f" · {p.get('reason')}" if p.get("reason") else "")
    if t == "digilocker.connected":
        return f"{p.get('documents', 0)} issued document(s) listed" + (" · SIMULATED" if p.get("mode") != "live" else "")
    if t == "digilocker.document_pulled":
        return f"{p.get('doctype', '')} from {p.get('issuer', '')} · SHA-256 {str(p.get('sha256', ''))[:12]}…" + \
            (" · HMAC verified" if p.get("hmacVerified") else "") + (" · SIMULATED" if p.get("mode") != "live" else "")
    if t == "digilocker.disconnected":
        return "Token, document list and pulled copies deleted"
    if t == "onboarding.started":
        return "Candidate moved to onboarding"
    return ""


def timeline(db: Session, candidate_id: str, org_id: str | None) -> list[dict]:
    """Events for display. Organisation-specific events of OTHER organisations are listed (so the chain stays checkable)
    but their details are hidden."""
    out = []
    for e in db.query(EvidenceEvent).filter_by(candidate_id=candidate_id).order_by(EvidenceEvent.seq):
        hidden = bool(e.organization_id and org_id is not None and e.organization_id != org_id)
        out.append({"seq": e.seq, "type": "hidden" if hidden else e.event_type,
                    "label": "Activity at another organisation" if hidden else LABELS.get(e.event_type, e.event_type),
                    "detail": "Details are visible only to that organisation." if hidden else describe(e),
                    "actorRole": e.actor_role, "applicationId": None if hidden else e.application_id,
                    "at": e.at.isoformat(timespec="seconds") + "Z", "hash": e.event_hash, "prevHash": e.prev_hash, "hidden": hidden})
    return out
