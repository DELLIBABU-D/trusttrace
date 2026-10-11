"""Deterministic comparison rules. These – not an AI model – decide whether something matches.

Each rule returns comparison rows and findings. A field that could not be extracted with enough confidence is
reported as "not checked" (match = None) and never as a mismatch, so poor scans do not create false accusations.
"""
from __future__ import annotations

from dataclasses import dataclass, field as dc_field
from datetime import date

from .fields import company_similarity, degree_code, name_similarity, name_tokens

MIN_CONFIDENCE = 0.6       # below this an extracted value is shown but never used to declare a mismatch
NAME_MATCH = 0.8           # token similarity for "same name"
NAME_MISMATCH = 0.34       # below this (with confident extraction) the names are considered different
COMPANY_MATCH = 0.6
DATE_TOLERANCE_MONTHS = 1  # letters often say 1 Jun while the profile says May/Jun
OVERLAP_MONTHS = 2         # full-time jobs overlapping more than this need review


@dataclass
class Finding:
    code: str
    severity: str  # info | warning | critical
    title: str
    detail: str
    evidence: dict = dc_field(default_factory=dict)


@dataclass
class CheckResult:
    comparison: list[dict] = dc_field(default_factory=list)
    findings: list[Finding] = dc_field(default_factory=list)

    def row(self, label: str, extracted, claimed, match: bool | None, note: str = "", ev: dict | None = None):
        self.comparison.append({"field": label, "extracted": _s(extracted), "claimed": _s(claimed), "match": match, "note": note, "evidence": ev or {}})

    @property
    def match_score(self) -> int | None:
        decided = [c for c in self.comparison if c["match"] is not None]
        return round(100 * sum(c["match"] for c in decided) / len(decided)) if decided else None

    @property
    def consistency(self) -> str:
        if any(f.severity == "critical" for f in self.findings) or any(c["match"] is False for c in self.comparison):
            return "inconsistent"
        if any(f.severity == "warning" for f in self.findings):
            return "needs_review"
        if not any(c["match"] is True for c in self.comparison):
            return "insufficient_data"
        if any(c["match"] is None for c in self.comparison):
            return "partially_consistent"
        return "consistent"


def _s(v):
    if v is None:
        return None
    if isinstance(v, list):
        return ", ".join(str(x) for x in v)
    return str(v)


def _val(f: dict | None):
    return f.get("value") if f else None


def _confident(f: dict | None) -> bool:
    return bool(f) and f.get("value") not in (None, "", []) and f.get("confidence", 0) >= MIN_CONFIDENCE


def _ev(f: dict | None, doc_id: str | None) -> dict:
    if not f:
        return {}
    return {"documentId": doc_id, "page": f.get("page"), "snippet": f.get("snippet"), "source": f.get("source")}


def _months(ym: str | None) -> int | None:
    if not ym or ym == "present":
        return None
    y, m = ym[:7].split("-")[:2]
    return int(y) * 12 + int(m)


def _month_of(iso_or_ym: str | None) -> str | None:
    return iso_or_ym[:7] if iso_or_ym and iso_or_ym != "present" else iso_or_ym


def compare_name(r: CheckResult, extracted: dict | None, claimed: str, doc_id: str | None, where: str):
    if not extracted:
        r.row("Name", None, claimed, None, f"Name not found on the {where}")
        return
    sim = name_similarity(_val(extracted), claimed)
    if sim >= NAME_MATCH:
        r.row("Name", _val(extracted), claimed, True, ev=_ev(extracted, doc_id))
    elif sim < NAME_MISMATCH and _confident(extracted) and len(name_tokens(_val(extracted))) >= 2:
        r.row("Name", _val(extracted), claimed, False, f"Name similarity {sim:.2f}", _ev(extracted, doc_id))
        r.findings.append(Finding("name_mismatch", "warning", f"Name on the {where} differs from the profile",
                                  f"The {where} shows \"{_val(extracted)}\" but the profile name is \"{claimed}\".", _ev(extracted, doc_id)))
    else:
        r.row("Name", _val(extracted), claimed, None, f"Partial name match ({sim:.2f}); needs a person to check", _ev(extracted, doc_id))


# ------------------------------------------------------------------------------------------- resume vs profile

