"""Database schema (SQLAlchemy 2.x). Every change here needs an Alembic migration in migrations/versions."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, LargeBinary, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)  # stored as naive UTC


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160))
    website: Mapped[str] = mapped_column(String(300), default="")
    company_size: Mapped[str] = mapped_column(String(20), default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | suspended
    retention_days: Mapped[int] = mapped_column(Integer, default=180)
    notify_on_flag: Mapped[bool] = mapped_column(Boolean, default=True)
    notify_daily_digest: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    members: Mapped[list[User]] = relationship(back_populates="organization")
    jobs: Mapped[list[Job]] = relationship(back_populates="organization")


class User(Base):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    role: Mapped[str] = mapped_column(String(20))  # candidate | recruiter
    email: Mapped[str] = mapped_column(String(254), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str] = mapped_column(String(120))
    phone: Mapped[str] = mapped_column(String(20), default="")
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    organization: Mapped[Organization | None] = relationship(back_populates="members")
    candidate: Mapped[Candidate | None] = relationship(back_populates="user", uselist=False)


class AuthSession(Base):
    """One row per issued token, so logout and password changes can revoke it."""
    __tablename__ = "auth_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)  # JWT jti
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    user_agent: Mapped[str] = mapped_column(String(300), default="")


class OtpChallenge(Base):
    __tablename__ = "otp_challenges"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    phone: Mapped[str] = mapped_column(String(20), index=True)
    code_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    used_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Candidate(Base):
    __tablename__ = "candidates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    location: Mapped[str] = mapped_column(String(120), default="")
    headline: Mapped[str] = mapped_column(String(120), default="")
    linkedin_url: Mapped[str] = mapped_column(String(300), default="")
    github_url: Mapped[str] = mapped_column(String(300), default="")
    skills: Mapped[list] = mapped_column(JSON, default=list)
    phone_verified_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    user: Mapped[User] = relationship(back_populates="candidate")
    education: Mapped[list[Education]] = relationship(cascade="all, delete-orphan", order_by="Education.position")
    employment: Mapped[list[Employment]] = relationship(cascade="all, delete-orphan", order_by="Employment.position")
    references: Mapped[list[Reference]] = relationship(cascade="all, delete-orphan", order_by="Reference.position")
    documents: Mapped[list[Document]] = relationship(back_populates="candidate")
    consents: Mapped[list[ConsentRecord]] = relationship(cascade="all, delete-orphan")


class Education(Base):
    __tablename__ = "education"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    degree: Mapped[str] = mapped_column(String(120))
    institution: Mapped[str] = mapped_column(String(160))
    start_year: Mapped[int] = mapped_column(Integer)
    end_year: Mapped[int] = mapped_column(Integer)
    score: Mapped[str] = mapped_column(String(20), default="")


class Employment(Base):
    __tablename__ = "employment"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    company: Mapped[str] = mapped_column(String(160))
    title: Mapped[str] = mapped_column(String(120))
    start_month: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    end_month: Mapped[str] = mapped_column(String(7), default="")
    current: Mapped[bool] = mapped_column(Boolean, default=False)


class Reference(Base):
    __tablename__ = "references"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    name: Mapped[str] = mapped_column(String(120))
    relationship_: Mapped[str] = mapped_column("relationship", String(80))
    company: Mapped[str] = mapped_column(String(160), default="")
    email: Mapped[str] = mapped_column(String(254), default="")
    phone: Mapped[str] = mapped_column(String(20), default="")


class ConsentRecord(Base):
    __tablename__ = "consent_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    purpose: Mapped[str] = mapped_column(String(40))  # biometric | document_processing
    granted: Mapped[bool] = mapped_column(Boolean)
    policy_version: Mapped[str] = mapped_column(String(20))
    recorded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    ip_address: Mapped[str] = mapped_column(String(64), default="")
    user_agent: Mapped[str] = mapped_column(String(300), default="")


class Document(Base):
    __tablename__ = "documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))  # resume | marksheet | education_certificate | id_document | experience_letter | certificate | selfie
    original_name: Mapped[str] = mapped_column(String(255))
    storage_name: Mapped[str] = mapped_column(String(64), unique=True)  # random file name inside UPLOAD_DIR
    content_type: Mapped[str] = mapped_column(String(60))
    size_bytes: Mapped[int] = mapped_column(Integer)
    sha256: Mapped[str] = mapped_column(String(64), index=True)
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    uploaded_by: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    replaced_by_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    replaced_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Uploading never verifies. Only a verification run (Phase 3+) may change this.
    verification_status: Mapped[str] = mapped_column(String(20), default="pending")

    candidate: Mapped[Candidate] = relationship(back_populates="documents")


class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title: Mapped[str] = mapped_column(String(120))
    department: Mapped[str] = mapped_column(String(120), default="")
    location: Mapped[str] = mapped_column(String(120))
    employment_type: Mapped[str] = mapped_column(String(20))
    work_mode: Mapped[str] = mapped_column(String(20))
    experience_min: Mapped[int] = mapped_column(Integer, default=0)
    experience_max: Mapped[int] = mapped_column(Integer, default=0)
    salary_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    salary_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skills: Mapped[list] = mapped_column(JSON, default=list)
    description: Mapped[str] = mapped_column(Text)
    requirements: Mapped[str] = mapped_column(Text, default="")
    assessments: Mapped[list] = mapped_column(JSON, default=list)
    deadline: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="open")  # draft | open | closed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    organization: Mapped[Organization] = relationship(back_populates="jobs")
    applications: Mapped[list[Application]] = relationship(back_populates="job")


class Application(Base):
    __tablename__ = "applications"
    __table_args__ = (UniqueConstraint("candidate_id", "job_id", name="uq_application_candidate_job"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), default="applied")
    applied_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)

    job: Mapped[Job] = relationship(back_populates="applications")
    candidate: Mapped[Candidate] = relationship()
    events: Mapped[list[ApplicationEvent]] = relationship(cascade="all, delete-orphan", order_by="ApplicationEvent.at")
    trust_report: Mapped[TrustReport | None] = relationship(uselist=False, cascade="all, delete-orphan")
    decisions: Mapped[list[ReviewDecision]] = relationship(cascade="all, delete-orphan", order_by="ReviewDecision.at")


class ApplicationEvent(Base):
    """Status history of an application (who changed what, when, and why)."""
    __tablename__ = "application_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30))
    note: Mapped[str] = mapped_column(Text, default="")
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReviewDecision(Base):
    __tablename__ = "review_decisions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    decision: Mapped[str] = mapped_column(String(20))  # approve | reject | reverify
    reason: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    recipient_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    sender_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    sender_label: Mapped[str] = mapped_column(String(200))
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), nullable=True)
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    read_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class VerificationRun(Base):
    """One execution of a check (identity, education, ...). Populated from Phase 3 onwards."""
    __tablename__ = "verification_runs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    check: Mapped[str] = mapped_column(String(30))
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    detail: Mapped[str] = mapped_column(Text, default="")
    job_id: Mapped[str | None] = mapped_column(ForeignKey("verification_jobs.id", ondelete="SET NULL"), nullable=True, index=True)
    error: Mapped[str] = mapped_column(Text, default="")


class Finding(Base):
    __tablename__ = "findings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("verification_runs.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    code: Mapped[str] = mapped_column(String(60))
    severity: Mapped[str] = mapped_column(String(20))  # info | warning | critical
    title: Mapped[str] = mapped_column(String(200))
    detail: Mapped[str] = mapped_column(Text, default="")
    points: Mapped[int] = mapped_column(Integer, default=0)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Assessment(Base):
    __tablename__ = "assessments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    skill: Mapped[str] = mapped_column(String(80))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=30)
    questions: Mapped[list] = mapped_column(JSON, default=list)  # filled from Phase 3 question bank
    status: Mapped[str] = mapped_column(String(20), default="assigned")
    due_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    answers: Mapped[dict] = mapped_column(JSON, default=dict)
    tab_switches: Mapped[int] = mapped_column(Integer, default=0)
    copy_paste: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # Phase 4
    template_id: Mapped[str | None] = mapped_column(ForeignKey("assessment_templates.id", ondelete="SET NULL"), nullable=True, index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    camera_consent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    percent: Mapped[float | None] = mapped_column(Float, nullable=True)
    per_skill: Mapped[dict] = mapped_column(JSON, default=dict)
    results: Mapped[dict] = mapped_column(JSON, default=dict)  # question id -> {"chosen", "correct": bool}
    submit_reason: Mapped[str] = mapped_column(String(20), default="")  # submitted | time_up


class AssessmentTemplate(Base):
    """One assessment per job. Questions must all be approved by a recruiter before publishing; then they are locked."""
    __tablename__ = "assessment_templates"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), unique=True)
    title: Mapped[str] = mapped_column(String(160))
    duration_minutes: Mapped[int] = mapped_column(Integer, default=20)
    pass_percent: Mapped[int] = mapped_column(Integer, default=60)
    status: Mapped[str] = mapped_column(String(20), default="draft")  # draft | published
    generation_note: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    published_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    questions: Mapped[list[TemplateQuestion]] = relationship(cascade="all, delete-orphan", order_by="TemplateQuestion.position")


class TemplateQuestion(Base):
    __tablename__ = "template_questions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    template_id: Mapped[str] = mapped_column(ForeignKey("assessment_templates.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, default=0)
    skill: Mapped[str] = mapped_column(String(80))
    difficulty: Mapped[str] = mapped_column(String(10), default="medium")
    prompt: Mapped[str] = mapped_column(Text)
    code: Mapped[str] = mapped_column(Text, default="")
    options: Mapped[list] = mapped_column(JSON, default=list)  # [{"id": "a", "text": "..."}]
    correct_option_id: Mapped[str] = mapped_column(String(8))
    explanation: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(20))  # gemini | question_bank | recruiter
    source_ref: Mapped[str] = mapped_column(String(40), default="")
    edited: Mapped[bool] = mapped_column(Boolean, default=False)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AssessmentEvent(Base):
    """Integrity timeline of one attempt. Signals for a human reviewer, never proof of cheating."""
    __tablename__ = "assessment_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    assessment_id: Mapped[str] = mapped_column(ForeignKey("assessments.id", ondelete="CASCADE"), index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)  # server time
    client_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Interview(Base):
    __tablename__ = "interviews"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    mode: Mapped[str] = mapped_column(String(20))
    interviewer: Mapped[str] = mapped_column(String(120))
    meeting_link: Mapped[str] = mapped_column(String(300), default="")
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    created_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    # Phase 4
    candidate_response: Mapped[str] = mapped_column(String(30), default="")  # "" | accepted | reschedule_requested
    candidate_note: Mapped[str] = mapped_column(Text, default="")
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    entry_outcome: Mapped[str] = mapped_column(String(20), default="")  # "" | matched | uncertain | needs_review
    entry_checked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    application: Mapped[Application] = relationship()


class ActivityEvent(Base):
    """Audit trail of security-relevant actions."""
    __tablename__ = "activity_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    actor_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(60))
    entity_type: Mapped[str] = mapped_column(String(40), default="")
    entity_id: Mapped[str] = mapped_column(String(32), default="")
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class TrustReport(Base):
    """Computed trust score per application. Written by the scoring engine in Phase 5."""
    __tablename__ = "trust_reports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), unique=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    risk: Mapped[str | None] = mapped_column(String(20), nullable=True)
    breakdown: Mapped[dict] = mapped_column(JSON, default=dict)
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ====================================================================== Phase 3: verification engine


class VerificationJob(Base):
    """One "Run verification" request. Processed by the background worker (services/queue.py)."""
    __tablename__ = "verification_jobs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason: Mapped[str] = mapped_column(String(40), default="manual")  # manual | document_changed | profile_changed | registration
    status: Mapped[str] = mapped_column(String(20), default="queued")  # queued | running | done | failed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    error: Mapped[str] = mapped_column(Text, default="")


class DocumentExtraction(Base):
    """Fields read from one document. Only the extracted fields and short evidence snippets are kept, never the full text."""
    __tablename__ = "document_extractions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    document_sha256: Mapped[str] = mapped_column(String(64))  # extraction is redone when the file changes
    method: Mapped[str] = mapped_column(String(40))  # pymupdf_text | ocr_tesseract | pymupdf_text+ocr | gemini+rules
    status: Mapped[str] = mapped_column(String(20))  # ok | low_text | failed
    pages: Mapped[int] = mapped_column(Integer, default=0)
    text_chars: Mapped[int] = mapped_column(Integer, default=0)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FaceEnrollment(Base):
    __tablename__ = "face_enrollments"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    source_document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    embedding_encrypted: Mapped[bytes] = mapped_column(LargeBinary)  # Fernet-encrypted float32 vector
    model: Mapped[str] = mapped_column(String(80))
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | revoked
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class FaceCheck(Base):
    """Result of one identity recheck. The probe photo itself is not stored."""
    __tablename__ = "face_checks"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    stage: Mapped[str] = mapped_column(String(30))  # id_document | assessment | interview | manual
    reference_id: Mapped[str] = mapped_column(String(32), default="")  # assessment / interview id
    decision: Mapped[str] = mapped_column(String(30))  # match | no_match | no_face | multiple_faces | poor_quality | no_enrollment | no_consent | error
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    threshold: Mapped[float | None] = mapped_column(Float, nullable=True)
    quality: Mapped[dict] = mapped_column(JSON, default=dict)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DuplicateAlert(Base):
    __tablename__ = "duplicate_alerts"
    __table_args__ = (UniqueConstraint("candidate_a_id", "candidate_b_id", "kind", name="uq_duplicate_pair_kind"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_a_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)  # lower id of the pair
    candidate_b_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(20))  # phone | face
    similarity: Mapped[float | None] = mapped_column(Float, nullable=True)
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    review_status: Mapped[str] = mapped_column(String(30), default="open")  # open | not_duplicate | confirmed_duplicate
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow)


class IssuerRecord(Base):
    """SIMULATED issuer registry for hackathon testing (loaded with manage.py load-issuer-records). Not a real university database."""
    __tablename__ = "issuer_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    issuer: Mapped[str] = mapped_column(String(200))
    register_number: Mapped[str] = mapped_column(String(60), index=True)
    student_name: Mapped[str] = mapped_column(String(160))
    qualification: Mapped[str] = mapped_column(String(160), default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    loaded_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class IssuerConfirmation(Base):
    """Issuer authenticity is tracked separately from document consistency."""
    __tablename__ = "issuer_confirmations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[str | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)
    method: Mapped[str] = mapped_column(String(30))  # simulated_registry | recruiter_attestation
    result: Mapped[str] = mapped_column(String(20))  # confirmed | denied | no_record
    detail: Mapped[str] = mapped_column(Text, default="")
    reference: Mapped[str] = mapped_column(String(200), default="")
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    recorded_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReferenceRequest(Base):
    """Recruiter asks a referee/HR contact to confirm employment through a one-time link."""
    __tablename__ = "reference_requests"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    reference_id: Mapped[str | None] = mapped_column(ForeignKey("references.id", ondelete="SET NULL"), nullable=True)
    employment_id: Mapped[str | None] = mapped_column(ForeignKey("employment.id", ondelete="SET NULL"), nullable=True)
    application_id: Mapped[str | None] = mapped_column(ForeignKey("applications.id", ondelete="SET NULL"), nullable=True)
    requested_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    referee_name: Mapped[str] = mapped_column(String(120))
    referee_contact: Mapped[str] = mapped_column(String(254), default="")
    company: Mapped[str] = mapped_column(String(160), default="")
    claimed_title: Mapped[str] = mapped_column(String(120), default="")
    claimed_start: Mapped[str] = mapped_column(String(7), default="")
    claimed_end: Mapped[str] = mapped_column(String(7), default="")
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="sent")  # sent | responded | expired | cancelled
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    response: Mapped[dict] = mapped_column(JSON, default=dict)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    simulated: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ============================================================================ Phase 5: fraud intelligence & scoring

class DeviceSighting(Base):
    """A candidate action seen from a browser/network. Only keyed hashes are stored (HMAC with the server secret);
    the raw browser ID and IP address are never saved. Shared devices/networks are weak signals, not proof."""
    __tablename__ = "device_sightings"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    device_hash: Mapped[str] = mapped_column(String(32), default="", index=True)
    network_hash: Mapped[str] = mapped_column(String(32), default="", index=True)
    action: Mapped[str] = mapped_column(String(30))  # register | login | apply
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PatternAlert(Base):
    """Output of a suspicious-pattern rule. Needs human review; never blocks anyone automatically."""
    __tablename__ = "pattern_alerts"
    __table_args__ = (UniqueConstraint("candidate_id", "rule_id", "evidence_key", name="uq_pattern_alert"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    rule_id: Mapped[str] = mapped_column(String(40))
    severity: Mapped[str] = mapped_column(String(10))  # info | warning
    strength: Mapped[str] = mapped_column(String(10))  # weak | medium
    evidence_key: Mapped[str] = mapped_column(String(80))
    evidence: Mapped[dict] = mapped_column(JSON, default=dict)
    first_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    review_status: Mapped[str] = mapped_column(String(20), default="open")  # open | reviewed_ok | confirmed
    review_note: Mapped[str] = mapped_column(Text, default="")
    reviewed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class CheckReview(Base):
    """A recruiter's resolution of a check-level concern (append-only; the latest row per check wins)."""
    __tablename__ = "check_reviews"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    check: Mapped[str] = mapped_column(String(30))  # identity | education | employment | resume
    status: Mapped[str] = mapped_column(String(20))  # resolved | upheld
    note: Mapped[str] = mapped_column(Text)
    evidence_run_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # concern key (document + findings) that was reviewed
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ScoringRuleset(Base):
    """Every version of the scoring rules ever used (append-only)."""
    __tablename__ = "scoring_rulesets"
    version: Mapped[str] = mapped_column(String(60), primary_key=True)
    rules: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ScoreRecord(Base):
    """One computed trust score with its full explanation (append-only score history)."""
    __tablename__ = "score_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    ruleset_version: Mapped[str] = mapped_column(ForeignKey("scoring_rulesets.version"))
    score: Mapped[int] = mapped_column(Integer)
    raw_score: Mapped[int] = mapped_column(Integer)
    breakdown: Mapped[dict] = mapped_column(JSON)
    fingerprint: Mapped[str] = mapped_column(String(64))
    trigger: Mapped[str] = mapped_column(String(40), default="")
    computed_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class ReportReview(Base):
    """'Marked reviewed' by a recruiter, tied to the exact score version they saw (append-only)."""
    __tablename__ = "report_reviews"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    score_record_id: Mapped[str | None] = mapped_column(ForeignKey("score_records.id", ondelete="SET NULL"), nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="")
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ================================================================== Phase 6: evidence chain, passports, per-organisation alert reviews


