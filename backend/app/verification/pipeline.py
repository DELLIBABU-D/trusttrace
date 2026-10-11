"""Runs every check for one candidate and saves runs, findings, extractions, face results and duplicate alerts."""
from __future__ import annotations

import logging
import traceback
from datetime import date

from sqlalchemy.orm import Session

from .. import storage
from ..models import (Candidate, Document, DocumentExtraction, FaceCheck, FaceEnrollment, Finding as FindingRow, IssuerConfirmation, VerificationRun,
                      IssuerRecord, ReferenceRequest, VerificationJob, VerificationRun, utcnow)
from . import duplicates, face as facemod, fields as fx, gemini, textract
from .crypto import decrypt_embedding, encrypt_embedding
from .fields import name_similarity
from .rules import CheckResult, Finding, education_rules, employment_rules, resume_rules

log = logging.getLogger("trusttrace.verification")
PARSERS = {"resume": fx.parse_resume, "marksheet": fx.parse_marksheet, "education_certificate": fx.parse_marksheet,
           "experience_letter": fx.parse_experience_letter}
AI_KIND = {"resume": "resume", "marksheet": "marksheet", "education_certificate": "marksheet", "experience_letter": "experience_letter"}
AI_KEYS = {"resume": ("name", "phone"), "marksheet": ("name", "registerNumber", "institution", "year", "totalMarks", "cgpa", "percentage"),
           "experience_letter": ("name", "company", "designation", "joiningDate", "relievingDate")}
LABELS = {
    "name": "Name", "email": "Email", "phone": "Mobile", "registerNumber": "Register Number", "institution": "Board / University",
    "degree": "Degree", "year": "Year", "totalMarks": "Total Marks", "cgpa": "CGPA", "percentage": "Percentage", "company": "Company",
    "designation": "Designation", "joiningDate": "Joining Date", "relievingDate": "Relieving Date", "durationMonths": "Experience Duration (months)",
}


# ------------------------------------------------------------------------------------------- helpers

def profile_dict(c: Candidate) -> dict:
    return {
        "fullName": c.user.full_name, "phone": c.user.phone, "skills": list(c.skills or []),
        "education": [{"degree": e.degree, "institution": e.institution, "startYear": str(e.start_year), "endYear": str(e.end_year), "score": e.score}
                      for e in c.education],
        "experience": [{"id": e.id, "company": e.company, "title": e.title, "start": e.start_month, "end": e.end_month, "current": e.current}
                       for e in c.employment],
    }


def current_doc(c: Candidate, *kinds: str) -> Document | None:
    docs = [d for d in c.documents if d.replaced_by_id is None and d.kind in kinds]
    docs.sort(key=lambda d: (kinds.index(d.kind), -d.uploaded_at.timestamp()))
    return docs[0] if docs else None


def extraction_for(db: Session, doc: Document, profile: dict) -> DocumentExtraction:
    """Reuse the stored extraction while the file is unchanged; otherwise read the file again."""
    existing = (db.query(DocumentExtraction).filter_by(document_id=doc.id, document_sha256=doc.sha256)
                .order_by(DocumentExtraction.created_at.desc()).first())
    # reuse, unless it failed or was unreadable before OCR was installed (then read the file again)
    if existing and existing.status != "failed" and not (existing.status == "low_text" and textract.ocr_available()):
        # Field parsing depends on the profile (e.g. claimed names), so re-parse is cheap but text is not stored:
        # re-read only if the profile changed is unnecessary because comparison happens in rules, not here.
        return existing
    path = storage.path_for(doc.storage_name)
    if not path:
        row = DocumentExtraction(document_id=doc.id, document_sha256=doc.sha256, method="none", status="failed", error="The stored file is missing.")
        db.add(row)
        return row
    data = path.read_bytes()
    ext = textract.extract(data, doc.content_type)
    parsed: dict = {}
    if ext.text.strip():
        parsed = PARSERS[doc.kind](ext.text, ext.page_texts, profile)
        if gemini.enabled():
            parsed = gemini.merge(parsed, gemini.suggest(AI_KIND[doc.kind], ext.text), AI_KEYS[AI_KIND[doc.kind]])
    row = DocumentExtraction(document_id=doc.id, document_sha256=doc.sha256, method=ext.method + ("+gemini" if parsed.get("_aiAssisted") else ""),
                             status=ext.status, pages=ext.pages, text_chars=len(ext.text), fields=parsed, error=ext.error)
    db.add(row)
    db.flush()
    return row