def resume_rules(resume: dict | None, profile: dict, doc_id: str | None, dob: date | None) -> CheckResult:
    r = CheckResult()
    if resume is None:
        r.findings.append(Finding("resume_missing", "info", "No resume uploaded", "Upload a resume to compare it with the profile."))
        timeline_rules(r, profile, dob)
        return r
    compare_name(r, resume.get("name"), profile["fullName"], doc_id, "resume")

    # Education: graduation year, degree and institution of each profile entry
    entries = resume.get("education") or []
    for edu in profile.get("education", []):
        code = degree_code(edu["degree"])
        match = next((e for e in entries if code and e["degree"].get("code") == code), None)
        label = edu["degree"]
        if not match:
            r.row(f"{label}: listed on resume", None, label, None, "Degree not found on the resume")
            r.findings.append(Finding("degree_not_on_resume", "info", f"{label} is not mentioned on the resume",
                                      "The profile lists this qualification but the resume text does not mention it."))
            continue
        ey = match.get("endYear")
        if _confident(ey):
            ok = int(_val(ey)) == int(edu["endYear"])
            r.row(f"{label}: graduation year", _val(ey), edu["endYear"], ok, ev=_ev(ey, doc_id))
            if not ok:
                r.findings.append(Finding("graduation_year_mismatch", "warning", f"{label} graduation year differs",
                                          f"Resume says {_val(ey)}, profile says {edu['endYear']}.", _ev(ey, doc_id)))
        else:
            r.row(f"{label}: graduation year", _val(ey), edu["endYear"], None, "Year not read with enough confidence", _ev(ey, doc_id))
        inst = match.get("institution")
        if inst:
            sim = company_similarity(_val(inst), edu["institution"])
            r.row(f"{label}: institution", _val(inst), edu["institution"], True if sim >= COMPANY_MATCH else None,
                  "" if sim >= COMPANY_MATCH else f"Institution names differ (similarity {sim:.2f}); check abbreviations", _ev(inst, doc_id))

    # Skills: missing skills are information only (a resume need not list everything)
    skills_found = set(s.lower() for s in (_val(resume.get("skills")) or []))
    claimed_skills = profile.get("skills", [])
    if claimed_skills:
        missing = [s for s in claimed_skills if s.lower() not in skills_found]
        r.row("Profile skills mentioned on resume", f"{len(claimed_skills) - len(missing)} of {len(claimed_skills)}", ", ".join(claimed_skills),
              None if missing else True, f"Not mentioned: {', '.join(missing)}" if missing else "")
        if missing:
            r.findings.append(Finding("skills_not_evidenced", "info", "Some profile skills are not on the resume", ", ".join(missing)))

    # Employment
    jobs = resume.get("employment") or []
    for exp in profile.get("experience", []):
        best = max(jobs, key=lambda j: company_similarity(_val(j.get("company")) or "", exp["company"]), default=None)
        sim = company_similarity(_val(best.get("company")) or "", exp["company"]) if best else 0
        if not best or sim < COMPANY_MATCH:
            r.row(f"{exp['company']}: on resume", None, exp["company"], None, "Employer not found on the resume")
            r.findings.append(Finding("employment_not_on_resume", "info", f"{exp['company']} is not on the resume",
                                      "The profile lists this job but the resume text does not mention it with dates."))
            continue
        _compare_dates(r, f"{exp['company']}: start", best.get("start"), exp["start"], doc_id, "resume")
        claimed_end = "present" if exp.get("current") else exp.get("end")
        _compare_dates(r, f"{exp['company']}: end", best.get("end"), claimed_end, doc_id, "resume")
    timeline_rules(r, profile, dob, jobs)
    return r


def _compare_dates(r: CheckResult, label: str, extracted: dict | None, claimed: str | None, doc_id: str | None, where: str):
    ext = _val(extracted)
    if not _confident(extracted) or not claimed:
        r.row(label, ext, claimed, None, "Date not read with enough confidence" if claimed else "", _ev(extracted, doc_id))
        return
    ext_m, claim_m = _month_of(ext), _month_of(claimed)
    if ext_m == "present" or claim_m == "present":
        ok = ext_m == claim_m
        r.row(label, ext_m, claim_m, ok, ev=_ev(extracted, doc_id))
    else:
        diff = abs(_months(ext_m) - _months(claim_m))
        ok = diff <= DATE_TOLERANCE_MONTHS
        r.row(label, ext_m, claim_m, ok, "" if ok else f"Differs by {diff} months", _ev(extracted, doc_id))
    if not ok:
        r.findings.append(Finding("employment_date_mismatch", "warning", f"{label} date differs",
                                  f"The {where} says {ext_m}, the profile says {claim_m}.", _ev(extracted, doc_id)))


