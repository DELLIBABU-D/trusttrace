"""Recruiter endpoints. Every query is scoped to the recruiter's own organisation."""
from __future__ import annotations

from datetime import timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response
from sqlalchemy import or_

from .. import activity, serialize
from ..evidence import chain as evidence
from ..fraud import reviews as alert_reviews
from ..deps import CurrentRecruiter, Db, Paging, paginate
from ..errors import bad_request, conflict, not_found
from ..models import (Application, ApplicationEvent, Assessment, Candidate, Finding, Interview, Job, Message, Organization, ReviewDecision,
                      TrustReport, User, utcnow)
from ..schemas import DecisionIn, InterviewIn, JobIn, SettingsIn, StatusChangeIn

router = APIRouter(prefix="/recruiter", tags=["recruiter"])

STATUS_SUBJECT = {
    "shortlisted": "You've been shortlisted", "clarification": "Clarification requested", "assessment": "Next step: assessment",
    "interview": "Next step: interview", "offer": "Offer update", "hired": "Welcome aboard", "rejected": "Application update",
    "resume_review": "Your application is under review", "verification": "Re-verification requested",
}
DECISION_STATUS = {"approve": "shortlisted", "reject": "rejected", "reverify": "verification"}


def _pass_mark(db, s: Assessment) -> int:
    from ..models import AssessmentTemplate
    t = db.get(AssessmentTemplate, s.template_id) if s.template_id else None
    return t.pass_percent if t else 60


def _org_jobs(db, rec: User):
    return db.query(Job).filter(Job.organization_id == rec.organization_id)


def _org_apps(db, rec: User):
    return db.query(Application).join(Job).filter(Job.organization_id == rec.organization_id)


def _job(db, rec: User, job_id: str) -> Job:
    j = db.get(Job, job_id)
    if not j or j.organization_id != rec.organization_id:
        raise not_found("Job")
    return j


def _app(db, rec: User, app_id: str) -> Application:
    a = db.get(Application, app_id)
    if not a or a.job.organization_id != rec.organization_id:
        raise not_found("Application")
    return a


def _notify(db, rec: User, a: Application, subject: str, body: str) -> None:
    db.add(Message(recipient_id=a.candidate.user_id, sender_id=rec.id, sender_label=f"{rec.full_name}, {rec.organization.name}",
                   application_id=a.id, subject=f"{subject} – {a.job.title}", body=body))


def _set_status(db, rec: User, a: Application, status: str, note: str) -> None:
    a.status, a.updated_at = status, utcnow()
    db.add(ApplicationEvent(application_id=a.id, status=status, note=note, actor_id=rec.id))
    activity.log(db, rec.id, "application.status_changed", "application", a.id, status=status)
    evidence.record(db, a.candidate_id, "recruiter.status_changed", actor_role="recruiter", actor_ref=rec.id, application_id=a.id,
                    organization_id=rec.organization_id, status=status, noteSha256=evidence.note_hash(note) if note else None)
    if status == "hired":
        evidence.record(db, a.candidate_id, "onboarding.started", actor_role="recruiter", actor_ref=rec.id, application_id=a.id,
                        organization_id=rec.organization_id, jobId=a.job_id)


def _open_alerts(db, kind: str, ids: list[str], org_id: str) -> int:
    rv = alert_reviews.latest(db, kind, ids, org_id)
    return sum(1 for i in ids if alert_reviews.status(rv.get(i)) == "open")


# ---------------------------------------------------------------- dashboard

def _scored(db, apps: list[Application]) -> dict[str, dict]:
    """Fresh explainable score per application (recomputed only when its evidence changed)."""
    from ..fraud import scoring
    out = {a.id: scoring.refresh(db, a, "list_view").breakdown for a in apps}
    db.commit()
    return out


def _row(a: Application, rec: User, b: dict) -> dict:
    return serialize.applicant_row(a, rec.id) | {
        "trustScore": b["score"], "risk": b["risk"], "reviewCount": b["reviewCount"], "pendingCount": b["pendingCount"],
        "concerns": [c["title"] for c in b["checks"] if c["bucket"] in ("needs_review", "inconsistent")][:3]}