class EvidenceEvent(Base):
    """One link in a candidate's tamper-evident evidence chain (append-only; enforced by database triggers).

    payload_hash = SHA-256(canonical JSON payload); event_hash = HMAC-SHA256(server key, canonical header incl. prev_hash).
    Payloads hold ids, statuses and content hashes only: never document text, photos, embeddings or contact details."""
    __tablename__ = "evidence_events"
    __table_args__ = (UniqueConstraint("candidate_id", "seq", name="uq_evidence_seq"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(String(32), index=True)  # plain id: the chain outlives profile erasure
    seq: Mapped[int] = mapped_column(Integer)
    event_type: Mapped[str] = mapped_column(String(60))
    application_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    organization_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # set for organisation-specific events
    actor_role: Mapped[str] = mapped_column(String(20))  # candidate | recruiter | system | referee
    actor_ref: Mapped[str] = mapped_column(String(32), default="")
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    payload_hash: Mapped[str] = mapped_column(String(64))
    prev_hash: Mapped[str] = mapped_column(String(64))
    event_hash: Mapped[str] = mapped_column(String(64))
    key_id: Mapped[str] = mapped_column(String(16))
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PassportRecord(Base):
    """A signed, minimal TrustTrace QR passport for one application. Revocation/supersession updates status only."""
    __tablename__ = "passports"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    public_id: Mapped[str] = mapped_column(String(24), unique=True, index=True)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    application_id: Mapped[str] = mapped_column(ForeignKey("applications.id", ondelete="CASCADE"), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    issued_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    score_record_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    report_version: Mapped[str] = mapped_column(String(80))
    chain_seq: Mapped[int] = mapped_column(Integer, default=0)
    chain_hash: Mapped[str] = mapped_column(String(64), default="")
    claims: Mapped[dict] = mapped_column(JSON, default=dict)
    token: Mapped[str] = mapped_column(Text)
    key_id: Mapped[str] = mapped_column(String(16))
    issued_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)
    status: Mapped[str] = mapped_column(String(20), default="active")  # active | revoked | superseded
    status_reason: Mapped[str] = mapped_column(Text, default="")
    status_changed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status_changed_by: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class AlertReview(Base):
    """A recruiter's review of a duplicate or pattern alert, scoped to their organisation (append-only; latest per org wins).
    One organisation's judgement never changes another organisation's view or score."""
    __tablename__ = "alert_reviews"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    alert_kind: Mapped[str] = mapped_column(String(20))  # duplicate | pattern
    alert_id: Mapped[str] = mapped_column(String(32), index=True)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30))  # duplicate: open|not_duplicate|confirmed_duplicate · pattern: open|reviewed_ok|confirmed
    note: Mapped[str] = mapped_column(Text, default="")
    reviewer_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


