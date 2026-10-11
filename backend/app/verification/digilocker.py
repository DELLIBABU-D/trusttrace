"""DigiLocker comparison: pull the candidate's issuer-issued education document from DigiLocker (with their consent)
and compare it field by field with the certificate they uploaded.

Two providers share one flow:

* **live** — DigiLocker Requester API (MeriPehchaan / API Setu spec v2.3):
  OAuth 2.0 authorization code + PKCE (S256) at ``/public/oauth2/1/authorize``, token at ``/public/oauth2/2/token``,
  issued documents at ``/public/oauth2/2/files/issued``, files at ``/public/oauth2/1/file/{uri}`` and certificate XML at
  ``/public/oauth2/1/xml/{uri}``. Downloads are checked against the ``hmac`` response header (HMAC-SHA256 with the client
  secret). Requires an approved DigiLocker partner app (client id/secret, registered redirect URI, approved doctypes).
* **simulated** — a built-in stand-in for demos and tests. Records come from ``manage.py load-digilocker-records``; every
  screen and API response labels them SIMULATED and they never count as verification or change the score.

Only metadata of the issued-documents list is stored. The access token is encrypted (Fernet), kept only until it
expires, and deleted when the candidate disconnects. Nothing is shared with DigiLocker except the OAuth request.
"""
from __future__ import annotations

import base64
import hashlib
import hmac as hmaclib
import json
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from .. import config, storage
from ..models import Candidate, DigiLockerDocument, DigiLockerLink, DigiLockerSimRecord, utcnow
from .crypto import decrypt_text, encrypt_text
from .fields import name_similarity

LINK_TTL_MINUTES = 15
MAX_DOC_BYTES = 5 * 1024 * 1024
EDU_HINTS = re.compile(r"mark|grade|degree|diploma|certificate|transcript|result|passing|provisional|consolidated|hsc|ssc|class\s*x|cbse|board|universit", re.I)


class DigiLockerError(Exception):
    pass


# ---------------------------------------------------------------- PKCE / helpers

def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def pkce_pair() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(48))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def redirect_uri(base: str) -> str:
    return config.DIGILOCKER_REDIRECT_URI or f"{(config.PUBLIC_URL or base).rstrip('/')}/api/digilocker/callback"


def hmac_ok(body: bytes, header: str | None) -> bool:
    """DigiLocker sends an 'hmac' header computed with the client secret; accept hex or base64 encodings."""
    if not header or not config.DIGILOCKER_CLIENT_SECRET:
        return False
    digest = hmaclib.new(config.DIGILOCKER_CLIENT_SECRET.encode(), body, hashlib.sha256).digest()
    candidates = {digest.hex(), base64.b64encode(digest).decode(), _b64url(digest)}
    return any(hmaclib.compare_digest(header.strip(), c) for c in candidates)


# ---------------------------------------------------------------- providers

@dataclass
class Fetched:
    body: bytes
    mime: str
    hmac_verified: bool