@router.get("/dashboard")
def dashboard(rec: CurrentRecruiter, db: Db):
    from ..models import DuplicateAlert, PatternAlert
    apps = _org_apps(db, rec)
    all_apps = apps.all()
    ids = [a.id for a in all_apps]
    scored = _scored(db, all_apps)
    recent = sorted(all_apps, key=lambda a: a.applied_at, reverse=True)[:8]
    cand_ids = list({a.candidate_id for a in all_apps})
    buckets = {k: {"verified": 0, "consistent": 0, "pending": 0, "needs_review": 0, "inconsistent": 0, "not_started": 0} for k in ("identity", "education", "employment")}
    for b in scored.values():
        for c in b["checks"]:
            if c["key"] in buckets:
                buckets[c["key"]][c["bucket"]] += 1
    attempts = db.query(Assessment).filter(Assessment.application_id.in_(ids)).all() if ids else []
    done = [x for x in attempts if x.status == "submitted" and x.percent is not None]
    attention = sorted((a for a in all_apps if scored[a.id]["reviewCount"]), key=lambda a: (scored[a.id]["score"], a.applied_at))[:6]
    return {
        "organisation": rec.organization.name, "organisationStatus": rec.organization.status,
        "totalApplicants": len(ids),
        "inAssessment": sum(1 for a in all_apps if a.status == "assessment"),
        "assessmentsSubmitted": len(done),
        "interviewsScheduled": db.query(Interview).filter(Interview.application_id.in_(ids), Interview.status == "scheduled").count() if ids else 0,
        "offersSent": sum(1 for a in all_apps if a.status in ("offer", "hired")),
        "openJobs": _org_jobs(db, rec).filter(Job.status == "open").count(),
        "recentApplications": [_row(a, rec, scored[a.id]) for a in recent],
        "needsAttention": [_row(a, rec, scored[a.id]) for a in attention],
        "reviewQueue": {
            "applicationsNeedingReview": sum(1 for b in scored.values() if b["reviewCount"]),
            "openDuplicateAlerts": _open_alerts(db, "duplicate", [d.id for d in db.query(DuplicateAlert.id).filter(
                (DuplicateAlert.candidate_a_id.in_(cand_ids)) | (DuplicateAlert.candidate_b_id.in_(cand_ids)))] if cand_ids else [], rec.organization_id),
            "openPatternAlerts": _open_alerts(db, "pattern", [p.id for p in db.query(PatternAlert.id).filter(PatternAlert.candidate_id.in_(cand_ids))]
                                              if cand_ids else [], rec.organization_id),
            "pendingChecks": sum(b["pendingCount"] for b in scored.values()),
        },
        "verificationSummary": buckets,
        "assessmentSummary": {"assigned": len(attempts), "submitted": len(done),
                              "averagePercent": round(sum(x.percent for x in done) / len(done), 1) if done else None},
    }


# ---------------------------------------------------------------- jobs

def _apply_job(j: Job, body: JobIn) -> None:
    j.title, j.department, j.location = body.title, body.department or "", body.location
    j.employment_type, j.work_mode = body.employment_type, body.work_mode
    j.experience_min, j.experience_max, j.salary_min, j.salary_max = body.experience_min, body.experience_max, body.salary_min, body.salary_max
    j.skills, j.description, j.requirements, j.assessments, j.deadline = body.skills, body.description, body.requirements, body.assessments, body.deadline
    if body.status == "closed" and j.status != "closed":
        j.closed_at = utcnow()
    j.status = body.status


@router.get("/jobs")
def jobs(rec: CurrentRecruiter, db: Db, page: Paging, response: Response):
    return [serialize.job(j) for j in paginate(_org_jobs(db, rec).order_by(Job.created_at.desc()), page, response)]


@router.post("/jobs", status_code=201)
def create_job(body: JobIn, rec: CurrentRecruiter, db: Db):
    j = Job(organization_id=rec.organization_id, created_by=rec.id)
    _apply_job(j, body)
    db.add(j)
    db.flush()
    activity.log(db, rec.id, "job.created", "job", j.id, status=j.status)
    db.commit()
    db.refresh(j)
    return serialize.job(j)


