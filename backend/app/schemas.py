"""Request/response schemas. JSON uses camelCase to match the frontend types in frontend/src/api/types.ts."""
from __future__ import annotations

import re
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pydantic.alias_generators import to_camel

EMAIL_RE = re.compile(r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+$")
MOBILE_RE = re.compile(r"^[6-9][0-9]{9}$")
URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.I)
YEAR_RE = re.compile(r"^(19[7-9][0-9]|20[0-3][0-9])$")
MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


class Camel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, str_strip_whitespace=True)


def _email(v: str) -> str:
    v = v.strip().lower()
    if len(v) > 254 or not EMAIL_RE.match(v):
        raise ValueError("Enter a valid email address")
    return v


def _password(v: str) -> str:
    if len(v) < 8 or not re.search(r"[A-Z]", v) or not re.search(r"[0-9]", v):
        raise ValueError("Password needs at least 8 characters, an uppercase letter and a number")
    if len(v) > 128:
        raise ValueError("Password is too long")
    return v


def _url(v: str) -> str:
    if v and not URL_RE.match(v):
        raise ValueError("Enter a full URL starting with https://")
    return v


# ---------------------------------------------------------------- auth

Role = Literal["candidate", "recruiter"]


class LoginIn(Camel):
    role: Role
    email: str
    password: str = Field(min_length=1, max_length=128)
    _e = field_validator("email")(_email)


class SessionUserOut(Camel):
    id: str
    role: Role
    full_name: str
    email: str
    organisation: str | None = None
    organisation_status: str | None = None
    avatar_url: str | None = None


class TokenOut(Camel):
    token: str
    user: SessionUserOut


class RecruiterRegisterIn(Camel):
    full_name: str = Field(min_length=3, max_length=120)
    organisation: str = Field(min_length=2, max_length=160)
    email: str
    phone: str = Field(pattern=r"^\+?[0-9 ]{10,15}$")
    company_size: Literal["1-50", "51-200", "201-1000", "1000+"]
    password: str
    _e = field_validator("email")(_email)
    _p = field_validator("password")(_password)


class OtpIn(Camel):
    phone: str

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        if not MOBILE_RE.match(v):
            raise ValueError("Enter a 10-digit Indian mobile number")
        return v


# ---------------------------------------------------------------- candidate profile parts

class EducationIn(Camel):
    degree: str = Field(min_length=2, max_length=120)
    institution: str = Field(min_length=2, max_length=160)
    start_year: str
    end_year: str
    score: str = Field(default="", max_length=20)

    @model_validator(mode="after")
    def _years(self):
        if not YEAR_RE.match(self.start_year) or not YEAR_RE.match(self.end_year):
            raise ValueError("Education years must look like 2021")
        if int(self.end_year) < int(self.start_year):
            raise ValueError("Education ends before it starts")
        return self


class ExperienceIn(Camel):
    company: str = Field(min_length=2, max_length=160)
    title: str = Field(min_length=2, max_length=120)
    start: str
    end: str = ""
    current: bool = False

    @model_validator(mode="after")
    def _months(self):
        if not MONTH_RE.match(self.start):
            raise ValueError("Experience start must be a month like 2023-06")
        if self.current:
            self.end = ""
        elif not MONTH_RE.match(self.end):
            raise ValueError("Experience needs an end month, or mark it as current")
        elif self.end < self.start:
            raise ValueError("Experience ends before it starts")
        return self


class ReferenceIn(Camel):
    name: str = Field(min_length=2, max_length=120)
    relationship: str = Field(min_length=2, max_length=80)
    company: str = Field(default="", max_length=160)
    email: str = ""
    phone: str = ""

    @model_validator(mode="after")
    def _contact(self):
        if self.email:
            self.email = _email(self.email)
        if self.phone and not re.match(r"^\+?[0-9 ]{10,15}$", self.phone):
            raise ValueError("Reference phone number is not valid")
        if not self.email and not self.phone:
            raise ValueError("Give an email or phone number for each reference")
        return self


