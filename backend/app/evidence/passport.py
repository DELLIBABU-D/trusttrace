"""TrustTrace QR Passport: a signed, minimal-data verification summary for one application.

Token format:  ``TT1.<base64url(canonical JSON claims)>.<base64url(Ed25519 signature)>``

* Signed with an Ed25519 key kept on the server (data/passport_ed25519.pem or TT_PASSPORT_KEY_FILE). The public key is
  published at /api/passport/public-key, so anyone can check a token offline; the server additionally checks expiry,
  revocation and whether the evidence changed since issue.
* Claims hold a pseudonymous candidate reference, check STATUSES, a skill-assessment summary, issue/expiry time, the
  score-report version and the evidence-chain head. Never photos, documents, embeddings, phone numbers, emails, dates of
  birth or the trust score itself.
* Pending and simulated checks are listed as "pending" (and simulated ones are named in ``sim``); only checks that were
  actually confirmed are "verified". Document consistency is "consistent", never "verified".
* A passport is superseded automatically when the evidence behind it changes (new score-report version); a recruiter of
  the issuing organisation can revoke it with a reason, and regenerate it when the candidate is still eligible.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from functools import lru_cache

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from sqlalchemy.orm import Session

from .. import config
from ..models import Application, PassportRecord, ScoreRecord, utcnow
from . import chain

PREFIX = "TT1"
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"  # no 0/O/1/I/L
STATUS_TEXT = {"verified": "Verified", "consistent": "Consistent (documents agree; not independently confirmed)",
               "pending": "Pending", "not_started": "Not checked", "needs_review": "Needs review", "inconsistent": "Inconsistent"}
CHECK_TEXT = {"phone": "Mobile number (OTP)", "identity": "Identity (selfie vs ID document)", "education": "Education documents",
              "issuer": "Certificate issuer", "digilocker": "DigiLocker copy of the certificate", "employment": "Employment documents", "references": "Employment references",
              "resume": "Resume vs profile", "duplicates": "Duplicate-profile check", "patterns": "Application patterns"}


# ---------------------------------------------------------------- keys & encoding

def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


@lru_cache(maxsize=4)
def _keys(pem: bytes) -> tuple[Ed25519PrivateKey, bytes, str]:
    priv = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(priv, Ed25519PrivateKey):
        raise RuntimeError("The passport signing key must be an Ed25519 key.")
    pub = priv.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return priv, pub, hashlib.sha256(pub).hexdigest()[:12]


def keys() -> tuple[Ed25519PrivateKey, bytes, str]:
    return _keys(config.passport_signing_key_pem())


def public_key_info() -> dict:
    _, pub, kid = keys()
    return {"alg": "Ed25519", "kid": kid, "publicKey": _b64(pub), "format": f"{PREFIX}.<base64url(JSON claims)>.<base64url(signature over '{PREFIX}.' + claims part)>"}


def sign(claims: dict) -> str:
    priv, _, _ = keys()
    body = _b64(chain.canonical(claims))
    sig = priv.sign(f"{PREFIX}.{body}".encode())
    return f"{PREFIX}.{body}.{_b64(sig)}"


def decode(token: str) -> tuple[dict | None, str | None]:
    """Signature check only. Returns (claims, None) or (None, reason)."""
    parts = (token or "").strip().split(".")
    if len(parts) != 3 or parts[0] != PREFIX or len(token) > 4000:
        return None, "malformed"
    _, pub, kid = keys()
    try:
        sig = _unb64(parts[2])
        Ed25519PublicKey.from_public_bytes(pub).verify(sig, f"{PREFIX}.{parts[1]}".encode())
        claims = json.loads(_unb64(parts[1]))
    except (InvalidSignature, ValueError, json.JSONDecodeError):
        return None, "bad_signature"
    if not isinstance(claims, dict) or claims.get("kid") != kid:
        return None, "bad_signature"
    return claims, None


def _unix(naive_utc: datetime) -> int:
    return int(naive_utc.replace(tzinfo=timezone.utc).timestamp())


def _iso(ts: int | None) -> str | None:
    return datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None).isoformat() + "Z" if ts else None


def candidate_ref(candidate_id: str) -> str:
    """Stable pseudonymous reference; does not reveal the database id."""
    return "TTC-" + hashlib.sha256(f"tt-candidate-ref:{candidate_id}".encode()).hexdigest()[:10].upper()


def _public_id() -> str:
    return "TTP-" + "".join(secrets.choice(ALPHABET) for _ in range(10))


# ---------------------------------------------------------------- eligibility & claims

def _check_statuses(breakdown: dict) -> tuple[dict[str, str], list[str]]:
    rows = {c["key"]: c for c in breakdown.get("checks", [])}
    st = {}
    for key in ("phone", "identity", "education", "issuer", "digilocker", "employment", "resume", "patterns"):
        if key in rows:
            st[key] = rows[key]["bucket"]
    st["duplicates"] = rows["duplicate"]["bucket"] if "duplicate" in rows else "not_started"
    refs = [c for k, c in rows.items() if k.startswith("ref-")]
    if refs:
        st["references"] = "verified" if any(c["bucket"] == "verified" for c in refs) else \
            "inconsistent" if any(c["bucket"] == "inconsistent" for c in refs) else "pending"
    sim = sorted({("references" if c["key"].startswith("ref-") else c["key"]) for c in rows.values() if c.get("simulated")})
    return st, sim


def eligibility(db: Session, app: Application, breakdown: dict) -> dict:
    """Objective rules (documented in PROJECT_STATUS.md). Returns {eligible, reasons[]} – reasons say what is missing."""
    st, _ = _check_statuses(breakdown)
    reasons = []
    if app.status in ("rejected", "withdrawn"):
        reasons.append("The application is closed (rejected).")
    if st.get("phone") != "verified":
        reasons.append("Mobile number is not verified.")
    if st.get("identity") != "verified":
        reasons.append("Identity is not verified: the selfie has not been matched with the ID document.")
    if st.get("education", "not_started") == "not_started":
        reasons.append("Education documents have not been checked yet.")
    open_items = [c["title"] for c in breakdown.get("checks", []) if c["bucket"] in ("needs_review", "inconsistent")]
    if open_items:
        reasons.append("These still need a reviewer's decision: " + ", ".join(open_items) + ".")
    v = chain.verify(db, app.candidate_id)
    if not v["intact"]:
        reasons.append("The evidence chain failed verification.")
    return {"eligible": not reasons, "reasons": reasons, "chainIntact": v["intact"]}


def _skills(breakdown: dict) -> list[dict]:
    out = []
    for a in breakdown.get("assessment") or []:
        if a.get("status") == "submitted":
            out.append({"t": (a.get("title") or "Assessment")[:60], "s": f"{a.get('score')}/{a.get('maxScore')}",
                        "p": a.get("percent"), "rs": a.get("reviewSignals", 0)})
    return out[:5]


def build_claims(app: Application, record: ScoreRecord, breakdown: dict, public_id: str, head, now: datetime, exp: datetime) -> dict:
    st, sim = _check_statuses(breakdown)
    _, _, kid = keys()
    return {"v": 1, "typ": "TrustTrace-Passport", "pid": public_id, "kid": kid, "sub": candidate_ref(app.candidate_id),
            "iss": app.job.organization.name[:80], "role": app.job.title[:80], "c": st, "sim": sim, "sk": _skills(breakdown),
            "rv": f"{record.id[:12]}@{record.ruleset_version}", "ch": f"{head.seq}:{head.event_hash[:24]}" if head else "0:",
            "iat": _unix(now), "exp": _unix(exp)}


# ---------------------------------------------------------------- lifecycle

def active_for(db: Session, app_id: str) -> PassportRecord | None:
    return db.query(PassportRecord).filter_by(application_id=app_id, status="active").order_by(PassportRecord.issued_at.desc()).first()


def _set_status(db: Session, p: PassportRecord, status: str, reason: str, actor_id: str | None) -> None:
    p.status, p.status_reason, p.status_changed_at, p.status_changed_by = status, reason, utcnow(), actor_id
    chain.record(db, p.candidate_id, f"passport.{status}", actor_role="recruiter" if actor_id else "system", actor_ref=actor_id or "",
                 application_id=p.application_id, organization_id=p.organization_id, publicId=p.public_id, reason=reason[:200])


def issue(db: Session, app: Application, recruiter_id: str) -> PassportRecord:
    from ..fraud import scoring
    record = scoring.refresh(db, app, "passport_issue")
    breakdown = getattr(record, "live", record.breakdown)
    elig = eligibility(db, app, breakdown)
    if not elig["eligible"]:
        from ..errors import conflict
        raise conflict("Not eligible for a passport yet: " + " ".join(elig["reasons"]), "passport_not_eligible")
    old = active_for(db, app.id)
    if old:
        _set_status(db, old, "superseded", "Replaced by a newly generated passport.", recruiter_id)
    now = utcnow().replace(microsecond=0)
    exp = now + timedelta(days=config.PASSPORT_TTL_DAYS)
    public_id = _public_id()
    while db.query(PassportRecord).filter_by(public_id=public_id).first():
        public_id = _public_id()
    # the issue event is recorded first, so the pinned chain head includes it
    chain.record(db, app.candidate_id, "passport.issued", actor_role="recruiter", actor_ref=recruiter_id, application_id=app.id,
                 organization_id=app.job.organization_id, publicId=public_id, reportVersion=f"{record.id}@{record.ruleset_version}",
                 expiresAt=exp)
    head = chain.head(db, app.candidate_id)
    claims = build_claims(app, record, breakdown, public_id, head, now, exp)
    _, _, kid = keys()
    p = PassportRecord(public_id=public_id, candidate_id=app.candidate_id, application_id=app.id, organization_id=app.job.organization_id,
                       issued_by=recruiter_id, score_record_id=record.id, report_version=f"{record.id}@{record.ruleset_version}",
                       chain_seq=head.seq, chain_hash=head.event_hash, claims=claims, token=sign(claims), key_id=kid,
                       issued_at=now, expires_at=exp)
    db.add(p)
    db.flush()
    return p


def revoke(db: Session, p: PassportRecord, recruiter_id: str, reason: str) -> None:
    from ..errors import conflict
    if p.status != "active":
        raise conflict("This passport is no longer active.", "passport_inactive")
    _set_status(db, p, "revoked", reason, recruiter_id)


def on_new_score(db: Session, app: Application, record: ScoreRecord) -> None:
    """Called when a new score-report version is saved: the evidence changed, so an active passport no longer matches."""
    p = active_for(db, app.id)
    if p and p.score_record_id != record.id:
        before = db.get(ScoreRecord, p.score_record_id) if p.score_record_id else None
        same = before is not None and before.score == record.score and \
            {(c["key"], c["bucket"]) for c in (before.breakdown or {}).get("checks", [])} == \
            {(c["key"], c["bucket"]) for c in (getattr(record, "live", None) or record.breakdown or {}).get("checks", [])}
        if same:  # e.g. only the ruleset version changed: the evidence behind the passport did not
            return
        _set_status(db, p, "superseded", "The evidence changed after issue (new trust-report version). A recruiter can regenerate it.", None)


# ---------------------------------------------------------------- presentation

def verify_url(base: str, p: PassportRecord) -> str:
    """What the QR code holds: a short link to the controlled verification page (reliable to scan)."""
    return f"{(config.PUBLIC_URL or base).rstrip('/')}/verify/{p.public_id}"


def token_url(base: str, p: PassportRecord) -> str:
    """Link that carries the full signed token (verifiable offline with the public key)."""
    return f"{(config.PUBLIC_URL or base).rstrip('/')}/verify/{p.token}"


def qr_svg(text: str) -> str | None:
    """QR code as an SVG data URL (OpenCV's encoder; no extra dependency)."""
    try:
        import cv2
        params = cv2.QRCodeEncoder_Params()
        params.correction_level = cv2.QRCodeEncoder_CORRECT_LEVEL_L
        m = cv2.QRCodeEncoder_create(params).encode(text)
    except Exception:  # noqa: BLE001 - QR is a convenience; the link still works
        return None
    n = m.shape[0]
    dark = [f"M{x},{y}h1v1h-1z" for y in range(n) for x in range(n) if m[y, x] == 0]
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges">'
           f'<rect width="{n}" height="{n}" fill="#fff"/><path fill="#0b1f2e" d="{"".join(dark)}"/></svg>')
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