def flat_extracted(fields: dict) -> list[dict]:
    rows = []
    for key, label in LABELS.items():
        f = fields.get(key)
        if isinstance(f, dict) and "value" in f:
            rows.append({"label": label, "value": None if f["value"] is None else str(f["value"]), "confidence": f.get("confidence"),
                         "page": f.get("page"), "snippet": f.get("snippet"), "source": f.get("source")})
    return rows


def avg_confidence(fields: dict) -> int | None:
    vals = [f["confidence"] for f in fields.values() if isinstance(f, dict) and "confidence" in f and f.get("value") not in (None, "", [])]
    return round(100 * sum(vals) / len(vals)) if vals else None


STATUS_FROM_CONSISTENCY = {"consistent": "consistent", "partially_consistent": "consistent", "inconsistent": "inconsistent",
                           "needs_review": "needs_review", "insufficient_data": "needs_review"}


def save_run(db: Session, cand: Candidate, job: VerificationJob, check: str, status: str, result: dict, detail: str,
             findings: list[Finding], doc: Document | None = None, error: str = "") -> VerificationRun:
    run = VerificationRun(candidate_id=cand.id, check=check, document_id=doc.id if doc else None, status=status, job_id=job.id,
                          result=result, detail=detail, error=error, finished_at=utcnow())
    db.add(run)
    db.flush()
    for f in findings:
        db.add(FindingRow(run_id=run.id, candidate_id=cand.id, code=f.code, severity=f.severity, title=f.title, detail=f.detail,
                          points=0, evidence=f.evidence))
    _record_result(db, cand, check, run, result, findings, doc)
    return run


def _record_result(db: Session, cand: Candidate, check: str, run: VerificationRun, result: dict, findings: list[Finding], doc: Document | None) -> None:
    """Evidence-chain entry for a verification outcome. Re-runs with the same outcome are not repeated."""
    from ..evidence import chain as evidence
    from ..models import EvidenceEvent
    payload = {"check": check, "status": run.status, "documentId": doc.id if doc else None, "documentSha256": doc.sha256 if doc else None,
               "findingCodes": sorted({f.code for f in findings}), "consistency": result.get("consistency"),
               "idDocument": (result.get("idDocument") or {}).get("status") if check == "identity" else None,
               "issuer": {"status": (result.get("issuer") or {}).get("status"), "simulated": bool((result.get("issuer") or {}).get("simulated"))}
               if check == "education" and result.get("issuer") else None,
               "digilocker": {"status": result["digilocker"]["status"], "simulated": result["digilocker"].get("simulated")}
               if check == "education" and (result.get("digilocker") or {}).get("status") not in (None, "off", "not_connected") else None}
    digest = evidence.sha256(evidence.canonical(evidence._clean(payload)))
    recent = (db.query(EvidenceEvent).filter_by(candidate_id=cand.id, event_type="verification.result")
              .order_by(EvidenceEvent.seq.desc()).limit(40).all())
    last = next((e for e in recent if e.payload.get("check") == check), None)
    if last and last.payload.get("digest") == digest:
        return
    evidence.record(db, cand.id, "verification.result", actor_role="system", runId=run.id, digest=digest, **payload)


