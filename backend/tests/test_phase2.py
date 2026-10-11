"""End-to-end API tests for Phase 2: accounts, roles, profiles, jobs, applications, documents."""
from __future__ import annotations

import itertools
import json

from conftest import JPEG_DATA_URL, PDF, PNG

import manage

_n = itertools.count(1)


def auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def register_recruiter(client, approve: bool = True) -> tuple[str, dict]:
    i = f"{next(_n)}{__import__('uuid').uuid4().hex[:6]}"
    email = f"hr{i}@acme{i}.example"
    r = client.post("/api/auth/register/recruiter", json={
        "fullName": "Priya Raman", "organisation": f"Acme Labs {i}", "email": email, "phone": "+91 98765 43210",
        "companySize": "51-200", "password": "Recruit3rPass"})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["user"]["organisationStatus"] == "pending"
    if approve:
        manage._set_org(email, "approved")
    return body["token"], body["user"]


def job_body(**over) -> dict:
    b = {"title": "Backend Developer", "department": "Engineering", "location": "Chennai", "employmentType": "full_time", "workMode": "hybrid",
         "experienceMin": 0, "experienceMax": 2, "salaryMin": 400000, "salaryMax": 700000, "skills": ["Python", "SQL"],
         "description": "Build and maintain APIs for our hiring platform with FastAPI and SQL.", "requirements": "B.E./B.Tech",
         "assessments": ["Coding (MCQ)"], "deadline": None, "status": "open"}
    b.update(over)
    return b


def register_candidate(client, otp_box, phone: str | None = None) -> tuple[str, dict]:
    i = f"{next(_n)}{__import__('uuid').uuid4().hex[:6]}"
    phone = phone or "9" + str(__import__("uuid").uuid4().int)[:9]
    assert client.post("/api/auth/otp", json={"phone": phone}).status_code == 200
    payload = {"fullName": "Arun Kumar", "email": f"arun{i}@mail.example", "phone": phone, "otp": otp_box[phone], "dateOfBirth": "2004-05-17",
               "password": "Candidat3Pass", "education": [{"degree": "B.E. CSE", "institution": "Anna University", "startYear": "2022", "endYear": "2026", "score": "8.4"}],
               "experience": [], "selfie": JPEG_DATA_URL, "consent": True}
    r = client.post("/api/candidates/register", data={"payload": json.dumps(payload)}, files={"idDocument": ("aadhaar.png", PNG, "image/png")})
    assert r.status_code == 201, r.text
    return r.json()["token"], payload


# ------------------------------------------------------------------ the scenario requested for Phase 2

