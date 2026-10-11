"""Phase 3: verification engine, identity continuity and duplicate detection.

All documents are synthetic (tests/synth.py). Face images are public LFW test images used by OpenCV's own tests.
"""
from __future__ import annotations

import io
import itertools
import json
import logging

import pytest
import synth
from test_phase2 import auth, job_body, register_recruiter

from app.verification import face as facemod, gemini, textract

_n = itertools.count(500)
needs_pymupdf = pytest.mark.skipif(textract.pymupdf() is None, reason="PyMuPDF not installed")
needs_ocr = pytest.mark.skipif(not textract.ocr_available(), reason="Tesseract not installed")
needs_face = pytest.mark.skipif(not facemod.available()[0], reason="face models unavailable")


def make_candidate(client, otp_box, *, name="Arun Kumar", phone=None, selfie=None, id_doc=None, dob="2004-05-17",
                   education=None, experience=None):
    i = f"{next(_n)}{__import__('uuid').uuid4().hex[:6]}"  # unique even if pytest imports this module twice
    phone = phone or "9" + str(__import__("uuid").uuid4().int)[:9]
    client.post("/api/auth/otp", json={"phone": phone})
    payload = {"fullName": name, "email": f"cand{i}@mail.example", "phone": phone, "otp": otp_box[phone], "dateOfBirth": dob,
               "password": "Candidat3Pass",
               "education": education or [{"degree": "B.E. Computer Science", "institution": "Anna University", "startYear": "2022", "endYear": "2026", "score": "8.4"}],
               "experience": experience or [], "selfie": synth.data_url(selfie or synth.face_jpeg("Alvaro_Uribe_0028.jpg")), "consent": True}
    files = {"idDocument": ("id.jpg", id_doc or synth.face_jpeg("Alvaro_Uribe_0029.jpg"), "image/jpeg")}
    r = client.post("/api/candidates/register", data={"payload": json.dumps(payload)}, files=files)
    assert r.status_code == 201, r.text
    return r.json()["token"], payload


def upload(client, token, kind, data, name="doc.pdf", ctype="application/pdf"):
    r = client.post("/api/candidate/documents", files={kind: (name, data, ctype)}, headers=auth(token))
    assert r.status_code == 201, r.text
    return r.json()[0]


def statuses(client, token):
    return {i["key"]: i["status"] for i in client.get("/api/candidate/verification", headers=auth(token)).json()}


def finding_codes(result):
    return {f["code"] for f in result.get("findings", [])}


def resume_result(client, token):
    from app.db import SessionLocal
    from app.models import User
    from app import serialize
    with SessionLocal() as db:
        cid = db.query(User).filter_by(id=_uid(token)).one().candidate.id
        return serialize.latest_result(db, cid, "resume")


def _uid(token):
    from app.security import decode_token
    return decode_token(token, "access")["sub"]


# ------------------------------------------------------------------------------------------- resume

@needs_pymupdf
def test_resume_matching_graduation_year_is_consistent(client, otp_box):
    token, _ = make_candidate(client, otp_box)
    upload(client, token, "resume", synth.resume(grad=(2022, 2026)))
    res = resume_result(client, token)
    rows = {c["field"]: c for c in res["comparison"]}
    assert rows["B.E. Computer Science: graduation year"]["match"] is True
    assert rows["Name"]["match"] is True
    assert "graduation_year_mismatch" not in finding_codes(res)
    assert res["extraction"]["method"].startswith("pymupdf_text")
    assert statuses(client, token)["resume"] == "consistent"
    # evidence points at the real page and text
    ev = rows["B.E. Computer Science: graduation year"]["evidence"]
    assert ev["page"] == 1 and "2026" in ev["snippet"]


@needs_pymupdf
def test_resume_mismatching_graduation_year_is_flagged_not_accused(client, otp_box):
    token, _ = make_candidate(client, otp_box)
    upload(client, token, "resume", synth.resume(grad=(2021, 2025)))
    res = resume_result(client, token)
    assert "graduation_year_mismatch" in finding_codes(res)
    row = next(c for c in res["comparison"] if c["field"].endswith("graduation year"))
    assert (row["extracted"], row["claimed"], row["match"]) == ("2025", "2026", False)
    assert statuses(client, token)["resume"] == "inconsistent"
    # "inconsistent" is a review status; nothing is rejected or blocked automatically
    assert all(a["status"] != "rejected" for a in client.get("/api/candidate/applications", headers=auth(token)).json())