class LiveProvider:
    mode = "live"

    def __init__(self) -> None:
        if not (config.DIGILOCKER_CLIENT_ID and config.DIGILOCKER_CLIENT_SECRET):
            raise DigiLockerError("DigiLocker live mode needs TT_DIGILOCKER_CLIENT_ID and TT_DIGILOCKER_CLIENT_SECRET.")

    # kept as a method so tests can replace the network layer
    def http(self, method: str, url: str, *, data: dict | None = None, token: str | None = None) -> tuple[int, dict, bytes]:
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(url, data=body, method=method)
        if body is not None:
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed https base URL from config
                return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read(MAX_DOC_BYTES + 1)
        except urllib.error.HTTPError as exc:
            return exc.code, {}, exc.read(4096)
        except (urllib.error.URLError, TimeoutError) as exc:
            raise DigiLockerError(f"DigiLocker could not be reached ({type(exc).__name__}).") from exc

    def authorize_url(self, state: str, challenge: str, base: str) -> str:
        q = {"response_type": "code", "client_id": config.DIGILOCKER_CLIENT_ID, "redirect_uri": redirect_uri(base), "state": state,
             "code_challenge": challenge, "code_challenge_method": "S256", "scope": "openid",
             "purpose": "Compare your education certificate for a job application"}
        return f"{config.DIGILOCKER_BASE}/public/oauth2/1/authorize?{urllib.parse.urlencode(q)}"

    def exchange(self, code: str, verifier: str, base: str) -> dict:
        status, _, body = self.http("POST", f"{config.DIGILOCKER_BASE}/public/oauth2/2/token", data={
            "code": code, "grant_type": "authorization_code", "client_id": config.DIGILOCKER_CLIENT_ID,
            "client_secret": config.DIGILOCKER_CLIENT_SECRET, "redirect_uri": redirect_uri(base), "code_verifier": verifier})
        if status != 200:
            raise DigiLockerError(f"DigiLocker refused the sign-in (HTTP {status}).")
        tok = json.loads(body or b"{}")
        if not tok.get("access_token"):
            raise DigiLockerError("DigiLocker did not return an access token.")
        return tok

    def issued(self, token: str) -> list[dict]:
        status, _, body = self.http("GET", f"{config.DIGILOCKER_BASE}/public/oauth2/2/files/issued", token=token)
        if status != 200:
            raise DigiLockerError(f"Could not read your DigiLocker documents (HTTP {status}).")
        data = json.loads(body or b"{}")
        items = data.get("items", data if isinstance(data, list) else [])
        return [{k: str(i.get(k, "")) for k in ("name", "type", "date", "mime", "uri", "doctype", "description", "issuerid", "issuer")}
                for i in items if isinstance(i, dict) and i.get("uri")]

    def fetch(self, token: str, item: dict) -> Fetched:
        uri = urllib.parse.quote(item["uri"], safe="")
        kind = "xml" if "xml" in (item.get("mime") or "") else "file"
        status, headers, body = self.http("GET", f"{config.DIGILOCKER_BASE}/public/oauth2/1/{kind}/{uri}", token=token)
        if status != 200 and kind == "xml":  # XML not available for every document: fall back to the PDF
            status, headers, body = self.http("GET", f"{config.DIGILOCKER_BASE}/public/oauth2/1/file/{uri}", token=token)
        if status != 200:
            raise DigiLockerError(f"Could not download the document from DigiLocker (HTTP {status}).")
        if len(body) > MAX_DOC_BYTES:
            raise DigiLockerError("The DigiLocker document is larger than 5 MB.")
        return Fetched(body, headers.get("content-type", "").split(";")[0] or item.get("mime", ""), hmac_ok(body, headers.get("hmac")))


class SimulatedProvider:
    """Same interface, backed by DigiLockerSimRecord rows. The 'authorize' page is TrustTrace's own, labelled SIMULATED."""
    mode = "simulated"

    def __init__(self, db: Session, cand: Candidate) -> None:
        self.db, self.cand = db, cand

    def authorize_url(self, state: str, challenge: str, base: str) -> str:
        return f"/digilocker-simulated?state={urllib.parse.quote(state)}"

    def exchange(self, code: str, verifier: str, base: str) -> dict:
        if not code.startswith("SIM-"):
            raise DigiLockerError("Invalid simulated authorisation code.")
        return {"access_token": "SIM-" + secrets.token_urlsafe(16), "expires_in": 3600, "name": self.cand.user.full_name}

    def _records(self) -> list[DigiLockerSimRecord]:
        u = self.cand.user
        rows = self.db.query(DigiLockerSimRecord).all()
        return [r for r in rows if (r.mobile and r.mobile == u.phone) or (not r.mobile and name_similarity(r.holder_name, u.full_name) >= 0.8)]

    def issued(self, token: str) -> list[dict]:
        return [{"name": r.title or f"{r.degree} – {r.issuer}", "type": "file", "date": str(r.year or ""), "mime": "application/pdf",
                 "uri": f"sim/{r.id}", "doctype": r.doctype, "description": "SIMULATED DigiLocker record", "issuerid": "SIMULATED",
                 "issuer": r.issuer} for r in self._records()]

    def fetch(self, token: str, item: dict) -> Fetched:
        rec = self.db.get(DigiLockerSimRecord, item["uri"].removeprefix("sim/"))
        if not rec or rec not in self._records():
            raise DigiLockerError("That simulated record is not available for this account.")
        from ..demo_docs import pdf
        body = pdf([rec.issuer.upper(), "CONSOLIDATED MARK SHEET  (SIMULATED DIGILOCKER COPY)", f"Name of the Candidate : {rec.holder_name.upper()}",
                    f"Register Number : {rec.register_number or 'NA'}", f"Degree : {rec.degree}", f"Year of Passing : {rec.year or ''}",
                    f"CGPA : {rec.cgpa or ''}", "Issued via DigiLocker (SIMULATED for testing - not an official record)"])
        return Fetched(body, "application/pdf", False)