def test_full_flow_persists(client, otp_box):
    # 1. recruiter registers and creates a job
    rtoken, ruser = register_recruiter(client)
    r = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(rtoken))
    assert r.status_code == 201, r.text
    job = r.json()
    assert job["company"] == ruser["organisation"] and job["applicantCount"] == 0

    # 2. candidate registers (OTP + selfie + ID) and sees the job
    ctoken, cdata = register_candidate(client, otp_box)
    jobs = client.get("/api/jobs", headers=auth(ctoken))
    assert jobs.status_code == 200 and job["id"] in [j["id"] for j in jobs.json()]
    assert int(jobs.headers["X-Total-Count"]) >= 1

    # 3. candidate uploads a resume
    r = client.post("/api/candidate/documents", files={"resume": ("cv.pdf", PDF, "application/pdf")}, headers=auth(ctoken))
    assert r.status_code == 201, r.text
    doc = r.json()[0]
    assert doc["kind"] == "resume" and doc["status"] == "pending" and len(doc["sha256"]) == 64  # uploaded ≠ verified

    # 4. candidate applies; a second click is rejected
    r = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken))
    assert r.status_code == 201, r.text
    app_id = r.json()["id"]
    dup = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken))
    assert dup.status_code == 409 and dup.json()["code"] == "already_applied"

    # 5. log out, then log back in: everything is still there
    assert client.post("/api/auth/logout", headers=auth(ctoken)).status_code == 200
    assert client.get("/api/candidate/dashboard", headers=auth(ctoken)).status_code == 401  # revoked token
    login = client.post("/api/auth/login", json={"role": "candidate", "email": cdata["email"], "password": cdata["password"]})
    assert login.status_code == 200
    ctoken = login.json()["token"]
    dash = client.get("/api/candidate/dashboard", headers=auth(ctoken)).json()
    assert dash["appliedJobs"] == 1
    assert {i["key"]: i["status"] for i in dash["verification"]}["resume"] not in ("verified", "not_started")  # read and compared, never auto-verified
    assert sorted(d["kind"] for d in client.get("/api/candidate/documents", headers=auth(ctoken)).json()) == ["id_document", "resume"]
    apps = client.get("/api/candidate/applications", headers=auth(ctoken)).json()
    assert [a["id"] for a in apps] == [app_id] and apps[0]["status"] == "applied"

    # 6. recruiter sees the applicant, shortlists and requests clarification; the candidate gets messages
    rdash = client.get("/api/recruiter/dashboard", headers=auth(rtoken)).json()
    assert rdash["totalApplicants"] == 1 and rdash["recentApplications"][0]["applicationId"] == app_id
    rep = client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(rtoken))
    body = rep.json()
    # Phase 5: the score is baseline + the rules that actually fired (here only the OTP-verified mobile)
    assert rep.status_code == 200 and body["trustScore"] == 80 + sum(e["applied"] for e in body["trust"]["entries"])
    assert [e["ruleId"] for e in body["trust"]["entries"]] == ["ID.PHONE_OTP"]
    assert client.post(f"/api/recruiter/applicants/{app_id}/status", json={"status": "shortlisted"}, headers=auth(rtoken)).status_code == 200
    r = client.post(f"/api/recruiter/applicants/{app_id}/status", json={"status": "clarification", "note": "Please upload your semester 6 marksheet."}, headers=auth(rtoken))
    assert r.status_code == 200 and r.json()["status"] == "clarification"
    msgs = client.get("/api/candidate/messages", headers=auth(ctoken)).json()
    assert len(msgs) == 2 and "marksheet" in msgs[0]["body"]

    # 7. recruiter can download the candidate's resume via a signed link; others cannot
    rdocs = rep.json()["documents"]
    url = next(d["previewUrl"] for d in rdocs if d["kind"] == "resume")
    got = client.get(url)
    assert got.status_code == 200 and got.content == PDF and got.headers["cache-control"].startswith("private")


# ------------------------------------------------------------------ authentication & authorisation

def test_login_failures_and_roles(client, otp_box):
    rtoken, _ = register_recruiter(client)
    ctoken, cdata = register_candidate(client, otp_box)
    bad = client.post("/api/auth/login", json={"role": "candidate", "email": cdata["email"], "password": "WrongPass1"})
    assert bad.status_code == 401 and bad.json()["code"] == "invalid_credentials"
    unknown = client.post("/api/auth/login", json={"role": "candidate", "email": "nobody@x.example", "password": "WrongPass1"})
    assert unknown.status_code == 401 and unknown.json()["detail"] == bad.json()["detail"]  # no account enumeration
    wrong_tab = client.post("/api/auth/login", json={"role": "recruiter", "email": cdata["email"], "password": cdata["password"]})
    assert wrong_tab.status_code == 401 and wrong_tab.json()["code"] == "wrong_role"
    # role guards
    assert client.get("/api/recruiter/dashboard", headers=auth(ctoken)).status_code == 403
    assert client.get("/api/candidate/dashboard", headers=auth(rtoken)).status_code == 403
    assert client.post("/api/recruiter/jobs", json=job_body(), headers=auth(ctoken)).status_code == 403
    # no / forged tokens
    assert client.get("/api/candidate/profile").status_code == 401
    assert client.get("/api/candidate/profile", headers=auth("abc.def.ghi")).status_code == 401
    import jwt as pyjwt
    forged = pyjwt.encode({"sub": "x", "typ": "access", "jti": "y", "exp": 9999999999}, "not-the-key", algorithm="HS256")
    assert client.get("/api/candidate/profile", headers=auth(forged)).status_code == 401


