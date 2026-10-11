"""DigiLocker comparison: simulated flow (labelled, never counted) and the live partner-API flow against a fake
DigiLocker server (PKCE, token exchange, issued list, XML download with HMAC header)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import urllib.parse

import pytest
import synth
from test_phase2 import auth, job_body, register_recruiter
from test_phase3 import _uid, make_candidate, needs_pymupdf, upload

from app import config
from app.db import SessionLocal
from app.models import DigiLockerDocument, DigiLockerLink, DigiLockerSimRecord, User
from app.verification import digilocker as dlk

SECRET = "test-client-secret"


def connect(client, token):
    r = client.post("/api/candidate/digilocker/start", json={"consent": True}, headers=auth(token))
    assert r.status_code == 200, r.text
    return r.json()["authorizeUrl"]


def sim_records(name, year=2026, reg="SAMPLE2026CS001", mobile=""):
    with SessionLocal() as db:
        db.add(DigiLockerSimRecord(mobile=mobile, holder_name=name, issuer="Anna University", register_number=reg,
                                   degree="Bachelor of Engineering", year=year, cgpa="8.40", title="Consolidated Mark Sheet"))
        db.commit()


def edu(client, token):
    return client.get("/api/candidate/verification/education", headers=auth(token)).json()


@needs_pymupdf
def test_simulated_digilocker_is_compared_but_never_counted(client, otp_box, monkeypatch):
    monkeypatch.setenv("TT_DIGILOCKER_MODE", "simulated")
    name = "Simran Kaur"
    token, _ = make_candidate(client, otp_box, name=name, selfie=synth.blank_jpeg())
    upload(client, token, "marksheet", synth.marksheet(name=name.upper(), reg="SAMPLE2026CS001", year=2026))
    sim_records(name)
    st = client.get("/api/candidate/digilocker", headers=auth(token)).json()
    assert st["mode"] == "simulated" and st["simulated"] and not st["connected"]
    assert client.post("/api/candidate/digilocker/start", json={"consent": False}, headers=auth(token)).status_code == 400
    url = connect(client, token)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
    assert url.startswith("/digilocker-simulated?")
    view = client.get(f"/api/digilocker/simulated/{state}").json()
    assert view["simulated"] and view["documents"][0]["issuer"] == "Anna University"
    redirect = client.post(f"/api/digilocker/simulated/{state}", json={"allow": True}).json()["redirect"]
    r = client.get(redirect, follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"].endswith("digilocker=connected")
    st = client.get("/api/candidate/digilocker", headers=auth(token)).json()
    assert st["connected"] and len(st["issued"]) == 1 and st["issued"][0]["likelyEducation"]
    r = client.post("/api/candidate/digilocker/fetch", json={"uri": st["issued"][0]["uri"]}, headers=auth(token))
    assert r.status_code == 200, r.text
    e = edu(client, token)
    dl = e["digilocker"]
    assert dl["status"] == "match" and dl["simulated"] and "SIMULATED" in dl["summary"]
    assert {row["field"]: row["match"] for row in dl["rows"]}["Year of passing"] is True
    assert e["status"] == "consistent"  # a simulated match never upgrades to verified
    # the recruiter sees it as pending/simulated, and no points are given
    rtoken, _ = register_recruiter(client)
    job = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(rtoken)).json()
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(token)).json()["id"]
    rep = client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(rtoken)).json()
    row = next(c for c in rep["trust"]["checks"] if c["key"] == "digilocker")
    assert row["bucket"] == "pending" and row["simulated"]
    assert not any(x["ruleId"].startswith("EDU.DIGILOCKER") and x["applied"] for x in rep["trust"]["entries"])
    assert rep["verification"]["education"]["digilocker"]["status"] == "match"
    # evidence chain records the connection and the pulled copy
    types = [x["type"] for x in client.get(f"/api/recruiter/applicants/{app_id}/evidence", headers=auth(rtoken)).json()["events"]]
    assert "digilocker.connected" in types and "digilocker.document_pulled" in types
    # disconnect removes token, list and copy
    assert client.delete("/api/candidate/digilocker", headers=auth(token)).json()["ok"]
    with SessionLocal() as db:
        cid = db.get(User, _uid(token)).candidate.id
        assert db.query(DigiLockerLink).filter_by(candidate_id=cid).count() == 0
        assert db.query(DigiLockerDocument).filter_by(candidate_id=cid).count() == 0
    assert edu(client, token)["digilocker"]["status"] == "not_connected"


@needs_pymupdf
def test_simulated_mismatch_is_shown(client, otp_box, monkeypatch):
    monkeypatch.setenv("TT_DIGILOCKER_MODE", "simulated")
    name = "Tanvi Joshi"
    token, _ = make_candidate(client, otp_box, name=name, selfie=synth.blank_jpeg())
    upload(client, token, "marksheet", synth.marksheet(name=name.upper(), reg="SAMPLE2026CS001", year=2024))  # edited year
    sim_records(name, year=2026)
    url = connect(client, token)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
    client.get(client.post(f"/api/digilocker/simulated/{state}", json={"allow": True}).json()["redirect"], follow_redirects=False)
    uri = client.get("/api/candidate/digilocker", headers=auth(token)).json()["issued"][0]["uri"]
    client.post("/api/candidate/digilocker/fetch", json={"uri": uri}, headers=auth(token))
    dl = edu(client, token)["digilocker"]
    rows = {row["field"]: row for row in dl["rows"]}
    assert dl["status"] == "mismatch" and rows["Year of passing"]["match"] is False
    assert rows["Year of passing"]["uploaded"] == "2024" and rows["Year of passing"]["digilocker"] == "2026"
    assert any(f["code"] == "digilocker_mismatch" and f["severity"] == "info" for f in edu(client, token)["findings"])


def test_denied_and_expired_requests(client, otp_box, monkeypatch):
    monkeypatch.setenv("TT_DIGILOCKER_MODE", "simulated")
    token, _ = make_candidate(client, otp_box, selfie=synth.blank_jpeg())
    url = connect(client, token)
    state = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
    redirect = client.post(f"/api/digilocker/simulated/{state}", json={"allow": False}).json()["redirect"]
    assert client.get(redirect, follow_redirects=False).headers["location"].endswith("digilocker=denied")
    r = client.get("/api/digilocker/callback?state=unknown&code=SIM-x", follow_redirects=False)
    assert r.status_code == 302 and "digilocker=error" in r.headers["location"]
    assert client.post("/api/candidate/digilocker/fetch", json={"uri": "sim/x"}, headers=auth(token)).status_code == 409
    monkeypatch.setenv("TT_DIGILOCKER_MODE", "off")
    assert client.get("/api/candidate/digilocker", headers=auth(token)).json()["enabled"] is False
    assert client.post("/api/candidate/digilocker/start", json={"consent": True}, headers=auth(token)).status_code == 400


# ------------------------------------------------------------------------------------------- live partner API (fake server)

class FakeDigiLocker:
    def __init__(self, xml: bytes, good_hmac: bool = True):
        self.xml, self.good_hmac, self.calls, self.challenge = xml, good_hmac, [], None

    def __call__(self, method, url, *, data=None, token=None):
        self.calls.append((method, url, data, token))
        path = urllib.parse.urlparse(url).path
        if path == "/public/oauth2/2/token":
            assert data["grant_type"] == "authorization_code" and data["client_secret"] == SECRET and data["code"] == "LIVECODE"
            verifier = data["code_verifier"]
            assert base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode() == self.challenge
            return 200, {}, json.dumps({"access_token": "AT-123", "expires_in": 3600, "name": "Kavin Raj"}).encode()
        assert token == "AT-123"
        if path == "/public/oauth2/2/files/issued":
            return 200, {}, json.dumps({"items": [{"name": "B.E. Degree Marksheet", "type": "file", "date": "2026-06-30", "mime": "application/xml",
                                                   "uri": "in.gov.au-MKSHT-AU2026CS042", "doctype": "MKSHT", "description": "Marksheet",
                                                   "issuerid": "in.gov.annauniv", "issuer": "Anna University"}]}).encode()
        if path.startswith("/public/oauth2/1/xml/"):
            mac = hmac.new(SECRET.encode(), self.xml, hashlib.sha256).hexdigest() if self.good_hmac else "0" * 64
            return 200, {"content-type": "application/xml", "hmac": mac}, self.xml
        return 404, {}, b""


XML_OK = b"""<?xml version="1.0" encoding="UTF-8"?><Certificate number="AU2026CS042" type="MKSHT">
<IssuedBy><Organization name="Anna University"/></IssuedBy><IssuedTo><Person name="KAVIN RAJ"/></IssuedTo>
<CertificateData><Examination name="Bachelor of Engineering" yearOfPassing="2026"/><Performance cgpa="8.40" rollNo="AU2026CS042"/></CertificateData></Certificate>"""


def live(monkeypatch, fake):
    monkeypatch.setenv("TT_DIGILOCKER_MODE", "live")
    monkeypatch.setattr(config, "DIGILOCKER_CLIENT_ID", "TESTCLIENT")
    monkeypatch.setattr(config, "DIGILOCKER_CLIENT_SECRET", SECRET)
    monkeypatch.setattr(dlk.LiveProvider, "http", lambda self, *a, **k: fake(*a, **k))


def live_connect(client, token, fake):
    url = connect(client, token)
    q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
    assert url.startswith("https://digilocker.meripehchaan.gov.in/public/oauth2/1/authorize?")
    assert q["client_id"] == ["TESTCLIENT"] and q["code_challenge_method"] == ["S256"] and q["scope"] == ["openid"]
    assert q["redirect_uri"][0].endswith("/api/digilocker/callback")
    fake.challenge = q["code_challenge"][0]
    r = client.get(f"/api/digilocker/callback?code=LIVECODE&state={q['state'][0]}", follow_redirects=False)
    assert r.headers["location"].endswith("digilocker=connected"), r.headers["location"]
    st = client.get("/api/candidate/digilocker", headers=auth(token)).json()
    assert st["mode"] == "live" and not st["simulated"] and st["issued"][0]["issuer"] == "Anna University"
    return st["issued"][0]["uri"]


@needs_pymupdf
def test_live_digilocker_match_verifies_education(client, otp_box, monkeypatch):
    fake = FakeDigiLocker(XML_OK)
    live(monkeypatch, fake)
    token, _ = make_candidate(client, otp_box, name="Kavin Raj", selfie=synth.blank_jpeg())
    upload(client, token, "marksheet", synth.marksheet(name="KAVIN RAJ", reg="AU2026CS042", year=2026))
    uri = live_connect(client, token, fake)
    r = client.post("/api/candidate/digilocker/fetch", json={"uri": uri}, headers=auth(token))
    assert r.status_code == 200 and r.json()["document"]["hmacVerified"] is True
    assert r.json()["document"]["fields"]["registerNumber"] == "AU2026CS042"
    e = edu(client, token)
    assert e["digilocker"]["status"] == "match" and not e["digilocker"]["simulated"]
    assert e["status"] == "verified"  # the issuer's own copy matched
    rtoken, _ = register_recruiter(client)
    job = client.post("/api/recruiter/jobs", json=job_body(), headers=auth(rtoken)).json()
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(token)).json()["id"]
    rep = client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(rtoken)).json()
    assert any(x["ruleId"] == "EDU.DIGILOCKER_MATCH" and x["applied"] == 8 for x in rep["trust"]["entries"])
    assert next(c for c in rep["trust"]["checks"] if c["key"] == "digilocker")["bucket"] == "verified"
    # the access token is stored encrypted, never in plain text
    with SessionLocal() as db:
        link = db.query(DigiLockerLink).filter_by(candidate_id=db.get(User, _uid(token)).candidate.id).one()
        assert "AT-123" not in link.access_token_enc and dlk.decrypt_text(link.access_token_enc) == "AT-123"


@needs_pymupdf
def test_live_digilocker_mismatch_and_bad_hmac(client, otp_box, monkeypatch):
    fake = FakeDigiLocker(XML_OK)
    live(monkeypatch, fake)
    token, _ = make_candidate(client, otp_box, name="Kavin Raj", selfie=synth.blank_jpeg())
    upload(client, token, "marksheet", synth.marksheet(name="KAVIN RAJ", reg="AU2026CS042", year=2025))  # edited year
    uri = live_connect(client, token, fake)
    client.post("/api/candidate/digilocker/fetch", json={"uri": uri}, headers=auth(token))
    e = edu(client, token)
    assert e["digilocker"]["status"] == "mismatch" and e["status"] == "inconsistent"
    assert any(f["code"] == "digilocker_mismatch" and f["severity"] == "critical" for f in e["findings"])
    # a match whose integrity header fails is never counted as a match
    fake2 = FakeDigiLocker(XML_OK, good_hmac=False)
    live(monkeypatch, fake2)
    token2, _ = make_candidate(client, otp_box, name="Kavin Raj", selfie=synth.blank_jpeg())
    upload(client, token2, "marksheet", synth.marksheet(name="KAVIN RAJ", reg="AU2026CS042", year=2026))
    uri2 = live_connect(client, token2, fake2)
    assert client.post("/api/candidate/digilocker/fetch", json={"uri": uri2}, headers=auth(token2)).json()["document"]["hmacVerified"] is False
    e2 = edu(client, token2)
    assert e2["digilocker"]["status"] == "partial" and e2["status"] != "verified"


def test_xml_parser_ignores_entities():
    assert dlk.parse_xml(b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><x name="&a;"/>') == {}
    f = dlk.parse_xml(XML_OK)
    assert f["year"]["value"] == 2026 and f["cgpa"]["value"] == "8.40" and f["name"]["value"] == "KAVIN RAJ"