@router.get("/jobs/{job_id}")
def get_job(job_id: str, rec: CurrentRecruiter, db: Db):
    return serialize.job(_job(db, rec, job_id))


@router.put("/jobs/{job_id}")
def update_job(job_id: str, body: JobIn, rec: CurrentRecruiter, db: Db):
    j = _job(db, rec, job_id)
    _apply_job(j, body)
    activity.log(db, rec.id, "job.updated", "job", j.id, status=j.status)
    db.commit()
    return serialize.job(j)


@router.post("/jobs/{job_id}/close")
def close_job(job_id: str, rec: CurrentRecruiter, db: Db):
    j = _job(db, rec, job_id)
    if j.status != "closed":
        j.status, j.closed_at = "closed", utcnow()
        activity.log(db, rec.id, "job.closed", "job", j.id)
        db.commit()
    return serialize.job(j)


# ---------------------------------------------------------------- applicants

@router.get("/applicants", summary="Applicants with search, filters and sorting (score is decision support only)")
def applicants(rec: CurrentRecruiter, db: Db, page: Paging, response: Response,
               job_id: Annotated[str | None, Query(alias="jobId")] = None, status: str | None = None,
               search: Annotated[str | None, Query(max_length=100)] = None,
               sort: Literal["applied_desc", "applied_asc", "score_asc", "score_desc", "name"] = "applied_desc",
               attention: bool = False):
    q = _org_apps(db, rec).join(Candidate, Application.candidate_id == Candidate.id).join(User, Candidate.user_id == User.id)
    if job_id:
        q = q.filter(Application.job_id == job_id)
    if status:
        q = q.filter(Application.status == status)
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(or_(User.full_name.ilike(like), Job.title.ilike(like)))
    rows = q.all()
    scored = _scored(db, rows)
    if attention:
        rows = [a for a in rows if scored[a.id]["reviewCount"]]
    keyf = {"applied_desc": lambda a: -a.applied_at.timestamp(), "applied_asc": lambda a: a.applied_at.timestamp(),
            "score_asc": lambda a: (scored[a.id]["score"], a.applied_at), "score_desc": lambda a: (-scored[a.id]["score"], a.applied_at),
            "name": lambda a: a.candidate.user.full_name.lower()}[sort]
    rows.sort(key=keyf)
    response.headers["X-Total-Count"] = str(len(rows))
    return [_row(a, rec, scored[a.id]) for a in rows[page.offset: page.offset + page.limit]]


RUN_TO_CHECK = {"verified": "passed", "consistent": "passed", "pending": "pending", "processing": "pending", "not_started": "not_started",
                "inconsistent": "failed", "failed": "failed", "flagged": "failed", "needs_review": "review"}
SEVERITY_TO_CHECK = {"critical": "failed", "warning": "review", "info": "pending"}


def latest_findings(db, cand_id: str) -> dict[str, list[Finding]]:
    runs = serialize.latest_runs(db, cand_id)
    out: dict[str, list[Finding]] = {}
    for check, run in runs.items():
        out[check] = db.query(Finding).filter_by(run_id=run.id).order_by(Finding.created_at).all()
    return out


