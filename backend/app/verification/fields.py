"""Deterministic field extraction from document text (regular expressions and simple heuristics).

Every field carries a confidence (0–1) and evidence (page number and a short snippet) so a reviewer can see
where a value came from. When a value cannot be found it is simply absent: absence is "not found", never a mismatch.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MONTHS.update({"sept": 9, "june": 6, "july": 7, "march": 3, "april": 4, "august": 8, "january": 1, "february": 2,
               "october": 10, "november": 11, "december": 12, "september": 9})
MON = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
YEAR = r"(?:19[7-9]\d|20[0-4]\d)"

DEGREES = [  # (code, label, pattern)
    ("PHD", "Ph.D.", r"\bph\.?\s?d\b|\bdoctor of philosophy\b"),
    ("MTECH", "M.Tech", r"\bm\.?\s?tech\b|\bmaster of technology\b"),
    ("ME", "M.E.", r"\bm\.\s?e\.?(?=\s|$|,)|\bmaster of engineering\b"),
    ("MCA", "MCA", r"\bm\.?\s?c\.?\s?a\b|\bmaster of computer applications?\b"),
    ("MBA", "MBA", r"\bm\.?\s?b\.?\s?a\b|\bmaster of business administration\b"),
    ("MSC", "M.Sc", r"\bm\.?\s?sc\b|\bmaster of science\b"),
    ("BTECH", "B.Tech", r"\bb\.?\s?tech\b|\bbachelor of technology\b"),
    ("BE", "B.E.", r"\bb\.\s?e\.?(?=\s|$|,|\()|\bbachelor of engineering\b|\bB\.?E\b(?=\s*[-–(,]?\s*(?:cse|ece|eee|mech|civil|it|computer))"),
    ("BCA", "BCA", r"\bb\.?\s?c\.?\s?a\b|\bbachelor of computer applications?\b"),
    ("BSC", "B.Sc", r"\bb\.?\s?sc\b|\bbachelor of science\b"),
    ("BCOM", "B.Com", r"\bb\.?\s?com\b|\bbachelor of commerce\b"),
    ("BBA", "BBA", r"\bb\.?\s?b\.?\s?a\b|\bbachelor of business administration\b"),
    ("DIPLOMA", "Diploma", r"\bdiploma\b"),
    ("HSC", "Class XII / HSC", r"\bh\.?s\.?c\b|\bclass\s*(?:xii|12)\b|\b12th\b|\bhigher secondary\b"),
    ("SSLC", "Class X / SSLC", r"\bs\.?s\.?l\.?c\b|\bclass\s*(?:x|10)\b|\b10th\b|\bsecondary school\b"),
]
INSTITUTION_RE = re.compile(r"[A-Z][\w.&'()\- ,]*?(?:University|Institute|College|School|Board|Academy|IIT|NIT|IIIT|Vidyalaya)[\w.&'()\- ,]*", re.I)
COMPANY_SUFFIX = r"(?:pvt\.?|private|ltd\.?|limited|llp|inc\.?|corp(?:oration)?\.?|technologies|technology|solutions|systems|labs|software|services|infotech|consultancy|global|industries)"
ROLE_WORDS = r"(?:engineer|developer|intern|analyst|manager|designer|consultant|lead|architect|tester|scientist|associate|administrator|specialist|executive|programmer|trainee|officer)"
SKILLS = [
    "Python", "Java", "JavaScript", "TypeScript", "C", "C++", "C#", "Go", "Rust", "Kotlin", "Swift", "PHP", "Ruby", "R", "MATLAB", "Scala", "Dart",
    "SQL", "MySQL", "PostgreSQL", "MongoDB", "SQLite", "Oracle", "Redis", "Firebase", "Cassandra", "Elasticsearch",
    "HTML", "CSS", "React", "Angular", "Vue", "Next.js", "Node.js", "Express", "Django", "Flask", "FastAPI", "Spring", "Spring Boot", "Tailwind",
    "Bootstrap", "jQuery", "Redux", "GraphQL", "REST", "Flutter", "React Native", "Android", "iOS",
    "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "Jenkins", "Git", "GitHub", "Linux", "CI/CD", "Airflow", "Kafka", "Spark", "Hadoop",
    "Machine Learning", "Deep Learning", "NLP", "Computer Vision", "TensorFlow", "PyTorch", "Keras", "scikit-learn", "Pandas", "NumPy", "OpenCV",
    "Power BI", "Tableau", "Excel", "Data Analysis", "Data Structures", "Algorithms", "DSA", "OOP", "Selenium", "JUnit", "Pytest", "Figma",
    "IoT", "Arduino", "Embedded C", "Raspberry Pi", "Blockchain", "Cyber Security", "Networking", "Agile", "Scrum", "JIRA",
]


@dataclass
class Evidence:
    page: int | None
    snippet: str


def field(value, confidence: float, ev: Evidence | None, source: str = "rules", **extra) -> dict:
    out = {"value": value, "confidence": round(max(0.0, min(1.0, confidence)), 2), "source": source}
    if ev:
        out["page"], out["snippet"] = ev.page, ev.snippet
    out.update(extra)
    return out


# ------------------------------------------------------------------------------------------- helpers

def norm_text(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w@.+&/ -]", " ", s or "")).strip().lower()


def name_tokens(name: str) -> list[str]:
    return [t for t in re.split(r"[^a-z]+", (name or "").lower()) if t]


def name_similarity(a: str, b: str) -> float:
    """Token overlap that tolerates initials and word order ("D Delli Babu" ~ "Delli Babu D")."""
    ta, tb = name_tokens(a), name_tokens(b)
    if not ta or not tb:
        return 0.0
    full_a, full_b = {t for t in ta if len(t) > 1}, {t for t in tb if len(t) > 1}
    if not full_a or not full_b:
        return 0.0
    common = len(full_a & full_b)
    score = common / max(len(full_a), len(full_b))
    # initials: "s" in one name matching a full word starting with s in the other
    ini_a, ini_b = {t for t in ta if len(t) == 1}, {t for t in tb if len(t) == 1}
    extra_a, extra_b = full_a - full_b, full_b - full_a
    if ini_a and extra_b and all(any(w.startswith(i) for i in ini_a) for w in extra_b):
        score = max(score, common / len(full_a)) if full_a else score
    if ini_b and extra_a and all(any(w.startswith(i) for i in ini_b) for w in extra_a):
        score = max(score, common / len(full_b)) if full_b else score
    return round(min(1.0, score), 2)


def company_key(name: str) -> set[str]:
    words = re.sub(COMPANY_SUFFIX, " ", (name or "").lower(), flags=re.I)
    return {w for w in re.split(r"[^a-z0-9]+", words) if len(w) > 1 and w not in {"the", "and", "of", "india"}}


def company_similarity(a: str, b: str) -> float:
    ka, kb = company_key(a), company_key(b)
    if not ka or not kb:
        return 0.0
    if ka <= kb or kb <= ka:
        return 1.0
    return round(len(ka & kb) / len(ka | kb), 2)


def _evidence(page_texts: list[str], needle_start: int, text: str) -> Evidence:
    """Find which page an offset into the joined text belongs to, and cut a short snippet."""
    page, pos = None, 0
    for i, t in enumerate(page_texts):
        if needle_start < pos + len(t) + 1:
            page = i + 1
            break
        pos += len(t) + 1
    a = max(0, text.rfind("\n", 0, needle_start) + 1)
    b = text.find("\n", needle_start)
    snippet = re.sub(r"\s+", " ", text[a: b if b != -1 else None]).strip()
    return Evidence(page, snippet[:140])


def parse_date(s: str, end: bool = False) -> date | None:
    """Parse '12/06/2023', '2023-06-12', '12 June 2023', 'June 12, 2023', 'Jun 2023', '06/2023', '2023'."""
    s = (s or "").strip().lower().replace(",", " ")
    if re.fullmatch(r"(present|current|now|till date|ongoing|today)", s):
        return None
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})", s)
    if m:
        d, mo, y = int(m[1]), int(m[2]), int(m[3])
        if 1 <= mo <= 12 and 1 <= d <= 31:
            return _safe_date(y, mo, d)
    m = re.fullmatch(r"(\d{4})[/.-](\d{1,2})[/.-](\d{1,2})", s)
    if m:
        return _safe_date(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({MON})\.?\s+(\d{{4}})", s)
    if m:
        return _safe_date(int(m[3]), _mon(m[2]), int(m[1]))
    m = re.fullmatch(rf"({MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\s+(\d{{4}})", s)
    if m:
        return _safe_date(int(m[3]), _mon(m[1]), int(m[2]))
    m = re.fullmatch(rf"({MON})\.?\s*['’]?\s*(\d{{4}}|\d{{2}})", s)
    if m:
        y = int(m[2]) if len(m[2]) == 4 else 2000 + int(m[2])
        return _safe_date(y, _mon(m[1]), 28 if end else 1)
    m = re.fullmatch(r"(\d{1,2})[/.-](\d{4})", s)
    if m and 1 <= int(m[1]) <= 12:
        return _safe_date(int(m[2]), int(m[1]), 28 if end else 1)
    m = re.fullmatch(r"(\d{4})", s)
    if m:
        return _safe_date(int(m[1]), 12 if end else 1, 28 if end else 1)
    return None


def _mon(s: str) -> int:
    s = s.lower().rstrip(".")
    return MONTHS.get(s) or MONTHS[s[:3]]


def _safe_date(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, min(d, 28) if m == 2 else min(d, 30) if m in (4, 6, 9, 11) else d)
    except ValueError:
        return None


def month_str(d: date | None) -> str | None:
    return f"{d.year:04d}-{d.month:02d}" if d else None


DATE_TOKEN = rf"(?:\d{{1,2}}[/.-]\d{{1,2}}[/.-]\d{{4}}|\d{{4}}[/.-]\d{{1,2}}[/.-]\d{{1,2}}|\d{{1,2}}(?:st|nd|rd|th)?\s+{MON}\.?,?\s+\d{{4}}|{MON}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?,?\s+\d{{4}}|{MON}\.?\s*['’]?\s*(?:\d{{4}}|\d{{2}})\b|\d{{1,2}}[/.-]\d{{4}}|{YEAR})"
RANGE_RE = re.compile(rf"({DATE_TOKEN})\s*(?:-|–|—|to|till|until)\s*({DATE_TOKEN}|present|current|now|till date|ongoing)", re.I)


def find_degree(line: str) -> tuple[str, str] | None:
    for code, label, pat in DEGREES:
        if re.search(pat, line, re.I):
            return code, label
    return None


def degree_code(text: str) -> str | None:
    hit = find_degree(text or "")
    return hit[0] if hit else None


# ------------------------------------------------------------------------------------------- common fields

def contact_fields(text: str, pages: list[str]) -> dict:
    out = {}
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
    if m:
        out["email"] = field(m.group(0).lower(), 0.95, _evidence(pages, m.start(), text))
    m = re.search(r"(?:\+?91[\s-]?|0)?([6-9]\d{4}[\s-]?\d{5})\b", text)
    if m:
        out["phone"] = field(re.sub(r"\D", "", m.group(1)), 0.9, _evidence(pages, m.start(), text))
    return out


def _name_words(val: str) -> str:
    """Keep the leading words of a captured name: stop at the first ordinary lower-case word ("was", "has", "is")."""
    out = []
    for w in val.split():
        if w[0].isupper() or (len(w) <= 2 and w.rstrip(".").isalpha() and w[0].isupper()):
            out.append(w)
        else:
            break
    return " ".join(out).strip(" .")


def _clean_institution(val: str) -> str:
    val = re.split(rf"\s*{YEAR}|\s+(?:cgpa|gpa|percentage|score|marks)\b", val, maxsplit=1, flags=re.I)[0]
    return val.strip(" ,-–|")


def find_name(text: str, pages: list[str], claimed: str | None, labels: tuple[str, ...] = ()) -> dict | None:
    if labels:
        m = re.search(rf"(?:{'|'.join(labels)})\s*[:\-–.]\s*([A-Za-z][A-Za-z .']{{2,60}})", text, re.I)
        if m:
            val = re.sub(r"\s+", " ", m.group(1)).strip(" .")
            val = re.split(r"\s{2,}|\b(?:reg|register|roll|father|mother|dob|date)\b", val, flags=re.I)[0].strip(" .")
            val = _name_words(val)
            if val:
                return field(val.title() if val.isupper() else val, 0.85, _evidence(pages, m.start(1), text))
    if claimed:
        toks = [re.escape(t) for t in name_tokens(claimed) if len(t) > 1]
        if toks:
            m = re.search(r"\b" + r"[\s.,]+(?:[a-z]\.?\s*)?".join(toks) + r"\b", text, re.I)
            if m:
                return field(re.sub(r"\s+", " ", m.group(0)).strip(), 0.9, _evidence(pages, m.start(), text))
    for line in text.splitlines()[:6]:  # resume header: first short line made of letters
        s = line.strip()
        if 2 <= len(s.split()) <= 4 and re.fullmatch(r"[A-Za-z][A-Za-z .']+", s) and not re.search(r"resume|curriculum|vitae|profile|contact", s, re.I):
            return field(s.title() if s.isupper() else s, 0.6, _evidence(pages, text.find(s), text))
    return None


def find_skills(text: str, claimed: list[str]) -> list[str]:
    vocab = {s.lower(): s for s in SKILLS}
    for s in claimed or []:
        vocab.setdefault(s.lower(), s)
    found = []
    for low, original in vocab.items():
        pat = r"(?<![\w+#.])" + re.escape(low) + r"(?![\w+#])"
        if len(low) <= 2 and low not in ("go", "r", "c"):
            continue
        if low in ("c", "r", "go"):  # too ambiguous unless written as a listed skill
            pat = r"(?:^|[,:|•\-]\s*)" + re.escape(low) + r"(?=\s*(?:,|\||•|$|\n))"
        if re.search(pat, text, re.I | re.M):
            found.append(original)
    return sorted(set(found), key=str.lower)


# ------------------------------------------------------------------------------------------- resume

def education_entries(text: str, pages: list[str]) -> list[dict]:
    lines = text.splitlines()
    offsets, pos = [], 0
    for ln in lines:
        offsets.append(pos)
        pos += len(ln) + 1
    entries = []
    used = set()
    for i, ln in enumerate(lines):
        deg = find_degree(ln)
        if not deg or i in used:
            continue
        window = " ".join(lines[max(0, i - 1): i + 3])
        inst = None
        for ln2 in lines[i: i + 3] + lines[max(0, i - 1): i]:  # line by line, so the degree text is not swallowed
            rest = ln2
            dm = re.search(next(p for c, _, p in DEGREES if c == deg[0]), rest, re.I) if ln2 is ln else None
            if dm:
                rest = rest[dm.end():]
            im = INSTITUTION_RE.search(rest)
            if im and not find_degree(im.group(0)):
                inst = im
                break
        years = [int(y) for y in re.findall(YEAR, window)]
        score = re.search(r"(?:cgpa|gpa|percentage|score|marks)\s*[:\-]?\s*(\d{1,2}(?:\.\d{1,2})?\s*(?:/\s*10)?|\d{2}(?:\.\d+)?\s*%)", window, re.I) \
            or re.search(r"\b(\d{2}(?:\.\d+)?)\s*%", window)
        ev = _evidence(pages, offsets[i], text)
        win_start = offsets[max(0, i - 1)]

        def ev_for(token: str) -> Evidence:
            pos = text.find(token, win_start)
            return _evidence(pages, pos, text) if pos >= 0 else ev
        entries.append({
            "degree": field(deg[1], 0.85, ev, code=deg[0]),
            "institution": field(_clean_institution(inst.group(0)), 0.7, ev_for(inst.group(0).strip())) if inst else None,
            "startYear": field(min(years), 0.6, ev_for(str(min(years)))) if len(years) >= 2 else None,
            "endYear": field(max(years), 0.75 if len(years) >= 2 else 0.55, ev_for(str(max(years)))) if years else None,
            "score": field(score.group(1).strip(), 0.6, ev_for(score.group(1).strip())) if score else None,
        })
        used.update(range(i, i + 3))
    return entries


def employment_entries(text: str, pages: list[str], claimed_companies: list[str]) -> list[dict]:
    entries = []
    lines = text.splitlines()
    for m in RANGE_RE.finditer(text):
        start, end_raw = m.group(1), m.group(2)
        start_d = parse_date(start)
        ongoing = re.fullmatch(r"present|current|now|till date|ongoing", end_raw.strip(), re.I) is not None
        end_d = None if ongoing else parse_date(end_raw, end=True)
        if not start_d:
            continue
        # Context: the line with the dates and the two lines before it.
        line_start = text.rfind("\n", 0, m.start()) + 1
        line_idx = text.count("\n", 0, line_start)
        ctx_lines = lines[max(0, line_idx - 2): line_idx + 2]
        ctx = " | ".join(ctx_lines)
        if find_degree(ctx) and not re.search(ROLE_WORDS, ctx, re.I):
            continue  # an education date range, not a job
        company, conf = None, 0.0
        for c in claimed_companies:
            if c and re.search(re.escape(c), ctx, re.I):
                company, conf = c, 0.85
                break
        if not company:
            cm = re.search(rf"([A-Z][\w&.\- ]{{1,50}}?\s{COMPANY_SUFFIX}(?:\s(?:pvt\.?|private|ltd\.?|limited))*\.?)", ctx, re.I)
            if cm:
                company, conf = cm.group(1).strip(" |,-"), 0.65
            else:
                am = re.search(rf"{ROLE_WORDS}\s*(?:at|@|,|\||-|–)\s*([A-Z][\w&.\- ]{{2,50}})", ctx, re.I)
                if am:
                    company, conf = re.split(r"\s*[|,(]\s*|\s+-\s+", am.group(1))[0].strip(), 0.5
        rm = re.search(rf"((?:[A-Z][\w/&+-]*\s){{0,3}}{ROLE_WORDS}\b)", ctx, re.I)
        ev = _evidence(pages, m.start(), text)
        entries.append({
            "company": field(company, conf, ev) if company else None,
            "title": field(rm.group(1).strip().title() if rm.group(1).islower() else rm.group(1).strip(), 0.6, ev) if rm else None,
            "start": field(month_str(start_d), 0.8, ev),
            "end": field("present" if ongoing else month_str(end_d), 0.8, ev) if (ongoing or end_d) else None,
            "current": ongoing,
            "internship": bool(re.search(r"\bintern(ship)?\b", ctx, re.I)),
        })
    return entries


def parse_resume(text: str, pages: list[str], profile: dict) -> dict:
    out: dict = {}
    name = find_name(text, pages, profile.get("fullName"))
    if name:
        out["name"] = name
    out.update(contact_fields(text, pages))
    out["education"] = education_entries(text, pages)
    out["skills"] = field(find_skills(text, profile.get("skills", [])), 0.8, None)
    out["employment"] = employment_entries(text, pages, [e["company"] for e in profile.get("experience", [])])
    return out


# ------------------------------------------------------------------------------------------- marksheet / certificate

def parse_marksheet(text: str, pages: list[str], profile: dict) -> dict:
    out: dict = {}
    name = find_name(text, pages, profile.get("fullName"), ("name of the candidate", "candidate'?s name", "name of (?:the )?student", "student name", "name"))
    if name:
        out["name"] = name
    m = re.search(r"(?:reg(?:ister|istration)?\.?\s*(?:no|number)\.?|roll\s*(?:no|number)\.?|enrol?l?ment\s*(?:no|number)\.?|seat\s*no\.?|usn|prn)\s*[:\-.]?\s*([A-Z0-9][A-Z0-9/-]{3,19})", text, re.I)
    if m:
        out["registerNumber"] = field(m.group(1).upper(), 0.85, _evidence(pages, m.start(1), text))
    inst = INSTITUTION_RE.search(text)
    if inst:
        out["institution"] = field(_clean_institution(re.sub(r"\s+", " ", inst.group(0))), 0.7, _evidence(pages, inst.start(), text))
    deg = find_degree(text)
    if deg:
        idx = re.search(next(p for c, _, p in DEGREES if c == deg[0]), text, re.I).start()
        out["degree"] = field(deg[1], 0.8, _evidence(pages, idx, text), code=deg[0])
    m = re.search(rf"(?:year of passing|passing year|year of completion|month\s*(?:&|and)\s*year(?: of passing)?|examination held in|exam held in|held in|session)\s*[:\-]?\s*(?:{MON}\.?\s*,?\s*)?({YEAR})", text, re.I)
    if m:
        out["year"] = field(int(m.group(1)), 0.85, _evidence(pages, m.start(1), text))
    else:
        years = [(int(y.group(0)), y.start()) for y in re.finditer(YEAR, text)]
        if years:
            y, pos = max(years)
            out["year"] = field(y, 0.5, _evidence(pages, pos, text))
    m = re.search(r"(?:grand\s+)?total(?:\s+marks)?(?:\s+obtained)?\s*[:\-]?\s*(\d{2,4})\s*(?:/|out of)\s*(\d{2,4})", text, re.I)
    if m and int(m.group(1)) <= int(m.group(2)):
        out["totalMarks"] = field(f"{m.group(1)}/{m.group(2)}", 0.85, _evidence(pages, m.start(), text))
    m = re.search(r"\b(c?gpa|sgpa|cpi)\s*[:\-]?\s*(\d{1,2}\.\d{1,2})", text, re.I)
    if m:
        out["cgpa"] = field(m.group(2), 0.85, _evidence(pages, m.start(), text))
    m = re.search(r"\b(\d{2}(?:\.\d{1,2})?)\s*%", text)
    if m:
        out["percentage"] = field(m.group(1), 0.7, _evidence(pages, m.start(), text))
    return out


# ------------------------------------------------------------------------------------------- experience letter

def parse_experience_letter(text: str, pages: list[str], profile: dict) -> dict:
    out: dict = {}
    name = find_name(text, pages, profile.get("fullName"), ("this is to certify that (?:mr\\.?|ms\\.?|mrs\\.?)?", "employee name", "name"))
    if name:
        out["name"] = name
    claimed = [e["company"] for e in profile.get("experience", [])]
    company = None
    for c in claimed:
        m = re.search(re.escape(c), text, re.I)
        if m:
            company = field(c, 0.85, _evidence(pages, m.start(), text))
            break
    if not company:
        m = re.search(rf"([A-Z][\w&.\- ]{{1,50}}?\s{COMPANY_SUFFIX}(?:\s(?:pvt\.?|private|ltd\.?|limited))*\.?)", text)
        if m:
            company = field(m.group(1).strip(" ,.-"), 0.6, _evidence(pages, m.start(), text))
    if company:
        out["company"] = company
    m = re.search(rf"(?:designation|position|role|post)\s*(?:of|as|:|-)?\s*(?:an?\s+)?((?:[A-Z][\w/&+-]*\s?){{1,5}})", text) or \
        re.search(rf"\bas\s+(?:an?\s+)?((?:[A-Z][\w/&+-]*\s){{0,3}}{ROLE_WORDS})", text, re.I)
    if m:
        out["designation"] = field(m.group(1).strip(" .,"), 0.7, _evidence(pages, m.start(1), text))
    jm = re.search(rf"(?:date of joining|joining date|doj|joined(?: us)?(?: on)?|from|since|employed with us from)\s*[:\-]?\s*(?:on\s+)?({DATE_TOKEN})", text, re.I)
    rm = re.search(rf"(?:date of relieving|relieving date|last working day|relieved(?: on)?|till|to|until)\s*[:\-]?\s*(?:on\s+)?({DATE_TOKEN}|present|date)", text[jm.end():] if jm else text, re.I)
    if jm:
        d = parse_date(jm.group(1))
        if d:
            out["joiningDate"] = field(d.isoformat(), 0.8, _evidence(pages, jm.start(1), text))
    if rm:
        offset = jm.end() if jm else 0
        raw = rm.group(1)
        d = parse_date(raw, end=True)
        if d:
            out["relievingDate"] = field(d.isoformat(), 0.8, _evidence(pages, offset + rm.start(1), text))
        elif re.fullmatch(r"present|date", raw, re.I):
            out["relievingDate"] = field("present", 0.6, _evidence(pages, offset + rm.start(1), text))
    if "joiningDate" in out and out.get("relievingDate", {}).get("value") not in (None, "present"):
        a, b = date.fromisoformat(out["joiningDate"]["value"]), date.fromisoformat(out["relievingDate"]["value"])
        months = (b.year - a.year) * 12 + b.month - a.month
        out["durationMonths"] = field(months, 0.8, None)
    return out