@needs_pymupdf
def test_document_change_recomputes_results(client, otp_box):
    token, _ = make_candidate(client, otp_box)
    doc = upload(client, token, "resume", synth.resume(grad=(2021, 2025)))
    assert statuses(client, token)["resume"] == "inconsistent"
    r = client.put(f"/api/candidate/documents/{doc['id']}", files={"file": ("cv2.pdf", synth.resume(grad=(2022, 2026)), "application/pdf")}, headers=auth(token))
    assert r.status_code == 200
    assert statuses(client, token)["resume"] == "consistent"


@needs_pymupdf
def test_employment_overlap_and_impossible_timeline(client, otp_box):
    exp = [{"company": "Zoho", "title": "Developer", "start": "2023-01", "end": "2024-06", "current": False},
           {"company": "Freshworks", "title": "Developer", "start": "2023-06", "end": "2024-12", "current": False},
           {"company": "TinyCo", "title": "Engineer", "start": "2012-01", "end": "2012-06", "current": False}]
    token, _ = make_candidate(client, otp_box, experience=exp, dob="2004-05-17")
    upload(client, token, "resume", synth.resume(jobs=[("Developer", "Zoho", "Jan 2023 - Jun 2024")]))
    res = resume_result(client, token)
    codes = finding_codes(res)
    assert "employment_overlap" in codes          # Zoho and Freshworks overlap by 12 months
    assert "impossible_timeline" in codes         # TinyCo started before age 14
    assert "employment_not_on_resume" in codes    # Freshworks is missing from the resume (information only)
    assert statuses(client, token)["resume"] == "inconsistent"


# ------------------------------------------------------------------------------------------- education

@needs_pymupdf
def test_marksheet_consistent_but_issuer_not_checked(client, otp_box):
    token, _ = make_candidate(client, otp_box)
    upload(client, token, "marksheet", synth.marksheet(year=2026))
    edu = client.get("/api/candidate/verification/education", headers=auth(token)).json()
    rows = {c["field"]: c for c in edu["comparison"]}
    assert rows["Year"]["match"] is True and rows["Name"]["match"] is True and rows["Board / University"]["match"] is True
    assert edu["status"] == "consistent"            # documents agree …
    assert edu["issuer"]["status"] == "not_checked"  # … but that does NOT make the certificate genuine
    assert "do not prove" in edu["issuer"]["label"]
    assert {e["label"] for e in edu["extracted"]} >= {"Name", "Register Number", "Year", "CGPA"}


@needs_pymupdf
def test_marksheet_missing_year_is_not_a_mismatch(client, otp_box):
    token, _ = make_candidate(client, otp_box)
    upload(client, token, "marksheet", synth.marksheet(include_year=False).replace(b"2026", b"XXXX"))
    edu = client.get("/api/candidate/verification/education", headers=auth(token)).json()
    year = next(c for c in edu["comparison"] if c["field"] == "Year")
    assert year["match"] is None and "education_year_mismatch" not in finding_codes(edu)
    assert edu["status"] != "inconsistent"


@needs_pymupdf
def test_marksheet_year_mismatch_and_resume_conflict(client, otp_box):
    token, _ = make_candidate(client, otp_box)
    upload(client, token, "resume", synth.resume(grad=(2022, 2026)))
    upload(client, token, "marksheet", synth.marksheet(year=2024))
    edu = client.get("/api/candidate/verification/education", headers=auth(token)).json()
    codes = finding_codes(edu)
    assert "education_year_mismatch" in codes and "resume_document_year_conflict" in codes
    assert edu["status"] == "inconsistent"
    ev = next(c for c in edu["comparison"] if c["field"] == "Year")["evidence"]
    assert ev["documentId"] and "2024" in ev["snippet"]


