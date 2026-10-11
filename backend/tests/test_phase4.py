"""Phase 4: Proof of Skill assessments, assessment integrity events and interview identity continuity.

Synthetic data only: recruiter-written questions are created in the tests; faces are the public LFW test images.
"""
from __future__ import annotations

import io
import json
from datetime import timedelta

import pytest
import synth
from test_phase2 import auth, job_body, register_recruiter
from test_phase3 import make_candidate, needs_face, upload

from app.skills import bank, generate


def q_body(skill="Python", answer="b", prompt="Which keyword defines a function in Python?"):
    return {"skill": skill, "difficulty": "easy", "prompt": prompt, "options": ["func", "def", "lambda", "fn"], "correctOptionId": answer,
            "explanation": "def defines a function."}


def setup_job(client, skills=("Python", "SQL")):
    rtoken, _ = register_recruiter(client)
    job = client.post("/api/recruiter/jobs", json=job_body(skills=list(skills)), headers=auth(rtoken)).json()
    return rtoken, job


def publish_with_questions(client, rtoken, job, n_bank=4, custom=True):
    h = auth(rtoken)
    r = client.post(f"/api/recruiter/jobs/{job['id']}/assessment/generate", json={"count": n_bank, "durationMinutes": 10, "passPercent": 60, "source": "bank"}, headers=h)
    assert r.status_code == 200, r.text
    t = r.json()
    if custom:
        t = client.post(f"/api/recruiter/jobs/{job['id']}/assessment/questions", json=q_body(), headers=h).json()
    for q in t["questions"]:
        if not q["approved"]:
            t = client.post(f"/api/recruiter/assessment-questions/{q['id']}/approve", headers=h).json()
    r = client.post(f"/api/recruiter/jobs/{job['id']}/assessment/publish", headers=h)
    assert r.status_code == 200, r.text
    return r.json()


def candidate_attempt(client, ctoken):
    rows = client.get("/api/candidate/assessments", headers=auth(ctoken)).json()
    assert rows, "no assessment assigned"
    return rows[0]


# ------------------------------------------------------------------------------------------- question bank / generation

def test_question_bank_is_well_formed_and_deterministic():
    for skill, items in bank.BANK.items():
        assert len(items) >= 5, skill
        for q in items:
            assert len(q["options"]) == 4 and q["answer"] in "abcd" and len({o["text"] for o in q["options"]}) == 4
    a, _ = bank.pick(["Python", "SQL"], 6, seed="job-1")
    b, _ = bank.pick(["python", "postgresql"], 6, seed="job-1")
    assert [q["bankId"] for q in a] == [q["bankId"] for q in b]  # same job + same skills -> same questions
    assert {q["skill"] for q in a} == {"Python", "SQL"}
    _, unknown = bank.pick(["Python", "Underwater Basket Weaving"], 4, seed="x")
    assert unknown == ["Underwater Basket Weaving"]