def provider(db: Session, cand: Candidate):
    mode = config.digilocker_mode()
    if mode == "live":
        return LiveProvider()
    if mode == "simulated":
        return SimulatedProvider(db, cand)
    raise DigiLockerError("DigiLocker is switched off on this server.")


# ---------------------------------------------------------------- flow

def start(db: Session, cand: Candidate, base: str) -> str:
    prov = provider(db, cand)
    verifier, challenge = pkce_pair()
    state = secrets.token_urlsafe(24)
    db.add(DigiLockerLink(candidate_id=cand.id, mode=prov.mode, state=state, code_verifier_enc=encrypt_text(verifier),
                          expires_at=utcnow() + timedelta(minutes=LINK_TTL_MINUTES)))
    return prov.authorize_url(state, challenge, base)


def complete(db: Session, state: str, code: str | None, error: str | None, base: str) -> DigiLockerLink:
    link = db.query(DigiLockerLink).filter_by(state=state).one_or_none()
    if not link or link.status != "pending" or link.expires_at < utcnow():
        raise DigiLockerError("This DigiLocker request has expired. Start again from the Education page.")
    if error or not code:
        link.status, link.error = "denied", (error or "No authorisation code")[:300]
        return link
    cand = db.get(Candidate, link.candidate_id)
    prov = provider(db, cand)
    if prov.mode != link.mode:
        raise DigiLockerError("The DigiLocker mode changed on the server. Start again.")
    tok = prov.exchange(code, decrypt_text(link.code_verifier_enc), base)
    link.access_token_enc = encrypt_text(tok["access_token"])
    link.token_expires_at = utcnow() + timedelta(seconds=int(tok.get("expires_in") or 3600))
    link.account_name = str(tok.get("name") or "")[:200]
    link.code_verifier_enc = ""
    link.issued = prov.issued(tok["access_token"])
    link.status = "connected"
    return link


def active_link(db: Session, cand_id: str) -> DigiLockerLink | None:
    return (db.query(DigiLockerLink).filter_by(candidate_id=cand_id, status="connected")
            .order_by(DigiLockerLink.created_at.desc()).first())


def fetch_document(db: Session, cand: Candidate, uri: str) -> DigiLockerDocument:
    link = active_link(db, cand.id)
    if not link:
        raise DigiLockerError("Connect DigiLocker first.")
    if not link.token_expires_at or link.token_expires_at < utcnow():
        raise DigiLockerError("The DigiLocker session has expired. Connect again.")
    item = next((i for i in link.issued if i.get("uri") == uri), None)
    if not item:
        raise DigiLockerError("That document is not in your DigiLocker list.")
    prov = provider(db, cand)
    got = prov.fetch(decrypt_text(link.access_token_enc), item)
    fields = parse_document(got.body, got.mime, cand)
    for old in db.query(DigiLockerDocument).filter_by(candidate_id=cand.id, active=True):
        old.active = False
        storage.delete(old.storage_name)
    name, sha = storage.save_raw(got.body)
    doc = DigiLockerDocument(candidate_id=cand.id, mode=link.mode, uri=uri[:300], doctype=item.get("doctype", "")[:60],
                             title=item.get("name", "")[:200], issuer=item.get("issuer", "")[:200], issuer_id=item.get("issuerid", "")[:80],
                             issued_on=item.get("date", "")[:20], mime=got.mime[:60], storage_name=name, sha256=sha,
                             hmac_verified=got.hmac_verified, fields=fields)
    db.add(doc)
    db.flush()
    return doc