class CandidateRegisterIn(Camel):
    full_name: str = Field(min_length=3, max_length=120)
    email: str
    phone: str
    otp: str = Field(pattern=r"^[0-9]{6}$")
    date_of_birth: date
    password: str
    education: list[EducationIn] = Field(min_length=1, max_length=10)
    experience: list[ExperienceIn] = Field(default_factory=list, max_length=20)
    selfie: str
    consent: bool = False
    consent_biometric: bool | None = None
    consent_documents: bool | None = None
    _e = field_validator("email")(_email)
    _p = field_validator("password")(_password)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        if not MOBILE_RE.match(v):
            raise ValueError("Enter a 10-digit Indian mobile number")
        return v

    @field_validator("date_of_birth")
    @classmethod
    def _dob(cls, v: date) -> date:
        age = (date.today() - v).days / 365.25
        if age < 16 or age > 80:
            raise ValueError("You must be at least 16 years old")
        return v

    @model_validator(mode="after")
    def _consent(self):
        bio = self.consent if self.consent_biometric is None else self.consent_biometric
        docs = self.consent if self.consent_documents is None else self.consent_documents
        if not (bio and docs):
            raise ValueError("Consent to biometric and document processing is required")
        self.consent_biometric, self.consent_documents = True, True
        return self


class ProfileUpdateIn(Camel):
    full_name: str = Field(min_length=3, max_length=120)
    email: str
    phone: str
    location: str = Field(min_length=2, max_length=120)
    headline: str = Field(min_length=3, max_length=80)
    linkedin_url: str = ""
    github_url: str = ""
    skills: list[str] = Field(default_factory=list, max_length=20)
    education: list[EducationIn] | None = Field(default=None, max_length=10)
    experience: list[ExperienceIn] | None = Field(default=None, max_length=20)
    references: list[ReferenceIn] | None = Field(default=None, max_length=5)
    _e = field_validator("email")(_email)
    _l = field_validator("linkedin_url", "github_url")(_url)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        if not MOBILE_RE.match(v):
            raise ValueError("Enter a 10-digit Indian mobile number")
        return v

    @field_validator("skills")
    @classmethod
    def _skills(cls, v: list[str]) -> list[str]:
        out: list[str] = []
        for s in v:
            s = s.strip()[:40]
            if s and s.lower() not in {x.lower() for x in out}:
                out.append(s)
        return out


# ---------------------------------------------------------------- jobs

EmploymentType = Literal["full_time", "part_time", "internship", "contract"]
WorkMode = Literal["onsite", "remote", "hybrid"]


class JobIn(Camel):
    title: str = Field(min_length=3, max_length=120)
    department: str | None = Field(default=None, max_length=120)
    location: str = Field(min_length=2, max_length=120)
    employment_type: EmploymentType
    work_mode: WorkMode
    experience_min: int = Field(ge=0, le=40)
    experience_max: int = Field(ge=0, le=40)
    salary_min: int | None = Field(default=None, ge=0)
    salary_max: int | None = Field(default=None, ge=0)
    skills: list[str] = Field(min_length=1, max_length=30)
    description: str = Field(min_length=30, max_length=10000)
    requirements: str = Field(default="", max_length=5000)
    assessments: list[str] = Field(default_factory=list, max_length=10)
    deadline: date | None = None
    status: Literal["draft", "open", "closed"] = "open"

    @model_validator(mode="after")
    def _ranges(self):
        if self.experience_max < self.experience_min:
            raise ValueError("Maximum experience must be at least the minimum")
        if self.salary_min is not None and self.salary_max is not None and self.salary_max < self.salary_min:
            raise ValueError("Maximum salary must be at least the minimum")
        self.skills = [s.strip()[:40] for s in self.skills if s.strip()]
        if not self.skills:
            raise ValueError("Add at least one skill")
        return self


class StatusChangeIn(Camel):
    status: Literal["shortlisted", "clarification", "assessment", "interview", "offer", "hired", "rejected", "resume_review", "verification"]
    note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def _note(self):
        if self.status in ("clarification", "rejected") and len(self.note) < 10:
            raise ValueError("Write a message of at least 10 characters for the candidate")
        return self


class DecisionIn(Camel):
    decision: Literal["approve", "reject", "reverify"]
    reason: str = Field(min_length=10, max_length=2000)


class InterviewIn(Camel):
    application_id: str
    scheduled_at: datetime
    duration_minutes: int = Field(ge=15, le=180)
    mode: Literal["video", "onsite"]
    interviewer: str = Field(min_length=2, max_length=120)
    meeting_link: str | None = None
    _l = field_validator("meeting_link")(lambda v: _url(v or "") or None)


class SettingsIn(Camel):
    organisation: str = Field(min_length=2, max_length=160)
    website: str = ""
    retention_days: int = Field(ge=30, le=730)
    notify_on_flag: bool
    notify_daily_digest: bool
    _l = field_validator("website")(_url)


class AssessmentSubmitIn(Camel):
    answers: dict[str, str]
    tab_switches: int = Field(ge=0)
    copy_paste: int = Field(ge=0)
    duration_seconds: int = Field(ge=0)
