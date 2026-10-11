"""Assessment assignment, scoring, integrity timeline and Proof of Skill.

Scores measure one test only. A low score is never treated as dishonesty, and integrity events (tab switches,
copy/paste, focus changes) are review signals for a person, never proof of cheating.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from .. import serialize
from ..models import (Application, ApplicationEvent, Assessment, AssessmentEvent, AssessmentTemplate, Candidate, DocumentExtraction, FaceCheck,
                      Job, Message, utcnow)
from . import bank

GRACE_SECONDS = 30  # network delay allowance after the timer ends
CLIENT_EVENT_KINDS = {"camera_granted", "camera_denied", "camera_declined", "visibility_hidden", "visibility_visible", "window_blur",
                      "window_focus", "copy", "paste", "cut", "fullscreen_exit"}
MAX_CLIENT_EVENTS = 400
REVIEW_SIGNALS = {"visibility_hidden": "Left the test tab", "window_blur": "Test window lost focus", "copy": "Copied text", "paste": "Pasted text",
                  "cut": "Cut text", "fullscreen_exit": "Left full screen"}
UNCERTAIN_FLOOR = 0.25  # face similarity between this and facemod.SAME_PERSON is "uncertain" rather than "needs review"

ASSIGNABLE_STATUSES = ("applied", "shortlisted", "verification", "resume_review", "clarification", "assessment")


# ------------------------------------------------------------------------------------------- templates

def question_json(q, include_answer: bool) -> dict:
    out = {"id": q.id, "position": q.position, "skill": q.skill, "difficulty": q.difficulty, "prompt": q.prompt, "code": q.code or None,
           "options": q.options, "source": q.source, "edited": q.edited, "approved": q.approved, "approvedAt": serialize.iso(q.approved_at)}
    if include_answer:
        out["correctOptionId"] = q.correct_option_id
        out["explanation"] = q.explanation
    return out


def template_json(t: AssessmentTemplate, db: Session) -> dict:
    attempts = db.query(Assessment).filter_by(template_id=t.id).all()
    return {
        "id": t.id, "jobId": t.job_id, "title": t.title, "durationMinutes": t.duration_minutes, "passPercent": t.pass_percent, "status": t.status,
        "generationNote": t.generation_note, "publishedAt": serialize.iso(t.published_at),
        "questions": [question_json(q, True) for q in t.questions],
        "approvedCount": sum(q.approved for q in t.questions), "questionCount": len(t.questions),
        "assignedCount": len(attempts), "submittedCount": sum(a.status == "submitted" for a in attempts),
    }


def snapshot(t: AssessmentTemplate) -> list[dict]:
    return [{"id": q.id, "skill": q.skill, "difficulty": q.difficulty, "prompt": q.prompt, "code": q.code or None, "options": q.options,
             "answer": q.correct_option_id, "source": q.source} for q in t.questions]


def assign(db: Session, app: Application, actor_id: str | None) -> Assessment | None:
    """Give an application the job's published assessment (once)."""
    t = db.query(AssessmentTemplate).filter_by(job_id=app.job_id, status="published").one_or_none()
    if not t or app.status in ("rejected", "hired", "offer"):
        return None
    existing = db.query(Assessment).filter_by(application_id=app.id, template_id=t.id).first()
    if existing:
        return existing
    skills = sorted({q.skill for q in t.questions})
    s = Assessment(application_id=app.id, template_id=t.id, title=t.title, skill=", ".join(skills)[:80], duration_minutes=t.duration_minutes,
                   questions=snapshot(t), status="assigned", answers={}, per_skill={}, results={})
    db.add(s)
    if app.status in ASSIGNABLE_STATUSES and app.status != "assessment":
        app.status, app.updated_at = "assessment", utcnow()
        db.add(ApplicationEvent(application_id=app.id, status="assessment", note=f"Skill assessment assigned: {t.title}", actor_id=actor_id))
    db.add(Message(recipient_id=app.candidate.user_id, sender_id=actor_id, sender_label=f"{app.job.organization.name}", application_id=app.id,
                   subject=f"Skill assessment assigned – {app.job.title}",
                   body=f"Please complete \"{t.title}\" ({len(t.questions)} questions, {t.duration_minutes} minutes) from your Assessments page. "
                        "You'll be asked whether to turn on your camera for an optional identity check before you start."))
    return s


# ------------------------------------------------------------------------------------------- attempts

def public_questions(s: Assessment) -> list[dict]:
    """What the candidate sees: never the answer key."""
    return [{"id": q["id"], "skill": q.get("skill"), "prompt": q["prompt"], "code": q.get("code"), "difficulty": q.get("difficulty", "medium"),
             "options": q["options"]} for q in s.questions or []]


