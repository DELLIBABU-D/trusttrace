"""Phase 6: evidence chain, QR passport, security hardening.

Synthetic data only (generated documents, public LFW test faces from OpenCV's test data).
"""
from __future__ import annotations

import base64
import json
from datetime import timedelta

import pytest
import synth
from test_phase2 import auth, job_body, register_recruiter
from test_phase3 import make_candidate, needs_face, needs_pymupdf, upload

from app.db import SessionLocal, engine
from app.evidence import chain, passport
from app.models import EvidenceEvent, PassportRecord, User, utcnow


def setup(client):
    rtoken, _ = register_recruiter(client)
    job = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(rtoken)).json()
    return rtoken, job


def cand_id(token):
    from test_phase3 import _uid
    with SessionLocal() as db:
        return db.query(User).filter_by(id=_uid(token)).one().candidate.id


def evidence(client, rtoken, app_id):
    r = client.get(f"/api/recruiter/applicants/{app_id}/evidence", headers=auth(rtoken))
    assert r.status_code == 200, r.text
    return r.json()


def clear_reviews(client, rtoken, app_id):
    """A recruiter reviews whatever still needs a decision (duplicate/pattern alerts) so the passport rules can be met."""
    rep = client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(rtoken)).json()
    for al in rep["duplicateAlerts"]:
        if al["reviewStatus"] == "open":
            assert client.post(f"/api/recruiter/applicants/{app_id}/duplicates/{al['id']}/review",
                               json={"status": "not_duplicate", "note": "Shared public test photo in this test run."}, headers=auth(rtoken)).status_code == 200
    for al in rep["patternAlerts"]:
        if al["reviewStatus"] == "open":
            assert client.post(f"/api/recruiter/applicants/{app_id}/patterns/{al['id']}/review",
                               json={"status": "reviewed_ok", "note": "Reviewed during the automated test."}, headers=auth(rtoken)).status_code == 200


def clean_application(client, otp_box):
    rtoken, job = setup(client)
    token, _ = make_candidate(client, otp_box)
    upload(client, token, "resume", synth.resume(grad=(2022, 2026)))
    upload(client, token, "marksheet", synth.marksheet(year=2026))
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(token)).json()["id"]
    return rtoken, token, app_id


def raw_sql(sql: str, params: tuple = ()) -> None:
    """Simulates a privileged person editing the database file directly (bypassing the app and its triggers)."""
    conn = engine.raw_connection()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


# ------------------------------------------------------------------------------------------- evidence chain

@needs_pymupdf
def test_evidence_chain_records_key_events_and_verifies(client, otp_box):
    rtoken, job = setup(client)
    token, user = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    upload(client, token, "marksheet", synth.marksheet(year=2024))
    upload(client, token, "marksheet", synth.marksheet(year=2025))  # replacement
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(token)).json()["id"]
    client.post(f"/api/recruiter/applicants/{app_id}/status", json={"status": "shortlisted", "note": ""}, headers=auth(rtoken))
    client.post(f"/api/recruiter/applicants/{app_id}/mark-reviewed", json={"note": "Looked at everything."}, headers=auth(rtoken))
    ev = evidence(client, rtoken, app_id)
    types = [e["type"] for e in ev["events"]]
    for t in ("candidate.registered", "document.uploaded", "document.replaced", "verification.result", "application.submitted",
              "recruiter.status_changed", "recruiter.report_reviewed"):
        assert t in types, t
    assert ev["verification"]["intact"] and ev["verification"]["events"] == len(ev["events"])
    seqs = [e["seq"] for e in ev["events"]]
    assert seqs == list(range(1, len(seqs) + 1))
    assert ev["events"][0]["prevHash"] == chain.GENESIS
    for a, b in zip(ev["events"], ev["events"][1:]):
        assert b["prevHash"] == a["hash"]  # every event links to the one before it
    # the replacement event names the replaced document's hash
    with SessionLocal() as db:
        rep = db.query(EvidenceEvent).filter_by(candidate_id=cand_id(token), event_type="document.replaced").one()
        assert rep.payload["replaces"][0]["sha256"] and rep.payload["sha256"] != rep.payload["replaces"][0]["sha256"]
        # payloads hold ids, statuses and hashes only: no contact details, names or document text
        blob = json.dumps([e.payload for e in db.query(EvidenceEvent).filter_by(candidate_id=cand_id(token))])
        for secret in (user["email"], user["phone"], "Arun Kumar", "Anna University", "Looked at everything"):
            assert secret not in blob
    assert "cannot stop someone with full control" in ev["note"]


