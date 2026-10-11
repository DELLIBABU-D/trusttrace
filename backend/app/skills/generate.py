"""Draft assessment questions for a job: Gemini when configured, otherwise the local question bank.

Generated questions are always saved as drafts (approved=False). A recruiter must review, edit if needed and approve
each one before the assessment can be published. Nothing generated here is shown to candidates directly.
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request

from . import bank

log = logging.getLogger("trusttrace.skills")


def _valid(q: dict) -> dict | None:
    """Accept a generated question only if it is a well-formed 4-option MCQ with exactly one known answer."""
    try:
        prompt = str(q["prompt"]).strip()
        options = [str(o).strip() for o in q["options"]]
        answer = int(q["answerIndex"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (10 <= len(prompt) <= 600) or len(options) != 4 or any(not o or len(o) > 200 for o in options):
        return None
    if len({o.lower() for o in options}) != 4 or not 0 <= answer <= 3:
        return None
    diff = str(q.get("difficulty", "medium")).lower()
    return {
        "prompt": prompt, "code": (str(q.get("code") or "").strip() or None), "difficulty": diff if diff in ("easy", "medium", "hard") else "medium",
        "options": [{"id": k, "text": t} for k, t in zip("abcd", options)], "answer": "abcd"[answer],
        "explanation": str(q.get("explanation") or "").strip()[:500], "skill": str(q.get("skill") or "").strip()[:80],
    }


def from_gemini(skills: list[str], count: int, job_title: str, transport=None) -> list[dict] | None:
    """Return validated questions, or None if Gemini is disabled or fails (never raises; never logs the key)."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key or not skills:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    prompt = (
        f"Write {count} multiple-choice questions to check practical knowledge for the job '{job_title[:120]}'. "
        f"Cover these skills evenly: {', '.join(s[:40] for s in skills[:10])}. "
        "Each question must have exactly 4 options and exactly one correct option. Avoid trick questions and anything that depends on "
        "personal background. Return JSON: {\"questions\": [{\"skill\": str, \"difficulty\": \"easy|medium|hard\", \"prompt\": str, "
        "\"code\": str or null, \"options\": [4 strings], \"answerIndex\": 0-3, \"explanation\": str}]}"
    )
    body = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": {"temperature": 0.4, "responseMimeType": "application/json"}}
    req = urllib.request.Request(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                                 data=json.dumps(body).encode(), method="POST",
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    try:
        opener = transport or urllib.request.urlopen
        with opener(req, timeout=40) as resp:
            payload = json.loads(resp.read().decode())
        data = json.loads(payload["candidates"][0]["content"]["parts"][0]["text"])
        items = data.get("questions", []) if isinstance(data, dict) else []
    except (urllib.error.URLError, TimeoutError, KeyError, IndexError, ValueError, OSError, AttributeError) as exc:
        log.warning("Gemini question generation unavailable (%s); using the local question bank", type(exc).__name__)
        return None
    out = [v for v in (_valid(q) for q in items if isinstance(q, dict)) if v]
    if len(out) < len(items):
        log.info("Discarded %d malformed generated question(s)", len(items) - len(out))
    return out[:count] or None


def draft_questions(skills: list[str], count: int, job_id: str, job_title: str, prefer: str = "auto", transport=None) -> tuple[list[dict], str, str]:
    """Return (questions, source, note). source is 'gemini' or 'question_bank'."""
    if prefer != "bank":
        qs = from_gemini(skills, count, job_title, transport)
        if qs:
            return qs, "gemini", f"{len(qs)} question(s) drafted by Gemini (AI). Check every question and answer key before approving."
    qs, unknown = bank.pick(skills, count, seed=job_id)
    note = f"{len(qs)} question(s) from the built-in question bank."
    if prefer != "bank" and os.environ.get("GEMINI_API_KEY"):
        note += " Gemini was configured but did not return usable questions."
    if unknown:
        note += f" No built-in questions for: {', '.join(unknown[:8])} — add your own questions for these skills."
    return qs, "question_bank", note
