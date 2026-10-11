"""Optional Gemini-assisted field extraction (server-side only).

Enabled only when GEMINI_API_KEY is set. The key is read from the environment, sent in a request header, and
never logged. Gemini only suggests field values; they are stored with source="gemini" and a confidence below the
rule threshold, so an AI-suggested value can confirm a match but can never by itself create a mismatch finding.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

log = logging.getLogger("trusttrace.gemini")
AI_CONFIDENCE = 0.55  # deliberately below rules.MIN_CONFIDENCE
MAX_CHARS = 12000

PROMPTS = {
    "resume": "Extract from this resume: name, emails, phone, education (degree, institution, startYear, endYear, score), "
              "employment (company, title, start YYYY-MM, end YYYY-MM or 'present'), skills (list).",
    "marksheet": "Extract from this marksheet/certificate: name, registerNumber, institution (board or university), degree, year (of passing), "
                 "totalMarks, cgpa, percentage.",
    "experience_letter": "Extract from this experience letter: name (employee), company, designation, joiningDate (YYYY-MM-DD), relievingDate (YYYY-MM-DD or 'present').",
}


def enabled() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def suggest(kind: str, text: str, transport=None) -> dict | None:
    """Return a dict of suggested values, or None when disabled or on any failure (never raises)."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key or kind not in PROMPTS or not text.strip():
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    body = {
        "contents": [{"parts": [{"text": PROMPTS[kind] + " Use null when a value is not present. Do not guess. "
                                 "Return only JSON.\n\n---DOCUMENT---\n" + text[:MAX_CHARS]}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        opener = transport or urllib.request.urlopen
        with opener(req, timeout=25) as resp:
            payload = json.loads(resp.read().decode())
        raw = payload["candidates"][0]["content"]["parts"][0]["text"]
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError, OSError) as exc:
        log.warning("Gemini extraction unavailable (%s); continuing with rule-based extraction only", type(exc).__name__)
        return None


def merge(rule_fields: dict, ai: dict | None, simple_keys: tuple[str, ...]) -> dict:
    """Fill fields the rules could not find with AI suggestions (never overwrite a rule-based value)."""
    if not ai:
        return rule_fields
    out = dict(rule_fields)
    for k in simple_keys:
        v = ai.get(k)
        if v in (None, "", []) or out.get(k):
            continue
        out[k] = {"value": v, "confidence": AI_CONFIDENCE, "source": "gemini"}
    out["_aiAssisted"] = True
    return out