def test_password_is_hashed_with_argon2(client, otp_box):
    _, cdata = register_candidate(client, otp_box)
    from app.db import SessionLocal
    from app.models import User
    with SessionLocal() as db:
        u = db.query(User).filter_by(email=cdata["email"]).one()
        assert u.password_hash.startswith("$argon2id$") and cdata["password"] not in u.password_hash


def test_recruiter_registration_validation(client):
    r = client.post("/api/auth/register/recruiter", json={"fullName": "A", "organisation": "X", "email": "bad", "phone": "1",
                                                           "companySize": "huge", "password": "short"})
    assert r.status_code == 422 and r.json()["code"] == "validation_error" and len(r.json()["fields"]) >= 4
    token, user = register_recruiter(client, approve=False)
    dup = client.post("/api/auth/register/recruiter", json={"fullName": "Priya Raman", "organisation": "Other", "email": user["email"],
                                                             "phone": "+91 98765 43210", "companySize": "1-50", "password": "Recruit3rPass"})
    assert dup.status_code == 409


def test_pending_organisation_jobs_are_hidden(client, otp_box):
    rtoken, _ = register_recruiter(client, approve=False)
    job = client.post("/api/recruiter/jobs", json=job_body(title="Hidden Role"), headers=auth(rtoken)).json()
    ctoken, _ = register_candidate(client, otp_box)
    assert job["id"] not in [j["id"] for j in client.get("/api/jobs", headers=auth(ctoken)).json()]
    assert client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken)).status_code == 404


def test_candidate_otp_required_and_checked(client, otp_box):
    phone = "9876500001"
    payload = {"fullName": "Test Person", "email": "otp@mail.example", "phone": phone, "otp": "000000", "dateOfBirth": "2003-01-01",
               "password": "Candidat3Pass", "education": [{"degree": "BSc", "institution": "College", "startYear": "2020", "endYear": "2023", "score": ""}],
               "experience": [], "selfie": JPEG_DATA_URL, "consent": True}
    files = {"idDocument": ("id.pdf", PDF, "application/pdf")}
    r = client.post("/api/candidates/register", data={"payload": json.dumps(payload)}, files=files)
    assert r.status_code == 400 and r.json()["code"] == "otp_invalid"  # never requested
    client.post("/api/auth/otp", json={"phone": phone})
    wrong = "111111" if otp_box[phone] != "111111" else "222222"
    payload["otp"] = wrong
    assert client.post("/api/candidates/register", data={"payload": json.dumps(payload)}, files=files).json()["code"] == "otp_invalid"
    payload.update(otp=otp_box[phone], consent=False)
    r = client.post("/api/candidates/register", data={"payload": json.dumps(payload)}, files=files)
    assert r.status_code == 400 and "Consent" in r.json()["detail"]


# ------------------------------------------------------------------ documents

def test_invalid_uploads_rejected(client, otp_box):
    ctoken, _ = register_candidate(client, otp_box)
    h = auth(ctoken)
    fake_pdf = client.post("/api/candidate/documents", files={"resume": ("cv.pdf", b"MZ\x90\x00 not a pdf", "application/pdf")}, headers=h)
    assert fake_pdf.status_code == 415 and fake_pdf.json()["code"] == "unsupported_file_type"
    png_resume = client.post("/api/candidate/documents", files={"resume": ("cv.png", PNG, "image/png")}, headers=h)
    assert png_resume.status_code == 415  # resumes must be PDF
    big = client.post("/api/candidate/documents", files={"marksheet": ("m.pdf", b"%PDF-" + b"0" * (5 * 1024 * 1024 + 10), "application/pdf")}, headers=h)
    assert big.status_code == 413
    empty = client.post("/api/candidate/documents", files={"marksheet": ("m.pdf", b"", "application/pdf")}, headers=h)
    assert empty.status_code == 400
    unknown = client.post("/api/candidate/documents", files={"passport_photo": ("p.png", PNG, "image/png")}, headers=h)
    assert unknown.status_code == 400 and unknown.json()["code"] == "invalid_document_kind"
    # all-or-nothing: a valid file next to an invalid one is not saved
    mixed = client.post("/api/candidate/documents", files=[("marksheet", ("m.pdf", PDF, "application/pdf")), ("resume", ("x.pdf", b"nope", "application/pdf"))], headers=h)
    assert mixed.status_code == 415
    assert "marksheet" not in [d["kind"] for d in client.get("/api/candidate/documents", headers=h).json()]