@needs_pymupdf
def test_simulated_issuer_registry_and_recruiter_attestation(client, otp_box, tmp_path):
    import manage
    csv = tmp_path / "issuers.csv"
    csv.write_text("issuer,register_number,student_name,qualification,year\nAnna University,AU2026SIM01,Arun Kumar,B.E. CSE,2026\n")
    manage.load_issuer_records(str(csv))
    token, _ = make_candidate(client, otp_box)
    upload(client, token, "marksheet", synth.marksheet(reg="AU2026SIM01", year=2026))
    edu = client.get("/api/candidate/verification/education", headers=auth(token)).json()
    assert edu["issuer"]["status"] == "confirmed" and edu["issuer"]["simulated"] is True and "SIMULATED" in edu["issuer"]["label"]
    assert edu["status"] == "consistent"  # simulated confirmation never upgrades to "verified"
    # A recruiter records a real confirmation from the university -> verified
    rtoken, _ = register_recruiter(client)
    job = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(rtoken)).json()
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(token)).json()["id"]
    r = client.post(f"/api/recruiter/applicants/{app_id}/issuer-confirmation",
                    json={"result": "confirmed", "detail": "Called the controller of examinations; record matches.", "reference": "Email 12 Oct"}, headers=auth(rtoken))
    assert r.status_code == 201
    edu = client.get("/api/candidate/verification/education", headers=auth(token)).json()
    assert edu["issuer"]["method"] == "recruiter_attestation" and edu["status"] == "verified"


# ------------------------------------------------------------------------------------------- employment & references

@needs_pymupdf
def test_experience_letter_dates_inconsistent(client, otp_box):
    exp = [{"company": "Zoho Corporation", "title": "Software Engineer Intern", "start": "2025-05", "end": "2025-07", "current": False}]
    token, _ = make_candidate(client, otp_box, experience=exp)
    upload(client, token, "experience_letter", synth.experience_letter(joined="01/01/2025", relieved="31/07/2025"))
    emp = client.get("/api/candidate/verification/employment", headers=auth(token)).json()
    rows = {c["field"]: c for c in emp["comparison"]}
    assert rows["Name"]["match"] is True  # "certify that Mr. Arun Kumar was employed…" must not read as a different name
    assert rows["Company"]["match"] is True and rows["Designation"]["match"] is True
    assert rows["Joining Date"]["match"] is False and rows["Relieving Date"]["match"] is True
    assert "employment_date_mismatch" in finding_codes(emp)
    assert emp["status"] == "inconsistent"


@needs_pymupdf
def test_reference_request_workflow(client, otp_box):
    exp = [{"company": "Zoho Corporation", "title": "Software Engineer Intern", "start": "2025-05", "end": "2025-07", "current": False}]
    token, data = make_candidate(client, otp_box, experience=exp)
    prof = client.get("/api/candidate/profile", headers=auth(token)).json()
    prof["references"] = [{"name": "Priya HR", "relationship": "HR Manager", "company": "Zoho Corporation", "email": "hr@zoho.example", "phone": ""}]
    body = {k: prof[k] for k in ("fullName", "email", "phone", "skills", "education", "experience", "references")}
    body.update(location="Chennai", headline="Developer", linkedinUrl="", githubUrl="")
    assert client.put("/api/candidate/profile", json=body, headers=auth(token)).status_code == 200
    ref_id = client.get("/api/candidate/profile", headers=auth(token)).json()["references"][0]["id"]
    assert statuses(client, token)["employment"] == "needs_review"  # experience claimed, no evidence yet
    rtoken, _ = register_recruiter(client)
    job = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(rtoken)).json()
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(token)).json()["id"]
    link = client.post(f"/api/recruiter/applicants/{app_id}/reference-requests", json={"referenceId": ref_id}, headers=auth(rtoken)).json()["link"]
    tok = link.rsplit("/", 1)[1]
    assert statuses(client, token)["employment"] == "needs_review"
    view = client.get(f"/api/reference/{tok}").json()
    assert view["company"] == "Zoho Corporation" and view["status"] == "sent" and "email" not in view
    assert client.get("/api/reference/not-a-real-token").status_code == 404
    ans = {"confirmed": True, "title": "Software Engineer Intern", "start": "2025-05", "end": "2025-07", "comments": "Good intern",
           "responderName": "Priya", "responderRole": "HR"}
    assert client.post(f"/api/reference/{tok}", json=ans).status_code == 200
    assert client.post(f"/api/reference/{tok}", json=ans).status_code == 409  # one-time link
    assert statuses(client, token)["employment"] == "verified"  # real HR confirmation actually received


def test_simulated_reference_is_labelled_and_does_not_verify(client, otp_box):
    exp = [{"company": "Infosys", "title": "Analyst", "start": "2024-01", "end": "2024-12", "current": False}]
    token, _ = make_candidate(client, otp_box, experience=exp)
    rtoken, _ = register_recruiter(client)
    job = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(rtoken)).json()
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(token)).json()["id"]
    rr = client.post(f"/api/recruiter/applicants/{app_id}/reference-requests", json={"refereeName": "Test HR", "refereeContact": "hr@infosys.example"},
                     headers=auth(rtoken)).json()
    assert client.post(f"/api/recruiter/applicants/{app_id}/reference-requests/{rr['id']}/simulate", json={"confirmed": True}, headers=auth(rtoken)).status_code == 200
    rep = client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(rtoken)).json()
    assert rep["verification"]["employment"]["status"] != "verified"
    assert any("SIMULATED" in r["title"] for r in rep["sections"]["employment"])


