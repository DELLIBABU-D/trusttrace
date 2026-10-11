"""Per-organisation reviews of duplicate and pattern alerts.

Alerts are facts about candidate accounts (same verified number, very similar face, shared browser...). Whether an alert
is harmless is a judgement, and each organisation makes its own: one recruiter's "not a duplicate" never changes what
another organisation sees or scores. Reviews are append-only; the latest one per organisation counts.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from ..models import AlertReview

OPEN = "open"


def latest(db: Session, kind: str, alert_ids: list[str], org_id: str | None) -> dict[str, AlertReview]:
    if not alert_ids or not org_id:
        return {}
    out: dict[str, AlertReview] = {}
    q = (db.query(AlertReview).filter(AlertReview.alert_kind == kind, AlertReview.alert_id.in_(alert_ids), AlertReview.organization_id == org_id)
         .order_by(AlertReview.at, AlertReview.id))
    for r in q:
        out[r.alert_id] = r
    return out


def status(rv: AlertReview | None) -> str:
    return rv.status if rv else OPEN


def add(db: Session, kind: str, alert_id: str, org_id: str, new_status: str, note: str, reviewer_id: str) -> AlertReview:
    r = AlertReview(alert_kind=kind, alert_id=alert_id, organization_id=org_id, status=new_status, note=note, reviewer_id=reviewer_id)
    db.add(r)
    db.flush()
    return r
