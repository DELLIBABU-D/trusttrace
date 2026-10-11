"""Convert database rows into the JSON shapes the frontend expects (frontend/src/api/types.ts)."""
from __future__ import annotations

from datetime import date, datetime

from sqlalchemy.orm import Session

from . import models as m
from .security import issue_download_token

DOC_KIND_LABEL = {
    "resume": "Resume", "marksheet": "Marksheet", "education_certificate": "Degree certificate", "id_document": "Government ID",
    "experience_letter": "Experience letter", "certificate": "Certificate", "selfie": "Enrolment photo",
}
STAGES = [("applied", "Applied"), ("verification", "Verification"), ("assessment", "Assessment"), ("interview", "Interview"), ("decision", "Decision")]
_STAGE_INDEX = {"applied": 0, "verification": 1, "resume_review": 1, "clarification": 1, "shortlisted": 2, "assessment": 2, "interview": 3, "offer": 4, "hired": 4, "rejected": 4}


def iso(v: datetime | date | None) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.replace(microsecond=0).isoformat() + "Z"
    return v.isoformat()


def session_user(user: m.User) -> dict:
    org = user.organization
    return {
        "id": user.id, "role": user.role, "fullName": user.full_name, "email": user.email,
        "organisation": org.name if org else None, "organisationStatus": org.status if org else None, "avatarUrl": None,
    }


def download_url(doc: m.Document, viewer_id: str) -> str:
    return f"/api/files/{doc.id}?token={issue_download_token(doc.id, viewer_id)}"


def current_docs(cand: m.Candidate) -> list[m.Document]:
    return [d for d in cand.documents if d.replaced_by_id is None]


def selfie_url(cand: m.Candidate, viewer_id: str) -> str | None:
    """The enrolment photo is biometric data: it is not shown to anyone while biometric consent is withdrawn."""
    consents = sorted((c for c in cand.consents if c.purpose == "biometric"), key=lambda c: c.recorded_at)
    if consents and not consents[-1].granted and viewer_id != cand.user_id:
        return None
    doc = next((d for d in current_docs(cand) if d.kind == "selfie"), None)
    return download_url(doc, viewer_id) if doc else None


def document(doc: m.Document, viewer_id: str) -> dict:
    return {
        "id": doc.id, "kind": doc.kind, "fileName": doc.original_name, "sizeBytes": doc.size_bytes, "contentType": doc.content_type,
        "sha256": doc.sha256, "uploadedAt": iso(doc.uploaded_at), "previewUrl": download_url(doc, viewer_id), "status": doc.verification_status,
    }


def job(j: m.Job, applied: bool | None = None) -> dict:
    out = {
        "id": j.id, "title": j.title, "company": j.organization.name, "department": j.department or None, "location": j.location,
        "employmentType": j.employment_type, "workMode": j.work_mode, "experienceMin": j.experience_min, "experienceMax": j.experience_max,
        "salaryMin": j.salary_min, "salaryMax": j.salary_max, "skills": list(j.skills or []), "description": j.description,
        "requirements": j.requirements, "assessments": list(j.assessments or []), "deadline": iso(j.deadline), "postedAt": iso(j.created_at),
        "status": j.status, "applicantCount": len(j.applications),
    }
    if applied is not None:
        out["applied"] = applied
    return out


def application(a: m.Application) -> dict:
    idx = _STAGE_INDEX.get(a.status, 0)
    events = {e.status: e.at for e in a.events}
    stages = []
    for i, (key, label) in enumerate(STAGES):
        if a.status == "rejected" and i == idx:
            status = "failed"
        elif i < idx or (i == idx and a.status in ("offer", "hired")):
            status = "passed"
        elif i == idx and i > 0:
            status = "pending"
        elif i == 0:
            status = "passed"
        else:
            status = "not_started"
        at = a.applied_at if key == "applied" else next((events[s] for s, n in _STAGE_INDEX.items() if n == i and s in events), None)
        stages.append({"key": key, "label": label, "status": status, "at": iso(at)})
    report = a.trust_report
    return {
        "id": a.id, "jobId": a.job_id, "jobTitle": a.job.title, "company": a.job.organization.name, "status": a.status,
        "appliedAt": iso(a.applied_at), "updatedAt": iso(a.updated_at), "trustScore": report.score if report else None, "stages": stages,
        "history": [{"status": e.status, "note": e.note, "at": iso(e.at)} for e in a.events],
    }


