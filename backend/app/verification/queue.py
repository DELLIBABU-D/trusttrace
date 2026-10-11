"""Controlled job queue: one background worker thread processes verification jobs in order.

TT_VERIFICATION_SYNC=1 runs jobs immediately in the request (used by tests). Jobs left "queued" or "running" by a
previous server process are picked up again on start-up.
"""
from __future__ import annotations

import logging
import os
import queue as _queue
import threading

from ..db import SessionLocal
from ..models import VerificationJob, utcnow

log = logging.getLogger("trusttrace.verification")
_q: _queue.Queue[str] = _queue.Queue()
_worker: threading.Thread | None = None
_start_lock = threading.Lock()


def sync_mode() -> bool:
    return os.environ.get("TT_VERIFICATION_SYNC") == "1"


def _loop() -> None:
    from .pipeline import run_job

    while True:
        job_id = _q.get()
        try:
            with SessionLocal() as db:
                run_job(db, job_id)
        except Exception:  # noqa: BLE001
            log.exception("worker error")
        finally:
            _q.task_done()


def start() -> None:
    global _worker
    with _start_lock:
        if _worker and _worker.is_alive():
            return
        _worker = threading.Thread(target=_loop, name="verification-worker", daemon=True)
        _worker.start()
    with SessionLocal() as db:  # resume unfinished jobs
        for job in db.query(VerificationJob).filter(VerificationJob.status.in_(["queued", "running"])).order_by(VerificationJob.created_at):
            job.status = "queued"
            _q.put(job.id)
        db.commit()


def enqueue(db, candidate_id: str, requested_by: str | None, reason: str) -> VerificationJob:
    """Create a job unless one is already waiting for this candidate (repeated uploads collapse into one run)."""
    waiting = db.query(VerificationJob).filter_by(candidate_id=candidate_id, status="queued").first()
    if waiting:
        return waiting
    job = VerificationJob(candidate_id=candidate_id, requested_by=requested_by, reason=reason)
    db.add(job)
    db.commit()
    if sync_mode():
        from .pipeline import run_job
        with SessionLocal() as db2:
            run_job(db2, job.id)
        db.refresh(job)
    else:
        start()
        _q.put(job.id)
    return job


def wait_idle(timeout: float = 60) -> None:
    """Testing helper."""
    import time
    end = time.time() + timeout
    while _q.unfinished_tasks and time.time() < end:
        time.sleep(0.05)