# ------------------------------------------------------------------------------------------- face

@needs_face
def test_face_enrolment_and_id_match(client, otp_box):
    token, _ = make_candidate(client, otp_box, selfie=synth.face_jpeg("Alvaro_Uribe_0028.jpg"), id_doc=synth.face_jpeg("Alvaro_Uribe_0029.jpg"))
    ident = client.get("/api/candidate/verification/identity", headers=auth(token)).json()
    assert ident["enrolment"]["status"] == "enrolled"
    assert ident["idDocument"]["status"] == "match" and ident["idDocument"]["similarity"] >= facemod.SAME_PERSON
    assert ident["status"] == "verified" and "Liveness is not checked" in ident["summary"]
    from app.db import SessionLocal
    from app.models import FaceEnrollment
    with SessionLocal() as db:
        row = db.query(FaceEnrollment).filter_by(status="active").order_by(FaceEnrollment.created_at.desc()).first()
        assert not row.embedding_encrypted.startswith(b"\x00") and len(row.embedding_encrypted) > 512  # encrypted, not raw floats


@needs_face
def test_face_id_mismatch_needs_review(client, otp_box):
    token, _ = make_candidate(client, otp_box, selfie=synth.face_jpeg("Alvaro_Uribe_0028.jpg"), id_doc=synth.face_jpeg("Aaron_Tippin_0001.jpg"))
    ident = client.get("/api/candidate/verification/identity", headers=auth(token)).json()
    assert ident["idDocument"]["status"] == "no_match" and ident["status"] == "inconsistent"


@needs_face
def test_identity_rechecks_and_error_handling(client, otp_box):
    token, _ = make_candidate(client, otp_box, selfie=synth.face_jpeg("Jose_Luis_Rodriguez_Zapatero_0001.jpg"),
                              id_doc=synth.face_jpeg("Jose_Luis_Rodriguez_Zapatero_0001.jpg", 2.2))
    h = auth(token)
    check = lambda img: client.post("/api/candidate/identity/check", json={"stage": "manual", "image": synth.data_url(img)}, headers=h).json()  # noqa: E731
    assert check(synth.face_jpeg("Jose_Luis_Rodriguez_Zapatero_0001.jpg", 2.6))["decision"] == "match"
    assert check(synth.face_jpeg("Aaron_Tippin_0001.jpg"))["decision"] == "no_match"
    assert check(synth.blank_jpeg())["decision"] == "no_face"
    assert check(synth.two_faces_jpeg())["decision"] == "multiple_faces"
    dark = synth.face_jpeg("Jose_Luis_Rodriguez_Zapatero_0001.jpg")
    import cv2
    import numpy as np
    img = cv2.imdecode(np.frombuffer(dark, np.uint8), cv2.IMREAD_COLOR)
    assert check(cv2.imencode(".jpg", (img * 0.15).astype(np.uint8))[1].tobytes())["decision"] in ("poor_quality", "no_face")
    bad = client.post("/api/candidate/identity/check", json={"stage": "manual", "image": "data:image/jpeg;base64," + "A" * 200}, headers=h)
    assert bad.status_code == 400
    assert client.post("/api/candidate/identity/check", json={"stage": "interview", "referenceId": "someone-elses", "image": synth.data_url(dark)},
                       headers=h).status_code == 404
    ident = client.get("/api/candidate/verification/identity", headers=h).json()
    assert [r["decision"] for r in ident["rechecks"]][:2] == ["match", "no_match"]
    assert ident["status"] == "needs_review"  # a failed recheck after a good enrolment goes to a person