def test_gemini_questions_are_validated_and_fall_back(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-xyz")

    class Resp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    good = {"skill": "Python", "difficulty": "easy", "prompt": "What does len('abc') return?", "options": ["2", "3", "4", "abc"], "answerIndex": 1}
    bad = {"prompt": "Broken?", "options": ["a", "a"], "answerIndex": 9}
    payload = {"candidates": [{"content": {"parts": [{"text": json.dumps({"questions": [good, bad]})}]}}]}
    qs, source, note = generate.draft_questions(["Python"], 5, "j", "Dev", transport=lambda req, timeout: Resp(json.dumps(payload).encode()))
    assert source == "gemini" and len(qs) == 1 and qs[0]["answer"] == "b" and "Gemini" in note

    def boom(req, timeout):
        raise OSError("offline")
    qs, source, note = generate.draft_questions(["Python"], 3, "j", "Dev", transport=boom)
    assert source == "question_bank" and len(qs) == 3 and "did not return usable questions" in note


# ------------------------------------------------------------------------------------------- builder & publishing

def test_generated_questions_need_review_before_publishing(client, otp_box):
    rtoken, job = setup_job(client)
    h = auth(rtoken)
    t = client.post(f"/api/recruiter/jobs/{job['id']}/assessment/generate", json={"count": 4, "source": "bank"}, headers=h).json()
    assert t["status"] == "draft" and t["questionCount"] == 4 and t["approvedCount"] == 0
    assert all(q["source"] == "question_bank" and q["correctOptionId"] in "abcd" for q in t["questions"])
    r = client.post(f"/api/recruiter/jobs/{job['id']}/assessment/publish", headers=h)
    assert r.status_code == 400 and r.json()["code"] == "unapproved_questions"
    # editing an approved question requires approving it again
    qid = t["questions"][0]["id"]
    client.post(f"/api/recruiter/assessment-questions/{qid}/approve", headers=h)
    t = client.put(f"/api/recruiter/assessment-questions/{qid}", json=q_body(answer="b"), headers=h).json()
    q = next(x for x in t["questions"] if x["id"] == qid)
    assert q["edited"] and not q["approved"] and q["prompt"].startswith("Which keyword")
    # invalid question bodies
    assert client.post(f"/api/recruiter/jobs/{job['id']}/assessment/questions", json=q_body() | {"options": ["a", "a", "b", "c"]}, headers=h).status_code == 422
    assert client.post(f"/api/recruiter/jobs/{job['id']}/assessment/questions", json=q_body() | {"correctOptionId": "e"}, headers=h).status_code == 422
    # another organisation can't see or change it
    other, _ = register_recruiter(client)
    assert client.get(f"/api/recruiter/jobs/{job['id']}/assessment", headers=auth(other)).status_code == 404
    assert client.post(f"/api/recruiter/assessment-questions/{qid}/approve", headers=auth(other)).status_code == 404


def test_publish_assigns_locks_and_scores(client, otp_box):
    rtoken, job = setup_job(client)
    ctoken, _ = make_candidate(client, otp_box)
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken)).json()["id"]
    t = publish_with_questions(client, rtoken, job)
    assert t["status"] == "published" and t["assignedCount"] == 1
    # locked after publishing
    qid = t["questions"][0]["id"]
    assert client.put(f"/api/recruiter/assessment-questions/{qid}", json=q_body(), headers=auth(rtoken)).json()["code"] == "assessment_locked"
    # candidate sees it, no questions before start, never the answer key
    att = candidate_attempt(client, ctoken)
    assert att["status"] == "assigned" and att["questionCount"] == 5
    s = client.get(f"/api/candidate/assessments/{att['id']}", headers=auth(ctoken)).json()
    assert s["questions"] == []
    s = client.post(f"/api/candidate/assessments/{att['id']}/start", json={"cameraConsent": False, "cameraState": "declined"}, headers=auth(ctoken)).json()
    assert len(s["questions"]) == 5 and 590 <= s["remainingSeconds"] <= 600
    assert "correctOptionId" not in json.dumps(s) and '"answer"' not in json.dumps(s)
    # answer: all correct except the recruiter question (answer b -> choose a)
    key = {q["id"]: q["correctOptionId"] for q in t["questions"]}
    answers = {q["id"]: key[q["id"]] for q in s["questions"]}
    custom_id = next(q["id"] for q in t["questions"] if q["source"] == "recruiter")
    answers[custom_id] = "a"
    assert client.put(f"/api/candidate/assessments/{att['id']}/answers", json={"answers": {"nope": "a"}}, headers=auth(ctoken)).status_code == 400
    res = client.post(f"/api/candidate/assessments/{att['id']}/submit", json={"answers": answers}, headers=auth(ctoken)).json()
    assert (res["score"], res["maxScore"], res["percent"]) == (4, 5, 80.0) and res["status"] == "submitted"
    assert res["perSkill"]["Python"]["total"] >= 2
    # no second submission, no edits
    again = client.post(f"/api/candidate/assessments/{att['id']}/submit", json={"answers": {q: key[q] for q in answers}}, headers=auth(ctoken))
    assert again.status_code == 409 and again.json()["code"] == "already_submitted"
    assert client.put(f"/api/candidate/assessments/{att['id']}/answers", json={"answers": {}}, headers=auth(ctoken)).status_code == 409
    # results persist; recruiter sees answers and the application moved to "assessment"
    assert candidate_attempt(client, ctoken)["score"] == 4
    detail = client.get(f"/api/recruiter/assessments/{att['id']}", headers=auth(rtoken)).json()
    assert detail["candidateName"] and sum(a["correct"] for a in detail["answers"]) == 4
    assert client.get("/api/recruiter/dashboard", headers=auth(rtoken)).json()["inAssessment"] == 1
    # another candidate cannot touch this attempt
    other, _ = make_candidate(client, otp_box)
    assert client.get(f"/api/candidate/assessments/{att['id']}", headers=auth(other)).status_code == 404
    assert client.post(f"/api/candidate/assessments/{att['id']}/submit", json={"answers": {}}, headers=auth(other)).status_code == 404


