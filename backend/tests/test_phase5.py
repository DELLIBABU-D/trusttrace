"""Phase 5: suspicious patterns, relationship graph, explainable trust score, recruiter decision support, auditability.

Synthetic data only (generated documents, public LFW test faces from OpenCV's test data).
"""
from __future__ import annotations

import json
import uuid

import pytest
import synth
from test_phase2 import auth, job_body, register_recruiter
from test_phase3 import make_candidate, needs_face, needs_pymupdf, upload

from app.fraud import config


def apply(client, token, job_id, device=None):
    return client.post(f"/api/jobs/{job_id}/apply", headers=auth(token) | ({"X-TT-Device": device} if device else {}))


def report(client, rtoken, app_id):
    r = client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(rtoken))
    assert r.status_code == 200, r.text
    return r.json()


def entries(rep, applied_only=True):
    return {e["ruleId"]: e for e in rep["trust"]["entries"] if (e["applied"] != 0 or not applied_only)}


def setup(client):
    rtoken, _ = register_recruiter(client)
    job = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(rtoken)).json()
    return rtoken, job


# ------------------------------------------------------------------------------------------- explainable score

@needs_pymupdf
@needs_face
def test_clean_vs_inconsistent_candidates(client, otp_box):
    rtoken, job = setup(client)
    clean, _ = make_candidate(client, otp_box)
    upload(client, clean, "resume", synth.resume(grad=(2022, 2026)))
    upload(client, clean, "marksheet", synth.marksheet(year=2026))
    messy, _ = make_candidate(client, otp_box, id_doc=synth.face_jpeg("Aaron_Tippin_0001.jpg"))  # ID photo of a different person
    upload(client, messy, "resume", synth.resume(grad=(2021, 2025)))
    upload(client, messy, "marksheet", synth.marksheet(year=2024))
    a_clean = apply(client, clean, job["id"]).json()["id"]
    a_messy = apply(client, messy, job["id"]).json()["id"]
    rc, rm = report(client, rtoken, a_clean), report(client, rtoken, a_messy)
    ec, em = entries(rc), entries(rm)
    # (other tests in this session enrolled the same public test face, so a face-duplicate alert is expected and correct here)
    assert {"ID.PHONE_OTP", "ID.FACE_ID_MATCH", "EDU.CONSISTENT", "RES.CONSISTENT"} <= set(ec)
    assert not any(e["applied"] < 0 for k, e in ec.items() if not k.startswith("DUP."))
    assert {"ID.FACE_ID_MISMATCH", "EDU.INCONSISTENT", "RES.INCONSISTENT"} <= set(em)
    assert rc["trustScore"] > config.BASELINE > rm["trustScore"]
    # every point is explained: score = baseline + sum of applied weights, clamped; each entry has evidence + timestamp
    for rep in (rc, rm):
        t = rep["trust"]
        assert t["score"] == max(0, min(100, t["baseline"] + sum(e["applied"] for e in t["entries"]))) == rep["trustScore"]
        for e in t["entries"]:
            assert e["evidence"] and e["at"] and e["weight"] == config.current()["rules"][e["ruleId"]]["weight"]
    # inconsistencies are review items, never automatic rejections
    assert rm["status"] == "applied"
    assert "not a measure of a person's honesty" in rm["trust"]["disclaimer"]


@needs_pymupdf
def test_score_adjustments_match_saved_evidence(client, otp_box):
    rtoken, job = setup(client)
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    upload(client, token, "marksheet", synth.marksheet(year=2024))
    app_id = apply(client, token, job["id"]).json()["id"]
    rep = report(client, rtoken, app_id)
    from app.db import SessionLocal
    from app.models import ScoreRecord, VerificationRun
    with SessionLocal() as db:
        for e in rep["trust"]["entries"]:
            for ev in e["evidence"]:
                if ev["type"] == "verification_run":
                    run = db.get(VerificationRun, ev["id"])
                    assert run is not None and run.candidate_id  # the evidence is a real saved run
        stored = db.get(ScoreRecord, rep["trust"]["scoreRecordId"])
        assert stored.score == rep["trustScore"] and stored.ruleset_version == rep["trust"]["version"]
    edu = entries(rep)["EDU.INCONSISTENT"]
    assert any(ev["type"] == "finding" and ev["id"] == "education_year_mismatch" for ev in edu["evidence"])