@needs_face
def test_missing_enrolment_and_consent_withdrawal(client, otp_box):
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg(), id_doc=synth.face_jpeg("Aaron_Tippin_0001.jpg"))
    h = auth(token)
    ident = client.get("/api/candidate/verification/identity", headers=h).json()
    assert ident["status"] == "needs_review" and "No face" in ident["summary"]
    r = client.post("/api/candidate/identity/check", json={"stage": "manual", "image": synth.data_url(synth.face_jpeg("Aaron_Tippin_0001.jpg"))}, headers=h)
    assert r.json()["decision"] == "no_enrollment"
    token2, _ = make_candidate(client, otp_box, selfie=synth.face_jpeg("Aaron_Tippin_0001.jpg"))
    h2 = auth(token2)
    assert client.post("/api/candidate/consents", json={"purpose": "biometric", "granted": False}, headers=h2).status_code == 200
    from app.db import SessionLocal
    from app.models import FaceEnrollment, User
    with SessionLocal() as db:
        cid = db.query(User).filter_by(id=_uid(token2)).one().candidate.id
        assert db.query(FaceEnrollment).filter_by(candidate_id=cid).count() == 0  # embedding deleted
    r = client.post("/api/candidate/identity/check", json={"stage": "manual", "image": synth.data_url(synth.face_jpeg("Aaron_Tippin_0001.jpg"))}, headers=h2)
    assert r.json()["decision"] == "no_consent"


# ------------------------------------------------------------------------------------------- duplicates

def test_phone_duplicate_alert_and_name_only_never_alerts(client, otp_box):
    a, _ = make_candidate(client, otp_box, name="Same Name", phone="9000011111", selfie=synth.blank_jpeg())
    b, _ = make_candidate(client, otp_box, name="Other Person", phone="9000011111", selfie=synth.blank_jpeg())
    c, _ = make_candidate(client, otp_box, name="Same Name", phone="9000022222", selfie=synth.blank_jpeg())
    from app.db import SessionLocal
    from app import serialize
    from app.models import User
    with SessionLocal() as db:
        res = {k: serialize.latest_result(db, db.query(User).filter_by(id=_uid(t)).one().candidate.id, "duplicate") for k, t in (("a", a), ("b", b), ("c", c))}
    assert statuses(client, b)["duplicate"] == "needs_review"  # an alert asks for review; it is not a verdict
    assert [x["kind"] for x in res["b"]["alerts"]] == ["phone"]
    assert res["c"]["alerts"] == [] and statuses(client, c)["duplicate"] == "consistent"  # same name only -> no alert
    alert = res["b"]["alerts"][0]
    assert alert["otherAccount"].startswith("Candidate account …") and "Same Name" not in json.dumps(alert)  # no personal data of the other account
    # recruiter review (human decision); the candidate is not blocked
    rtoken, _ = register_recruiter(client)
    job = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(rtoken)).json()
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(b)).json()["id"]
    r = client.post(f"/api/recruiter/applicants/{app_id}/duplicates/{alert['id']}/review", json={"status": "not_duplicate", "note": "Family members sharing one phone."},
                    headers=auth(rtoken))
    assert r.status_code == 200

    def dup_status(tok):
        rep = client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(tok)).json()
        return rep["duplicateAlerts"][0]["reviewStatus"], next(c for c in rep["trust"]["checks"] if c["key"] == "duplicate")["bucket"]
    assert dup_status(rtoken) == ("not_duplicate", "consistent")
    # Phase 6: reviews are per organisation; another organisation still sees the alert as open
    rtoken2, _ = register_recruiter(client)
    job2 = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(rtoken2)).json()
    app2 = client.post(f"/api/jobs/{job2['id']}/apply", headers=auth(b)).json()["id"]
    rep2 = client.get(f"/api/recruiter/applicants/{app2}/report", headers=auth(rtoken2)).json()
    assert rep2["duplicateAlerts"][0]["reviewStatus"] == "open" and "Family" not in json.dumps(rep2["duplicateAlerts"])
    # a reviewer confirming the duplicate is what makes it inconsistent for that organisation (still not blocked)
    client.post(f"/api/recruiter/applicants/{app_id}/duplicates/{alert['id']}/review", json={"status": "confirmed_duplicate", "note": "Same person confirmed on a call."},
                headers=auth(rtoken))
    assert dup_status(rtoken) == ("confirmed_duplicate", "inconsistent")
    assert statuses(client, b)["duplicate"] == "needs_review"  # the candidate-level run only says alerts exist
    assert client.get("/api/candidate/dashboard", headers=auth(b)).status_code == 200


