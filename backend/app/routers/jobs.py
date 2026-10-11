"""Job browsing and applying (candidates)."""
from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import String, cast, or_
from sqlalchemy.exc import IntegrityError

from .. import activity, serialize
from ..evidence import chain as evidence
from ..deps import CurrentCandidate, Db, Paging, paginate
from ..errors import ApiError, conflict, not_found
from ..fraud import devices, patterns, scoring
from ..models import Application, ApplicationEvent, Job, Organization

router = APIRouter(prefix="/jobs", tags=["jobs"])


def visible_jobs(db):
    """Jobs candidates may see: open, from an approved organisation, deadline not passed."""
    return (db.query(Job).join(Organization).filter(Job.status == "open", Organization.status == "approved")
            .filter(or_(Job.deadline.is_(None), Job.deadline >= date.today())).order_by(Job.created_at.desc()))


@router.get("", summary="Browse open jobs")
def list_jobs(cand: CurrentCandidate, db: Db, page: Paging, response: Response,
              search: Annotated[str | None, Query(max_length=100)] = None, location: Annotated[str | None, Query(max_length=100)] = None,
              type: Annotated[str | None, Query(pattern="^(full_time|part_time|internship|contract)$")] = None,  # noqa: A002
              mode: Annotated[str | None, Query(pattern="^(onsite|remote|hybrid)$")] = None):
    q = visible_jobs(db)
    if search:
        like = f"%{search.strip()}%"
        q = q.filter(or_(Job.title.ilike(like), Organization.name.ilike(like), Job.description.ilike(like), cast(Job.skills, String).ilike(like)))
    if location:
        q = q.filter(Job.location.ilike(f"%{location.strip()}%"))
    if type:
        q = q.filter(Job.employment_type == type)
    if mode:
        q = q.filter(Job.work_mode == mode)
    applied = {a.job_id for a in db.query(Application.job_id).filter_by(candidate_id=cand.id)}
    return [serialize.job(j, applied=j.id in applied) for j in paginate(q, page, response)]


@router.get("/{job_id}")
def get_job(job_id: str, cand: CurrentCandidate, db: Db):
    j = visible_jobs(db).filter(Job.id == job_id).one_or_none()
    if not j:
        raise not_found("Job")
    applied = db.query(Application).filter_by(candidate_id=cand.id, job_id=j.id).first() is not None
    return serialize.job(j, applied=applied)


@router.post("/{job_id}/apply", status_code=201, summary="Apply to a job (one application per job)")
def apply(job_id: str, cand: CurrentCandidate, db: Db, request: Request):
    j = visible_jobs(db).filter(Job.id == job_id).one_or_none()
    if not j:
        raise not_found("Job")
    existing = db.query(Application).filter_by(candidate_id=cand.id, job_id=j.id).first()
    if existing:
        # logged so repeated submissions can be spotted (pattern P2), then refused
        activity.log(db, cand.user_id, "application.duplicate_attempt", "job", j.id)
        db.flush()
        patterns.scan(db, cand)
        scoring.refresh_candidate(db, cand.id, "duplicate_attempt")
        db.commit()
        raise ApiError(409, "already_applied", "You have already applied to this job.")
    a = Application(candidate_id=cand.id, job_id=j.id, status="applied")
    db.add(a)
    try:
        db.flush()
    except IntegrityError as exc:  # two clicks racing each other
        db.rollback()
        raise conflict("You have already applied to this job.", "already_applied") from exc
    db.add(ApplicationEvent(application_id=a.id, status="applied", actor_id=cand.user_id))
    db.flush()
    from ..skills import service as skill_service
    skill_service.assign(db, a, None)  # the job's published assessment, if any
    devices.record(db, request, cand.id, "apply")
    db.flush()
    patterns.scan(db, cand)
    scoring.refresh_candidate(db, cand.id, "application_created")
    activity.log(db, cand.user_id, "application.created", "application", a.id, job=j.id)
    evidence.record(db, cand.id, "application.submitted", actor_role="candidate", actor_ref=cand.user_id, application_id=a.id,
                    organization_id=j.organization_id, jobId=j.id, jobTitle=j.title)
    db.commit()
    db.refresh(a)
    return serialize.application(a)