def test_applying_after_publishing_assigns_automatically(client, otp_box):
    rtoken, job = setup_job(client)
    publish_with_questions(client, rtoken, job, custom=False)
    ctoken, _ = make_candidate(client, otp_box)
    client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken))
    assert candidate_attempt(client, ctoken)["questionCount"] == 4
    msgs = client.get("/api/candidate/messages", headers=auth(ctoken)).json()
    assert any("Skill assessment assigned" in m["subject"] for m in msgs)


def test_time_limit_uses_answers_saved_before_the_deadline(client, otp_box):
    rtoken, job = setup_job(client)
    ctoken, _ = make_candidate(client, otp_box)
    client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken))
    t = publish_with_questions(client, rtoken, job, custom=False)
    att = candidate_attempt(client, ctoken)
    s = client.post(f"/api/candidate/assessments/{att['id']}/start", json={"cameraConsent": False}, headers=auth(ctoken)).json()
    key = {q["id"]: q["correctOptionId"] for q in t["questions"]}
    first = s["questions"][0]["id"]
    client.put(f"/api/candidate/assessments/{att['id']}/answers", json={"answers": {first: key[first]}}, headers=auth(ctoken))
    from app.db import SessionLocal
    from app.models import Assessment, utcnow
    with SessionLocal() as db:  # simulate the clock running out
        a = db.get(Assessment, att["id"])
        a.ends_at = utcnow() - timedelta(minutes=2)
        db.commit()
    late = client.post(f"/api/candidate/assessments/{att['id']}/submit", json={"answers": key}, headers=auth(ctoken)).json()
    assert late["submitReason"] == "time_up" and late["score"] == 1  # late answers ignored


# ------------------------------------------------------------------------------------------- integrity events

def test_integrity_events_timeline(client, otp_box):
    rtoken, job = setup_job(client)
    ctoken, _ = make_candidate(client, otp_box)
    client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken))
    publish_with_questions(client, rtoken, job, custom=False)
    att = candidate_attempt(client, ctoken)
    h = auth(ctoken)
    assert client.post(f"/api/candidate/assessments/{att['id']}/events", json={"events": [{"type": "copy"}]}, headers=h).status_code == 409  # not started
    client.post(f"/api/candidate/assessments/{att['id']}/start", json={"cameraConsent": True, "cameraState": "denied"}, headers=h)
    evs = [{"type": "visibility_hidden", "clientAt": "2026-10-09T10:00:01Z"}, {"type": "visibility_visible"}, {"type": "window_blur"},
           {"type": "window_focus"}, {"type": "paste", "detail": {"chars": 42}}, {"type": "copy"}]
    assert client.post(f"/api/candidate/assessments/{att['id']}/events", json={"events": evs}, headers=h).json()["recorded"] == 6
    assert client.post(f"/api/candidate/assessments/{att['id']}/events", json={"events": [{"type": "keystrokes"}]}, headers=h).status_code == 422
    client.post(f"/api/candidate/assessments/{att['id']}/submit", json={"answers": {}}, headers=h)
    d = client.get(f"/api/recruiter/assessments/{att['id']}", headers=auth(rtoken)).json()
    kinds = [e["kind"] for e in d["timeline"]]
    assert kinds[:2] == ["started", "camera_denied"] and kinds[-1] == "submitted"
    assert d["signals"]["visibility_hidden"] == 1 and d["signals"]["paste"] == 1 and d["signals"]["window_blur"] == 1
    assert all(e["at"] for e in d["timeline"]) and next(e for e in d["timeline"] if e["kind"] == "paste")["detail"] == {"chars": 42}
    assert d["cameraConsent"] is True
    # events after submission are refused
    assert client.post(f"/api/candidate/assessments/{att['id']}/events", json={"events": [{"type": "copy"}]}, headers=h).status_code == 409
    # recruiter of another organisation can't see the timeline
    other, _ = register_recruiter(client)
    assert client.get(f"/api/recruiter/assessments/{att['id']}", headers=auth(other)).status_code == 404