def result_payload(doc: Document | None, ext: DocumentExtraction | None, r: CheckResult, summary: str, **extra) -> dict:
    out = {
        "documentId": doc.id if doc else None,
        "extracted": flat_extracted(ext.fields) if ext else [],
        "confidence": avg_confidence(ext.fields) if ext else None,
        "comparison": r.comparison,
        "matchScore": r.match_score,
        "summary": summary,
        "consistency": r.consistency,
        "findings": [{"code": f.code, "severity": f.severity, "title": f.title, "detail": f.detail, "evidence": f.evidence} for f in r.findings],
        "extraction": {"method": ext.method, "status": ext.status, "error": ext.error, "pages": ext.pages} if ext else None,
    }
    out.update(extra)
    return out


def _summary(r: CheckResult, what: str) -> str:
    c = r.consistency
    if c == "inconsistent":
        n = sum(1 for x in r.comparison if x["match"] is False) + sum(1 for f in r.findings if f.severity == "critical")
        return f"{n} conflict{'s' if n != 1 else ''} found between the {what} and the profile. A person should review the evidence."
    if c == "needs_review":
        return f"The {what} mostly agrees with the profile, but some points need a person to check."
    if c == "insufficient_data":
        return f"Not enough could be read from the {what} to compare it."
    if c == "partially_consistent":
        return f"Fields that could be read from the {what} match the profile; some could not be checked."
    return f"The {what} matches the profile."


def _extraction_problem(ext: DocumentExtraction) -> str | None:
    if ext.status == "failed":
        return ext.error or "The document could not be read."
    if ext.status == "low_text":
        return ext.error or "Very little text could be read from this document (it may be a scan or photo)."
    return None


# ------------------------------------------------------------------------------------------- checks

def check_resume(db, cand, job, profile, dob, consent_docs) -> dict | None:
    doc = current_doc(cand, "resume")
    if not doc:
        r = resume_rules(None, profile, None, dob)
        status = "inconsistent" if any(f.severity == "critical" for f in r.findings) else "not_started"
        save_run(db, cand, job, "resume", status, result_payload(None, None, r, "No resume uploaded yet."), "No resume uploaded yet.", r.findings)
        return None
    if not consent_docs:
        save_run(db, cand, job, "resume", "not_started", {"summary": "Document processing consent is not given."}, "Consent required", [], doc)
        return None
    ext = extraction_for(db, doc, profile)
    problem = _extraction_problem(ext)
    resume_fields = ext.fields if ext.fields else None
    r = resume_rules(resume_fields, profile, doc.id, dob)
    if problem and not resume_fields:
        save_run(db, cand, job, "resume", "needs_review", result_payload(doc, ext, r, problem), problem, r.findings, doc, error=problem)
        return None
    status = STATUS_FROM_CONSISTENCY[r.consistency]
    summary = _summary(r, "resume") + (f" Note: {problem}" if problem else "")
    save_run(db, cand, job, "resume", status, result_payload(doc, ext, r, summary), summary, r.findings, doc)
    return resume_fields


def issuer_status(db: Session, cand: Candidate, doc: Document | None, fields: dict | None, actor_job: VerificationJob) -> dict:
    """Issuer authenticity is separate from document consistency. Matching fields never make a certificate genuine."""
    conf = (db.query(IssuerConfirmation).filter_by(candidate_id=cand.id, method="recruiter_attestation")
            .order_by(IssuerConfirmation.at.desc()).first())
    if conf:
        return {"status": conf.result, "method": conf.method, "simulated": False, "detail": conf.detail, "reference": conf.reference,
                "at": conf.at.isoformat() + "Z", "label": {"confirmed": "Confirmed by issuer (recorded by recruiter)",
                                                           "denied": "Issuer says this record is not genuine",
                                                           "no_record": "Issuer has no matching record"}[conf.result]}
    reg = (fields or {}).get("registerNumber", {}).get("value") if fields else None
    if reg and db.query(IssuerRecord).count():
        rec = db.query(IssuerRecord).filter(IssuerRecord.register_number == str(reg).upper()).first()
        if rec:
            ok = name_similarity(rec.student_name, cand.user.full_name) >= 0.8
            year = (fields.get("year") or {}).get("value")
            ok = ok and (rec.year is None or year is None or int(year) == rec.year)
            result = "confirmed" if ok else "denied"
            detail = f"{rec.issuer}: register {rec.register_number}, {rec.student_name}, {rec.year or ''}"
        else:
            result, detail = "no_record", f"No simulated issuer record for register number {reg}."
        db.add(IssuerConfirmation(candidate_id=cand.id, document_id=doc.id if doc else None, method="simulated_registry", result=result,
                                  detail=detail, simulated=True))
        label = {"confirmed": "SIMULATED registry: record found and matches", "denied": "SIMULATED registry: record found but details differ",
                 "no_record": "SIMULATED registry: no record found"}[result]
        return {"status": result, "method": "simulated_registry", "simulated": True, "detail": detail, "label": label}
    return {"status": "not_checked", "method": None, "simulated": False,
            "label": "Not checked with the issuer. Matching fields do not prove the certificate is genuine."}