@router.get("/applicants/{app_id}/report", summary="Trust report for one application")
def report(app_id: str, rec: CurrentRecruiter, db: Db):
    from ..verification import duplicates as dup
    from ..verification.pipeline import alert_json
    from .verification import job_json, latest_job

    from .fraud import trust_bundle

    a = _app(db, rec, app_id)
    c = a.candidate
    bundle = trust_bundle(db, a, rec)  # recomputes the explainable score if any evidence changed
    items = serialize.verification_items(db, c)
    checks = [{"key": i["key"], "title": i["label"], "status": RUN_TO_CHECK.get(i["status"], "pending"),
               "detail": i.get("detail") or ("Documents received; run verification to check them." if i["status"] == "pending" else "Not run yet.")}
              for i in items]
    by_key = {ch["key"]: ch for ch in checks}
    fnd = latest_findings(db, c.id)

    def rows(check: str) -> list[dict]:
        return [{"key": f.id, "title": f.title, "detail": f.detail, "status": SEVERITY_TO_CHECK[f.severity], "severity": f.severity,
                 "evidence": f.evidence} for f in fnd.get(check, [])]

    verification = {k: serialize.latest_result(db, c.id, k) for k in ("identity", "education", "employment", "resume", "duplicate")}
    edu_issuer = verification["education"].get("issuer")
    issuer_row = [{"key": "issuer", "title": "Issuer authenticity", "detail": edu_issuer.get("label", ""),
                   "status": {"confirmed": "passed" if not edu_issuer.get("simulated") else "review", "denied": "failed" if not edu_issuer.get("simulated") else "review",
                              "no_record": "review"}.get(edu_issuer.get("status"), "not_started")}] if edu_issuer else []
    # References requested by another organisation: the outcome is shared evidence, the referee's comments are not.
    refs = [x if x.get("orgId") in (None, rec.organization_id) else
            {**x, "referee": "Referee", "response": None, "requestedElsewhere": True} for x in (verification["employment"].get("references") or [])]
    verification["employment"] = {**verification["employment"], "references": refs}
    ref_rows = [{"key": f"ref-{x['id']}", "title": f"Reference: {x['referee']} ({x['company'] or 'employer'})" + (" – SIMULATED" if x.get("simulated") else "")
                 + (" – requested by another organisation" if x.get("requestedElsewhere") else ""),
                 "detail": {"sent": "Waiting for the referee to answer", "expired": "Link expired", "cancelled": "Cancelled"}.get(x["status"],
                           ("Confirmed employment" if x.get("confirmed") else "Did not confirm employment") + (f" · {x['response'].get('comments')}" if x.get("response") and x["response"].get("comments") else "")),
                 "status": "pending" if x["status"] == "sent" else ("review" if x.get("simulated") else ("passed" if x.get("confirmed") else "failed"))}
                for x in refs]
    rechecks = verification["identity"].get("rechecks") or []
    recheck_rows = [{"key": f"face-{i}", "title": f"Face recheck: {x['stage']}", "detail": f"{x['decision'].replace('_', ' ')}"
                     + (f" · similarity {x['similarity']:.2f}" if x.get("similarity") is not None else ""),
                     "status": "passed" if x["decision"] == "match" else "failed" if x["decision"] == "no_match" else "review"} for i, x in enumerate(rechecks)]
    dup_alerts = dup.alerts_for(db, c.id)
    org_reviews = alert_reviews.latest(db, "duplicate", [al.id for al in dup_alerts], rec.organization_id)
    alerts = [alert_json(al, c.id, org_reviews.get(al.id)) for al in dup_alerts]
    # the duplicate row reflects the live alerts, not only the last verification run (alerts can appear later)
    open_n = sum(al["reviewStatus"] == "open" for al in alerts)
    conf_n = sum(al["reviewStatus"] == "confirmed_duplicate" for al in alerts)
    if open_n or conf_n:
        by_key["duplicate"] = {**by_key["duplicate"], "status": "failed" if conf_n else "review",
                               "detail": f"{open_n} open and {conf_n} confirmed potential duplicate alert(s). Nothing is blocked automatically."}
    alert_rows = [{"key": f"dup-{al['id']}", "title": f"Potential duplicate profile ({'mobile number' if al['kind'] == 'phone' else 'face'})",
                   "detail": f"{al['otherAccount']}: {al['evidence'].get('reason', '')}" + (f" · similarity {al['similarity']:.2f}" if al.get("similarity") else "")
                   + f" · review: {al['reviewStatus'].replace('_', ' ')}",
                   "status": "failed" if al["reviewStatus"] == "confirmed_duplicate" else "review" if al["reviewStatus"] == "open" else "passed"} for al in alerts]
    tr: TrustReport | None = a.trust_report
    assess = db.query(Assessment).filter_by(application_id=a.id).all()
    ivs = db.query(Interview).filter_by(application_id=a.id).order_by(Interview.scheduled_at).all()
    profile = serialize.profile(c, rec.id)
    return {
        "applicationId": a.id, "status": a.status, "jobTitle": a.job.title, "appliedAt": serialize.iso(a.applied_at),
        "candidate": {"id": c.id, "fullName": c.user.full_name, "headline": c.headline or "Headline not added", "location": c.location or "Location not added",
                      "photoUrl": profile["photoUrl"], "email": c.user.email, "phone": c.user.phone, "phoneVerified": profile["phoneVerified"]},
        "trustScore": bundle["trust"]["score"], "risk": bundle["trust"]["risk"],
        **bundle,
        "checks": checks,
        "sections": {
            "identity": [by_key["identity"]] + rows("identity") + recheck_rows,
            "education": [by_key["education"]] + issuer_row + rows("education"),
            "employment": [by_key["employment"]] + rows("employment") + ref_rows + [by_key["resume"]] + rows("resume"),
            "assessment": [{"key": s.id, "title": s.title,
                            "status": ("pending" if s.status != "submitted" else "passed" if (s.percent or 0) >= _pass_mark(db, s) else "review"),
                            "detail": (f"Score {s.score}/{s.max_score} ({s.percent:g}%) · {s.tab_switches} tab switch(es), {s.copy_paste} copy/paste "
                                       "(review signals only)" if s.status == "submitted" else s.status.replace("_", " ").capitalize())} for s in assess],
            "interview": [{"key": i.id, "title": f"Interview with {i.interviewer}",
                           "status": {"matched": "passed", "uncertain": "review", "needs_review": "review"}.get(i.entry_outcome, "passed" if i.status == "completed" else "pending"),
                           "detail": f"{serialize.iso(i.scheduled_at)} · {i.status}"
                                     + (f" · candidate {i.candidate_response.replace('_', ' ')}" if i.candidate_response else "")
                                     + (f" · entry identity check: {i.entry_outcome.replace('_', ' ')}" if i.entry_outcome else "")} for i in ivs],
            "risk": [by_key["duplicate"]] + alert_rows + [r for k in ("resume", "education", "employment", "identity") for r in rows(k) if r["severity"] == "critical"],
        },
        "verification": {**verification, "duplicate": {**verification["duplicate"], "alerts": alerts}},
        "duplicateAlerts": alerts,
        "job": job_json(latest_job(db, c.id)),
        "profile": {k: profile[k] for k in ("skills", "education", "experience", "references", "dateOfBirth", "linkedinUrl", "githubUrl")},
        "documents": [serialize.document(d, rec.id) for d in serialize.current_docs(c) if d.kind != "selfie"],
        "decisions": [{"id": d.id, "decision": d.decision, "reason": d.reason, "reviewer": (db.get(User, d.reviewer_id).full_name if d.reviewer_id else "Unknown"),
                       "at": serialize.iso(d.at)} for d in reversed(a.decisions)],
        "history": [{"status": e.status, "note": e.note, "at": serialize.iso(e.at)} for e in a.events],
    }