@needs_pymupdf
def test_tampering_with_stored_events_is_detected(client, otp_box):
    rtoken, job = setup(client)
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    upload(client, token, "marksheet", synth.marksheet(year=2026))
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(token)).json()["id"]
    cid = cand_id(token)
    assert evidence(client, rtoken, app_id)["verification"]["intact"]
    # 1) the app's own database connection cannot edit or delete evidence (append-only triggers)
    with SessionLocal() as db:
        e = db.query(EvidenceEvent).filter_by(candidate_id=cid, seq=2).one()
        e.payload = {**e.payload, "sha256": "0" * 64}
        with pytest.raises(Exception, match="append-only"):
            db.commit()
        db.rollback()
        db.delete(db.query(EvidenceEvent).filter_by(candidate_id=cid, seq=1).one())
        with pytest.raises(Exception, match="append-only"):
            db.commit()
    # 2) someone with direct file access drops the trigger and edits history: verification pinpoints it
    raw_sql("DROP TRIGGER evidence_events_no_update")
    raw_sql("DROP TRIGGER evidence_events_no_delete")
    try:
        with SessionLocal() as db:
            e2 = db.query(EvidenceEvent).filter_by(candidate_id=cid, seq=2).one()
            tampered = json.dumps({**e2.payload, "sha256": "f" * 64})
        raw_sql("UPDATE evidence_events SET payload = ? WHERE candidate_id = ? AND seq = 2", (tampered, cid))
        v = evidence(client, rtoken, app_id)["verification"]
        assert not v["intact"] and {"seq": 2, "reason": "payload_modified"}.items() <= v["problems"][0].items()
        # rewriting the payload hash too is caught by the HMAC (needs the server key to forge)
        raw_sql("UPDATE evidence_events SET payload_hash = ? WHERE candidate_id = ? AND seq = 2",
                (chain.sha256(chain.canonical(json.loads(tampered))), cid))
        v = evidence(client, rtoken, app_id)["verification"]
        assert [p["reason"] for p in v["problems"] if p["seq"] == 2] == ["hash_mismatch"]
        # deleting an event breaks the sequence and the link
        raw_sql("DELETE FROM evidence_events WHERE candidate_id = ? AND seq = 3", (cid,))
        reasons = {p["reason"] for p in evidence(client, rtoken, app_id)["verification"]["problems"]}
        assert {"missing_events", "broken_link"} <= reasons
        # changing the time of an event is caught as well
        raw_sql("UPDATE evidence_events SET at = '2020-01-01 00:00:00.000000' WHERE candidate_id = ? AND seq = 1", (cid,))
        assert any(p["seq"] == 1 and p["reason"] == "hash_mismatch" for p in evidence(client, rtoken, app_id)["verification"]["problems"])
    finally:
        for table, of in (("evidence_events", ""),):
            raw_sql(f"CREATE TRIGGER IF NOT EXISTS {table}_no_update BEFORE UPDATE {of}ON {table} BEGIN SELECT RAISE(ABORT, 'audit records are append-only'); END;")
            raw_sql(f"CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table} BEGIN SELECT RAISE(ABORT, 'audit records are append-only'); END;")