def check_education(db, cand, job, profile, resume_fields, consent_docs) -> None:
    doc = current_doc(cand, "marksheet", "education_certificate")
    if not doc:
        save_run(db, cand, job, "education", "not_started", {"summary": "No marksheet or certificate uploaded yet.",
                                                              "issuer": {"status": "not_checked", "label": "No document to check"}},
                 "No marksheet uploaded yet.", [])
        return
    if not consent_docs:
        save_run(db, cand, job, "education", "not_started", {"summary": "Document processing consent is not given."}, "Consent required", [], doc)
        return
    ext = extraction_for(db, doc, profile)
    problem = _extraction_problem(ext)
    r = education_rules(ext.fields or None, profile, resume_fields, doc.id)
    other = current_doc(cand, "education_certificate") if doc.kind == "marksheet" else None
    if other:  # a second education document adds its findings too
        ext2 = extraction_for(db, other, profile)
        r2 = education_rules(ext2.fields or None, profile, resume_fields, other.id)
        r.findings.extend(r2.findings)
        r.comparison.extend({**c, "field": f"Certificate: {c['field']}"} for c in r2.comparison)
    issuer = issuer_status(db, cand, doc, ext.fields, job)
    status = STATUS_FROM_CONSISTENCY[r.consistency] if ext.fields else "needs_review"
    if issuer["status"] == "denied" and not issuer.get("simulated"):
        status = "inconsistent"
        r.findings.append(Finding("issuer_denied", "critical", "Issuer did not confirm this certificate", issuer.get("detail", "")))
    elif issuer["status"] == "confirmed" and not issuer.get("simulated") and status == "consistent":
        status = "verified"
    # DigiLocker: the issuer's own copy, pulled with the candidate's consent, compared field by field
    from ..config import digilocker_mode
    from . import digilocker as dlk
    dl = dlk.compare(ext.fields or None, dlk.current_document(db, cand.id)) if digilocker_mode() != "off" else {"status": "off"}
    if dl["status"] == "mismatch":
        r.findings.append(Finding("digilocker_mismatch", "info" if dl["simulated"] else "critical",
                                  "Uploaded certificate differs from the DigiLocker copy" + (" (SIMULATED record, not counted)" if dl["simulated"] else ""),
                                  dl["summary"], {"digilockerDocumentId": dl["documentId"]}))
        if not dl["simulated"]:
            status = "inconsistent"
    elif dl["status"] == "match" and not dl["simulated"] and status == "consistent":
        status = "verified"
    summary = (problem + " " if problem and not ext.fields else "") + (_summary(r, "document") if ext.fields else "")
    save_run(db, cand, job, "education", status, result_payload(doc, ext, r, summary.strip(), issuer=issuer, digilocker=dl), summary.strip(),
             r.findings, doc, error=problem or "")