def test_document_ownership_and_replacement(client, otp_box):
    a_token, _ = register_candidate(client, otp_box)
    b_token, _ = register_candidate(client, otp_box)
    rtoken, _ = register_recruiter(client)
    doc = client.post("/api/candidate/documents", files={"marksheet": ("m.pdf", PDF, "application/pdf")}, headers=auth(a_token)).json()[0]
    # B cannot replace or download A's document
    assert client.put(f"/api/candidate/documents/{doc['id']}", files={"file": ("x.pdf", PDF, "application/pdf")}, headers=auth(b_token)).status_code == 404
    b_url = client.get("/api/candidate/documents", headers=auth(b_token)).json()[0]["previewUrl"]
    stolen = b_url.split("?")[0].rsplit("/", 1)[0] + "/" + doc["id"] + "?" + b_url.split("?")[1]
    assert client.get(stolen).status_code == 401  # token is bound to B's own document
    # a recruiter with no application from A cannot view it either
    from app.db import SessionLocal
    from app.models import Document
    from app.security import decode_token, issue_download_token
    rid = decode_token(rtoken, "access")["sub"]
    assert client.get(f"/api/files/{doc['id']}?token={issue_download_token(doc['id'], rid)}").status_code == 404
    # expired / tampered link
    assert client.get(f"/api/files/{doc['id']}?token=garbage").status_code == 401
    # A replaces the marksheet; the old record is kept for audit and its file is removed
    new = client.put(f"/api/candidate/documents/{doc['id']}", files={"file": ("m2.pdf", PDF + b"v2", "application/pdf")}, headers=auth(a_token))
    assert new.status_code == 200
    kinds = [d["kind"] for d in client.get("/api/candidate/documents", headers=auth(a_token)).json()]
    assert kinds.count("marksheet") == 1
    with SessionLocal() as db:
        assert db.get(Document, doc["id"]).replaced_by_id == new.json()["id"]
    # uploaded files are not reachable as static files
    from app.models import Document as D
    with SessionLocal() as db:
        storage_name = db.get(D, new.json()["id"]).storage_name
    for path in (f"/uploads/{storage_name}", f"/data/uploads/{storage_name}", f"/assets/../../backend/data/uploads/{storage_name}"):
        assert PDF not in client.get(path).content


# ------------------------------------------------------------------ recruiter scoping & jobs

def test_recruiter_cannot_touch_other_org(client, otp_box):
    a_token, _ = register_recruiter(client)
    b_token, _ = register_recruiter(client)
    job = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(a_token)).json()
    ctoken, _ = register_candidate(client, otp_box)
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken)).json()["id"]
    assert client.get(f"/api/recruiter/jobs/{job['id']}", headers=auth(b_token)).status_code == 404
    assert client.put(f"/api/recruiter/jobs/{job['id']}", json=job_body(title="Hijack"), headers=auth(b_token)).status_code == 404
    assert client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(b_token)).status_code == 404
    assert client.post(f"/api/recruiter/applicants/{app_id}/status", json={"status": "shortlisted"}, headers=auth(b_token)).status_code == 404
    assert client.get("/api/recruiter/applicants", headers=auth(b_token)).json() == []
    # candidate cannot read someone else's application
    other, _ = register_candidate(client, otp_box)
    assert client.get(f"/api/candidate/applications/{app_id}", headers=auth(other)).status_code == 404