@needs_face
def test_assessment_face_recheck_goes_into_timeline(client, otp_box):
    rtoken, job = setup_job(client)
    ctoken, _ = make_candidate(client, otp_box)
    client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken))
    publish_with_questions(client, rtoken, job, custom=False)
    att = candidate_attempt(client, ctoken)
    client.post(f"/api/candidate/assessments/{att['id']}/start", json={"cameraConsent": True, "cameraState": "granted"}, headers=auth(ctoken))
    r = client.post("/api/candidate/identity/check", json={"stage": "assessment", "referenceId": att["id"],
                                                           "image": synth.data_url(synth.face_jpeg("Alvaro_Uribe_0029.jpg"))}, headers=auth(ctoken)).json()
    assert r["decision"] == "match" and r["outcome"] == "matched"
    r = client.post("/api/candidate/identity/check", json={"stage": "assessment", "referenceId": att["id"],
                                                           "image": synth.data_url(synth.face_jpeg("Aaron_Tippin_0001.jpg"))}, headers=auth(ctoken)).json()
    assert r["decision"] == "no_match" and r["outcome"] in ("uncertain", "needs_review")
    d = client.get(f"/api/recruiter/assessments/{att['id']}", headers=auth(rtoken)).json()
    assert [f["outcome"] for f in d["faceChecks"]][:1] == ["matched"] and sum(e["kind"] == "face_check" for e in d["timeline"]) == 2


# ------------------------------------------------------------------------------------------- Proof of Skill

def test_proof_of_skill_compares_claims_with_scores(client, otp_box):
    rtoken, job = setup_job(client, skills=("Python", "SQL"))
    ctoken, cdata = make_candidate(client, otp_box)
    prof = client.get("/api/candidate/profile", headers=auth(ctoken)).json()
    body = {k: prof[k] for k in ("fullName", "email", "phone")} | {"location": "Chennai", "headline": "Developer", "linkedinUrl": "", "githubUrl": "",
                                                                   "skills": ["Python", "Java"]}
    assert client.put("/api/candidate/profile", json=body, headers=auth(ctoken)).status_code == 200
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken)).json()["id"]
    t = publish_with_questions(client, rtoken, job, n_bank=4, custom=False)
    att = candidate_attempt(client, ctoken)
    s = client.post(f"/api/candidate/assessments/{att['id']}/start", json={"cameraConsent": False}, headers=auth(ctoken)).json()
    skill_of = {q["id"]: q["skill"] for q in t["questions"]}
    key = {q["id"]: q["correctOptionId"] for q in t["questions"]}
    wrong = {"a": "b", "b": "c", "c": "d", "d": "a"}
    answers = {qid: (key[qid] if skill_of[qid] == "SQL" else wrong[key[qid]]) for qid in key}  # Python all wrong, SQL all right
    client.post(f"/api/candidate/assessments/{att['id']}/submit", json={"answers": answers}, headers=auth(ctoken))
    p = client.get(f"/api/recruiter/applicants/{app_id}/skills", headers=auth(rtoken)).json()
    rows = {r["skill"]: r for r in p["skills"]}
    assert rows["Python"]["profile"] and rows["Python"]["required"] and rows["Python"]["assessed"]["percent"] == 0
    assert "never of dishonesty" in rows["Python"]["note"]  # a low score is not an accusation
    assert rows["SQL"]["assessed"]["percent"] == 100 and not rows["SQL"]["profile"] and rows["SQL"]["note"] == "Demonstrated in the assessment."
    assert rows["Java"]["profile"] and rows["Java"]["assessed"] is None
    assert "not proof" in p["disclaimer"]
    # report tab: a low overall score is "review", never "failed"
    rep = client.get(f"/api/recruiter/applicants/{app_id}/report", headers=auth(rtoken)).json()
    assert rep["sections"]["assessment"][0]["status"] in ("review", "passed")
    assert client.get("/api/candidate/skills", headers=auth(ctoken)).json()["attempts"] == 1