@needs_pymupdf
def test_pending_and_simulated_checks_get_no_credit(client, otp_box, tmp_path):
    import manage
    rtoken, job = setup(client)
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    upload(client, token, "marksheet", synth.marksheet(reg="AU2026SIMX", year=2026))
    app_id = apply(client, token, job["id"]).json()["id"]
    rep = report(client, rtoken, app_id)
    checks = {c["key"]: c for c in rep["trust"]["checks"]}
    assert checks["issuer"]["bucket"] == "pending" and "EDU.ISSUER_CONFIRMED" not in entries(rep)
    assert checks["education"]["bucket"] == "consistent"  # consistent documents are not "verified"
    assert checks["employment"]["bucket"] == "not_started" and not any(k.startswith("EMP.") for k in entries(rep))
    # a SIMULATED issuer record matches but still gives no credit
    csv = tmp_path / "issuers.csv"
    csv.write_text("issuer,register_number,student_name,qualification,year\nAnna University,AU2026SIMX,Arun Kumar,B.E. CSE,2026\n")
    manage.load_issuer_records(str(csv))
    client.post("/api/candidate/verification/run", headers=auth(token))
    rep = report(client, rtoken, app_id)
    issuer = next(c for c in rep["trust"]["checks"] if c["key"] == "issuer")
    assert issuer["simulated"] and issuer["bucket"] == "pending" and "EDU.ISSUER_CONFIRMED" not in entries(rep)
    # a reference request that hasn't been answered stays pending
    rr = client.post(f"/api/recruiter/applicants/{app_id}/reference-requests", json={"refereeName": "HR Desk", "refereeContact": "hr@x.example"},
                     headers=auth(rtoken))
    assert rr.status_code == 201
    client.post("/api/candidate/verification/run", headers=auth(token))
    rep = report(client, rtoken, app_id)
    ref = next(c for c in rep["trust"]["checks"] if c["key"].startswith("ref-"))
    assert ref["bucket"] == "pending" and "EMP.REFERENCE_CONFIRMED" not in entries(rep)


@needs_pymupdf
def test_document_update_and_resolution_recompute_the_report(client, otp_box):
    rtoken, job = setup(client)
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    doc = upload(client, token, "marksheet", synth.marksheet(year=2024))
    app_id = apply(client, token, job["id"]).json()["id"]
    before = report(client, rtoken, app_id)
    assert "EDU.INCONSISTENT" in entries(before)
    # recruiter resolves the concern with an explanation -> penalty removed, evidence kept, new score record
    r = client.post(f"/api/recruiter/applicants/{app_id}/checks/education/review",
                    json={"status": "resolved", "note": "Candidate showed the revaluation certificate; 2024 is the original exam year."}, headers=auth(rtoken))
    assert r.status_code == 200
    resolved = entries(r.json(), applied_only=False)["EDU.INCONSISTENT"]
    assert resolved["status"] == "resolved" and resolved["applied"] == 0 and any(ev["type"] == "check_review" for ev in resolved["evidence"])
    after = report(client, rtoken, app_id)
    assert after["trustScore"] == before["trustScore"] + 10
    # an unrelated re-run keeps the resolution (same document, same findings)
    client.post("/api/candidate/verification/run", headers=auth(token))
    assert report(client, rtoken, app_id)["trustScore"] == after["trustScore"]
    # replacing the document is new evidence -> recomputed from scratch
    client.put(f"/api/candidate/documents/{doc['id']}", files={"file": ("m.pdf", synth.marksheet(year=2026), "application/pdf")}, headers=auth(token))
    fixed = report(client, rtoken, app_id)
    assert "EDU.CONSISTENT" in entries(fixed) and "EDU.INCONSISTENT" not in entries(fixed, applied_only=False)
    hist = client.get(f"/api/recruiter/applicants/{app_id}/score-history", headers=auth(rtoken)).json()
    assert len(hist) >= 3 and any(h["trigger"] == "check_reviewed" for h in hist)
    assert all(h["version"] == config.current()["version"] for h in hist)