def remaining_seconds(s: Assessment) -> int:
    if not s.ends_at:
        return s.duration_minutes * 60
    return max(0, int((s.ends_at - utcnow()).total_seconds()))


def add_event(db: Session, s: Assessment, cand_id: str, kind: str, client_at=None, **detail) -> None:
    db.add(AssessmentEvent(assessment_id=s.id, candidate_id=cand_id, kind=kind, client_at=client_at, detail=detail))


def score(s: Assessment) -> None:
    answers = s.answers or {}
    results, per_skill = {}, {}
    for q in s.questions or []:
        chosen = answers.get(q["id"])
        correct = chosen is not None and chosen == q["answer"]
        results[q["id"]] = {"chosen": chosen, "correct": correct}
        k = q.get("skill") or "General"
        ps = per_skill.setdefault(k, {"correct": 0, "total": 0})
        ps["total"] += 1
        ps["correct"] += int(correct)
    for ps in per_skill.values():
        ps["percent"] = round(100 * ps["correct"] / ps["total"]) if ps["total"] else 0
    s.results, s.per_skill = results, per_skill
    s.max_score = len(s.questions or [])
    s.score = sum(r["correct"] for r in results.values())
    s.percent = round(100 * s.score / s.max_score, 1) if s.max_score else 0.0


def finalize(db: Session, s: Assessment, cand_id: str, reason: str) -> None:
    score(s)
    s.status, s.submitted_at, s.submit_reason = "submitted", utcnow(), reason
    counts = event_counts(db, s.id)
    s.tab_switches, s.copy_paste = counts.get("visibility_hidden", 0), counts.get("copy", 0) + counts.get("paste", 0) + counts.get("cut", 0)
    add_event(db, s, cand_id, "time_up" if reason == "time_up" else "submitted", score=s.score, maxScore=s.max_score)
    app = db.get(Application, s.application_id)
    db.add(ApplicationEvent(application_id=app.id, status=app.status, note=f"Assessment submitted ({'time ran out' if reason == 'time_up' else 'by the candidate'})"))
    from ..evidence import chain as evidence
    evidence.record(db, cand_id, "assessment.submitted", actor_role="candidate" if reason != "time_up" else "system", actor_ref=app.candidate.user_id,
                    application_id=app.id, organization_id=app.job.organization_id, assessmentId=s.id, title=s.title, reason=reason,
                    score=s.score, maxScore=s.max_score, percent=s.percent, reviewSignals=(s.tab_switches or 0) + (s.copy_paste or 0),
                    eventCounts=counts, answersSha256=evidence.sha256(evidence.canonical(s.answers or {})))


def expire_if_due(db: Session, s: Assessment, cand_id: str) -> bool:
    if s.status == "in_progress" and s.ends_at and utcnow() > s.ends_at + timedelta(seconds=GRACE_SECONDS):
        finalize(db, s, cand_id, "time_up")
        db.commit()
        return True
    return False


