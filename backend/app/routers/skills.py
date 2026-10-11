"""Phase 4 endpoints: Proof of Skill assessments (builder, attempts, scoring, integrity timeline) and interview
invitations with an identity check at entry."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, Response
from pydantic import Field, field_validator, model_validator

from .. import activity, serialize
from ..deps import CurrentCandidate, CurrentRecruiter, Db, Paging, paginate
from ..errors import ApiError, bad_request, conflict, not_found
from ..models import Application, Assessment, AssessmentTemplate, Interview, Job, TemplateQuestion, utcnow
from ..schemas import Camel
from ..skills import generate, service

router = APIRouter(tags=["assessments & interviews"])


# ================================================================== recruiter: assessment builder

def _org_job(db, rec, job_id: str) -> Job:
    j = db.get(Job, job_id)
    if not j or j.organization_id != rec.organization_id:
        raise not_found("Job")
    return j


def _template(db, job: Job) -> AssessmentTemplate | None:
    return db.query(AssessmentTemplate).filter_by(job_id=job.id).one_or_none()


def _draft_template(db, rec, job_id: str) -> AssessmentTemplate:
    t = _template(db, _org_job(db, rec, job_id))
    if not t:
        raise not_found("Assessment")
    if t.status != "draft":
        raise conflict("This assessment is published and locked. Questions can't be changed after candidates receive them.", "assessment_locked")
    return t


def _org_question(db, rec, qid: str) -> TemplateQuestion:
    q = db.get(TemplateQuestion, qid)
    t = db.get(AssessmentTemplate, q.template_id) if q else None
    if not q or not t or db.get(Job, t.job_id).organization_id != rec.organization_id:
        raise not_found("Question")
    if t.status != "draft":
        raise conflict("This assessment is published and locked.", "assessment_locked")
    return q


class GenerateIn(Camel):
    count: int = Field(default=10, ge=3, le=20)
    duration_minutes: int = Field(default=20, ge=5, le=120)
    pass_percent: int = Field(default=60, ge=0, le=100)
    title: str = Field(default="", max_length=160)
    source: Literal["auto", "bank"] = "auto"
    replace: bool = False


class QuestionIn(Camel):
    skill: str = Field(min_length=1, max_length=80)
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    prompt: str = Field(min_length=10, max_length=600)
    code: str = Field(default="", max_length=2000)
    options: list[str] = Field(min_length=4, max_length=4)
    correct_option_id: Literal["a", "b", "c", "d"]
    explanation: str = Field(default="", max_length=500)

    @field_validator("options")
    @classmethod
    def _opts(cls, v: list[str]) -> list[str]:
        v = [o.strip() for o in v]
        if any(not o or len(o) > 200 for o in v):
            raise ValueError("Each option needs 1–200 characters")
        if len({o.lower() for o in v}) != 4:
            raise ValueError("Options must all be different")
        return v


class SettingsIn(Camel):
    title: str = Field(min_length=3, max_length=160)
    duration_minutes: int = Field(ge=5, le=120)
    pass_percent: int = Field(ge=0, le=100)


@router.get("/recruiter/jobs/{job_id}/assessment", summary="The job's assessment (with answer keys), or null")
def get_builder(job_id: str, rec: CurrentRecruiter, db: Db):
    job = _org_job(db, rec, job_id)
    t = _template(db, job)
    return {"job": {"id": job.id, "title": job.title, "skills": job.skills}, "template": service.template_json(t, db) if t else None,
            "geminiConfigured": bool(__import__("os").environ.get("GEMINI_API_KEY"))}


@router.post("/recruiter/jobs/{job_id}/assessment/generate", summary="Draft questions (Gemini if configured, else the local bank)")
def generate_questions(job_id: str, body: GenerateIn, rec: CurrentRecruiter, db: Db):
    job = _org_job(db, rec, job_id)
    t = _template(db, job)
    if t and t.status != "draft":
        raise conflict("This assessment is published and locked.", "assessment_locked")
    if not job.skills:
        raise bad_request("Add required skills to the job first.", "no_skills")
    drafted, source, note = generate.draft_questions(job.skills, body.count, job.id, job.title, body.source)
    if not drafted:
        raise ApiError(422, "no_questions", note + " Write your own questions instead.")
    if not t:
        t = AssessmentTemplate(job_id=job.id, title=body.title or f"{job.title} – skill check", created_by=rec.id)
        db.add(t)
        db.flush()
    t.duration_minutes, t.pass_percent = body.duration_minutes, body.pass_percent
    if body.title:
        t.title = body.title
    if body.replace:
        t.questions = [q for q in t.questions if q.source == "recruiter"]
    start = len(t.questions)
    for i, q in enumerate(drafted):
        t.questions.append(TemplateQuestion(position=start + i, skill=q["skill"] or job.skills[0], difficulty=q["difficulty"], prompt=q["prompt"],
                                            code=q.get("code") or "", options=q["options"], correct_option_id=q["answer"],
                                            explanation=q.get("explanation", ""), source=source, source_ref=q.get("bankId", ""), approved=False))
    t.generation_note = note
    activity.log(db, rec.id, "assessment.generated", "assessment_template", t.id, source=source, count=len(drafted))
    db.commit()
    db.refresh(t)
    return service.template_json(t, db)


@router.put("/recruiter/jobs/{job_id}/assessment", summary="Change title, duration and pass mark (draft only)")
def update_settings(job_id: str, body: SettingsIn, rec: CurrentRecruiter, db: Db):
    t = _draft_template(db, rec, job_id)
    t.title, t.duration_minutes, t.pass_percent = body.title, body.duration_minutes, body.pass_percent
    db.commit()
    return service.template_json(t, db)


@router.post("/recruiter/jobs/{job_id}/assessment/questions", status_code=201, summary="Add a recruiter-written question")
def add_question(job_id: str, body: QuestionIn, rec: CurrentRecruiter, db: Db):
    job = _org_job(db, rec, job_id)
    t = _template(db, job)
    if t and t.status != "draft":
        raise conflict("This assessment is published and locked.", "assessment_locked")
    if not t:
        t = AssessmentTemplate(job_id=job.id, title=f"{job.title} – skill check", created_by=rec.id)
        db.add(t)
        db.flush()
    if len(t.questions) >= 40:
        raise bad_request("An assessment can have at most 40 questions.")
    t.questions.append(TemplateQuestion(position=len(t.questions), skill=body.skill, difficulty=body.difficulty, prompt=body.prompt, code=body.code,
                                        options=[{"id": k, "text": o} for k, o in zip("abcd", body.options)], correct_option_id=body.correct_option_id,
                                        explanation=body.explanation, source="recruiter", approved=True, approved_by=rec.id, approved_at=utcnow()))
    db.commit()
    db.refresh(t)
    return service.template_json(t, db)


@router.put("/recruiter/assessment-questions/{qid}", summary="Edit a draft question (it must be approved again)")
def edit_question(qid: str, body: QuestionIn, rec: CurrentRecruiter, db: Db):
    q = _org_question(db, rec, qid)
    q.skill, q.difficulty, q.prompt, q.code = body.skill, body.difficulty, body.prompt, body.code
    q.options = [{"id": k, "text": o} for k, o in zip("abcd", body.options)]
    q.correct_option_id, q.explanation = body.correct_option_id, body.explanation
    q.edited = True
    q.approved, q.approved_by, q.approved_at = False, None, None
    db.commit()
    return service.template_json(db.get(AssessmentTemplate, q.template_id), db)


@router.post("/recruiter/assessment-questions/{qid}/approve", summary="Approve a question and its answer key")
def approve_question(qid: str, rec: CurrentRecruiter, db: Db):
    q = _org_question(db, rec, qid)
    q.approved, q.approved_by, q.approved_at = True, rec.id, utcnow()
    db.commit()
    return service.template_json(db.get(AssessmentTemplate, q.template_id), db)


@router.delete("/recruiter/assessment-questions/{qid}")
def delete_question(qid: str, rec: CurrentRecruiter, db: Db):
    q = _org_question(db, rec, qid)
    t = db.get(AssessmentTemplate, q.template_id)
    db.delete(q)
    db.flush()
    for i, other in enumerate(sorted(t.questions, key=lambda x: x.position)):
        other.position = i
    db.commit()
    db.refresh(t)
    return service.template_json(t, db)


@router.post("/recruiter/jobs/{job_id}/assessment/publish", summary="Publish (locks questions) and assign to current applicants")
def publish(job_id: str, rec: CurrentRecruiter, db: Db):
    job = _org_job(db, rec, job_id)
    t = _draft_template(db, rec, job_id)
    if not t.questions:
        raise bad_request("Add at least one question before publishing.", "no_questions")
    pending = [q for q in t.questions if not q.approved]
    if pending:
        raise bad_request(f"{len(pending)} question(s) still need your approval. Review each question and its answer key first.", "unapproved_questions")
    t.status, t.published_at, t.published_by = "published", utcnow(), rec.id
    db.flush()
    assigned = sum(1 for a in job.applications if service.assign(db, a, rec.id))
    activity.log(db, rec.id, "assessment.published", "assessment_template", t.id, assigned=assigned)
    db.commit()
    db.refresh(t)
    return service.template_json(t, db)


# ================================================================== recruiter: results

def _org_attempt(db, rec, aid: str) -> Assessment:
    s = db.get(Assessment, aid)
    app = db.get(Application, s.application_id) if s else None
    if not s or not app or app.job.organization_id != rec.organization_id:
        raise not_found("Assessment")
    return s


@router.get("/recruiter/assessments", summary="All assessment attempts for your organisation's jobs")
def recruiter_attempts(rec: CurrentRecruiter, db: Db, page: Paging, response: Response):
    q = (db.query(Assessment).join(Application, Assessment.application_id == Application.id).join(Job, Application.job_id == Job.id)
         .filter(Job.organization_id == rec.organization_id).order_by(Assessment.submitted_at.desc().nullslast(), Assessment.id))
    return [service.attempt_json(db, s, for_recruiter=False) | {"candidateName": db.get(Application, s.application_id).candidate.user.full_name}
            for s in paginate(q, page, response)]


@router.get("/recruiter/assessments/{aid}", summary="Attempt detail: answers, per-skill score, integrity timeline, face checks")
def recruiter_attempt(aid: str, rec: CurrentRecruiter, db: Db):
    return service.attempt_json(db, _org_attempt(db, rec, aid), for_recruiter=True)


@router.get("/recruiter/applicants/{app_id}/skills", summary="Claimed skills vs. demonstrated assessment performance")
def recruiter_skills(app_id: str, rec: CurrentRecruiter, db: Db):
    app = db.get(Application, app_id)
    if not app or app.job.organization_id != rec.organization_id:
        raise not_found("Application")
    attempts = db.query(Assessment).filter_by(application_id=app.id).all()
    return service.proof_of_skill(db, app.candidate, app.job) | {"attemptsForThisJob": [service.attempt_json(db, s, False) for s in attempts]}


# ================================================================== candidate: attempts

def _my_attempt(db, cand, aid: str) -> Assessment:
    s = db.get(Assessment, aid)
    app = db.get(Application, s.application_id) if s else None
    if not s or not app or app.candidate_id != cand.id:
        raise not_found("Assessment")
    return s


def _session(s: Assessment) -> dict:
    return {"id": s.id, "title": s.title, "status": s.status, "durationSeconds": s.duration_minutes * 60, "remainingSeconds": service.remaining_seconds(s),
            "questionCount": len(s.questions or []), "cameraConsent": s.camera_consent,
            "questions": service.public_questions(s) if s.status == "in_progress" else [],
            "savedAnswers": (s.answers or {}) if s.status == "in_progress" else {}}


@router.get("/candidate/assessments")
def my_attempts(cand: CurrentCandidate, db: Db):
    app_ids = [a.id for a in db.query(Application.id).filter_by(candidate_id=cand.id)]
    rows = db.query(Assessment).filter(Assessment.application_id.in_(app_ids)).all() if app_ids else []
    for s in rows:
        service.expire_if_due(db, s, cand.id)
    return [service.attempt_json(db, s, False) | {"skill": s.skill, "dueAt": serialize.iso(s.due_at)} for s in rows]


@router.get("/candidate/assessments/{aid}", summary="Assessment session (questions only after start; answer keys never)")
def my_attempt(aid: str, cand: CurrentCandidate, db: Db):
    s = _my_attempt(db, cand, aid)
    service.expire_if_due(db, s, cand.id)
    return _session(s)


class StartIn(Camel):
    camera_consent: bool
    camera_state: Literal["granted", "denied", "unavailable", "declined"] = "declined"


@router.post("/candidate/assessments/{aid}/start", summary="Start the timer. Camera use is optional and recorded as the candidate chose.")
def start_attempt(aid: str, body: StartIn, cand: CurrentCandidate, db: Db):
    s = _my_attempt(db, cand, aid)
    if s.status == "submitted":
        raise conflict("This assessment has already been submitted.", "already_submitted")
    if not s.questions:
        raise bad_request("This assessment has no questions yet.", "no_questions")
    if s.status == "assigned":
        s.status, s.started_at = "in_progress", utcnow()
        s.ends_at = s.started_at + timedelta(minutes=s.duration_minutes)
        s.camera_consent = body.camera_consent
        service.add_event(db, s, cand.id, "started", cameraConsent=body.camera_consent)
        service.add_event(db, s, cand.id, {"granted": "camera_granted", "denied": "camera_denied", "unavailable": "camera_denied",
                                           "declined": "camera_declined"}[body.camera_state], state=body.camera_state)
        activity.log(db, cand.user_id, "assessment.started", "assessment", s.id)
    else:
        service.add_event(db, s, cand.id, "resumed")
    db.commit()
    if service.expire_if_due(db, s, cand.id):
        raise conflict("Time is up. Your saved answers were submitted.", "time_up")
    return _session(s)


class AnswersIn(Camel):
    answers: dict[str, str] = Field(max_length=200)


def _check_answers(s: Assessment, answers: dict[str, str]) -> dict[str, str]:
    valid = {q["id"]: {o["id"] for o in q["options"]} for q in s.questions or []}
    bad = [k for k, v in answers.items() if k not in valid or v not in valid[k]]
    if bad:
        raise bad_request("Some answers don't belong to this assessment.", "invalid_answers")
    return answers


@router.put("/candidate/assessments/{aid}/answers", summary="Save progress (while the timer is running)")
def save_answers(aid: str, body: AnswersIn, cand: CurrentCandidate, db: Db):
    s = _my_attempt(db, cand, aid)
    if service.expire_if_due(db, s, cand.id) or s.status == "submitted":
        raise conflict("This assessment has already been submitted.", "already_submitted")
    if s.status != "in_progress":
        raise conflict("Start the assessment first.", "not_started")
    s.answers = _check_answers(s, body.answers)
    db.commit()
    return {"saved": len(s.answers), "remainingSeconds": service.remaining_seconds(s)}


class EventIn(Camel):
    type: str = Field(max_length=30)
    client_at: datetime | None = None
    detail: dict = Field(default_factory=dict)

    @model_validator(mode="after")
    def _kind(self):
        if self.type not in service.CLIENT_EVENT_KINDS:
            raise ValueError(f"Unknown event type '{self.type}'")
        self.detail = {k: v for k, v in list(self.detail.items())[:5] if isinstance(v, (str, int, float, bool)) and len(str(v)) <= 100}
        return self


class EventsIn(Camel):
    events: list[EventIn] = Field(min_length=1, max_length=50)


@router.post("/candidate/assessments/{aid}/events", summary="Record integrity events (tab/focus changes, copy/paste, camera state)")
def record_events(aid: str, body: EventsIn, cand: CurrentCandidate, db: Db):
    s = _my_attempt(db, cand, aid)
    if s.status != "in_progress":
        raise conflict("Events can only be recorded while the assessment is running.", "not_running")
    if sum(service.event_counts(db, s.id).values()) + len(body.events) > service.MAX_CLIENT_EVENTS:
        raise ApiError(429, "too_many_events", "Too many events recorded for this attempt.")
    for e in body.events:
        client_at = e.client_at.astimezone(timezone.utc).replace(tzinfo=None) if e.client_at and e.client_at.tzinfo else e.client_at
        service.add_event(db, s, cand.id, e.type, client_at, **e.detail)
    db.commit()
    return {"recorded": len(body.events)}


class SubmitIn(Camel):
    answers: dict[str, str] = Field(default_factory=dict, max_length=200)


@router.post("/candidate/assessments/{aid}/submit", summary="Submit once. Scored on the server; cannot be repeated or edited.")
def submit(aid: str, body: SubmitIn, cand: CurrentCandidate, db: Db):
    s = _my_attempt(db, cand, aid)
    if s.status == "submitted":
        raise conflict("This assessment has already been submitted.", "already_submitted")
    if s.status != "in_progress":
        raise conflict("Start the assessment first.", "not_started")
    if service.expire_if_due(db, s, cand.id):  # late: the answers saved before the deadline count, not the late ones
        return service.attempt_json(db, s, False)
    s.answers = _check_answers(s, body.answers)
    service.finalize(db, s, cand.id, "submitted")
    activity.log(db, cand.user_id, "assessment.submitted", "assessment", s.id, score=s.score, maxScore=s.max_score)
    from ..fraud import scoring
    scoring.refresh(db, db.get(Application, s.application_id), "assessment_submitted")
    db.commit()
    return service.attempt_json(db, s, False)


@router.get("/candidate/skills", summary="My claimed skills vs. demonstrated assessment performance")
def my_skills(cand: CurrentCandidate, db: Db):
    return service.proof_of_skill(db, cand)


# ================================================================== interviews

def interview_json(db, i: Interview, for_recruiter: bool) -> dict:
    out = serialize.interview(i) | {
        "candidateResponse": i.candidate_response or None, "candidateNote": i.candidate_note or None, "acknowledgedAt": serialize.iso(i.acknowledged_at),
        "entryOutcome": i.entry_outcome or None, "entryCheckedAt": serialize.iso(i.entry_checked_at),
    }
    if not for_recruiter and not i.entry_checked_at:
        out["meetingLink"] = None  # revealed after the entry identity step
    if for_recruiter:
        out["faceChecks"] = service.face_checks(db, i.application.candidate_id, "interview", i.id)
    return out


def _my_interview(db, cand, iid: str) -> Interview:
    i = db.get(Interview, iid)
    if not i or i.application.candidate_id != cand.id:
        raise not_found("Interview")
    return i


@router.get("/candidate/interviews")
def my_interviews(cand: CurrentCandidate, db: Db):
    app_ids = [a.id for a in db.query(Application.id).filter_by(candidate_id=cand.id)]
    rows = db.query(Interview).filter(Interview.application_id.in_(app_ids)).order_by(Interview.scheduled_at).all() if app_ids else []
    return [interview_json(db, i, False) for i in rows]


@router.get("/candidate/interviews/{iid}")
def my_interview(iid: str, cand: CurrentCandidate, db: Db):
    return interview_json(db, _my_interview(db, cand, iid), False)


class RespondIn(Camel):
    response: Literal["accepted", "reschedule_requested"]
    note: str = Field(default="", max_length=1000)

    @model_validator(mode="after")
    def _note(self):
        if self.response == "reschedule_requested" and len(self.note.strip()) < 5:
            raise ValueError("Say which times would suit you")
        return self


@router.post("/candidate/interviews/{iid}/respond", summary="Acknowledge the invitation or ask to reschedule")
def respond(iid: str, body: RespondIn, cand: CurrentCandidate, db: Db):
    i = _my_interview(db, cand, iid)
    if i.status != "scheduled":
        raise conflict("This interview is no longer scheduled.", "interview_closed")
    i.candidate_response, i.candidate_note, i.acknowledged_at = body.response, body.note.strip(), utcnow()
    activity.log(db, cand.user_id, "interview.responded", "interview", i.id, response=body.response)
    db.commit()
    return interview_json(db, i, False)


class EntryIn(Camel):
    image: str | None = Field(default=None, max_length=4_000_000)
    camera: Literal["ok", "denied", "unavailable"] = "ok"


@router.post("/candidate/interviews/{iid}/entry", summary="Identity step before joining: live frame vs. enrolled face")
def interview_entry(iid: str, body: EntryIn, cand: CurrentCandidate, db: Db):
    from .verification import IdentityCheckIn, identity_check
    i = _my_interview(db, cand, iid)
    if i.status != "scheduled":
        raise conflict("This interview is no longer scheduled.", "interview_closed")
    if body.camera != "ok" or not body.image:
        from ..models import FaceCheck
        db.add(FaceCheck(candidate_id=cand.id, stage="interview", reference_id=i.id, decision="camera_unavailable", quality={"camera": body.camera}))
        result = {"decision": "camera_unavailable", "outcome": "needs_review", "similarity": None,
                  "message": "No camera, so identity couldn't be checked. You can still join; the recruiter will verify you in the call."}
    else:
        result = identity_check(IdentityCheckIn(stage="interview", reference_id=i.id, image=body.image), cand, db)
    i.entry_outcome, i.entry_checked_at = result["outcome"], utcnow()
    from ..evidence import chain as evidence
    evidence.record(db, cand.id, "interview.identity_check", actor_role="candidate", actor_ref=cand.user_id, application_id=i.application_id,
                    organization_id=i.application.job.organization_id, interviewId=i.id, outcome=result["outcome"],
                    decision=result.get("decision"), similarity=result.get("similarity"))
    from ..fraud import scoring
    scoring.refresh_candidate(db, cand.id, "interview_entry")
    db.commit()
    return result | {"interview": interview_json(db, i, False)}


class InterviewStatusIn(Camel):
    status: Literal["completed", "cancelled", "scheduled"]


@router.post("/recruiter/interviews/{iid}/status", summary="Mark an interview completed or cancelled")
def set_interview_status(iid: str, body: InterviewStatusIn, rec: CurrentRecruiter, db: Db):
    i = db.get(Interview, iid)
    if not i or i.application.job.organization_id != rec.organization_id:
        raise not_found("Interview")
    i.status = body.status
    activity.log(db, rec.id, "interview.status", "interview", i.id, status=body.status)
    db.commit()
    return interview_json(db, i, True)


@router.get("/recruiter/interviews", summary="Interviews for your organisation's applicants")
def recruiter_interviews(rec: CurrentRecruiter, db: Db, page: Paging, response: Response):
    q = (db.query(Interview).join(Application, Interview.application_id == Application.id).join(Job, Application.job_id == Job.id)
         .filter(Job.organization_id == rec.organization_id).order_by(Interview.scheduled_at.desc()))
    return [interview_json(db, i, True) for i in paginate(q, page, response)]