def timeline_rules(r: CheckResult, profile: dict, dob: date | None, resume_jobs: list[dict] | None = None):
    """Impossible or suspicious timelines in what the candidate entered (and in resume dates)."""
    jobs = [(e["company"], _months(e["start"]), None if e.get("current") else _months(e.get("end")), "intern" in e.get("title", "").lower())
            for e in profile.get("experience", [])]
    today = date.today()
    now_m = today.year * 12 + today.month
    birth_m = dob.year * 12 + dob.month if dob else None
    for company, s, e, _ in jobs:
        if s and e and e < s:
            r.findings.append(Finding("impossible_timeline", "critical", f"{company}: ends before it starts", "The end date is earlier than the start date."))
        if s and s > now_m + 1:
            r.findings.append(Finding("future_date", "critical", f"{company}: starts in the future", "The start date is after today."))
        if s and birth_m and s - birth_m < 14 * 12:
            r.findings.append(Finding("impossible_timeline", "critical", f"{company}: started before age 14",
                                      "The job start date is before the candidate turned 14."))
    full_time = [j for j in jobs if not j[3] and j[1]]
    for i in range(len(full_time)):
        for k in range(i + 1, len(full_time)):
            a, b = full_time[i], full_time[k]
            a_end, b_end = a[2] or now_m, b[2] or now_m
            overlap = min(a_end, b_end) - max(a[1], b[1])
            if overlap > OVERLAP_MONTHS:
                r.findings.append(Finding("employment_overlap", "warning", f"{a[0]} and {b[0]} overlap by {overlap} months",
                                          "Two full-time jobs at the same time can be legitimate (part-time, notice period) but need a person to check."))
    for edu in profile.get("education", []):
        if birth_m and int(edu["endYear"]) * 12 - birth_m < 14 * 12:
            r.findings.append(Finding("impossible_timeline", "critical", f"{edu['degree']}: completed before age 14",
                                      "The education end year is before the candidate turned 14."))
    for j in resume_jobs or []:
        s, e = _months(_val(j.get("start"))), _months(_val(j.get("end")))
        if s and e and e < s and _confident(j.get("start")):
            r.findings.append(Finding("impossible_timeline", "warning", "A resume job ends before it starts",
                                      f"{_val(j.get('start'))} to {_val(j.get('end'))}", j["start"]))


# ------------------------------------------------------------------------------------------- education documents

def education_rules(doc: dict | None, profile: dict, resume: dict | None, doc_id: str | None) -> CheckResult:
    r = CheckResult()
    if doc is None:
        return r
    compare_name(r, doc.get("name"), profile["fullName"], doc_id, "marksheet/certificate")
    educ = profile.get("education", [])
    code = (doc.get("degree") or {}).get("code")
    target = next((e for e in educ if code and degree_code(e["degree"]) == code), None) or (educ[0] if educ else None)
    if doc.get("degree"):
        if target and code:
            ok = degree_code(target["degree"]) == code
            r.row("Degree", _val(doc["degree"]), target["degree"], ok if _confident(doc["degree"]) else None, ev=_ev(doc["degree"], doc_id))
    if target and doc.get("institution"):
        sim = company_similarity(_val(doc["institution"]), target["institution"])
        r.row("Board / University", _val(doc["institution"]), target["institution"], True if sim >= COMPANY_MATCH else None,
              "" if sim >= COMPANY_MATCH else f"Names differ (similarity {sim:.2f}); check abbreviations or affiliating university",
              _ev(doc["institution"], doc_id))
    elif target:
        r.row("Board / University", None, target["institution"], None, "Not found on the document")
    yr = doc.get("year")
    if target:
        if _confident(yr):
            ok = int(_val(yr)) == int(target["endYear"])
            r.row("Year", _val(yr), target["endYear"], ok, ev=_ev(yr, doc_id))
            if not ok:
                r.findings.append(Finding("education_year_mismatch", "warning", "Year on the document differs from the profile",
                                          f"Document: {_val(yr)}. Profile: {target['endYear']}.", _ev(yr, doc_id)))
        else:
            r.row("Year", _val(yr), target["endYear"], None, "Year not read with enough confidence", _ev(yr, doc_id))
    # resume cross-check
    if resume and target and _confident(yr):
        entry = next((e for e in resume.get("education", []) if e["degree"].get("code") == degree_code(target["degree"])), None)
        if entry and _confident(entry.get("endYear")) and int(_val(entry["endYear"])) != int(_val(yr)):
            r.findings.append(Finding("resume_document_year_conflict", "warning", "Resume and certificate show different years",
                                      f"Resume: {_val(entry['endYear'])}. Certificate: {_val(yr)}.", _ev(yr, doc_id)))
    score_claim = (target or {}).get("score", "")
    doc_score = doc.get("cgpa") or doc.get("percentage")
    if score_claim and doc_score:
        try:
            a, b = float(_val(doc_score)), float(str(score_claim).replace("%", "").split("/")[0])
            ok = abs(a - b) <= (0.1 if a <= 10 and b <= 10 else 1.0) if (a <= 10) == (b <= 10) else None
            r.row("CGPA / Percentage", _val(doc_score), score_claim, ok if _confident(doc_score) else None,
                  "" if ok is not None else "Different scales (CGPA vs %); not compared", _ev(doc_score, doc_id))
            if ok is False and _confident(doc_score):
                r.findings.append(Finding("score_mismatch", "warning", "Score differs from the profile",
                                          f"Document: {_val(doc_score)}. Profile: {score_claim}.", _ev(doc_score, doc_id)))
        except ValueError:
            pass
    if doc.get("registerNumber"):
        r.row("Register Number", _val(doc["registerNumber"]), None, None, "Recorded for issuer confirmation", _ev(doc["registerNumber"], doc_id))
    if doc.get("totalMarks"):
        r.row("Total Marks", _val(doc["totalMarks"]), None, None, "", _ev(doc["totalMarks"], doc_id))
    return r


