"""Fraud-pattern thresholds and trust-score rules. Every value is documented here and can be overridden with a JSON
file named by TT_FRAUD_CONFIG (keys "patterns" and/or "rules"), so changes are explicit and versioned."""
from __future__ import annotations

import copy
import hashlib
import json
import os

BASELINE = 80  # prototype baseline from the TrustTrace concept; nothing has been verified at this point
SCORE_MIN, SCORE_MAX = 0, 100
BASE_VERSION = "ts-2026.10.1"

PATTERNS = {
    # P1: many applications in a short time from one account (bots, scripted mass-applying). Weak signal.
    "rapid_applications": {"count": 5, "window_minutes": 10},
    # P2: the same job applied to again and again (repeated submissions bounced by the duplicate check).
    "repeated_submissions": {"count": 3, "window_minutes": 10},
    # P3: one browser (random per-browser ID, stored only as a keyed hash) used by several candidate accounts.
    "shared_device": {"accounts": 2},
    # P4: one network address (keyed hash only) used by several candidate accounts within a day. Very weak:
    # colleges, offices and mobile carriers put many people behind one address.
    "shared_network": {"accounts": 3, "window_hours": 24},
    # P5: the same document type replaced many times in a day.
    "document_churn": {"count": 5, "window_hours": 24},
}

# rule id -> (category, weight, label). Positive weights need positive evidence; nothing is credited for checks not run.
RULES = {
    "ID.PHONE_OTP": ("identity", 2, "Mobile number verified by OTP"),
    "ID.FACE_ID_MATCH": ("identity", 6, "Enrolment photo matches the government ID photo"),
    "ID.FACE_ID_MISMATCH": ("identity", -8, "Enrolment photo does not match the ID photo (needs review)"),
    "ID.RECHECK_MATCH": ("identity", 2, "Live identity recheck matched the enrolled face"),
    "ID.RECHECK_MISMATCH": ("identity", -6, "A live identity recheck did not match (needs review)"),
    "EDU.CONSISTENT": ("education", 4, "Marksheet/certificate consistent with the profile"),
    "EDU.INCONSISTENT": ("education", -10, "High-confidence conflict between education document and profile"),
    "EDU.ISSUER_CONFIRMED": ("education", 6, "Issuer (university/board) confirmed the record"),
    "EDU.ISSUER_DENIED": ("education", -15, "Issuer said the record does not match"),
    "EDU.DIGILOCKER_MATCH": ("education", 8, "Uploaded certificate matches the issuer's DigiLocker copy"),
    "EDU.DIGILOCKER_MISMATCH": ("education", -15, "Uploaded certificate differs from the issuer's DigiLocker copy"),
    "EMP.CONSISTENT": ("employment", 3, "Experience letter consistent with the profile"),
    "EMP.INCONSISTENT": ("employment", -8, "High-confidence conflict between experience letter and profile"),
    "EMP.REFERENCE_CONFIRMED": ("employment", 5, "Referee/HR confirmed the employment"),
    "EMP.REFERENCE_DENIED": ("employment", -12, "Referee/HR did not confirm the employment"),
    "RES.CONSISTENT": ("resume", 2, "Resume consistent with the profile"),
    "RES.INCONSISTENT": ("resume", -6, "Resume conflicts with the profile (dates, education or employers)"),
    "DUP.OPEN_ALERT": ("duplicates", -4, "Potential duplicate profile awaiting review (each, max 2)"),
    "DUP.CONFIRMED": ("duplicates", -20, "Duplicate profile confirmed by a reviewer"),
    "PAT.OPEN_ALERT": ("patterns", -2, "Suspicious-pattern alert awaiting review (each, max 3)"),
    "PAT.CONFIRMED": ("patterns", -8, "Suspicious pattern confirmed by a reviewer"),
}
CAPS = {"DUP.OPEN_ALERT": 2, "PAT.OPEN_ALERT": 3}


def _load() -> tuple[dict, dict]:
    patterns, rules = copy.deepcopy(PATTERNS), dict(RULES)
    path = os.environ.get("TT_FRAUD_CONFIG")
    if path and os.path.isfile(path):
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        for k, v in (data.get("patterns") or {}).items():
            if k in patterns and isinstance(v, dict):
                patterns[k].update({kk: int(vv) for kk, vv in v.items() if kk in patterns[k]})
        for k, w in (data.get("rules") or {}).items():
            if k in rules:
                cat, _, label = rules[k]
                rules[k] = (cat, int(w), label)
    return patterns, rules


def current() -> dict:
    patterns, rules = _load()
    body = {"baseline": BASELINE, "patterns": patterns, "caps": CAPS,
            "rules": {k: {"category": c, "weight": w, "label": l} for k, (c, w, l) in rules.items()}}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:8]
    return body | {"version": f"{BASE_VERSION}+{digest}"}