def test_assessment_score_is_reported_separately(client, otp_box):
    rtoken, job = setup(client)
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    app_id = apply(client, token, job["id"]).json()["id"]
    before = report(client, rtoken, app_id)["trustScore"]
    h = auth(rtoken)
    client.post(f"/api/recruiter/jobs/{job['id']}/assessment/generate", json={"count": 3, "source": "bank"}, headers=h)
    t = client.get(f"/api/recruiter/jobs/{job['id']}/assessment", headers=h).json()["template"]
    for q in t["questions"]:
        client.post(f"/api/recruiter/assessment-questions/{q['id']}/approve", headers=h)
    client.post(f"/api/recruiter/jobs/{job['id']}/assessment/publish", headers=h)
    att = client.get("/api/candidate/assessments", headers=auth(token)).json()[0]
    client.post(f"/api/candidate/assessments/{att['id']}/start", json={"cameraConsent": False}, headers=auth(token))
    client.post(f"/api/candidate/assessments/{att['id']}/submit", json={"answers": {}}, headers=auth(token))  # 0 correct
    rep = report(client, rtoken, app_id)
    assert rep["trustScore"] == before and rep["trust"]["assessment"][0]["score"] == 0
    assert not any(e["category"] == "assessment" for e in rep["trust"]["entries"])


def test_score_is_clamped_and_rules_are_versioned(client, otp_box, tmp_path, monkeypatch):
    cfg = tmp_path / "fraud.json"
    cfg.write_text(json.dumps({"rules": {"ID.PHONE_OTP": 500}}))
    monkeypatch.setenv("TT_FRAUD_CONFIG", str(cfg))
    rtoken, job = setup(client)
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    app_id = apply(client, token, job["id"]).json()["id"]
    rep = report(client, rtoken, app_id)
    assert rep["trust"]["rawScore"] == 580 and rep["trustScore"] == 100
    from app.db import SessionLocal
    from app.models import ScoringRuleset
    with SessionLocal() as db:
        assert db.get(ScoringRuleset, rep["trust"]["version"]).rules["rules"]["ID.PHONE_OTP"]["weight"] == 500  # the changed ruleset is logged
    monkeypatch.delenv("TT_FRAUD_CONFIG")
    assert report(client, rtoken, app_id)["trust"]["version"] != rep["trust"]["version"]


# ------------------------------------------------------------------------------------------- patterns

def test_rapid_applications_and_repeated_submissions(client, otp_box):
    rtoken, _ = register_recruiter(client)
    jobs = [client.post("/api/recruiter/jobs", json=job_body(title=f"Role {i}"), headers=auth(rtoken)).json() for i in range(6)]
    slow, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    for j in jobs[:4]:  # below the threshold of 5
        apply(client, slow, j["id"])
    fast, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    for j in jobs[:5]:
        apply(client, fast, j["id"])
    for _ in range(3):
        assert apply(client, fast, jobs[0]["id"]).status_code == 409
    from app.db import SessionLocal
    from app.models import PatternAlert, User
    from app.security import decode_token
    with SessionLocal() as db:
        cid = lambda t: db.query(User).filter_by(id=decode_token(t, "access")["sub"]).one().candidate.id  # noqa: E731
        assert db.query(PatternAlert).filter_by(candidate_id=cid(slow)).count() == 0
        rules = {a.rule_id: a for a in db.query(PatternAlert).filter_by(candidate_id=cid(fast))}
    assert set(rules) == {"P1.RAPID_APPLICATIONS", "P2.REPEATED_SUBMISSIONS"}
    assert rules["P1.RAPID_APPLICATIONS"].evidence["applications"] == 5 and rules["P2.REPEATED_SUBMISSIONS"].evidence["attempts"] == 3
    app_id = client.get("/api/candidate/applications", headers=auth(fast)).json()[0]["id"]
    rep = report(client, rtoken, app_id)
    pa = {p["ruleId"]: p for p in rep["patternAlerts"]}
    assert pa["P1.RAPID_APPLICATIONS"]["reviewStatus"] == "open" and pa["P1.RAPID_APPLICATIONS"]["explanation"]
    assert sum(e["applied"] for e in rep["trust"]["entries"] if e["ruleId"] == "PAT.OPEN_ALERT") == -4
    # human review: "reviewed – OK" removes the penalty and is audited
    r = client.post(f"/api/recruiter/applicants/{app_id}/patterns/{pa['P1.RAPID_APPLICATIONS']['id']}/review",
                    json={"status": "reviewed_ok", "note": "Called the candidate; applied to several openings from a campus drive."}, headers=auth(rtoken))
    assert r.status_code == 200 and sum(e["applied"] for e in r.json()["trust"]["entries"] if e["ruleId"] == "PAT.OPEN_ALERT") == -2
    with SessionLocal() as db:
        from app.models import ActivityEvent
        assert db.query(ActivityEvent).filter_by(action="pattern.reviewed").count() >= 1