def check_employment(db, cand, job, profile, resume_fields, consent_docs) -> None:
    doc = current_doc(cand, "experience_letter")
    refs = db.query(ReferenceRequest).filter_by(candidate_id=cand.id).order_by(ReferenceRequest.created_at).all()
    from ..models import Application as _App
    org_of = {x.id: (lambda ap: ap.job.organization_id if ap else None)(db.get(_App, x.application_id) if x.application_id else None) for x in refs}
    ref_rows = [{"id": x.id, "orgId": org_of[x.id], "referee": x.referee_name, "company": x.company, "status": x.status, "simulated": x.simulated,
                 "confirmed": x.response.get("confirmed") if x.response else None, "respondedAt": x.responded_at.isoformat() + "Z" if x.responded_at else None,
                 "response": {k: x.response.get(k) for k in ("title", "start", "end", "comments")} if x.response else None} for x in refs]
    real_confirmed = [x for x in refs if x.status == "responded" and not x.simulated and x.response.get("confirmed") is True]
    denied = [x for x in refs if x.status == "responded" and x.response.get("confirmed") is False]
    pending = [x for x in refs if x.status == "sent"]
    if not profile["experience"] and not doc:
        save_run(db, cand, job, "employment", "not_started", {"summary": "No work experience claimed.", "references": ref_rows},
                 "No work experience claimed.", [])
        return
    r = CheckResult()
    ext = None
    problem = None
    if doc and consent_docs:
        ext = extraction_for(db, doc, profile)
        problem = _extraction_problem(ext)
        r = employment_rules(ext.fields or None, profile, resume_fields, doc.id)
    for x in denied:
        r.findings.append(Finding("reference_denied", "critical" if not x.simulated else "warning",
                                  f"{x.referee_name} did not confirm employment at {x.company}" + (" (SIMULATED response)" if x.simulated else ""),
                                  (x.response or {}).get("comments", "")))
    for x in real_confirmed:
        resp = x.response
        if resp.get("start") and x.claimed_start and resp["start"][:7] != x.claimed_start[:7]:
            r.findings.append(Finding("reference_date_differs", "warning", f"{x.referee_name} gave a different start date",
                                      f"Reference: {resp['start'][:7]}. Profile: {x.claimed_start}."))
    if r.consistency == "inconsistent" or denied and not all(x.simulated for x in denied):
        status = "inconsistent"
    elif any(f.severity == "warning" for f in r.findings):
        status = "needs_review"
    elif real_confirmed and (not doc or r.consistency in ("consistent", "partially_consistent")):
        status = "verified"
    elif doc and ext and ext.fields:
        status = STATUS_FROM_CONSISTENCY[r.consistency]
    elif pending:
        status = "pending"
    elif not doc:
        status = "needs_review"
        r.findings.append(Finding("employment_no_evidence", "info", "No experience letter uploaded",
                                  "Work experience is claimed but no experience letter or reference confirmation exists yet."))
    else:
        status = "needs_review"
    parts = []
    if doc and ext and ext.fields:
        parts.append(_summary(r, "experience letter"))
    elif problem:
        parts.append(problem)
    if real_confirmed:
        parts.append(f"{len(real_confirmed)} reference confirmation(s) received.")
    if pending:
        parts.append(f"{len(pending)} reference request(s) awaiting a reply.")
    if any(x.simulated for x in refs if x.status == "responded"):
        parts.append("Simulated reference responses are shown for testing and do not count as confirmation.")
    summary = " ".join(parts) or "Waiting for an experience letter or a reference confirmation."
    save_run(db, cand, job, "employment", status, result_payload(doc, ext, r, summary, references=ref_rows), summary, r.findings, doc,
             error=problem or "")


