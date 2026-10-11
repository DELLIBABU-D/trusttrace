"""Phase 5 endpoints: explainable trust score, suspicious-pattern alerts, relationship graph and recruiter review actions.
All are scoped to the recruiter's organisation; every action is written to the append-only audit log."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import Field

from .. import activity, serialize
from ..evidence import chain as evidence
from ..fraud import reviews as alert_reviews
from ..deps import CurrentRecruiter, Db
from ..errors import bad_request, not_found
from ..fraud import config, graph, patterns, scoring
from ..models import Application, CheckReview, PatternAlert, ReportReview, ScoreRecord, User, utcnow
from ..schemas import Camel

router = APIRouter(prefix="/recruiter", tags=["trust score & fraud intelligence"])


def _app(db, rec, app_id: str) -> Application:
    a = db.get(Application, app_id)
    if not a or a.job.organization_id != rec.organization_id:
        raise not_found("Application")
    return a


def trust_bundle(db, a: Application, rec) -> dict:
    """Score explanation + alerts + graph + reviews for the trust report (recomputes if the evidence changed)."""
    record = scoring.refresh(db, a, "report_view")
    db.commit()
    history = db.query(ScoreRecord).filter_by(application_id=a.id).order_by(ScoreRecord.computed_at.desc(), ScoreRecord.id.desc()).limit(20).all()
    reviews = db.query(ReportReview).filter_by(application_id=a.id).order_by(ReportReview.at.desc()).all()
    name = lambda uid: (db.get(User, uid).full_name if uid and db.get(User, uid) else "Unknown")  # noqa: E731
    return {
        "trust": getattr(record, "live", record.breakdown) | {"scoreRecordId": record.id, "computedAt": serialize.iso(record.computed_at), "trigger": record.trigger},
        "scoreHistory": [{"id": h.id, "score": h.score, "version": h.ruleset_version, "trigger": h.trigger, "at": serialize.iso(h.computed_at)} for h in history],
        "patternAlerts": _pattern_alerts(db, a.candidate_id, rec.organization_id),
        "graph": graph.view(db, a.candidate_id, rec.organization_id),
        "reportReviews": [{"id": r.id, "note": r.note, "reviewer": name(r.reviewer_id), "at": serialize.iso(r.at),
                           "score": db.get(ScoreRecord, r.score_record_id).score if r.score_record_id else None,
                           "current": r.score_record_id == record.id} for r in reviews],
    }


def _pattern_alerts(db, cand_id: str, org_id: str) -> list[dict]:
    pats = db.query(PatternAlert).filter_by(candidate_id=cand_id).order_by(PatternAlert.first_seen).all()
    rv = alert_reviews.latest(db, "pattern", [p.id for p in pats], org_id)
    return [patterns.alert_json(p, rv.get(p.id)) for p in pats]


class PatternReviewIn(Camel):
    status: Literal["reviewed_ok", "confirmed", "open"]
    note: str = Field(min_length=10, max_length=2000)


@router.post("/applicants/{app_id}/patterns/{alert_id}/review", summary="Review a suspicious-pattern alert (note required)")
def review_pattern(app_id: str, alert_id: str, body: PatternReviewIn, rec: CurrentRecruiter, db: Db):
    a = _app(db, rec, app_id)
    p = db.get(PatternAlert, alert_id)
    if not p or p.candidate_id != a.candidate_id:
        raise not_found("Alert")
    alert_reviews.add(db, "pattern", p.id, rec.organization_id, body.status, body.note, rec.id)  # this organisation's view only
    activity.log(db, rec.id, "pattern.reviewed", "pattern_alert", p.id, status=body.status, rule=p.rule_id)
    evidence.record(db, a.candidate_id, "recruiter.alert_review", actor_role="recruiter", actor_ref=rec.id, application_id=a.id,
                    organization_id=rec.organization_id, alertKind="pattern", alertId=p.id, rule=p.rule_id, status=body.status,
                    noteSha256=evidence.note_hash(body.note))
    scoring.refresh_candidate(db, a.candidate_id, "pattern_reviewed")
    db.commit()
    return trust_bundle(db, a, rec)


class CheckReviewIn(Camel):
    status: Literal["resolved", "upheld"]
    note: str = Field(min_length=10, max_length=2000)


@router.post("/applicants/{app_id}/checks/{check}/review", summary="Resolve (explained) or uphold a check-level concern")
def review_check(app_id: str, check: Literal["identity", "education", "employment", "resume"], body: CheckReviewIn, rec: CurrentRecruiter, db: Db):
    a = _app(db, rec, app_id)
    runs = serialize.latest_runs(db, a.candidate_id)
    if check not in runs:
        raise bad_request("This check hasn't run yet, so there is nothing to review.", "check_not_run")
    key = scoring.concern_key(check, runs[check], serialize.latest_result(db, a.candidate_id, check))
    review = CheckReview(application_id=a.id, check=check, status=body.status, note=body.note, evidence_run_id=key, reviewer_id=rec.id)
    db.add(review)
    db.flush()
    activity.log(db, rec.id, "check.reviewed", "application", a.id, check=check, status=body.status, runId=runs[check].id, reviewId=review.id)
    evidence.record(db, a.candidate_id, "recruiter.check_review", actor_role="recruiter", actor_ref=rec.id, application_id=a.id,
                    organization_id=rec.organization_id, check=check, status=body.status, concernKey=key, reviewId=review.id,
                    noteSha256=evidence.note_hash(body.note))
    scoring.refresh(db, a, "check_reviewed")
    db.commit()
    return trust_bundle(db, a, rec)


class MarkReviewedIn(Camel):
    note: str = Field(default="", max_length=2000)


@router.post("/applicants/{app_id}/mark-reviewed", summary="Record that you reviewed this report (tied to the exact score version)")
def mark_reviewed(app_id: str, body: MarkReviewedIn, rec: CurrentRecruiter, db: Db):
    a = _app(db, rec, app_id)
    record = scoring.refresh(db, a, "report_view")
    r = ReportReview(application_id=a.id, score_record_id=record.id, reviewer_id=rec.id, note=body.note.strip())
    db.add(r)
    db.flush()
    activity.log(db, rec.id, "report.reviewed", "application", a.id, scoreRecordId=record.id, score=record.score, reviewId=r.id)
    evidence.record(db, a.candidate_id, "recruiter.report_reviewed", actor_role="recruiter", actor_ref=rec.id, application_id=a.id,
                    organization_id=rec.organization_id, scoreRecordId=record.id, score=record.score, rulesetVersion=record.ruleset_version,
                    noteSha256=evidence.note_hash(r.note) if r.note else None)
    db.commit()
    return trust_bundle(db, a, rec)


@router.get("/applicants/{app_id}/score-history", summary="Every distinct score computed for this application, with explanations")
def score_history(app_id: str, rec: CurrentRecruiter, db: Db):
    a = _app(db, rec, app_id)
    rows = db.query(ScoreRecord).filter_by(application_id=a.id).order_by(ScoreRecord.computed_at, ScoreRecord.id).all()
    return [{"id": r.id, "score": r.score, "rawScore": r.raw_score, "version": r.ruleset_version, "trigger": r.trigger,
             "at": serialize.iso(r.computed_at), "breakdown": r.breakdown} for r in rows]


@router.get("/applicants/{app_id}/graph", summary="Linked candidate accounts (masked unless they applied to you)")
def relationship_graph(app_id: str, rec: CurrentRecruiter, db: Db):
    a = _app(db, rec, app_id)
    return graph.view(db, a.candidate_id, rec.organization_id)


@router.get("/scoring/rules", summary="The current scoring rules, weights and pattern thresholds")
def scoring_rules(rec: CurrentRecruiter):
    return config.current()