def _register_with_device(client, otp_box, device, phone=None, name="Arun Kumar"):
    phone = phone or "9" + str(uuid.uuid4().int)[:9]
    client.post("/api/auth/otp", json={"phone": phone})
    payload = {"fullName": name, "email": f"d{uuid.uuid4().hex[:10]}@mail.example", "phone": phone, "otp": otp_box[phone], "dateOfBirth": "2003-01-01",
               "password": "Candidat3Pass", "education": [{"degree": "BSc", "institution": "College", "startYear": "2020", "endYear": "2023", "score": ""}],
               "experience": [], "selfie": synth.data_url(synth.blank_jpeg()), "consent": True}
    r = client.post("/api/candidates/register", data={"payload": json.dumps(payload)}, files={"idDocument": ("id.png", synth.blank_jpeg(), "image/jpeg")},
                    headers={"X-TT-Device": device})
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_shared_device_graph_and_privacy(client, otp_box):
    rtoken, job = setup(client)
    device = "browser-" + uuid.uuid4().hex
    a = _register_with_device(client, otp_box, device, name="First Person")
    b = _register_with_device(client, otp_box, device, name="Second Person")
    shared_phone = "9" + str(uuid.uuid4().int)[:9]
    c = _register_with_device(client, otp_box, "other-" + uuid.uuid4().hex, phone=shared_phone, name="Third Person")
    d = _register_with_device(client, otp_box, "other-" + uuid.uuid4().hex, phone=shared_phone, name="Fourth Person")
    loner = _register_with_device(client, otp_box, "solo-" + uuid.uuid4().hex, name="First Person")  # same NAME as a, nothing else shared
    app_a = apply(client, a, job["id"], device).json()["id"]
    app_c = apply(client, c, job["id"]).json()["id"]
    app_l = apply(client, loner, job["id"]).json()["id"]
    g = client.get(f"/api/recruiter/applicants/{app_a}/graph", headers=auth(rtoken)).json()
    assert len(g["linked"]) == 1 and g["linked"][0]["strongest"] == "medium" and g["linked"][0]["signals"][0]["kind"] == "device"
    other = g["linked"][0]["account"]
    assert other.startswith("Candidate account …") and "Second Person" not in json.dumps(g)  # b didn't apply to this org -> masked
    assert "not a confirmed fraud ring" in g["note"]
    assert {p["ruleId"] for p in report(client, rtoken, app_a)["patternAlerts"]} >= {"P3.SHARED_DEVICE"}
    # strong link: same verified phone; d applied to this org, so the recruiter may see the name
    apply(client, d, job["id"])
    gc = client.get(f"/api/recruiter/applicants/{app_c}/graph", headers=auth(rtoken)).json()
    assert gc["linked"][0]["strongest"] == "strong" and gc["linked"][0]["account"] == "Fourth Person" and gc["linked"][0]["applicationId"]
    assert gc["clusterSize"] == 2
    # a matching name alone links nothing
    assert client.get(f"/api/recruiter/applicants/{app_l}/graph", headers=auth(rtoken)).json()["linked"] == []
    # the raw browser id is never stored
    from app.db import SessionLocal
    from app.models import DeviceSighting
    with SessionLocal() as db:
        assert all(device not in (s.device_hash or "") for s in db.query(DeviceSighting))
        # the alert is symmetric: the account that registered first is flagged too, not only the newest one
        from app.models import PatternAlert, User
        from app.security import decode_token
        for tok in (a, b):
            cid = db.query(User).filter_by(id=decode_token(tok, "access")["sub"]).one().candidate.id
            assert db.query(PatternAlert).filter_by(candidate_id=cid, rule_id="P3.SHARED_DEVICE").count() == 1