def test_job_edit_close_and_validation(client, otp_box):
    rtoken, _ = register_recruiter(client)
    bad = client.post("/api/recruiter/jobs", json=job_body(experienceMin=5, experienceMax=2, skills=[]), headers=auth(rtoken))
    assert bad.status_code == 422
    job = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(rtoken)).json()
    edited = client.put(f"/api/recruiter/jobs/{job['id']}", json=job_body(title="Senior Backend Developer"), headers=auth(rtoken)).json()
    assert edited["title"] == "Senior Backend Developer"
    ctoken, _ = register_candidate(client, otp_box)
    assert client.post(f"/api/recruiter/jobs/{job['id']}/close", headers=auth(rtoken)).json()["status"] == "closed"
    assert job["id"] not in [j["id"] for j in client.get("/api/jobs", headers=auth(ctoken)).json()]
    assert client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken)).status_code == 404


def test_profile_edit_and_validation(client, otp_box):
    ctoken, cdata = register_candidate(client, otp_box)
    h = auth(ctoken)
    prof = client.get("/api/candidate/profile", headers=h).json()
    assert prof["phoneVerified"] and len(prof["consents"]) == 2 and prof["education"][0]["institution"] == "Anna University"
    body = {"fullName": "Arun Kumar S", "email": cdata["email"], "phone": cdata["phone"], "location": "Coimbatore", "headline": "Python Developer",
            "linkedinUrl": "", "githubUrl": "https://github.com/arun", "skills": ["Python", "python", "SQL"],
            "education": prof["education"], "experience": [{"company": "Zoho", "title": "Intern", "start": "2025-05", "end": "2025-07", "current": False}],
            "references": [{"name": "Dr. Meena", "relationship": "Professor", "company": "Anna University", "email": "meena@au.example", "phone": ""}]}
    r = client.put("/api/candidate/profile", json=body, headers=h)
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["skills"] == ["Python", "SQL"] and p["experience"][0]["company"] == "Zoho" and p["references"][0]["name"] == "Dr. Meena"
    assert client.get("/api/candidate/profile", headers=h).json()["location"] == "Coimbatore"  # persisted
    body["githubUrl"] = "github.com/arun"
    assert client.put("/api/candidate/profile", json=body, headers=h).status_code == 422
    body["githubUrl"] = ""
    body["references"] = [{"name": "No Contact", "relationship": "Friend"}]
    assert client.put("/api/candidate/profile", json=body, headers=h).status_code == 422


def test_interview_scheduling(client, otp_box):
    rtoken, _ = register_recruiter(client)
    job = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(rtoken)).json()
    ctoken, _ = register_candidate(client, otp_box)
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken)).json()["id"]
    past = client.post("/api/recruiter/interviews", json={"applicationId": app_id, "scheduledAt": "2020-01-01T10:00:00Z", "durationMinutes": 45,
                                                         "mode": "video", "interviewer": "Ravi", "meetingLink": None}, headers=auth(rtoken))
    assert past.status_code == 400
    ok = client.post("/api/recruiter/interviews", json={"applicationId": app_id, "scheduledAt": "2099-01-01T10:00:00Z", "durationMinutes": 45,
                                                       "mode": "video", "interviewer": "Ravi", "meetingLink": "https://meet.example/x"}, headers=auth(rtoken))
    assert ok.status_code == 201, ok.text
    assert len(client.get("/api/candidate/interviews", headers=auth(ctoken)).json()) == 1
    assert client.get("/api/candidate/dashboard", headers=auth(ctoken)).json()["interviewsScheduled"] == 1


def test_empty_database_gives_zeroes(client):
    rtoken, _ = register_recruiter(client)
    d = client.get("/api/recruiter/dashboard", headers=auth(rtoken)).json()
    assert (d["totalApplicants"], d["inAssessment"], d["interviewsScheduled"], d["offersSent"], d["recentApplications"]) == (0, 0, 0, 0, [])
    assert client.get("/api/recruiter/reports", headers=auth(rtoken)).json()["flagsByCheck"] == []


def test_openapi_and_unknown_endpoint(client):
    spec = client.get("/api/openapi.json").json()
    assert "/api/jobs/{job_id}/apply" in spec["paths"] and "/api/auth/login" in spec["paths"]
    r = client.get("/api/does-not-exist")
    assert r.status_code == 404 and r.json()["code"] == "not_found"
