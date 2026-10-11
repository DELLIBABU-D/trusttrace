"""Potential duplicate profiles.

An alert is raised when another candidate account has
  * the same OTP-verified mobile number (after normalisation), or
  * an enrolled face whose SFace similarity is >= face.DUPLICATE (both candidates consented to biometric processing).
A matching name alone never raises an alert. Alerts are evidence for a human; nothing is blocked automatically.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from ..models import Candidate, DuplicateAlert, FaceEnrollment, User, utcnow
from . import face as facemod
from .crypto import decrypt_embedding


def normalize_phone(phone: str | None) -> str | None:
    digits = re.sub(r"\D", "", phone or "")
    if len(digits) == 12 and digits.startswith("91"):
        digits = digits[2:]
    elif len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    return digits if len(digits) == 10 else None


def has_consent(cand: Candidate, purpose: str) -> bool:
    records = sorted((c for c in cand.consents if c.purpose == purpose), key=lambda c: c.recorded_at)
    return bool(records) and records[-1].granted


def _upsert(db: Session, a: str, b: str, kind: str, similarity: float | None, evidence: dict) -> DuplicateAlert:
    lo, hi = sorted((a, b))
    alert = db.query(DuplicateAlert).filter_by(candidate_a_id=lo, candidate_b_id=hi, kind=kind).one_or_none()
    if alert is None:
        alert = DuplicateAlert(candidate_a_id=lo, candidate_b_id=hi, kind=kind)
        db.add(alert)
    alert.similarity, alert.evidence, alert.updated_at = similarity, evidence, utcnow()
    return alert


def scan(db: Session, cand: Candidate, embedding=None) -> list[DuplicateAlert]:
    found: list[DuplicateAlert] = []
    phone = normalize_phone(cand.user.phone) if cand.phone_verified_at else None
    if phone:
        others = (db.query(Candidate).join(User, Candidate.user_id == User.id)
                  .filter(Candidate.id != cand.id, Candidate.phone_verified_at.is_not(None)).all())
        for o in others:
            if normalize_phone(o.user.phone) == phone:
                found.append(_upsert(db, cand.id, o.id, "phone", None, {"reason": "Same OTP-verified mobile number", "phoneLast4": phone[-4:]}))
    if embedding is not None and has_consent(cand, "biometric"):
        rows = (db.query(FaceEnrollment).filter(FaceEnrollment.candidate_id != cand.id, FaceEnrollment.status == "active").all())
        for row in rows:
            other = db.get(Candidate, row.candidate_id)
            if not other or not has_consent(other, "biometric"):
                continue
            vec = decrypt_embedding(row.embedding_encrypted)
            if vec is None:
                continue
            sim = facemod.similarity(embedding, vec)
            if sim >= facemod.DUPLICATE:
                found.append(_upsert(db, cand.id, other.id, "face", round(sim, 3),
                                     {"reason": "Enrolled faces are very similar", "threshold": facemod.DUPLICATE, "model": facemod.MODEL_NAME}))
    return found


def alerts_for(db: Session, cand_id: str) -> list[DuplicateAlert]:
    return (db.query(DuplicateAlert).filter((DuplicateAlert.candidate_a_id == cand_id) | (DuplicateAlert.candidate_b_id == cand_id))
            .order_by(DuplicateAlert.created_at).all())


def other_label(alert: DuplicateAlert, cand_id: str) -> str:
    """Refers to the other account without exposing their name or contact details."""
    other = alert.candidate_b_id if alert.candidate_a_id == cand_id else alert.candidate_a_id
    return f"Candidate account …{other[-6:]}"