@needs_pymupdf
def test_other_organisations_see_only_masked_entries(client, otp_box):
    rtoken, job = setup(client)
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    app1 = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(token)).json()["id"]
    client.post(f"/api/recruiter/applicants/{app1}/decision", json={"decision": "reverify", "reason": "Please upload a clearer marksheet."},
                headers=auth(rtoken))
    rtoken2, job2 = setup(client)
    app2 = client.post(f"/api/jobs/{job2['id']}/apply", headers=auth(token)).json()["id"]
    mine = evidence(client, rtoken, app1)["events"]
    theirs = evidence(client, rtoken2, app2)
    assert any(e["type"] == "recruiter.decision" for e in mine)
    assert not any(e["type"] in ("recruiter.decision", "recruiter.status_changed") for e in theirs["events"])
    hidden = [e for e in theirs["events"] if e["hidden"]]
    assert hidden and all(e["label"] == "Activity at another organisation" and e["applicationId"] is None for e in hidden)
    assert theirs["verification"]["intact"]  # the whole chain is still checked
    # recruiters of other organisations and candidates cannot reach these endpoints
    assert client.get(f"/api/recruiter/applicants/{app1}/evidence", headers=auth(rtoken2)).status_code == 404
    assert client.get(f"/api/recruiter/applicants/{app1}/evidence", headers=auth(token)).status_code == 403
    assert client.get(f"/api/recruiter/applicants/{app1}/evidence").status_code == 401
    assert client.get(f"/api/recruiter/applicants/{app1}/passport", headers=auth(rtoken2)).status_code == 404
    assert client.post(f"/api/recruiter/applicants/{app1}/passport", headers=auth(token)).status_code == 403


# ------------------------------------------------------------------------------------------- passport

@needs_pymupdf
@needs_face
def test_passport_issue_and_public_verification(client, otp_box):
    rtoken, token, app_id = clean_application(client, otp_box)
    clear_reviews(client, rtoken, app_id)
    view = client.get(f"/api/recruiter/applicants/{app_id}/passport", headers=auth(rtoken)).json()
    assert view["eligibility"]["eligible"], view["eligibility"]
    r = client.post(f"/api/recruiter/applicants/{app_id}/passport", headers=auth(rtoken))
    assert r.status_code == 201, r.text
    p = r.json()["active"]
    assert p["status"] == "active" and p["passportId"].startswith("TTP-") and p["candidateRef"].startswith("TTC-")
    checks = {c["key"]: c for c in p["checks"]}
    assert checks["identity"]["status"] == "verified" and checks["phone"]["status"] == "verified"
    assert checks["education"]["status"] == "consistent" and "not independently confirmed" in checks["education"]["text"]
    assert checks["issuer"]["status"] in ("pending", "not_started")  # never "verified" without a real confirmation
    assert p["issuedAt"] and p["expiresAt"] and p["reportVersion"]
    # minimal data: no photo, phone, email, date of birth, embeddings or score in the signed token
    claims = json.loads(base64.urlsafe_b64decode(p["token"].split(".")[1] + "=="))
    blob = json.dumps(claims)
    with SessionLocal() as db:
        from app.models import Candidate
        u = db.get(Candidate, db.query(PassportRecord).filter_by(public_id=p["passportId"]).one().candidate_id).user
        for secret in (u.email, u.phone, u.full_name, "photo", "embedding", "score\":"):
            assert secret not in blob
    assert set(claims) == {"v", "typ", "pid", "kid", "sub", "iss", "role", "c", "sim", "sk", "rv", "ch", "iat", "exp"}
    # QR points at the controlled verification page and is a real, decodable QR code
    assert p["verifyUrl"].endswith("/verify/" + p["passportId"]) and p["tokenUrl"].endswith("/verify/" + p["token"])
    assert p["qrDataUrl"].startswith("data:image/svg+xml;base64,")
    import cv2
    params = cv2.QRCodeEncoder_Params()
    params.correction_level = cv2.QRCodeEncoder_CORRECT_LEVEL_L
    m = cv2.QRCodeEncoder_create(params).encode(p["verifyUrl"])
    assert cv2.QRCodeDetector().detectAndDecode(cv2.resize(m, None, fx=6, fy=6, interpolation=cv2.INTER_NEAREST))[0] == p["verifyUrl"]
    # public verification (no login)
    v = client.get(f"/api/passport/verify/{p['token']}").json()
    assert v["result"] == "valid" and v["signature"] == "valid" and v["chain"]["intact"] and v["passport"]["passportId"] == p["passportId"]
    assert client.get(f"/api/passport/verify/{p['passportId']}").json()["result"] == "valid"  # what the QR code opens
    assert client.get("/api/passport/verify/TTP-ZZZZZZZZZZ").json()["result"] == "unknown"
    key = client.get("/api/passport/public-key").json()
    assert key["alg"] == "Ed25519" and key["kid"] == claims["kid"]
    # the candidate sees it too
    mine = client.get("/api/candidate/passport", headers=auth(token)).json()
    assert mine["passports"][0]["passportId"] == p["passportId"] and mine["chain"]["intact"]
    ev = evidence(client, rtoken, app_id)["events"]
    assert ev[-1]["type"] == "passport.issued"