def describe_claims(claims: dict) -> dict:
    """Human-readable view of the claims (what the verify page and the passport screen show)."""
    sim = set(claims.get("sim") or [])
    alerts = {"duplicates": "No open duplicate-profile alerts (reviewed by the issuing recruiter)",
              "patterns": "No open suspicious-pattern alerts (reviewed by the issuing recruiter)"}
    checks = [{"key": k, "label": CHECK_TEXT.get(k, k), "status": v,
               "text": ("Pending – SIMULATED data, not an official verification" if k in sim else
                        alerts[k] if k in alerts and v == "consistent" else STATUS_TEXT.get(v, v))}
              for k, v in (claims.get("c") or {}).items()]
    order = list(CHECK_TEXT)
    checks.sort(key=lambda c: order.index(c["key"]) if c["key"] in order else 99)
    return {"passportId": claims.get("pid"), "candidateRef": claims.get("sub"), "issuer": claims.get("iss"), "role": claims.get("role"),
            "checks": checks, "skills": [{"title": s.get("t"), "score": s.get("s"), "percent": s.get("p"), "reviewSignals": s.get("rs", 0)}
                                         for s in claims.get("sk") or []],
            "reportVersion": claims.get("rv"), "chainHead": claims.get("ch"),
            "issuedAt": _iso(claims.get("iat")), "expiresAt": _iso(claims.get("exp"))}