def check_identity(db, cand, job, consent_bio) -> object | None:
    """Enrol the face from the registration selfie and compare it with the face on the ID document."""
    selfie = current_doc(cand, "selfie")
    if not consent_bio:
        db.query(FaceEnrollment).filter_by(candidate_id=cand.id, status="active").update({"status": "revoked"})
        save_run(db, cand, job, "identity", "not_started", {"summary": "Biometric consent is not given, so no face checks are run."}, "Consent required", [])
        return None
    ok, why = facemod.available()
    if not ok:
        save_run(db, cand, job, "identity", "needs_review", {"summary": f"Face checks are unavailable on this server: {why}"}, why, [], error=why)
        return None
    if not selfie:
        save_run(db, cand, job, "identity", "not_started", {"summary": "No enrolment photo."}, "No enrolment photo.", [])
        return None
    findings: list[Finding] = []
    enrol = (db.query(FaceEnrollment).filter_by(candidate_id=cand.id, status="active", source_document_id=selfie.id).first())
    embedding = decrypt_embedding(enrol.embedding_encrypted) if enrol else None
    if embedding is None:
        path = storage.path_for(selfie.storage_name)
        res = facemod.analyse(path.read_bytes(), strict_quality=False) if path else facemod.FaceResult("unreadable", "Enrolment photo file is missing.")
        if res.status != "ok":
            msg = {"no_face": "No face was found in the enrolment photo.", "multiple_faces": "The enrolment photo shows more than one face."}.get(res.status, res.message)
            findings.append(Finding("enrolment_failed", "warning", "Face enrolment failed", msg))
            save_run(db, cand, job, "identity", "needs_review", {"summary": msg + " The candidate should retake the photo.", "enrolment": {"status": res.status, "quality": res.quality}},
                     msg, findings, selfie)
            return None
        db.query(FaceEnrollment).filter_by(candidate_id=cand.id, status="active").update({"status": "revoked"})
        enrol = FaceEnrollment(candidate_id=cand.id, source_document_id=selfie.id, embedding_encrypted=encrypt_embedding(res.embedding),
                               model=facemod.MODEL_NAME, quality=res.quality)
        db.add(enrol)
        db.flush()
        embedding = res.embedding
        if res.quality.get("problems"):
            findings.append(Finding("enrolment_quality", "info", "Enrolment photo quality is low", "; ".join(res.quality["problems"])))
    # ID document photo
    id_doc = current_doc(cand, "id_document")
    id_result: dict = {"status": "not_checked", "label": "No ID document uploaded"}
    status = "needs_review"
    if id_doc:
        path = storage.path_for(id_doc.storage_name)
        img = textract.render_first_page_png(path.read_bytes(), id_doc.content_type) if path else None
        res = facemod.analyse(img, allow_multiple=True, strict_quality=False) if img else facemod.FaceResult("unreadable", "The ID document could not be rendered.")
        if res.status == "ok":
            sim = facemod.similarity(embedding, res.embedding)
            decision = "match" if sim >= facemod.SAME_PERSON else "no_match"
            db.add(FaceCheck(candidate_id=cand.id, stage="id_document", reference_id=id_doc.id, decision=decision, similarity=round(sim, 3),
                             threshold=facemod.SAME_PERSON, quality=res.quality))
            id_result = {"status": decision, "similarity": round(sim, 3), "threshold": facemod.SAME_PERSON,
                         "label": "Face on the ID matches the enrolment photo" if decision == "match" else "Face on the ID does not match the enrolment photo"}
            if decision == "match":
                status = "verified"
            else:
                status = "inconsistent"
                findings.append(Finding("id_face_mismatch", "warning", "ID photo does not match the enrolment photo",
                                        f"Similarity {sim:.2f} is below the threshold {facemod.SAME_PERSON}. Old or low-quality ID photos can cause this; a person must review.",
                                        {"documentId": id_doc.id, "similarity": round(sim, 3)}))
        else:
            id_result = {"status": res.status, "label": res.message or "No face found on the ID document"}
            findings.append(Finding("id_face_unreadable", "info", "Could not compare the ID photo", id_result["label"]))
    rechecks = (db.query(FaceCheck).filter(FaceCheck.candidate_id == cand.id, FaceCheck.stage != "id_document").order_by(FaceCheck.at).all())
    failed_rechecks = [x for x in rechecks if x.decision == "no_match"]
    if failed_rechecks:
        status = "inconsistent" if status != "verified" else "needs_review"
        findings.append(Finding("recheck_mismatch", "warning", f"{len(failed_rechecks)} identity recheck(s) did not match",
                                ", ".join(f"{x.stage} {x.at:%d %b %H:%M}: {x.similarity:.2f}" for x in failed_rechecks if x.similarity is not None)))
    summary = {"verified": "Enrolment photo and ID photo show the same face.", "inconsistent": "Face comparison found a difference that needs review.",
               "needs_review": "Face enrolled. The ID photo could not be compared automatically."}[status]
    save_run(db, cand, job, "identity", status, {
        "summary": summary + " Liveness is not checked: a photo of a photo can pass.",
        "enrolment": {"status": "enrolled", "quality": enrol.quality, "model": enrol.model, "at": enrol.created_at.isoformat() + "Z"},
        "idDocument": id_result,
        "rechecks": [{"stage": x.stage, "decision": x.decision, "similarity": x.similarity, "at": x.at.isoformat() + "Z"} for x in rechecks],
        "findings": [{"code": f.code, "severity": f.severity, "title": f.title, "detail": f.detail} for f in findings],
    }, summary, findings, selfie)
    return embedding