@needs_pymupdf
@needs_face
def test_passport_tampering_expiry_revocation_and_supersession(client, otp_box):
    rtoken, token, app_id = clean_application(client, otp_box)
    clear_reviews(client, rtoken, app_id)
    p = client.post(f"/api/recruiter/applicants/{app_id}/passport", headers=auth(rtoken)).json()["active"]
    head, body, sig = p["token"].split(".")
    # editing a claim (e.g. upgrading a status) breaks the signature
    claims = json.loads(base64.urlsafe_b64decode(body + "=="))
    claims["c"]["issuer"] = "verified"
    forged = head + "." + base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode() + "." + sig
    assert client.get(f"/api/passport/verify/{forged}").json()["result"] == "invalid"
    assert client.get("/api/passport/verify/not-a-token").json()["result"] == "invalid"
    assert client.get(f"/api/passport/verify/{head}.{body}.{'A' * 86}").json()["result"] == "invalid"
    # expiry is checked on the server
    with SessionLocal() as db:
        rec = db.query(PassportRecord).filter_by(public_id=p["passportId"]).one()
        real_exp, rec.expires_at = rec.expires_at, utcnow() - timedelta(minutes=1)
        db.commit()
    assert client.get(f"/api/passport/verify/{p['token']}").json()["result"] == "expired"
    with SessionLocal() as db:
        db.query(PassportRecord).filter_by(public_id=p["passportId"]).one().expires_at = real_exp
        db.commit()
    assert client.get(f"/api/passport/verify/{p['token']}").json()["result"] == "valid"
    # revocation needs a reason and is reported publicly
    assert client.post(f"/api/recruiter/applicants/{app_id}/passport/revoke", json={"reason": "short"}, headers=auth(rtoken)).status_code == 422
    r = client.post(f"/api/recruiter/applicants/{app_id}/passport/revoke", json={"reason": "Candidate asked us to withdraw it."}, headers=auth(rtoken))
    assert r.status_code == 200 and r.json()["active"] is None and r.json()["history"][0]["status"] == "revoked"
    v = client.get(f"/api/passport/verify/{p['token']}").json()
    assert v["result"] == "revoked" and "withdraw" in v["message"]
    # regenerate, then a significant change (new marksheet with a different year) supersedes it automatically
    p2 = client.post(f"/api/recruiter/applicants/{app_id}/passport", headers=auth(rtoken)).json()["active"]
    assert p2["passportId"] != p["passportId"]
    upload(client, token, "marksheet", synth.marksheet(year=2023))
    client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(rtoken))
    v2 = client.get(f"/api/passport/verify/{p2['token']}").json()
    assert v2["result"] == "superseded"
    view = client.get(f"/api/recruiter/applicants/{app_id}/passport", headers=auth(rtoken)).json()
    assert view["active"] is None and not view["eligibility"]["eligible"]  # the new inconsistency needs review first
    assert client.post(f"/api/recruiter/applicants/{app_id}/passport", headers=auth(rtoken)).status_code == 409
    # a rewrite of history before the pinned chain head is detected against the issued passport
    types = [e["type"] for e in evidence(client, rtoken, app_id)["events"]]
    assert types.count("passport.issued") == 2 and "passport.revoked" in types and "passport.superseded" in types


@needs_pymupdf
def test_ineligible_candidate_gets_reasons_not_a_passport(client, otp_box):
    rtoken, job = setup(client)
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())  # no face -> identity can't be verified
    upload(client, token, "marksheet", synth.marksheet(year=2024))  # year mismatch -> inconsistent
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(token)).json()["id"]
    view = client.get(f"/api/recruiter/applicants/{app_id}/passport", headers=auth(rtoken)).json()
    reasons = " ".join(view["eligibility"]["reasons"])
    assert not view["eligibility"]["eligible"] and "Identity is not verified" in reasons and "Education documents" in reasons
    r = client.post(f"/api/recruiter/applicants/{app_id}/passport", headers=auth(rtoken))
    assert r.status_code == 409 and r.json()["code"] == "passport_not_eligible"
    assert client.get("/api/candidate/passport", headers=auth(token)).json()["passports"] == []


