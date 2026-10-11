"""Explainable trust score (decision support, not a measure of honesty).

score = clamp(BASELINE + sum(applied rule weights), 0, 100)

* Every adjustment names a rule id, its weight, the evidence it rests on (verification run / finding / alert /
  face check / reference ids) and the time of that evidence.
* Checks that were never run, are pending, or used SIMULATED data add nothing (they are listed as pending).
* Missing information is never treated as fraud: no rule fires on absence of data.
* Assessment performance is reported separately and does not change the score.
* A recruiter resolving a concern (check review "resolved", alert "not a duplicate"/"reviewed – OK") removes that penalty;
  the original evidence and the resolution both stay visible.
* Scores are recomputed whenever the evidence changes; every distinct result is appended to score_records together with
  the ruleset version, so any past score can be explained.
"""
from __future__ import annotations

import hashlib
import json

from sqlalchemy.orm import Session

from .. import serialize
from ..models import (Application, Assessment, CheckReview, DuplicateAlert, FaceCheck, PatternAlert, ScoreRecord, ScoringRuleset, TrustReport,
                      utcnow)
from . import config
from . import reviews as alert_reviews
from .patterns import LABELS as PATTERN_LABELS

BUCKETS = ("verified", "consistent", "pending", "needs_review", "inconsistent", "not_started")
BUCKET_LABEL = {"verified": "Verified", "consistent": "Consistent (not independently confirmed)", "pending": "Pending",
                "needs_review": "Needs review", "inconsistent": "Inconsistent", "not_started": "Not started"}
RUN_BUCKET = {"verified": "verified", "consistent": "consistent", "inconsistent": "inconsistent", "needs_review": "needs_review",
              "failed": "needs_review", "flagged": "inconsistent", "pending": "pending", "not_started": "not_started"}


def ensure_ruleset(db: Session, cfg: dict) -> None:
    if not db.get(ScoringRuleset, cfg["version"]):
        db.add(ScoringRuleset(version=cfg["version"], rules={k: v for k, v in cfg.items() if k != "version"}))
        db.flush()


def risk_band(score: int, review_count: int = 0) -> str:
    """Review priority: 'high' below 50; 'review' below 75 or whenever anything still needs a person's review."""
    return "high" if score < 50 else "review" if (score < 75 or review_count) else "low"


def concern_key(check: str, run, result: dict) -> str | None:
    """Identifies the concern a reviewer looked at: same document + same findings => same concern, even across re-runs.
    A changed document or new findings produce a new key, so an old resolution no longer applies."""
    if not run:
        return None
    findings = sorted((f.get("code", ""), f.get("detail", "")) for f in result.get("findings") or [])
    extra = (result.get("idDocument") or {}).get("status", "") if check == "identity" else ""
    raw = json.dumps([check, run.document_id or "", run.status, findings, extra], default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:32]


def _latest_reviews(db: Session, app_id: str) -> dict[str, CheckReview]:
    out: dict[str, CheckReview] = {}
    for r in db.query(CheckReview).filter_by(application_id=app_id).order_by(CheckReview.at, CheckReview.id):
        out[r.check] = r
    return out


