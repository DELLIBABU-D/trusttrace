"""Write SYNTHETIC sample documents for manual testing of the verification engine.

    python backend/tests/make_sample_docs.py OUTPUT_FOLDER --name "Your Test Name" [--grad 2026] [--company "Zoho Corporation"]

Creates resume.pdf, marksheet.pdf (and marksheet_wrong_year.pdf), experience_letter.pdf. They are fake test files:
use them only to see how matching and mismatching details are reported. Never present them as real documents.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import synth

p = argparse.ArgumentParser()
p.add_argument("out")
p.add_argument("--name", default="Test Candidate")
p.add_argument("--grad", type=int, default=2026)
p.add_argument("--degree", default="B.E. Computer Science and Engineering")
p.add_argument("--college", default="Anna University")
p.add_argument("--company", default="Zoho Corporation")
p.add_argument("--title", default="Software Engineer Intern")
p.add_argument("--joined", default="01/05/2025")
p.add_argument("--relieved", default="31/07/2025")
a = p.parse_args()
out = Path(a.out)
out.mkdir(parents=True, exist_ok=True)
jobs = [(a.title, a.company, "May 2025 - Jul 2025")]
(out / "resume.pdf").write_bytes(synth.resume(name=a.name, degree=a.degree, college=a.college, grad=(a.grad - 4, a.grad), jobs=jobs))
(out / "marksheet.pdf").write_bytes(synth.marksheet(name=a.name.upper(), university=a.college, year=a.grad))
(out / "marksheet_wrong_year.pdf").write_bytes(synth.marksheet(name=a.name.upper(), university=a.college, year=a.grad - 2))
(out / "experience_letter.pdf").write_bytes(synth.experience_letter(name=a.name, company=a.company, title=a.title, joined=a.joined, relieved=a.relieved))
print(f"Synthetic test documents written to {out.resolve()}")