@needs_face
def test_face_duplicate_alert(client, otp_box):
    a, _ = make_candidate(client, otp_box, selfie=synth.face_jpeg("Alvaro_Uribe_0028.jpg"))
    b, _ = make_candidate(client, otp_box, selfie=synth.face_jpeg("Alvaro_Uribe_0028.jpg", 2.3))  # same person, second account
    from app.db import SessionLocal
    from app import serialize
    from app.models import User
    with SessionLocal() as db:
        res = serialize.latest_result(db, db.query(User).filter_by(id=_uid(b)).one().candidate.id, "duplicate")
    face_alerts = [x for x in res["alerts"] if x["kind"] == "face"]
    assert face_alerts and face_alerts[0]["similarity"] >= facemod.DUPLICATE


# ------------------------------------------------------------------------------------------- OCR, Gemini, robustness

@needs_ocr
def test_scanned_marksheet_is_read_with_ocr(client, otp_box):
    token, _ = make_candidate(client, otp_box)
    png = synth.text_image(["ANNA UNIVERSITY", "Name of the Candidate : ARUN KUMAR", "Register Number : AU2026CS777", "Year of Passing : 2026", "CGPA : 8.40"])
    upload(client, token, "marksheet", png, "scan.png", "image/png")
    edu = client.get("/api/candidate/verification/education", headers=auth(token)).json()
    assert edu["extraction"]["method"] == "ocr_tesseract"
    values = {e["label"]: e["value"] for e in edu["extracted"]}
    assert values.get("Year") == "2026" and "AU2026CS777" in (values.get("Register Number") or "")


@needs_pymupdf
def test_unreadable_pdf_does_not_create_findings(client, otp_box):
    token, _ = make_candidate(client, otp_box)
    upload(client, token, "resume", synth.pdf([]))  # valid PDF with no text at all
    res = resume_result(client, token)
    assert res["status"] == "needs_review" and not any(f["severity"] in ("warning", "critical") for f in res["findings"])


def test_gemini_suggestions_cannot_create_mismatches(monkeypatch, caplog):
    monkeypatch.setenv("GEMINI_API_KEY", "test-secret-key-123")

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def transport(req, timeout):
        assert req.get_header("X-goog-api-key") == "test-secret-key-123" and "key=" not in req.full_url
        inner = json.dumps({"name": "Someone Else", "year": 1999, "registerNumber": "X1"})
        return Resp(json.dumps({"candidates": [{"content": {"parts": [{"text": inner}]}}]}).encode())

    with caplog.at_level(logging.DEBUG):
        ai = gemini.suggest("marksheet", "some marksheet text", transport=transport)
    merged = gemini.merge({}, ai, ("name", "year", "registerNumber"))
    assert merged["year"]["source"] == "gemini" and merged["year"]["confidence"] < 0.6
    from app.verification.rules import education_rules
    r = education_rules(merged, {"fullName": "Arun Kumar", "education": [{"degree": "B.E.", "institution": "Anna University", "endYear": "2026", "score": ""}]},
                        None, "doc")
    assert not any(c["match"] is False for c in r.comparison) and not r.findings  # AI values alone never produce a mismatch
    def broken(req, timeout):
        raise TimeoutError
    assert gemini.suggest("marksheet", "text", transport=broken) is None
    assert "test-secret-key-123" not in caplog.text and "some marksheet text" not in caplog.text


def test_recruiter_can_run_verification_only_for_own_applicants(client, otp_box):
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    r1, _ = register_recruiter(client)
    r2, _ = register_recruiter(client)
    job = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(r1)).json()
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(token)).json()["id"]
    assert client.post(f"/api/recruiter/applicants/{app_id}/verification/run", headers=auth(r2)).status_code == 404
    r = client.post(f"/api/recruiter/applicants/{app_id}/verification/run", headers=auth(r1))
    assert r.status_code == 202 and r.json()["status"] == "done"
    rep = client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(r1)).json()
    assert set(rep["verification"]) == {"identity", "education", "employment", "resume", "duplicate"}
    assert rep["trustScore"] == 80 + sum(e["applied"] for e in rep["trust"]["entries"])  # Phase 5: every point comes from a fired rule


def test_field_extraction_does_not_swallow_surrounding_words():
    from app.verification import fields as fx
    text = "This is to certify that Mr. Arun Kumar was employed with us\nB.E. Computer Science\nAnna University, Chennai 2022 - 2026 CGPA: 8.4"
    assert fx.parse_experience_letter(text, [text], {"fullName": "", "experience": []})["name"]["value"] == "Arun Kumar"
    edu = fx.education_entries(text, [text])[0]
    assert edu["institution"]["value"] == "Anna University, Chennai" and edu["endYear"]["value"] == 2026
