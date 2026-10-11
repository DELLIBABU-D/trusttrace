# TrustTrace — Candidate Trust & Fraud Intelligence Platform

Hackathon prototype for **KERNEL PRIME'26 · SW-03**, by team **NEXTGEN MINDS**.

TrustTrace helps recruiters check candidates fairly:

- It reads uploaded documents and compares them with what the candidate claimed.
- It checks identity continuity with a consented webcam photo.
- It flags duplicate profiles and suspicious application patterns.
- It runs a proctored skill check.
- It explains every point of a trust score.
- It records the evidence in a tamper-evident hash chain.
- Candidates get a signed QR passport that any employer can verify.

People make every decision; nothing is rejected automatically.

## Run it

You need Python 3.11+. Node.js isn't needed.

```
cd trusttrace
python -m pip install -r backend/requirements.txt
python backend/manage.py doctor
python serve.py
```

Open **http://localhost:5173**. On Windows you can double-click `start.bat` instead.

The database starts empty. To approve a recruiter organisation, run:

```
python backend/manage.py approve-org <email>
```

Mobile OTP codes are printed in the server window.

## More

- **`PROJECT_STATUS.md`** has the details:
  - exact commands and settings
  - the feature matrix (fully working / partial / simulated / not implemented)
  - the step-by-step **judge demo** and presentation script
  - security and privacy notes
  - test results
  - troubleshooting
- **`.env.example`** lists every setting.
- To create sample documents for any name, run `python backend/manage.py make-sample-docs "Your Name" demo-docs`.

**What it doesn't do:** no government database is queried, there is no liveness or anti-spoofing check, and issuer checks
without an official integration are labelled *simulated* or *pending*.