def profile(c: m.Candidate, viewer_id: str) -> dict:
    u = c.user
    docs = {d.kind for d in current_docs(c)}
    checks = [
        bool(u.full_name), bool(u.email), bool(u.phone), c.phone_verified_at is not None, c.date_of_birth is not None, bool(c.location),
        bool(c.headline), bool(c.skills), bool(c.education), "selfie" in docs, "id_document" in docs, "resume" in docs,
        bool(docs & {"marksheet", "education_certificate"}),
    ]
    return {
        "id": c.id, "fullName": u.full_name, "email": u.email, "phone": u.phone, "phoneVerified": c.phone_verified_at is not None,
        "dateOfBirth": iso(c.date_of_birth), "location": c.location, "headline": c.headline, "linkedinUrl": c.linkedin_url,
        "githubUrl": c.github_url, "skills": list(c.skills or []), "photoUrl": selfie_url(c, viewer_id),
        "completeness": round(100 * sum(checks) / len(checks)),
        "education": [{"id": e.id, "degree": e.degree, "institution": e.institution, "startYear": str(e.start_year), "endYear": str(e.end_year), "score": e.score} for e in c.education],
        "experience": [{"id": e.id, "company": e.company, "title": e.title, "start": e.start_month, "end": e.end_month, "current": e.current} for e in c.employment],
        "references": [{"id": r.id, "name": r.name, "relationship": r.relationship_, "company": r.company, "email": r.email, "phone": r.phone} for r in c.references],
        "consents": [{"purpose": k.purpose, "granted": k.granted, "policyVersion": k.policy_version, "recordedAt": iso(k.recorded_at)} for k in sorted(c.consents, key=lambda k: k.recorded_at)],
    }


def verification_items(db: Session, c: m.Candidate) -> list[dict]:
    """Status per check, from the latest verification run. Before any run, uploaded documents show 'pending'."""
    docs = {d.kind for d in current_docs(c)}
    runs: dict[str, m.VerificationRun] = {}
    for r in db.query(m.VerificationRun).filter_by(candidate_id=c.id).order_by(m.VerificationRun.started_at):
        runs[r.check] = r

    def status(check: str, ready: bool) -> tuple[str, str | None]:
        if check in runs:
            return runs[check].status, iso(runs[check].finished_at or runs[check].started_at)
        return ("pending" if ready else "not_started"), None

    items = [
        ("identity", "Identity", "selfie" in docs and "id_document" in docs),
        ("education", "Education", bool(docs & {"marksheet", "education_certificate"})),
        ("employment", "Employment", "experience_letter" in docs),
        ("resume", "Resume Analysis", "resume" in docs),
        ("duplicate", "Duplicate Check", False),
    ]
    out = []
    for key, label, ready in items:
        st, at = status(key, ready)
        run = runs.get(key)
        out.append({"key": key, "label": label, "status": st, "updatedAt": at, "detail": run.detail if run else None})
    return out


def interview(i: m.Interview) -> dict:
    a = i.application
    return {
        "id": i.id, "applicationId": a.id, "candidateName": a.candidate.user.full_name, "jobTitle": a.job.title, "scheduledAt": iso(i.scheduled_at),
        "durationMinutes": i.duration_minutes, "mode": i.mode, "interviewer": i.interviewer, "meetingLink": i.meeting_link or None, "status": i.status,
    }


def assessment_summary(s: m.Assessment, a: m.Application) -> dict:
    return {
        "id": s.id, "title": s.title, "skill": s.skill, "questionCount": len(s.questions or []), "durationMinutes": s.duration_minutes,
        "status": s.status, "dueAt": iso(s.due_at), "jobTitle": a.job.title,
    }


def applicant_row(a: m.Application, viewer_id: str) -> dict:
    report = a.trust_report
    return {
        "applicationId": a.id, "candidateId": a.candidate_id, "candidateName": a.candidate.user.full_name,
        "photoUrl": selfie_url(a.candidate, viewer_id), "role": a.job.title, "trustScore": report.score if report else None,
        "status": a.status, "appliedAt": iso(a.applied_at),
    }


def message(msg: m.Message) -> dict:
    return {"id": msg.id, "from": msg.sender_label, "subject": msg.subject, "body": msg.body, "at": iso(msg.at), "read": msg.read_at is not None}


# ------------------------------------------------------------------ Phase 3 helpers

CHECK_LABELS = {"identity": "Identity", "education": "Education", "employment": "Employment", "resume": "Resume Analysis", "duplicate": "Duplicate Check"}


def latest_runs(db: Session, cand_id: str) -> dict[str, m.VerificationRun]:
    out: dict[str, m.VerificationRun] = {}
    for r in db.query(m.VerificationRun).filter_by(candidate_id=cand_id).order_by(m.VerificationRun.started_at):
        out[r.check] = r
    return out


def latest_result(db: Session, cand_id: str, check: str) -> dict:
    run = latest_runs(db, cand_id).get(check)
    if not run:
        return {"status": "not_started", "summary": "Verification has not run yet.", "at": None}
    return {**(run.result or {}), "status": run.status, "at": iso(run.finished_at or run.started_at), "error": run.error or None}