# ================================================================== DigiLocker comparison (live partner API or clearly-labelled simulation)


class DigiLockerLink(Base):
    """One DigiLocker consent session: PKCE state, a short-lived encrypted access token and the issued-documents list
    (metadata only). Deleted when the candidate disconnects."""
    __tablename__ = "digilocker_links"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(12))  # live | simulated
    state: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    code_verifier_enc: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | connected | denied | failed
    access_token_enc: Mapped[str] = mapped_column(Text, default="")
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    issued: Mapped[list] = mapped_column(JSON, default=list)
    account_name: Mapped[str] = mapped_column(String(200), default="")  # name on the DigiLocker account, for comparison
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class DigiLockerDocument(Base):
    """An education document pulled from DigiLocker (issuer-issued) and the fields read from it."""
    __tablename__ = "digilocker_documents"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    candidate_id: Mapped[str] = mapped_column(ForeignKey("candidates.id", ondelete="CASCADE"), index=True)
    mode: Mapped[str] = mapped_column(String(12))  # live | simulated
    uri: Mapped[str] = mapped_column(String(300))
    doctype: Mapped[str] = mapped_column(String(60), default="")
    title: Mapped[str] = mapped_column(String(200), default="")
    issuer: Mapped[str] = mapped_column(String(200), default="")
    issuer_id: Mapped[str] = mapped_column(String(80), default="")
    issued_on: Mapped[str] = mapped_column(String(20), default="")
    mime: Mapped[str] = mapped_column(String(60), default="")
    storage_name: Mapped[str] = mapped_column(String(64), default="")
    sha256: Mapped[str] = mapped_column(String(64), default="")
    hmac_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    fields: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class DigiLockerSimRecord(Base):
    """SIMULATED DigiLocker records for demos/tests (manage.py load-digilocker-records). Never counted as verification."""
    __tablename__ = "digilocker_sim_records"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    mobile: Mapped[str] = mapped_column(String(20), default="", index=True)
    holder_name: Mapped[str] = mapped_column(String(160))
    doctype: Mapped[str] = mapped_column(String(60), default="MARKSHEET")
    title: Mapped[str] = mapped_column(String(200), default="")
    issuer: Mapped[str] = mapped_column(String(200))
    register_number: Mapped[str] = mapped_column(String(60), default="")
    degree: Mapped[str] = mapped_column(String(160), default="")
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cgpa: Mapped[str] = mapped_column(String(20), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