def event_counts(db: Session, assessment_id: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for (kind,) in db.query(AssessmentEvent.kind).filter_by(assessment_id=assessment_id):
        out[kind] = out.get(kind, 0) + 1
    return out


def timeline(db: Session, s: Assessment) -> list[dict]:
    rows = db.query(AssessmentEvent).filter_by(assessment_id=s.id).order_by(AssessmentEvent.at, AssessmentEvent.id).all()
    return [{"kind": e.kind, "at": serialize.iso(e.at), "clientAt": serialize.iso(e.client_at), "detail": e.detail,
             "reviewSignal": e.kind in REVIEW_SIGNALS, "label": REVIEW_SIGNALS.get(e.kind)} for e in rows]


def face_checks(db: Session, candidate_id: str, stage: str, reference_id: str) -> list[dict]:
    rows = db.query(FaceCheck).filter_by(candidate_id=candidate_id, stage=stage, reference_id=reference_id).order_by(FaceCheck.at).all()
    return [{"decision": f.decision, "outcome": outcome_for(f.decision, f.similarity), "similarity": f.similarity, "threshold": f.threshold,
             "at": serialize.iso(f.at)} for f in rows]


def attempt_json(db: Session, s: Assessment, for_recruiter: bool) -> dict:
    app = db.get(Application, s.application_id)
    counts = event_counts(db, s.id)
    out = {
        "id": s.id, "applicationId": app.id, "jobTitle": app.job.title, "title": s.title, "status": s.status,
        "questionCount": len(s.questions or []), "durationMinutes": s.duration_minutes,
        "startedAt": serialize.iso(s.started_at), "submittedAt": serialize.iso(s.submitted_at), "submitReason": s.submit_reason or None,
        "score": s.score, "maxScore": s.max_score, "percent": s.percent, "perSkill": s.per_skill or {},
        "passPercent": _pass_percent(db, s), "cameraConsent": s.camera_consent,
        "signals": {k: counts.get(k, 0) for k in REVIEW_SIGNALS},
    }
    if for_recruiter:
        out["candidateName"] = app.candidate.user.full_name
        out["timeline"] = timeline(db, s)
        out["faceChecks"] = face_checks(db, app.candidate_id, "assessment", s.id)
        if s.status == "submitted":
            out["answers"] = [{"id": q["id"], "skill": q.get("skill"), "prompt": q["prompt"], "options": q["options"], "chosen": (s.results or {}).get(q["id"], {}).get("chosen"),
                               "correctOptionId": q["answer"], "correct": (s.results or {}).get(q["id"], {}).get("correct", False), "source": q.get("source")}
                              for q in s.questions or []]
    return out


def _pass_percent(db: Session, s: Assessment) -> int | None:
    t = db.get(AssessmentTemplate, s.template_id) if s.template_id else None
    return t.pass_percent if t else None


# ------------------------------------------------------------------------------------------- Proof of Skill

def _key(skill: str) -> tuple[str, str]:
    k = bank.canonical(skill)
    return (k, bank.LABELS[k]) if k else (skill.strip().lower(), skill.strip())


def resume_skills(db: Session, cand: Candidate) -> list[str]:
    doc = next((d for d in serialize.current_docs(cand) if d.kind == "resume"), None)
    if not doc:
        return []
    ext = (db.query(DocumentExtraction).filter_by(document_id=doc.id).order_by(DocumentExtraction.created_at.desc()).first())
    val = (ext.fields or {}).get("skills", {}).get("value") if ext else None
    return [str(v) for v in val] if isinstance(val, list) else []


def proof_of_skill(db: Session, cand: Candidate, job: Job | None = None) -> dict:
    rows: dict[str, dict] = {}

    def row(skill: str) -> dict:
        k, label = _key(skill)
        return rows.setdefault(k, {"skill": label, "profile": False, "resume": False, "required": False, "assessed": None})

    for s in cand.skills or []:
        row(s)["profile"] = True
    for s in resume_skills(db, cand):
        row(s)["resume"] = True
    if job:
        for s in job.skills or []:
            row(s)["required"] = True
    app_ids = [a.id for a in db.query(Application.id).filter_by(candidate_id=cand.id)]
    attempts = db.query(Assessment).filter(Assessment.application_id.in_(app_ids), Assessment.status == "submitted").all() if app_ids else []
    for s in attempts:
        for skill, ps in (s.per_skill or {}).items():
            r = row(skill)
            agg = r["assessed"] or {"correct": 0, "total": 0}
            agg["correct"] += ps.get("correct", 0)
            agg["total"] += ps.get("total", 0)
            r["assessed"] = agg
    for r in rows.values():
        a = r["assessed"]
        if a and a["total"]:
            a["percent"] = round(100 * a["correct"] / a["total"])
            claimed = r["profile"] or r["resume"]
            r["note"] = ("Demonstrated in the assessment." if a["percent"] >= 60 else
                         "Lower score on this test. One short test is not proof of the skill level, and never of dishonesty."
                         if claimed else "Assessed but not claimed.")
        else:
            r["note"] = "Claimed, not assessed yet." if (r["profile"] or r["resume"]) else ("Required by the job, not assessed yet." if r["required"] else "")
    ordered = sorted(rows.values(), key=lambda r: (not r["required"], r["assessed"] is None, r["skill"].lower()))
    return {"skills": ordered, "attempts": len(attempts),
            "disclaimer": "Scores show performance on short multiple-choice tests only. They are not proof that a claim is false."}


# ------------------------------------------------------------------------------------------- interview identity

def outcome_for(decision: str, similarity: float | None) -> str:
    """matched / uncertain / needs_review. Never 'failed': a person reviews anything that isn't a clear match."""
    if decision == "match":
        return "matched"
    if decision == "no_match":
        return "uncertain" if similarity is not None and similarity >= UNCERTAIN_FLOOR else "needs_review"
    if decision in ("no_face", "poor_quality"):
        return "uncertain"
    return "needs_review"  # multiple_faces, no_enrollment, no_consent, camera_unavailable, error