# ------------------------------------------------------------------------------------------- employment documents

def employment_rules(letter: dict | None, profile: dict, resume: dict | None, doc_id: str | None) -> CheckResult:
    r = CheckResult()
    exps = profile.get("experience", [])
    if letter is None:
        return r
    compare_name(r, letter.get("name"), profile["fullName"], doc_id, "experience letter")
    comp = letter.get("company")
    target = max(exps, key=lambda e: company_similarity(_val(comp) or "", e["company"]), default=None) if comp else None
    sim = company_similarity(_val(comp) or "", target["company"]) if target else 0
    if not comp:
        r.row("Company", None, ", ".join(e["company"] for e in exps) or None, None, "Company not found on the letter")
        return r
    if not target or sim < COMPANY_MATCH:
        r.row("Company", _val(comp), ", ".join(e["company"] for e in exps) or None, False if _confident(comp) and exps else None,
              "This employer is not in the profile", _ev(comp, doc_id))
        if _confident(comp):
            r.findings.append(Finding("letter_company_not_in_profile", "warning", "Experience letter is from an employer not listed in the profile",
                                      f"Letter: {_val(comp)}.", _ev(comp, doc_id)))
        return r
    r.row("Company", _val(comp), target["company"], True, ev=_ev(comp, doc_id))
    des = letter.get("designation")
    if des:
        s2 = name_similarity(_val(des), target["title"])
        r.row("Designation", _val(des), target["title"], True if s2 >= 0.5 else (False if _confident(des) and s2 == 0 else None),
              "" if s2 >= 0.5 else "Titles differ; check whether it is the same role", _ev(des, doc_id))
        if s2 == 0 and _confident(des):
            r.findings.append(Finding("designation_mismatch", "warning", "Designation differs from the profile",
                                      f"Letter: {_val(des)}. Profile: {target['title']}.", _ev(des, doc_id)))
    else:
        r.row("Designation", None, target["title"], None, "Not found on the letter")
    _compare_dates(r, "Joining Date", letter.get("joiningDate"), target["start"], doc_id, "letter")
    claimed_end = "present" if target.get("current") else target.get("end")
    rel = letter.get("relievingDate")
    if rel or claimed_end:
        _compare_dates(r, "Relieving Date", rel, claimed_end, doc_id, "letter")
    if letter.get("durationMonths"):
        r.row("Experience Duration", f"{_val(letter['durationMonths'])} months", None, None)
    if resume:
        job = max(resume.get("employment") or [], key=lambda j: company_similarity(_val(j.get("company")) or "", target["company"]), default=None)
        if job and company_similarity(_val(job.get("company")) or "", target["company"]) >= COMPANY_MATCH and _confident(job.get("start")) \
                and _confident(letter.get("joiningDate")):
            diff = abs(_months(_val(job["start"])) - _months(_month_of(_val(letter["joiningDate"]))))
            if diff > DATE_TOLERANCE_MONTHS:
                r.findings.append(Finding("resume_letter_date_conflict", "warning", "Resume and experience letter show different joining dates",
                                          f"Resume: {_val(job['start'])}. Letter: {_month_of(_val(letter['joiningDate']))}.", _ev(letter['joiningDate'], doc_id)))
    return r