def disconnect(db: Session, cand_id: str) -> int:
    n = 0
    for link in db.query(DigiLockerLink).filter_by(candidate_id=cand_id):
        db.delete(link)
        n += 1
    for d in db.query(DigiLockerDocument).filter_by(candidate_id=cand_id):
        storage.delete(d.storage_name)
        db.delete(d)
        n += 1
    return n


def current_document(db: Session, cand_id: str) -> DigiLockerDocument | None:
    return db.query(DigiLockerDocument).filter_by(candidate_id=cand_id, active=True).order_by(DigiLockerDocument.fetched_at.desc()).first()


# ---------------------------------------------------------------- reading the DigiLocker document

XML_KEYS = {
    "name": ("issuedtopersonname", "issuedtoname", "personname", "studentname", "candidatename", "fullname", "holdername", "studentfullname"),
    "registerNumber": ("rollno", "rollnumber", "regno", "registrationno", "registrationnumber", "registerno", "registernumber",
                       "enrollmentno", "enrolmentno", "enrollmentnumber", "seatno", "prn", "usn", "certificatenumber"),
    "year": ("yearofpassing", "passingyear", "examyear", "yearofexam", "resultyear", "passyear", "year"),
    "cgpa": ("cgpa", "cpi", "gpa", "ogpa"),
    "percentage": ("percentage", "percent", "aggregate"),
    "degree": ("examinationname", "coursename", "course", "degree", "programmename", "programme", "program", "qualification", "examname"),
    "institution": ("issuedbyorganizationname", "organizationname", "universityname", "university", "institutionname", "institution",
                    "institute", "college", "school", "boardname", "board", "orgname"),
}


def _f(value, source: str, conf: float = 0.95) -> dict:
    return {"value": value, "confidence": conf, "source": source, "page": 1, "snippet": str(value)[:80]}


def _k(s: str) -> str:
    return re.sub(r"[^a-z]", "", re.sub(r"^\{.*\}", "", s).lower())


def parse_xml(body: bytes) -> dict:
    """Issuer XML formats differ (CBSE, universities via NAD/ABC ...). Every attribute and leaf text is collected under
    several keys (attribute, element+attribute, top-level-section+element+attribute), so "IssuedTo/Person@name" is found
    as the holder's name and never confused with "Organization@name". Entity declarations are refused; size is capped."""
    if b"<!ENTITY" in body[:4096] or b"<!DOCTYPE" in body[:4096]:
        return {}
    root = ET.fromstring(body)
    flat: dict[str, str] = {}

    def walk(el, section: str) -> None:
        tag = _k(el.tag)
        for k, v in el.attrib.items():
            a = _k(k)
            for key in (f"{section}{tag}{a}", f"{section}{a}", f"{tag}{a}", a):
                flat.setdefault(key, v.strip())
        if el.text and el.text.strip() and not len(el):
            for key in (f"{section}{tag}", tag):
                flat.setdefault(key, el.text.strip())
        for child in el:
            walk(child, section or (tag if el is not root else ""))

    walk(root, "")
    for child in root:  # top-level sections such as IssuedTo / IssuedBy
        walk(child, _k(child.tag))
    out: dict = {}
    for field, keys in XML_KEYS.items():
        val = next((flat[k] for k in keys if flat.get(k)), None)
        if val:
            if field == "year":
                m = re.search(r"(19|20)\d{2}", val)
                if not m:
                    continue
                val = int(m.group(0))
            out[field] = _f(val, "digilocker_xml")
    if "degree" in out:
        from .fields import find_degree
        deg = find_degree(str(out["degree"]["value"]))
        if deg:
            out["degree"]["code"] = deg[0]
    return out