def check_duplicates(db, cand, job, embedding) -> None:
    duplicates.scan(db, cand, embedding)
    db.flush()
    alerts = duplicates.alerts_for(db, cand.id)
    # Reviews are per organisation (fraud/reviews.py), so this candidate-level run only reports that alerts exist.
    findings = [Finding(f"duplicate_{a.kind}", "warning", "Potential duplicate profile",
                        f"{duplicates.other_label(a, cand.id)}: {a.evidence.get('reason')}" + (f" (similarity {a.similarity:.2f})" if a.similarity else ""),
                        {"alertId": a.id}) for a in alerts]
    if alerts:
        status = "needs_review"
        summary = f"{len(alerts)} potential duplicate profile alert(s) for human review. Each organisation reviews them separately; nothing is blocked automatically."
    else:
        status = "consistent"
        summary = "No other account shares this verified mobile number or a very similar enrolled face."
    if embedding is None:
        summary += " Face comparison was not run (no enrolled face or no biometric consent)."
    save_run(db, cand, job, "duplicate", status, {"summary": summary, "alerts": [alert_json(a, cand.id) for a in alerts]}, summary, findings)


def alert_json(a, cand_id: str, review=None) -> dict:
    """``review``: the viewing organisation's latest AlertReview, or None (open for that organisation)."""
    return {"id": a.id, "kind": a.kind, "similarity": a.similarity, "evidence": a.evidence, "otherAccount": duplicates.other_label(a, cand_id),
            "reviewStatus": review.status if review else "open", "reviewNote": review.note if review else "",
            "reviewedAt": review.at.isoformat() + "Z" if review else None,
            "createdAt": a.created_at.isoformat() + "Z"}


# ------------------------------------------------------------------------------------------- job

def run_job(db: Session, job_id: str) -> None:
    job = db.get(VerificationJob, job_id)
    if not job or job.status not in ("queued", "running"):
        return
    job.status, job.started_at = "running", utcnow()
    db.commit()
    try:
        cand = db.get(Candidate, job.candidate_id)
        profile = profile_dict(cand)
        dob: date | None = cand.date_of_birth
        consent_docs = duplicates.has_consent(cand, "document_processing")
        consent_bio = duplicates.has_consent(cand, "biometric")
        resume_fields = check_resume(db, cand, job, profile, dob, consent_docs)
        check_education(db, cand, job, profile, resume_fields, consent_docs)
        check_employment(db, cand, job, profile, resume_fields, consent_docs)
        embedding = check_identity(db, cand, job, consent_bio)
        check_duplicates(db, cand, job, embedding)
        from ..fraud import patterns, scoring
        patterns.scan(db, cand)
        scoring.refresh_candidate(db, cand.id, f"verification:{job.reason}"[:40])
        job.status, job.finished_at = "done", utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001 - record and keep the worker alive
        db.rollback()
        job = db.get(VerificationJob, job_id)
        job.status, job.finished_at = "failed", utcnow()
        job.error = f"{type(exc).__name__}: {exc}"[:500]
        db.commit()
        log.error("verification job %s failed: %s", job_id, type(exc).__name__)
        log.debug("%s", traceback.format_exc())