# ------------------------------------------------------------------------------------------- access control & audit

def test_access_control_and_audit_records(client, otp_box):
    rtoken, job = setup(client)
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    app_id = apply(client, token, job["id"]).json()["id"]
    other, _ = register_recruiter(client)
    for path in (f"/report", "/graph", "/score-history"):
        assert client.get(f"/api/recruiter/applicants/{app_id}{path}", headers=auth(other)).status_code == 404
    assert client.post(f"/api/recruiter/applicants/{app_id}/mark-reviewed", json={}, headers=auth(other)).status_code == 404
    assert client.post(f"/api/recruiter/applicants/{app_id}/checks/education/review", json={"status": "resolved", "note": "x" * 12},
                       headers=auth(other)).status_code == 404
    assert client.get(f"/api/recruiter/applicants/{app_id}/graph", headers=auth(token)).status_code == 403
    assert client.get("/api/recruiter/scoring/rules", headers=auth(token)).status_code == 403
    # mark reviewed is tied to the exact score version
    r = client.post(f"/api/recruiter/applicants/{app_id}/mark-reviewed", json={"note": "Checked all evidence."}, headers=auth(rtoken)).json()
    assert r["reportReviews"][0]["current"] and r["reportReviews"][0]["score"] == r["trust"]["score"]
    # audit records can't be edited or deleted, even directly in the database
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    from app.db import SessionLocal
    with SessionLocal() as db:
        for sql in ("UPDATE score_records SET score = 100", "DELETE FROM score_records", "UPDATE activity_events SET action = 'x'",
                    "DELETE FROM report_reviews", "UPDATE scoring_rulesets SET rules = '{}'"):
            with pytest.raises(DBAPIError, match="append-only"):
                db.execute(text(sql))
            db.rollback()
    # no API exists to change a score
    assert client.put(f"/api/recruiter/applicants/{app_id}/score", json={"score": 100}, headers=auth(rtoken)).status_code in (404, 405)


def test_dashboard_and_applicant_list_use_real_data(client, otp_box):
    rtoken, job = setup(client)
    t1, _ = make_candidate(client, otp_box, name="Zara Khan", selfie=synth.blank_jpeg())
    t2, _ = make_candidate(client, otp_box, name="Anil Mehta", selfie=synth.blank_jpeg())
    apply(client, t1, job["id"])
    apply(client, t2, job["id"])
    d = client.get("/api/recruiter/dashboard", headers=auth(rtoken)).json()
    assert d["totalApplicants"] == 2 and set(d["reviewQueue"]) >= {"applicationsNeedingReview", "openDuplicateAlerts", "openPatternAlerts", "pendingChecks"}
    assert d["verificationSummary"]["identity"] and d["assessmentSummary"]["assigned"] == 0
    names = [r["candidateName"] for r in client.get("/api/recruiter/applicants?sort=name", headers=auth(rtoken)).json()]
    assert names == ["Anil Mehta", "Zara Khan"]
    rows = client.get("/api/recruiter/applicants?sort=score_desc", headers=auth(rtoken)).json()
    assert rows[0]["trustScore"] >= rows[1]["trustScore"] and "pendingCount" in rows[0] and "risk" in rows[0]
    assert client.get("/api/recruiter/applicants?search=zara", headers=auth(rtoken)).json()[0]["candidateName"] == "Zara Khan"
