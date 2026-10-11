"""Admin commands. Run from the project folder:

    python backend/manage.py init-db            create/upgrade the database (safe to run repeatedly, seeds nothing)
    python backend/manage.py list-orgs          show recruiter organisations and their approval status
    python backend/manage.py approve-org EMAIL  approve the organisation of the recruiter with this email
    python backend/manage.py suspend-org EMAIL  suspend it again (its jobs disappear from candidates)
    python backend/manage.py doctor             check PyMuPDF, OCR, face models and Gemini configuration
    python backend/manage.py run-verification EMAIL   re-run all checks for one candidate now
    python backend/manage.py load-issuer-records FILE.csv   load SIMULATED issuer records (hackathon testing only)
    python backend/manage.py purge-extractions DAYS   delete stored document extractions older than DAYS days
    python backend/manage.py delete-biometrics EMAIL  delete a candidate's face enrolment and face-check history
    python backend/manage.py purge-assessment-events DAYS   delete integrity events of attempts submitted more than DAYS days ago
    python backend/manage.py verify-chain EMAIL       check a candidate's evidence chain and list any tampering found
    python backend/manage.py erase-candidate EMAIL --yes   erase a candidate's personal data and files (right to erasure)
    python backend/manage.py make-sample-docs "Full Name" FOLDER   generate sample resume/marksheet/experience letter for any name
    python backend/manage.py load-digilocker-records FILE.csv   load SIMULATED DigiLocker records (demo/testing only)
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def init_db() -> None:
    from alembic import command
    from alembic.config import Config

    from app.config import DATA_DIR, UPLOAD_DIR

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    here = Path(__file__).resolve().parent
    cfg = Config(str(here / "alembic.ini"))
    cfg.set_main_option("script_location", str(here / "migrations"))
    command.upgrade(cfg, "head")


def _set_org(email: str, status: str) -> None:
    from app.db import SessionLocal
    from app.models import User, utcnow

    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email.strip().lower(), role="recruiter").one_or_none()
        if not user or not user.organization:
            sys.exit(f"No recruiter account with email {email}")
        org = user.organization
        org.status = status
        org.approved_at = utcnow() if status == "approved" else org.approved_at
        db.commit()
        print(f"{org.name}: {status}")


def list_orgs() -> None:
    from app.db import SessionLocal
    from app.models import Organization

    with SessionLocal() as db:
        orgs = db.query(Organization).order_by(Organization.created_at).all()
        if not orgs:
            print("No organisations yet.")
        for o in orgs:
            owner = o.members[0].email if o.members else "-"
            print(f"{o.status:<10} {o.name:<40} {owner}")


def doctor() -> None:
    from app.verification import face, gemini, textract

    print("PyMuPDF:     ", "OK" if textract.pymupdf() else "MISSING  -> pip install pymupdf")
    print("OCR:         ", "OK (Tesseract)" if textract.ocr_available() else "not installed (optional; scanned PDFs/photos will need review)")
    ok, why = face.available()
    print("Face models: ", "OK (YuNet + SFace)" if ok else f"UNAVAILABLE -> {why}")
    print("Gemini:      ", "enabled (GEMINI_API_KEY set)" if gemini.enabled() else "disabled (optional)")


def run_verification(email: str) -> None:
    import os
    os.environ["TT_VERIFICATION_SYNC"] = "1"
    from app.db import SessionLocal
    from app.models import Candidate, User
    from app.verification import queue

    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email.strip().lower(), role="candidate").one_or_none()
        if not user:
            sys.exit(f"No candidate account with email {email}")
        cand = db.query(Candidate).filter_by(user_id=user.id).one()
        job = queue.enqueue(db, cand.id, None, "admin")
        print(f"Verification job {job.id}: {job.status} {job.error or ''}")


def load_issuer_records(path: str) -> None:
    """CSV columns: issuer,register_number,student_name,qualification,year. Every row is stored as SIMULATED."""
    import csv
    from app.db import SessionLocal
    from app.models import IssuerRecord

    with open(path, newline="", encoding="utf-8") as fh, SessionLocal() as db:
        n = 0
        for row in csv.DictReader(fh):
            db.add(IssuerRecord(issuer=row["issuer"].strip(), register_number=row["register_number"].strip().upper(), student_name=row["student_name"].strip(),
                                qualification=row.get("qualification", "").strip(), year=int(row["year"]) if row.get("year") else None, simulated=True))
            n += 1
        db.commit()
    print(f"Loaded {n} SIMULATED issuer records (for testing only).")


def purge_extractions(days: int) -> None:
    from datetime import timedelta
    from app.db import SessionLocal
    from app.models import DocumentExtraction, utcnow

    with SessionLocal() as db:
        n = db.query(DocumentExtraction).filter(DocumentExtraction.created_at < utcnow() - timedelta(days=days)).delete()
        db.commit()
    print(f"Deleted {n} document extraction(s).")


def purge_assessment_events(days: int) -> None:
    from datetime import timedelta
    from app.db import SessionLocal
    from app.models import Assessment, AssessmentEvent, utcnow

    with SessionLocal() as db:
        old = [a.id for a in db.query(Assessment.id).filter(Assessment.submitted_at < utcnow() - timedelta(days=days))]
        n = db.query(AssessmentEvent).filter(AssessmentEvent.assessment_id.in_(old)).delete(synchronize_session=False) if old else 0
        db.commit()
    print(f"Deleted {n} assessment event(s). Scores and answers are kept.")


def delete_biometrics(email: str) -> None:
    from app.db import SessionLocal
    from app.models import Candidate, FaceCheck, FaceEnrollment, User

    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email.strip().lower(), role="candidate").one_or_none()
        if not user:
            sys.exit(f"No candidate account with email {email}")
        cand = db.query(Candidate).filter_by(user_id=user.id).one()
        a = db.query(FaceEnrollment).filter_by(candidate_id=cand.id).delete()
        b = db.query(FaceCheck).filter_by(candidate_id=cand.id).delete()
        db.commit()
    print(f"Deleted {a} face enrolment(s) and {b} face check(s).")


def load_digilocker_records(path: str) -> None:
    """CSV columns: mobile (optional; else matched by name), holder_name, issuer, doctype, title, register_number, degree, year, cgpa."""
    import csv

    from app.db import SessionLocal
    from app.models import DigiLockerSimRecord

    n = 0
    with open(path, newline="", encoding="utf-8-sig") as fh, SessionLocal() as db:
        for row in csv.DictReader(fh):
            row = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
            if not row.get("holder_name") or not row.get("issuer"):
                continue
            db.add(DigiLockerSimRecord(mobile=row.get("mobile", ""), holder_name=row["holder_name"], issuer=row["issuer"],
                                       doctype=row.get("doctype") or "MARKSHEET", title=row.get("title", ""),
                                       register_number=row.get("register_number", ""), degree=row.get("degree", ""),
                                       year=int(row["year"]) if row.get("year", "").isdigit() else None, cgpa=row.get("cgpa", "")))
            n += 1
        db.commit()
    print(f"Loaded {n} SIMULATED DigiLocker record(s). They are labelled SIMULATED everywhere and never count as verification.")


def verify_chain(email: str) -> None:
    from app.db import SessionLocal
    from app.evidence import chain
    from app.models import Candidate, PassportRecord, User

    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email.strip().lower(), role="candidate").one_or_none()
        if not user:
            sys.exit(f"No candidate account with email {email}")
        cand = db.query(Candidate).filter_by(user_id=user.id).one()
        anchors = [(p.chain_seq, p.chain_hash, f"passport {p.public_id}") for p in db.query(PassportRecord).filter_by(candidate_id=cand.id)]
        v = chain.verify(db, cand.id, anchors=anchors)
    print(f"Events: {v['events']}  ·  key {v['keyId']}  ·  {'INTACT' if v['intact'] else 'PROBLEMS FOUND'}")
    for p in v["problems"]:
        print(f"  #{p['seq']}: {p['reason']} – {p['detail']}")


def erase_candidate(email: str) -> None:
    """Right to erasure: removes personal data, uploaded files and biometric data. Applications stay (status only, shown as
    'Erased candidate'); append-only audit rows keep only ids, statuses and hashes, which is why they can stay."""
    import secrets as _s

    from app import storage
    from app.db import SessionLocal
    from app.evidence import passport
    from app.models import (AuthSession, Candidate, DeviceSighting, DocumentExtraction, Education, Employment, FaceCheck, FaceEnrollment,
                            Finding, Message, PassportRecord, Reference, User, VerificationRun, utcnow)
    from app.security import hash_secret

    with SessionLocal() as db:
        user = db.query(User).filter_by(email=email.strip().lower(), role="candidate").one_or_none()
        if not user:
            sys.exit(f"No candidate account with email {email}")
        cand = db.query(Candidate).filter_by(user_id=user.id).one()
        files = 0
        for d in cand.documents:
            storage.delete(d.storage_name)
            d.original_name, files = "erased", files + 1
        doc_ids = [d.id for d in cand.documents]
        if doc_ids:
            db.query(DocumentExtraction).filter(DocumentExtraction.document_id.in_(doc_ids)).delete(synchronize_session=False)
        from app.verification import digilocker as dlk
        dlk.disconnect(db, cand.id)
        for model in (FaceEnrollment, FaceCheck, DeviceSighting, Education, Employment, Reference):
            db.query(model).filter_by(candidate_id=cand.id).delete()
        for run in db.query(VerificationRun).filter_by(candidate_id=cand.id):
            run.result, run.detail = {"summary": "Erased at the candidate's request."}, ""
        db.query(Finding).filter_by(candidate_id=cand.id).update({"detail": "", "evidence": {}})
        db.query(Message).filter_by(recipient_id=user.id).delete()
        for p in db.query(PassportRecord).filter_by(candidate_id=cand.id, status="active"):
            passport._set_status(db, p, "revoked", "The candidate's data was erased.", None)
        cand.location = cand.headline = cand.linkedin_url = cand.github_url = ""
        cand.skills, cand.date_of_birth = [], None
        user.full_name, user.email, user.phone = "Erased candidate", f"erased-{user.id[:12]}@invalid.example", ""
        user.password_hash, user.is_active = hash_secret(_s.token_urlsafe(32)), False
        db.query(AuthSession).filter_by(user_id=user.id).update({"revoked_at": utcnow()})
        db.commit()
    print(f"Erased personal data for that account: {files} file(s) deleted, biometric and extracted data removed, sign-in disabled.")


if __name__ == "__main__":
    args = sys.argv[1:]
    if args[:1] == ["init-db"]:
        init_db()
        print("Database is up to date.")
    elif args[:1] == ["list-orgs"]:
        init_db()
        list_orgs()
    elif args[:1] == ["doctor"]:
        doctor()
    elif args[:1] == ["run-verification"] and len(args) == 2:
        init_db()
        run_verification(args[1])
    elif args[:1] == ["load-issuer-records"] and len(args) == 2:
        init_db()
        load_issuer_records(args[1])
    elif args[:1] == ["purge-extractions"] and len(args) == 2 and args[1].isdigit():
        init_db()
        purge_extractions(int(args[1]))
    elif args[:1] == ["purge-assessment-events"] and len(args) == 2 and args[1].isdigit():
        init_db()
        purge_assessment_events(int(args[1]))
    elif args[:1] == ["delete-biometrics"] and len(args) == 2:
        init_db()
        delete_biometrics(args[1])
    elif args[:1] == ["verify-chain"] and len(args) == 2:
        init_db()
        verify_chain(args[1])
    elif args[:1] == ["load-digilocker-records"] and len(args) == 2:
        init_db()
        load_digilocker_records(args[1])
    elif args[:1] == ["make-sample-docs"] and len(args) == 3:
        from app.demo_docs import write_set
        for p in write_set(args[1], args[2]):
            print("wrote", p)
        print("To demo DigiLocker (SIMULATED):  python backend/manage.py load-digilocker-records", str(Path(args[2]) / "digilocker_records.csv"))
        print("Profile to enter when registering: B.E. Computer Science and Engineering, Anna University, 2022-2026;"
              " work: Software Engineer Intern at Zoho Corporation Pvt Ltd, 2025-05 to 2025-07.")
    elif args[:1] == ["erase-candidate"] and len(args) == 3 and args[2] == "--yes":
        init_db()
        erase_candidate(args[1])
    elif args[:1] in (["approve-org"], ["suspend-org"]) and len(args) == 2:
        init_db()
        _set_org(args[1], "approved" if args[0] == "approve-org" else "suspended")
    else:
        print(__doc__)
        sys.exit(1)