# ------------------------------------------------------------------------------------------- interviews

def schedule(client, rtoken, app_id):
    r = client.post("/api/recruiter/interviews", json={"applicationId": app_id, "scheduledAt": "2099-01-01T10:00:00Z", "durationMinutes": 30, "mode": "video",
                                                       "interviewer": "Ravi", "meetingLink": "https://meet.example/abc"}, headers=auth(rtoken))
    assert r.status_code == 201, r.text
    return r.json()


def test_interview_invitation_acknowledgement_and_status(client, otp_box):
    rtoken, job = setup_job(client)
    ctoken, _ = make_candidate(client, otp_box)
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken)).json()["id"]
    iv = schedule(client, rtoken, app_id)
    mine = client.get("/api/candidate/interviews", headers=auth(ctoken)).json()[0]
    assert mine["id"] == iv["id"] and mine["meetingLink"] is None  # link only after the entry step
    assert client.post(f"/api/candidate/interviews/{iv['id']}/respond", json={"response": "reschedule_requested", "note": ""}, headers=auth(ctoken)).status_code == 422
    r = client.post(f"/api/candidate/interviews/{iv['id']}/respond", json={"response": "accepted"}, headers=auth(ctoken)).json()
    assert r["candidateResponse"] == "accepted" and r["acknowledgedAt"]
    rec = client.get("/api/recruiter/interviews", headers=auth(rtoken)).json()[0]
    assert rec["candidateResponse"] == "accepted"
    other, _ = make_candidate(client, otp_box)
    assert client.post(f"/api/candidate/interviews/{iv['id']}/respond", json={"response": "accepted"}, headers=auth(other)).status_code == 404
    assert client.post(f"/api/recruiter/interviews/{iv['id']}/status", json={"status": "completed"}, headers=auth(rtoken)).json()["status"] == "completed"
    assert client.post(f"/api/candidate/interviews/{iv['id']}/respond", json={"response": "accepted"}, headers=auth(ctoken)).status_code == 409


def test_interview_entry_without_camera_needs_review(client, otp_box):
    rtoken, job = setup_job(client)
    ctoken, _ = make_candidate(client, otp_box)
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken)).json()["id"]
    iv = schedule(client, rtoken, app_id)
    r = client.post(f"/api/candidate/interviews/{iv['id']}/entry", json={"camera": "denied"}, headers=auth(ctoken)).json()
    assert r["outcome"] == "needs_review" and r["interview"]["meetingLink"] == "https://meet.example/abc"
    rec = client.get("/api/recruiter/interviews", headers=auth(rtoken)).json()[0]
    assert rec["entryOutcome"] == "needs_review" and rec["faceChecks"][0]["decision"] == "camera_unavailable"


@needs_face
def test_interview_entry_face_outcomes(client, otp_box):
    rtoken, job = setup_job(client)
    ctoken, _ = make_candidate(client, otp_box)
    app_id = client.post(f"/api/jobs/{job['id']}/apply", headers=auth(ctoken)).json()["id"]
    iv = schedule(client, rtoken, app_id)
    entry = lambda img: client.post(f"/api/candidate/interviews/{iv['id']}/entry", json={"image": synth.data_url(img)}, headers=auth(ctoken)).json()
    assert entry(synth.face_jpeg("Alvaro_Uribe_0029.jpg"))["outcome"] == "matched"
    r = entry(synth.two_faces_jpeg())
    assert r["decision"] == "multiple_faces" and r["outcome"] == "needs_review"
    r = entry(synth.blank_jpeg())
    assert r["decision"] == "no_face" and r["outcome"] == "uncertain"
    r = entry(synth.face_jpeg("Aaron_Tippin_0001.jpg"))
    assert r["decision"] == "no_match" and r["outcome"] in ("uncertain", "needs_review") and r["liveness"] == "not_checked"
    rec = client.get("/api/recruiter/interviews", headers=auth(rtoken)).json()[0]
    assert [f["decision"] for f in rec["faceChecks"]] == ["match", "multiple_faces", "no_face", "no_match"]