def compute(db: Session, app: Application) -> dict:
    cfg = config.current()
    rules = cfg["rules"]
    cand = app.candidate
    runs = serialize.latest_runs(db, cand.id)
    results = {k: serialize.latest_result(db, cand.id, k) for k in ("identity", "education", "employment", "resume", "duplicate")}
    reviews = _latest_reviews(db, app.id)
    keys = {k: concern_key(k, runs.get(k), results[k]) for k in ("identity", "education", "employment", "resume")}
    entries: list[dict] = []
    checks: list[dict] = []

    def ev(kind: str, ref: str | None, label: str, at=None) -> dict:
        return {"type": kind, "id": ref, "label": label, "at": serialize.iso(at) if at is not None and not isinstance(at, str) else at}

    def apply(rule: str, evidence: list[dict], *, check: str | None = None, note: str = "") -> None:
        r = rules[rule]
        e = {"ruleId": rule, "label": r["label"], "category": r["category"], "weight": r["weight"], "applied": r["weight"],
             "status": "applied", "evidence": evidence, "at": max((x["at"] for x in evidence if x.get("at")), default=None), "note": note}
        rv = reviews.get(check) if check else None
        if r["weight"] < 0 and rv and rv.status == "resolved" and rv.evidence_run_id == keys.get(check):
            e.update(applied=0, status="resolved", note=f"Resolved by reviewer: {rv.note}")
            e["evidence"] = evidence + [ev("check_review", rv.id, "Recruiter review", rv.at)]
        entries.append(e)

    def check_row(key: str, title: str, bucket: str, detail: str, simulated: bool = False, run=None) -> None:
        rv = reviews.get(key) if key in ("identity", "education", "employment", "resume") else None
        checks.append({"key": key, "title": title, "bucket": bucket, "label": BUCKET_LABEL[bucket], "detail": detail, "simulated": simulated,
                       "runId": run.id if run else None, "at": serialize.iso(run.finished_at or run.started_at) if run else None,
                       "concernKey": keys.get(key),
                       "review": {"status": rv.status, "note": rv.note, "at": serialize.iso(rv.at)} if rv and run and rv.evidence_run_id == keys.get(key) else None})

    # ---------------- identity
    if cand.phone_verified_at:
        apply("ID.PHONE_OTP", [ev("candidate", cand.id, "OTP verified at registration", cand.phone_verified_at)])
        check_row("phone", "Mobile number", "verified", "Verified by one-time code")
    else:
        check_row("phone", "Mobile number", "pending", "Not verified (number changed after registration)")
    run = runs.get("identity")
    idres = results["identity"]
    iddoc = (idres.get("idDocument") or {}) if run else {}
    if run and iddoc.get("status") == "match":
        apply("ID.FACE_ID_MATCH", [ev("verification_run", run.id, f"Selfie vs ID similarity {iddoc.get('similarity')}", run.finished_at)], check="identity")
    elif run and iddoc.get("status") == "no_match":
        apply("ID.FACE_ID_MISMATCH", [ev("verification_run", run.id, f"Selfie vs ID similarity {iddoc.get('similarity')}", run.finished_at)], check="identity")
    check_row("identity", "Identity (selfie vs ID)", RUN_BUCKET.get(run.status, "pending") if run else "not_started",
              idres.get("summary") or "Not run yet.", run=run)
    rechecks = db.query(FaceCheck).filter(FaceCheck.candidate_id == cand.id, FaceCheck.stage != "id_document").order_by(FaceCheck.at).all()
    good = [f for f in rechecks if f.decision == "match"]
    bad = [f for f in rechecks if f.decision == "no_match"]
    if good:
        apply("ID.RECHECK_MATCH", [ev("face_check", f.id, f"{f.stage}: similarity {f.similarity}", f.at) for f in good[-3:]])
    if bad:
        apply("ID.RECHECK_MISMATCH", [ev("face_check", f.id, f"{f.stage}: similarity {f.similarity}", f.at) for f in bad[-3:]], check="identity")

    # ---------------- documents (education, employment, resume)
    def doc_rules(check: str, title: str, ok_rule: str, bad_rule: str) -> None:
        run = runs.get(check)
        res = results[check]
        if not run:
            check_row(check, title, "not_started", "Not run yet.")
            return
        bucket = RUN_BUCKET.get(run.status, "pending")
        crit = [f for f in res.get("findings") or [] if f.get("severity") in ("critical", "warning")]
        evid = [ev("verification_run", run.id, res.get("summary") or run.status, run.finished_at)]
        if res.get("consistency") in ("consistent", "partially_consistent") and run.status in ("consistent", "verified"):
            apply(ok_rule, evid)
        elif run.status == "inconsistent" and res.get("consistency") == "inconsistent":
            apply(bad_rule, evid + [ev("finding", f.get("code"), f.get("title", ""), run.finished_at) for f in crit[:5]], check=check)
        if bucket == "verified":  # document consistency alone never means verified; the outside confirmation is scored separately
            bucket = "consistent"
        check_row(check, title, bucket, res.get("summary") or run.status, run=run)

    doc_rules("education", "Education documents", "EDU.CONSISTENT", "EDU.INCONSISTENT")
    issuer = results["education"].get("issuer") if runs.get("education") else None
    if issuer:
        sim = bool(issuer.get("simulated"))
        if issuer.get("status") == "confirmed" and not sim:
            apply("EDU.ISSUER_CONFIRMED", [ev("issuer_confirmation", None, issuer.get("detail") or "Issuer confirmed", runs["education"].finished_at)])
            check_row("issuer", "Issuer authenticity", "verified", issuer.get("label") or "Confirmed by the issuer")
        elif issuer.get("status") == "denied" and not sim:
            apply("EDU.ISSUER_DENIED", [ev("issuer_confirmation", None, issuer.get("detail") or "Issuer denied", runs["education"].finished_at)], check="education")
            check_row("issuer", "Issuer authenticity", "inconsistent", issuer.get("label") or "Issuer did not confirm")
        else:
            check_row("issuer", "Issuer authenticity", "pending",
                      (issuer.get("label") or "Not checked with the issuer") + (" — simulated data, not counted" if sim else ""), simulated=sim)
    else:
        check_row("issuer", "Issuer authenticity", "not_started", "Not checked with the issuer.")
    dl = results["education"].get("digilocker") if runs.get("education") else None
    if dl and dl.get("status") in ("match", "mismatch", "partial", "no_upload"):  # row only exists once a DigiLocker copy was pulled
        dl_ev = [ev("digilocker_document", dl.get("documentId"), dl.get("summary", ""), dl.get("fetchedAt"))]
        if dl.get("simulated"):
            check_row("digilocker", "DigiLocker comparison", "pending", "SIMULATED DigiLocker record — shown for testing, not counted", simulated=True)
        elif dl["status"] == "match":
            apply("EDU.DIGILOCKER_MATCH", dl_ev)
            check_row("digilocker", "DigiLocker comparison", "verified", dl.get("summary", ""))
        elif dl["status"] == "mismatch":
            apply("EDU.DIGILOCKER_MISMATCH", dl_ev, check="education")
            check_row("digilocker", "DigiLocker comparison", "inconsistent", dl.get("summary", ""))
        else:
            check_row("digilocker", "DigiLocker comparison", "needs_review" if dl["status"] == "partial" else "pending", dl.get("summary", ""))
    doc_rules("employment", "Employment documents", "EMP.CONSISTENT", "EMP.INCONSISTENT")
    for ref in results["employment"].get("references") or [] if runs.get("employment") else []:
        title = f"Reference: {ref.get('referee')}"
        if ref.get("simulated"):
            check_row(f"ref-{ref['id']}", title, "pending", "SIMULATED answer — not counted", simulated=True)
        elif ref.get("status") == "responded" and ref.get("confirmed") is True:
            apply("EMP.REFERENCE_CONFIRMED", [ev("reference_request", ref["id"], f"{ref.get('referee')} confirmed", ref.get("respondedAt"))])
            check_row(f"ref-{ref['id']}", title, "verified", "Confirmed the employment")
        elif ref.get("status") == "responded" and ref.get("confirmed") is False:
            apply("EMP.REFERENCE_DENIED", [ev("reference_request", ref["id"], f"{ref.get('referee')} did not confirm", ref.get("respondedAt"))], check="employment")
            check_row(f"ref-{ref['id']}", title, "inconsistent", "Did not confirm the employment")
        else:
            check_row(f"ref-{ref['id']}", title, "pending", "Waiting for the referee" if ref.get("status") == "sent" else str(ref.get("status")))
    doc_rules("resume", "Resume vs profile", "RES.CONSISTENT", "RES.INCONSISTENT")

    # ---------------- duplicates & patterns (human-reviewed alerts)
    org_id = app.job.organization_id
    dups = db.query(DuplicateAlert).filter((DuplicateAlert.candidate_a_id == cand.id) | (DuplicateAlert.candidate_b_id == cand.id)).all()
    drev = alert_reviews.latest(db, "duplicate", [d.id for d in dups], org_id)
    dst = {d.id: alert_reviews.status(drev.get(d.id)) for d in dups}
    open_d = [d for d in dups if dst[d.id] == "open"]
    conf_d = [d for d in dups if dst[d.id] == "confirmed_duplicate"]
    for i, d in enumerate(open_d):
        apply("DUP.OPEN_ALERT", [ev("duplicate_alert", d.id, f"{d.kind} match", d.created_at)])
        if i + 1 > config.CAPS["DUP.OPEN_ALERT"]:
            entries[-1].update(applied=0, status="capped", note="Cap reached; counted at most twice")
    for d in conf_d:
        apply("DUP.CONFIRMED", [ev("duplicate_alert", d.id, f"{d.kind} match confirmed: {drev[d.id].note}", drev[d.id].at)])
    for d in dups:
        if dst[d.id] == "not_duplicate":
            entries.append({"ruleId": "DUP.OPEN_ALERT", "label": rules["DUP.OPEN_ALERT"]["label"], "category": "duplicates", "weight": rules["DUP.OPEN_ALERT"]["weight"],
                            "applied": 0, "status": "resolved", "evidence": [ev("duplicate_alert", d.id, f"{d.kind} match", d.created_at)],
                            "at": serialize.iso(drev[d.id].at), "note": f"Reviewed – not a duplicate: {drev[d.id].note}"})
    check_row("duplicate", "Duplicate profiles", "inconsistent" if conf_d else "needs_review" if open_d else
              ("consistent" if runs.get("duplicate") else "not_started"),
              f"{len(open_d)} open, {len(conf_d)} confirmed, {len(dups) - len(open_d) - len(conf_d)} dismissed" if dups else
              ("No shared verified number or similar face found" if runs.get("duplicate") else "Not run yet."), run=runs.get("duplicate"))
    pats = db.query(PatternAlert).filter_by(candidate_id=cand.id).order_by(PatternAlert.first_seen).all()
    prev = alert_reviews.latest(db, "pattern", [p.id for p in pats], org_id)
    pst = {p.id: alert_reviews.status(prev.get(p.id)) for p in pats}
    open_p = [p for p in pats if pst[p.id] == "open"]
    for i, p in enumerate(open_p):
        apply("PAT.OPEN_ALERT", [ev("pattern_alert", p.id, PATTERN_LABELS.get(p.rule_id, p.rule_id), p.last_seen)])
        if i + 1 > config.CAPS["PAT.OPEN_ALERT"]:
            entries[-1].update(applied=0, status="capped", note="Cap reached; counted at most three times")
    for p in pats:
        if pst[p.id] == "confirmed":
            apply("PAT.CONFIRMED", [ev("pattern_alert", p.id, f"{PATTERN_LABELS.get(p.rule_id)}: {prev[p.id].note}", prev[p.id].at)])
        elif pst[p.id] == "reviewed_ok":
            entries.append({"ruleId": "PAT.OPEN_ALERT", "label": rules["PAT.OPEN_ALERT"]["label"], "category": "patterns", "weight": rules["PAT.OPEN_ALERT"]["weight"],
                            "applied": 0, "status": "resolved", "evidence": [ev("pattern_alert", p.id, PATTERN_LABELS.get(p.rule_id, p.rule_id), p.last_seen)],
                            "at": serialize.iso(prev[p.id].at), "note": f"Reviewed – OK: {prev[p.id].note}"})
    check_row("patterns", "Application patterns", "needs_review" if open_p else "consistent",
              f"{len(open_p)} open alert(s)" if open_p else ("No unusual patterns" if not pats else f"{len(pats)} alert(s) reviewed"))

    # ---------------- assessment: reported separately, never part of the score
    attempts = db.query(Assessment).filter_by(application_id=app.id).all()
    assessment = [{"id": s.id, "title": s.title, "status": s.status, "score": s.score, "maxScore": s.max_score, "percent": s.percent,
                   "reviewSignals": (s.tab_switches or 0) + (s.copy_paste or 0)} for s in attempts]

    raw = cfg["baseline"] + sum(e["applied"] for e in entries)
    score = max(config.SCORE_MIN, min(config.SCORE_MAX, raw))
    grouped = {b: [c for c in checks if c["bucket"] == b] for b in BUCKETS}
    review_count = len(grouped["needs_review"]) + len(grouped["inconsistent"])
    return {
        "version": cfg["version"], "baseline": cfg["baseline"], "score": score, "rawScore": raw, "risk": risk_band(score, review_count),
        "entries": entries, "checks": checks, "groups": {b: [c["key"] for c in grouped[b]] for b in BUCKETS},
        "pendingCount": len(grouped["pending"]) + len(grouped["not_started"]),
        "reviewCount": len(grouped["needs_review"]) + len(grouped["inconsistent"]),
        "assessment": assessment,
        "disclaimer": "Decision support only. The score summarises the evidence collected so far; it is not a measure of a person's honesty, "
                      "and nobody is rejected automatically. Pending checks add nothing until they are actually completed.",
    }