def test_signature_helpers_reject_other_keys():
    claims = {"v": 1, "pid": "TTP-TEST", "kid": passport.keys()[2]}
    tok = passport.sign(claims)
    assert passport.decode(tok)[0] == claims
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    other = Ed25519PrivateKey.generate()
    body = tok.split(".")[1]
    fake = f"TT1.{body}." + base64.urlsafe_b64encode(other.sign(f"TT1.{body}".encode())).rstrip(b"=").decode()
    assert passport.decode(fake) == (None, "bad_signature")


# ------------------------------------------------------------------------------------------- security hardening

def test_oversized_requests_and_long_pdfs_are_refused(client, otp_box):
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    big = b"%PDF-1.4\n" + b"0" * (13 * 1024 * 1024)
    r = client.post("/api/candidate/documents", files={"resume": ("big.pdf", big, "application/pdf")}, headers=auth(token))
    assert r.status_code == 413
    from app.verification import textract
    fitz = textract.pymupdf()
    if fitz:
        doc = fitz.open()
        for _ in range(textract.MAX_PDF_PAGES + 1):
            doc.new_page().insert_text((72, 72), "page")
        res = textract.extract(doc.tobytes(), "application/pdf")
        assert res.status == "failed" and "at most" in res.error
    from app.verification import face
    import numpy as np
    import cv2
    huge = cv2.imencode(".png", np.zeros((7000, 7000), dtype=np.uint8))[1].tobytes()  # 49 megapixels, small file
    assert face.decode(huge) is None
    r = client.post("/api/candidate/documents", files={"certificate": ("huge.png", huge, "image/png")}, headers=auth(token))
    assert r.status_code == 413 and r.json()["code"] == "image_too_large"


def test_security_headers_and_path_traversal(client):
    r = client.get("/")
    assert "frame-ancestors 'none'" in r.headers.get("content-security-policy", "") and r.headers["x-content-type-options"] == "nosniff"
    assert client.get("/api/health").headers["cache-control"] == "no-store"
    for path in ("/..%2f..%2fbackend%2fdata%2ftrusttrace.db", "/../backend/app/config.py", "/%2e%2e/%2e%2e/backend/data/secret.key"):
        r = client.get(path)
        assert b"TT_SECRET_KEY" not in r.content and b"SQLite format" not in r.content
    assert client.get("/api/files/whatever?token=forged").status_code in (401, 403, 404)


@needs_pymupdf
def test_consent_withdrawal_erasure_and_suspended_orgs(client, otp_box):
    import manage
    rtoken, token, app_id = clean_application(client, otp_box)
    rep = client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(rtoken)).json()
    assert rep["candidate"]["photoUrl"]
    client.post("/api/candidate/consents", json={"purpose": "biometric", "granted": False}, headers=auth(token))
    rep = client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(rtoken)).json()
    assert rep["candidate"]["photoUrl"] is None  # biometric photo hidden while consent is withdrawn
    from app.models import FaceCheck, FaceEnrollment
    cid = cand_id(token)
    with SessionLocal() as db:
        assert db.query(FaceEnrollment).filter_by(candidate_id=cid).count() == 0 and db.query(FaceCheck).filter_by(candidate_id=cid).count() == 0
    # right to erasure
    from test_phase3 import _uid
    with SessionLocal() as db:
        email = db.get(User, _uid(token)).email
        files = [d.storage_name for d in db.query(__import__("app.models", fromlist=["Document"]).Document).filter_by(candidate_id=cid)]
    manage.erase_candidate(email)
    from app import storage
    assert files and all(storage.path_for(f) is None for f in files)  # files are gone
    assert client.get("/api/candidate/dashboard", headers=auth(token)).status_code == 401
    rep = client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(rtoken)).json()
    assert rep["candidate"]["fullName"] == "Erased candidate" and rep["candidate"]["phone"] == ""
    assert evidence(client, rtoken, app_id)["verification"]["intact"]  # audit chain holds no personal data, so it stays valid
    # a suspended organisation can no longer act
    with SessionLocal() as db:
        db.get(User, _uid(rtoken)).organization.status = "suspended"
        db.commit()
    assert client.get("/api/recruiter/dashboard", headers=auth(rtoken)).status_code == 403