def parse_document(body: bytes, mime: str, cand: Candidate) -> dict:
    if "xml" in mime or body.lstrip()[:5] == b"<?xml":
        try:
            return parse_xml(body)
        except ET.ParseError:
            return {}
    from . import textract
    from .fields import parse_marksheet
    from .pipeline import profile_dict
    ext = textract.extract(body, "application/pdf")
    return parse_marksheet(ext.text, ext.page_texts, profile_dict(cand)) if ext.text.strip() else {}


# ---------------------------------------------------------------- comparison: uploaded certificate vs DigiLocker

def _v(f):
    return f.get("value") if isinstance(f, dict) else None


def _norm(s) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(s or "").upper())


def compare(uploaded: dict | None, dl: DigiLockerDocument | None) -> dict:
    """Field-by-field comparison. 'match' needs the name plus at least one strong identifier (register number or year)
    to agree and nothing to disagree; any confident disagreement is a 'mismatch'."""
    if dl is None:
        return {"status": "not_connected"}
    base = {"mode": dl.mode, "simulated": dl.mode != "live", "documentId": dl.id, "title": dl.title, "issuer": dl.issuer,
            "doctype": dl.doctype, "issuedOn": dl.issued_on, "fetchedAt": dl.fetched_at.isoformat() + "Z", "hmacVerified": dl.hmac_verified,
            "sha256": dl.sha256}
    if not uploaded:
        return base | {"status": "no_upload", "rows": [], "summary": "No uploaded certificate to compare yet."}
    d = dl.fields or {}
    rows = []

    def row(label, a, b, match):
        rows.append({"field": label, "uploaded": None if a in (None, "") else str(a), "digilocker": None if b in (None, "") else str(b), "match": match})

    ua, da = _v(uploaded.get("name")), _v(d.get("name"))
    row("Name", ua, da, None if not (ua and da) else name_similarity(str(ua), str(da)) >= 0.8)
    ur, dr = _v(uploaded.get("registerNumber")), _v(d.get("registerNumber"))
    row("Register / roll number", ur, dr, None if not (ur and dr) else _norm(ur) == _norm(dr))
    uy, dy = _v(uploaded.get("year")), _v(d.get("year"))
    row("Year of passing", uy, dy, None if not (uy and dy) else int(uy) == int(dy))
    us, ds = _v(uploaded.get("cgpa")) or _v(uploaded.get("percentage")), _v(d.get("cgpa")) or _v(d.get("percentage"))
    try:
        sm = None if not (us and ds) else abs(float(us) - float(ds)) <= 0.05
    except ValueError:
        sm = None
    row("CGPA / percentage", us, ds, sm)
    ug, dg = _v(uploaded.get("degree")), _v(d.get("degree"))
    row("Degree / course", ug, dg, None if not (ug and dg) else (uploaded.get("degree", {}).get("code") == d.get("degree", {}).get("code")
                                                                if uploaded.get("degree", {}).get("code") and d.get("degree", {}).get("code") else None))
    decided = [r for r in rows if r["match"] is not None]
    bad = [r for r in decided if r["match"] is False]
    strong_ok = any(r["match"] for r in rows if r["field"] in ("Register / roll number", "Year of passing"))
    name_ok = rows[0]["match"] is True
    if bad:
        status = "mismatch"
        summary = "The uploaded certificate differs from the DigiLocker copy: " + ", ".join(r["field"] for r in bad) + "."
    elif name_ok and strong_ok:
        status = "match"
        summary = f"The uploaded certificate matches the DigiLocker copy issued by {dl.issuer or 'the issuer'} ({len(decided)} fields compared)."
    else:
        status = "partial"
        summary = "Not enough fields could be read from both documents to decide. A person should compare them."
    if dl.mode == "live" and not dl.hmac_verified and status == "match":
        status = "partial"  # never count a match whose download integrity (DigiLocker 'hmac' header) could not be confirmed
        summary += " The download's integrity header could not be verified, so a person should confirm it."
    if dl.mode != "live":
        summary = "SIMULATED DigiLocker record (testing only, not an official verification). " + summary
    return base | {"status": status, "rows": rows, "summary": summary}