def _fingerprint(result: dict) -> str:
    key = {"v": result["version"], "s": result["score"], "e": [(e["ruleId"], e["applied"], e["status"], [x.get("id") for x in e["evidence"]]) for e in result["entries"]],
           "c": [(c["key"], c["bucket"]) for c in result["checks"]]}
    return hashlib.sha256(json.dumps(key, sort_keys=True, default=str).encode()).hexdigest()


def refresh(db: Session, app: Application, trigger: str) -> ScoreRecord:
    """Recompute; append a score record only when the result changed. Caller commits."""
    result = compute(db, app)
    ensure_ruleset(db, config.current())
    fp = _fingerprint(result)
    last = db.query(ScoreRecord).filter_by(application_id=app.id).order_by(ScoreRecord.computed_at.desc(), ScoreRecord.id.desc()).first()
    if last and last.fingerprint == fp:
        last.live = result  # transient: freshest details (e.g. assessment summary) without a new history row
        return last
    rec = ScoreRecord(application_id=app.id, ruleset_version=result["version"], score=result["score"], raw_score=result["rawScore"],
                      breakdown=result, fingerprint=fp, trigger=trigger)
    db.add(rec)
    tr = app.trust_report or TrustReport(application_id=app.id)
    tr.score, tr.risk, tr.breakdown, tr.computed_at = result["score"], result["risk"], {"scoreRecordId": rec.id, "version": result["version"]}, utcnow()
    if not app.trust_report:
        db.add(tr)
    db.flush()
    rec.live = result
    from ..evidence import passport
    passport.on_new_score(db, app, rec)
    return rec


def refresh_candidate(db: Session, candidate_id: str, trigger: str) -> None:
    for app in db.query(Application).filter_by(candidate_id=candidate_id):
        refresh(db, app, trigger)