def passport_json(p: PassportRecord, base: str, *, include_qr: bool = True) -> dict:
    url = verify_url(base, p)
    return {"id": p.id, "status": p.status, "statusReason": p.status_reason or None,
            "statusChangedAt": p.status_changed_at.isoformat() + "Z" if p.status_changed_at else None,
            "expired": p.expires_at < utcnow(), "verifyUrl": url, "tokenUrl": token_url(base, p),
            "qrDataUrl": qr_svg(url) if include_qr and p.status == "active" else None,
            "token": p.token, **describe_claims(p.claims)}


PUBLIC_ID_RE = __import__("re").compile(r"^TTP-[A-Z0-9]{10}$")


def verify_ref(db: Session, ref: str) -> dict:
    """Accepts a passport id from the QR code (looked up, then its stored signed token is checked) or a full token."""
    ref = (ref or "").strip()
    if PUBLIC_ID_RE.match(ref.upper()):
        p = db.query(PassportRecord).filter_by(public_id=ref.upper()).one_or_none()
        if not p:
            return {"result": "unknown", "message": "TrustTrace has no passport with this ID. Do not rely on it."}
        return verify_token(db, p.token)
    return verify_token(db, ref)


def verify_token(db: Session, token: str) -> dict:
    """Public verification: signature, expiry, revocation/supersession and the pinned evidence-chain head."""
    claims, err = decode(token)
    if err:
        return {"result": "invalid", "message": "This passport could not be verified: the signature is invalid or the link is damaged. "
                                                "Do not rely on it."}
    p = db.query(PassportRecord).filter_by(public_id=claims.get("pid")).one_or_none()
    out = {"passport": describe_claims(claims), "signature": "valid"}
    if not p or p.token != token.strip():
        return out | {"result": "unknown", "message": "The signature is valid, but TrustTrace has no record of this passport. Do not rely on it."}
    if p.status == "revoked":
        return out | {"result": "revoked", "message": f"Revoked by the issuing organisation on {p.status_changed_at:%d %b %Y}: {p.status_reason}"}
    if p.status == "superseded":
        return out | {"result": "superseded", "message": "Superseded: the evidence changed after this passport was issued. Ask the candidate for the current one."}
    if p.expires_at < utcnow():
        return out | {"result": "expired", "message": f"Expired on {p.expires_at:%d %b %Y}."}
    v = chain.verify(db, p.candidate_id, anchors=[(p.chain_seq, p.chain_hash, "this passport")])
    if not v["intact"]:
        return out | {"result": "invalid", "message": "The evidence history behind this passport failed its integrity check. Do not rely on it.",
                      "chain": {"intact": False}}
    from ..models import Candidate
    cand = db.get(Candidate, p.candidate_id)
    return out | {"result": "valid", "holderName": cand.user.full_name if cand else None,
                  "message": "Valid. Signed by TrustTrace, not revoked or expired, and the evidence history is intact.",
                  "chain": {"intact": True, "events": v["events"]}}