@router.post("/applicants/{app_id}/status", summary="Shortlist, request clarification or move to a next step")
def change_status(app_id: str, body: StatusChangeIn, rec: CurrentRecruiter, db: Db):
    a = _app(db, rec, app_id)
    if a.status in ("hired",) and body.status != "hired":
        raise conflict("This candidate is already hired.")
    _set_status(db, rec, a, body.status, body.note)
    default = {"shortlisted": "Good news: you have been shortlisted. We'll share the next step soon.",
               "assessment": "Please complete the assessment for this role from your Assessments page.",
               "interview": "We'd like to interview you. You'll receive the schedule shortly."}
    _notify(db, rec, a, STATUS_SUBJECT[body.status], body.note or default.get(body.status, f"Your application status is now: {body.status.replace('_', ' ')}."))
    db.commit()
    return report(app_id, rec, db)


@router.post("/applicants/{app_id}/decision", summary="Record a review decision (reason required)")
def decide(app_id: str, body: DecisionIn, rec: CurrentRecruiter, db: Db):
    a = _app(db, rec, app_id)
    db.add(ReviewDecision(application_id=a.id, decision=body.decision, reason=body.reason, reviewer_id=rec.id))
    status = DECISION_STATUS[body.decision]
    _set_status(db, rec, a, status, body.reason)
    activity.log(db, rec.id, "review.decision", "application", a.id, decision=body.decision)
    evidence.record(db, a.candidate_id, "recruiter.decision", actor_role="recruiter", actor_ref=rec.id, application_id=a.id,
                    organization_id=rec.organization_id, decision=body.decision, reasonSha256=evidence.note_hash(body.reason))
    _notify(db, rec, a, STATUS_SUBJECT[status], body.reason if body.decision != "approve" else "Good news: you have been shortlisted.")
    db.commit()
    db.refresh(a)
    return report(app_id, rec, db)


