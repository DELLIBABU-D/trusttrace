"""Suspicious application-pattern rules (P1–P5). Thresholds live in fraud/config.py.

Each rule writes a PatternAlert with the rule id, the evidence that triggered it, first/last time seen, a severity and a
signal strength. Alerts are review prompts: shared devices and networks in particular have many innocent explanations.
Evidence about other accounts is limited to masked account references.
"""
from __future__ import annotations

from datetime import timedelta

from sqlalchemy.orm import Session

from ..models import ActivityEvent, Application, Candidate, DeviceSighting, Document, PatternAlert, utcnow
from . import config

LABELS = {
    "P1.RAPID_APPLICATIONS": "Many applications in a short time",
    "P2.REPEATED_SUBMISSIONS": "Repeated submissions to the same job",
    "P3.SHARED_DEVICE": "Browser shared with other candidate accounts",
    "P4.SHARED_NETWORK": "Network address shared with several candidate accounts",
    "P5.DOCUMENT_CHURN": "Same document replaced many times",
}
EXPLAIN = {
    "P1.RAPID_APPLICATIONS": "Could be a script, or simply someone applying to several roles quickly.",
    "P2.REPEATED_SUBMISSIONS": "Could be automation, or repeated clicks on a slow connection.",
    "P3.SHARED_DEVICE": "Family members, shared or lab computers and cyber cafés also share browsers.",
    "P4.SHARED_NETWORK": "Very weak: colleges, offices and mobile carriers put many people behind one address.",
    "P5.DOCUMENT_CHURN": "Could be fixing scan quality, or trying documents until one passes.",
}


def mask(candidate_id: str) -> str:
    return f"Candidate account …{candidate_id[-6:]}"


def _upsert(db: Session, cand_id: str, rule: str, key: str, severity: str, strength: str, evidence: dict, first, last) -> None:
    a = db.query(PatternAlert).filter_by(candidate_id=cand_id, rule_id=rule, evidence_key=key).one_or_none()
    if a:
        a.evidence, a.last_seen = evidence, max(a.last_seen, last)
        return
    db.add(PatternAlert(candidate_id=cand_id, rule_id=rule, evidence_key=key[:80], severity=severity, strength=strength,
                        evidence=evidence, first_seen=first, last_seen=last))


def _burst(times: list, count: int, window: timedelta):
    """First window containing >= count events, as (start, end, n) or None."""
    times = sorted(times)
    for i in range(len(times) - count + 1):
        j = i + count - 1
        if times[j] - times[i] <= window:
            k = j
            while k + 1 < len(times) and times[k + 1] - times[i] <= window:
                k += 1
            return times[i], times[k], k - i + 1
    return None


def scan(db: Session, cand: Candidate) -> None:
    p = config.current()["patterns"]
    # P1 rapid applications
    times = [a.applied_at for a in db.query(Application).filter_by(candidate_id=cand.id)]
    hit = _burst(times, p["rapid_applications"]["count"], timedelta(minutes=p["rapid_applications"]["window_minutes"]))
    if hit:
        start, end, n = hit
        _upsert(db, cand.id, "P1.RAPID_APPLICATIONS", start.strftime("%Y%m%d%H%M"), "warning", "weak",
                {"applications": n, "windowMinutes": p["rapid_applications"]["window_minutes"], "from": start.isoformat() + "Z", "to": end.isoformat() + "Z"},
                start, end)
    # P2 repeated submissions (duplicate apply attempts are logged by jobs.apply)
    attempts: dict[str, list] = {}
    for ev in db.query(ActivityEvent).filter_by(actor_id=cand.user_id, action="application.duplicate_attempt"):
        attempts.setdefault(ev.entity_id, []).append(ev.at)
    for job_id, ts in attempts.items():
        hit = _burst(ts, p["repeated_submissions"]["count"], timedelta(minutes=p["repeated_submissions"]["window_minutes"]))
        if hit:
            start, end, n = hit
            _upsert(db, cand.id, "P2.REPEATED_SUBMISSIONS", f"{job_id}:{start:%Y%m%d%H%M}", "info", "weak",
                    {"attempts": n, "jobId": job_id, "windowMinutes": p["repeated_submissions"]["window_minutes"]}, start, end)
    # P3 shared device / P4 shared network
    mine = db.query(DeviceSighting).filter_by(candidate_id=cand.id).all()
    for dev in {s.device_hash for s in mine if s.device_hash}:
        others = {s.candidate_id for s in db.query(DeviceSighting).filter(DeviceSighting.device_hash == dev, DeviceSighting.candidate_id != cand.id)}
        if len(others) + 1 >= p["shared_device"]["accounts"]:
            seen = [s.at for s in db.query(DeviceSighting).filter_by(device_hash=dev)]
            everyone = others | {cand.id}
            for cid in everyone:  # symmetric: every account on the browser gets the alert, not only the newest
                _upsert(db, cid, "P3.SHARED_DEVICE", f"dev:{dev[:16]}", "warning", "medium",
                        {"otherAccounts": sorted(mask(o) for o in everyone - {cid}), "deviceRef": dev[:8]}, min(seen), max(seen))
    window = timedelta(hours=p["shared_network"]["window_hours"])
    for s in [x for x in mine if x.network_hash]:
        near = db.query(DeviceSighting).filter(DeviceSighting.network_hash == s.network_hash, DeviceSighting.at >= s.at - window, DeviceSighting.at <= s.at + window)
        accounts = {x.candidate_id for x in near}
        if len(accounts) >= p["shared_network"]["accounts"]:
            for cid in accounts:
                _upsert(db, cid, "P4.SHARED_NETWORK", f"net:{s.network_hash[:16]}:{s.at:%Y%m%d}", "info", "weak",
                        {"accountsOnNetwork": len(accounts), "windowHours": p["shared_network"]["window_hours"], "networkRef": s.network_hash[:8]}, s.at, s.at)
            break
    # P5 document churn
    since = utcnow() - timedelta(hours=p["document_churn"]["window_hours"])
    kinds: dict[str, list] = {}
    for d in db.query(Document).filter(Document.candidate_id == cand.id, Document.uploaded_at >= since):
        kinds.setdefault(d.kind, []).append(d.uploaded_at)
    for kind, ts in kinds.items():
        if len(ts) >= p["document_churn"]["count"]:
            _upsert(db, cand.id, "P5.DOCUMENT_CHURN", f"{kind}:{min(ts):%Y%m%d}", "info", "weak",
                    {"documentType": kind, "uploads": len(ts), "windowHours": p["document_churn"]["window_hours"]}, min(ts), max(ts))


def alert_json(a: PatternAlert, review=None) -> dict:
    """``review`` is the viewing organisation's latest AlertReview (or None = open for that organisation)."""
    return {"id": a.id, "ruleId": a.rule_id, "label": LABELS.get(a.rule_id, a.rule_id), "explanation": EXPLAIN.get(a.rule_id, ""),
            "severity": a.severity, "strength": a.strength, "evidence": a.evidence, "firstSeen": a.first_seen.isoformat() + "Z",
            "lastSeen": a.last_seen.isoformat() + "Z", "reviewStatus": review.status if review else "open",
            "reviewNote": (review.note or None) if review else None,
            "reviewedAt": review.at.isoformat() + "Z" if review else None}