# ---------------------------------------------------------------- assessments & interviews

# GET /recruiter/assessments and /recruiter/interviews live in routers/skills.py (Phase 4).


@router.post("/interviews", status_code=201)
def schedule_interview(body: InterviewIn, rec: CurrentRecruiter, db: Db):
    a = _app(db, rec, body.application_id)
    if a.status in ("rejected", "hired"):
        raise bad_request("This application is closed.", "application_closed")
    when = body.scheduled_at.astimezone(timezone.utc).replace(tzinfo=None) if body.scheduled_at.tzinfo else body.scheduled_at
    if when < utcnow():
        raise bad_request("Pick a time in the future.", fields={"scheduledAt": "Must be in the future"})
    i = Interview(application_id=a.id, scheduled_at=when, duration_minutes=body.duration_minutes, mode=body.mode, interviewer=body.interviewer,
                  meeting_link=body.meeting_link or "", created_by=rec.id)
    db.add(i)
    db.flush()
    if a.status != "interview":
        _set_status(db, rec, a, "interview", "Interview scheduled")
    _notify(db, rec, a, "Interview scheduled",
            f"Your interview with {body.interviewer} is scheduled for {serialize.iso(when)} (UTC), {body.duration_minutes} minutes, "
            f"{'video call with identity check' if body.mode == 'video' else 'on-site'}.")
    activity.log(db, rec.id, "interview.scheduled", "interview", i.id)
    db.commit()
    db.refresh(i)
    return serialize.interview(i)


# ---------------------------------------------------------------- reports & settings

@router.get("/reports")
def reports(rec: CurrentRecruiter, db: Db):
    apps = _org_apps(db, rec).all()
    scores = [a.trust_report.score for a in apps if a.trust_report and a.trust_report.score is not None]
    bands = [("0–49", 0, 49), ("50–74", 50, 74), ("75–100", 75, 100)]
    flags: dict[str, int] = {}
    for cid in {a.candidate_id for a in apps}:  # only findings from each candidate's latest runs
        for check, items in latest_findings(db, cid).items():
            n = sum(1 for f in items if f.severity != "info")
            if n:
                label = serialize.CHECK_LABELS.get(check, check)
                flags[label] = flags.get(label, 0) + n
    return {"scoreBands": [{"band": b, "count": sum(lo <= s <= hi for s in scores)} for b, lo, hi in bands],
            "flagsByCheck": [{"check": k, "count": v} for k, v in sorted(flags.items())]}


def _settings(org: Organization, db) -> dict:
    team = db.query(User).filter_by(organization_id=org.id).order_by(User.created_at).all()
    return {"organisation": org.name, "organisationStatus": org.status, "website": org.website, "retentionDays": org.retention_days,
            "notifyOnFlag": org.notify_on_flag, "notifyDailyDigest": org.notify_daily_digest,
            "team": [{"id": u.id, "name": u.full_name, "email": u.email, "role": "Owner" if i == 0 else "Recruiter"} for i, u in enumerate(team)]}


@router.get("/settings")
def get_settings(rec: CurrentRecruiter, db: Db):
    return _settings(rec.organization, db)


@router.put("/settings")
def update_settings(body: SettingsIn, rec: CurrentRecruiter, db: Db):
    org = rec.organization
    org.name, org.website, org.retention_days = body.organisation, body.website, body.retention_days
    org.notify_on_flag, org.notify_daily_digest = body.notify_on_flag, body.notify_daily_digest
    activity.log(db, rec.id, "organization.settings_updated", "organization", org.id)
    db.commit()
    return _settings(org, db)
