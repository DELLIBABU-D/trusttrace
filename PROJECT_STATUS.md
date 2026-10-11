# TrustTrace — Project Status

**Team:** NEXTGEN MINDS · KERNEL PRIME'26 · SW-03 Candidate Trust & Fraud Intelligence Platform
**Current phase:** Phase 6 — Evidence chain, QR passport, end-to-end integration, security and demo readiness. **Complete** (all tests below pass).
This is a **hackathon prototype**, not a production system. The "Feature matrix" and "Known limitations" sections say exactly what is real, partial or simulated.

---

## Quick start (exact commands)

You need **Python 3.11 or newer**. Node.js is **not** needed: the website is already built into `frontend/dist`.

The app comes as **two zips** (the upload limit is 30 MB and the face model is 38 MB):
`trusttrace-phase6.zip` (the app) and `trusttrace-phase6-model-part2.zip` (second half of the face model).
Extract **both into the same folder**. The second zip adds one file to `trusttrace/backend/models/`. On first start the
server joins the two halves and checks them against OpenCV's official SHA-256.

**Windows (Command Prompt or PowerShell):**

```
cd trusttrace
python -m pip install -r backend\requirements.txt
python backend\manage.py doctor
python serve.py
```

or double-click **`start.bat`** (installs packages on the first run, then starts).

**macOS / Linux:** the same commands with `/`, or `./start.sh`.

Then open **http://localhost:5173**. API documentation: **http://localhost:5173/api/docs**.

| Task | Command |
|---|---|
| Create / upgrade the database (also done by `serve.py`) | `python backend/manage.py init-db` |
| Approve a recruiter organisation | `python backend/manage.py approve-org recruiter@company.com` |
| List organisations | `python backend/manage.py list-orgs` |
| Check PDF, OCR, face models, Gemini | `python backend/manage.py doctor` |
| Generate sample documents for ANY name | `python backend/manage.py make-sample-docs "Priya Sharma" demo-docs` |
| Load SIMULATED DigiLocker records (demo) | `python backend/manage.py load-digilocker-records demo-docs/digilocker_records.csv` |
| Verify a candidate's evidence chain | `python backend/manage.py verify-chain candidate@mail.com` |
| Erase a candidate's personal data | `python backend/manage.py erase-candidate candidate@mail.com --yes` |
| Run backend tests | `cd backend` then `python -m pytest -q` |

**Updating from Phase 5:** run the `pip install` line once (no new packages since Phase 5, but it's safe). To keep your data, copy
your old `backend\data` folder into the new `trusttrace\backend\`. `serve.py` upgrades it to migration `0005` automatically.
Database migrations: `0001` (Phase 2) … `0004` (Phase 5), `0005` (Phase 6: evidence chain, passports, per-organisation alert
reviews, append-only triggers, extra indexes). Manual: `cd backend` then `python -m alembic upgrade head` (or `downgrade 0004`).

### Good to know

- **A new install is empty.** No sample people, jobs, results or scores are ever created. Everything on screen comes from what you enter.
- **Mobile OTP:** no SMS provider is connected. The 6-digit code is printed in the window running `python serve.py`.
- **Recruiter approval:** new organisations start as *pending* (jobs hidden from candidates). Approve with `manage.py approve-org`,
  or for a local demo start with `TT_AUTO_APPROVE_ORGS=1` (put it in `.env`).
- **Camera:** use `http://localhost:5173`, not an IP address. Browsers allow the camera only on localhost or HTTPS.
- **Settings:** copy `.env.example` to `.env` and edit. Real environment variables override `.env`.
- **Keys:** on first start the server creates `backend/data/secret.key` (login tokens), `evidence.key` (evidence-chain HMAC) and
  `passport_ed25519.pem` (passport signatures). Keep that folder private and backed up.

### Settings (environment variables or `.env`)

| Variable | Default | Purpose |
|---|---|---|
| `PORT` | `5173` | Web server port |
| `TT_DATA_DIR` | `backend/data` | Database, uploads and generated keys |
| `TT_DATABASE_URL` | SQLite in `TT_DATA_DIR` | Optional PostgreSQL URL |
| `TT_SECRET_KEY` | generated `secret.key` | JWT signing key |
| `TT_EVIDENCE_KEY` | generated `evidence.key` | HMAC key of the evidence chain |
| `TT_PASSPORT_KEY_FILE` | generated `passport_ed25519.pem` | Ed25519 private key that signs passports |
| `TT_PASSPORT_TTL_DAYS` | `90` | Passport validity |
| `TT_PUBLIC_URL` | the URL the request came in on | Base URL printed in passport QR codes |
| `TT_TOKEN_TTL_HOURS` | `12` | Session length |
| `TT_MAX_REQUEST_MB` | `12` | Largest accepted request body |
| `TT_AUTO_APPROVE_ORGS` | `0` | `1` = approve new organisations immediately (demo only) |
| `TT_TESSERACT_CMD` | `tesseract` on PATH | Path to the Tesseract OCR program |
| `TT_FRAUD_CONFIG` | — | JSON override for scoring weights and pattern thresholds |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | not set | Optional Gemini assistance (server-side only) |
| `TT_DIGILOCKER_MODE` | `live` if client id+secret are set, else `simulated` | `live`, `simulated` or `off` |
| `TT_DIGILOCKER_CLIENT_ID`, `TT_DIGILOCKER_CLIENT_SECRET` | not set | DigiLocker partner (Requester) app credentials |
| `TT_DIGILOCKER_REDIRECT_URI` | `<public url>/api/digilocker/callback` | Must exactly match the redirect URI registered on the DigiLocker Partner Portal |
| `HOST` | `127.0.0.1` | `0.0.0.0` lets other devices on the same Wi-Fi connect |

---

## Feature matrix

**Fully working** = implemented, uses real data, covered by automated tests. **Partially working** = works, with a stated gap.
**Simulated** = clearly labelled stand-in for an outside service; never counted as verification. **Not implemented** = not built.

| Area | Feature | Status | Notes |
|---|---|---|---|
| Accounts | Candidate and recruiter registration, login, logout, sessions | Fully working | Argon2id passwords, JWT + server-side session revocation |
| Accounts | Mobile OTP | Partially working | Real codes, hashed, expiring, attempt-limited; **delivered to the server console** (no SMS gateway) |
| Accounts | Organisation approval | Partially working | CLI command (`approve-org`); no admin web screen |
| Accounts | Forgot / change password | Not implemented | |
| Jobs | Create, edit, close, list, apply (one per job) | Fully working | |
| Documents | Upload, replace, private download links, type sniffing, size and pixel limits | Fully working | 5 MB per file, 12 MB per request, PDF max 15 pages |
| Verification | PDF text extraction (PyMuPDF), OCR of scans (Tesseract) | Fully working | OCR needs the Tesseract program installed |
| Verification | Resume / education / employment field comparison and mismatch findings | Fully working | Fixed patterns; unusual layouts can give "not found" → needs review |
| Verification | Face match selfie vs ID photo, rechecks (YuNet + SFace) | Partially working | Real face model; **no liveness / anti-spoofing** |
| Verification | **DigiLocker comparison** (uploaded certificate vs the issuer's DigiLocker copy) | Partially working / Simulated | Live partner-API flow is implemented and tested against a fake DigiLocker server; using real DigiLocker needs approved partner credentials. Without them a clearly labelled SIMULATED DigiLocker is used, which never counts |
| Verification | Issuer authenticity | Simulated / partial | Simulated registry (`load-issuer-records`, labelled SIMULATED) or a recruiter's recorded attestation. No DigiLocker / university API |
| Verification | Employment references | Partially working | Real one-time referee link + public form; link is shown to the recruiter (no email service). "Simulate answer" exists for testing and is labelled SIMULATED |
| Fraud | Duplicate detection (same verified mobile, very similar face) | Fully working | Review is per organisation |
| Fraud | Suspicious patterns P1–P5, relationship graph | Fully working | Weak signals; shared-network rule ignores local/LAN addresses |
| Scoring | Explainable trust score (baseline 80, versioned rules, history) | Fully working | Heuristic weights; decision support only |
| Skills | Assessments (question bank / optional Gemini drafts, recruiter approval, server scoring, timer) | Fully working | Multiple choice only |
| Skills | Integrity events (focus/tab, copy/paste, camera state, face rechecks) | Fully working | Review signals, never proof of cheating |
| Interviews | Scheduling, candidate response, identity step at entry | Fully working | Uses the recruiter's own meeting link (no built-in video call) |
| Recruiter | Dashboard, applicant list (search/filter/sort), trust report, review actions, decisions | Fully working | |
| Audit | Append-only audit tables (DB triggers) | Fully working | SQLite triggers; see limitations |
| Audit | **Evidence chain** (SHA-256 payload hash + HMAC link per event, verification, timeline) | Fully working | Tamper-evident, not tamper-proof against a server administrator |
| Passport | **Signed QR passport** (Ed25519), public verify page, expiry, revocation, auto-supersede | Fully working | Issued by a recruiter when eligibility rules are met |
| Privacy | Consent records, consent withdrawal, erasure command | Partially working | Erasure and retention purges are admin commands; no automatic retention scheduler |
| Notifications | In-app messages to candidates | Fully working | |
| Notifications | Email / SMS notifications | Not implemented | Settings are saved but nothing is sent (labelled in the UI) |
| AI | Gemini question drafting and extraction gap filling | Partially working | Optional; needs a Google API key; falls back to local logic |

### Needs outside authorisation or paid access

| Capability | What would be needed |
|---|---|
| SMS OTP delivery | An SMS gateway account (e.g. MSG91, Twilio) and DLT registration in India; replace `deliver_otp()` in `backend/app/routers/auth.py` |
| Official certificate verification (DigiLocker) | Register a Requester app on the DigiLocker Partner Portal (organisation onboarding, approved document types, registered redirect URI), then set `TT_DIGILOCKER_CLIENT_ID`, `TT_DIGILOCKER_CLIENT_SECRET` and `TT_DIGILOCKER_REDIRECT_URI` — no code change |
| Government ID verification (Aadhaar/PAN) | Licensed KYC provider; **TrustTrace does not query any government database** |
| Liveness / anti-spoofing | A certified liveness SDK or service (paid) |
| Gemini assistance | Google AI Studio API key (free tier with limits, or paid) |
| Email notifications / reference emails | An email service (SMTP or a provider such as SendGrid) |
| Public deployment | HTTPS hosting and a domain (camera access requires HTTPS outside localhost) |

---

## Judge demo (works on an empty database, no predefined names)

Prepare once (2 minutes):

1. Start the app: `python serve.py` (fresh install, or delete `backend/data` for a clean database; keep a backup if you need it).
2. Generate sample documents for the name you will register (any name):
   `python backend/manage.py make-sample-docs "Your Chosen Name" demo-docs`
   This writes `resume.pdf`, `marksheet.pdf`, `marksheet_wrong_year.pdf` and `experience_letter.pdf`, all marked as generated samples.
   You can use real documents instead; then enter matching details in step 4.
3. Have an **ID photo of the same person who will sit in front of the webcam** (for example, a photo of their college ID card).
   Selfie-vs-ID matching only works if it's the same face.

Procedure (about 10 minutes). Every step is real; nothing is precomputed.

| # | Step | Where | What to show |
|---|---|---|---|
| 1 | Register a recruiter (any name/organisation) | `/recruiter/register` | Pending-approval banner. Run `python backend/manage.py approve-org <email>`, reload |
| 2 | Create a **Python Developer** job | Post a Job | Job appears in Jobs. Optional: *Assessment* → Draft from question bank → approve each question → Publish |
| 3 | Register a candidate with the chosen name | open a private window → `/register` | OTP appears in the server window; webcam selfie with consent; upload the ID photo |
| 4 | Enter education and employment | registration step 2 | Use the details printed by `make-sample-docs` (B.E. CSE, Anna University 2022–2026; Software Engineer Intern, Zoho, 2025-05 → 2025-07) |
| 5 | Upload resume, **marksheet_wrong_year.pdf** and the experience letter | Documents | "Uploaded 3 files"; verification starts in the background |
| 6 | Apply to Python Developer | Jobs | Application created |
| 7 | Run document verification | Recruiter: applicant → **Run verification** | Job finishes in seconds |
| 8 | Show extracted values | Candidate: Verification → Education | Year of passing **Mismatch** with the document value vs the profile value; employment page shows **Match** rows |
| 8b | (optional) DigiLocker comparison | Candidate: Verification → Education → Compare with DigiLocker | First run `load-digilocker-records demo-docs/digilocker_records.csv`. Connect (simulated) → Allow → **Compare this** → the table shows Year **Mismatch** against the DigiLocker copy, labelled SIMULATED |
| 9 | Face recheck with consent | Candidate: Verification (identity), or `/candidate/interviews/check` | "Face matches the enrolled photo" (similarity shown) |
| 10 | Short skill assessment | Candidate: Assessments → Start | Camera consent step → answer → switch tab once → submit → score |
| 11 | Integrity events | Recruiter: Assessments → Details | Focus lost / paste as review signals, face recheck, "not proof of cheating" |
| 12 | Recruiter dashboard | Recruiter: Dashboard | Real totals, Needs your attention, Review queue |
| 13 | Evidence-backed trust report + review action | Applicant → Summary / Education / Risk | "How this score was calculated" with rule ids and evidence; passport **Not eligible yet** with reasons. Click **Request clarification**; candidate uploads `marksheet.pdf`; reload → EDU.CONSISTENT, score recomputed; **Mark reviewed** |
| 14 | Audit chain and QR passport | Applicant → **Audit Trail**; right column → **Issue passport** | Chain intact with linked hashes; issue passport → open the QR link (or scan it) → "Valid TrustTrace passport". Revoke → page shows "revoked" with the reason |

Optional extras: run `python backend/manage.py verify-chain <candidate email>` to show the integrity check from the command line;
register a second candidate with the same mobile number to show a duplicate alert on the Risk tab.

This exact procedure is automated in `frontend/tests/e2e-demo.mjs` (33 checks, empty database, random candidate name each run).

### Judge presentation script (about 4 minutes)

1. **Problem (30 s).** Hiring fraud: edited marksheets, borrowed identities, proxy test-takers and duplicate profiles. Recruiters
   can't check everything by hand, and black-box "AI fraud scores" are unfair to honest candidates.
2. **Idea (20 s).** TrustTrace collects evidence, explains every point of a trust score, and leaves every decision to a person.
3. **Live demo (2.5 min).** Follow steps 3 → 8 → 13 → 14 above: register with webcam consent → the wrong-year marksheet is caught
   with the exact values → the trust report explains it with rule ids and evidence → the recruiter asks for clarification → the
   corrected document recomputes the score → the audit trail shows a hash-linked history → the signed QR passport verifies live
   and is revoked live.
4. **Honesty (30 s).** Pending and simulated checks are never called verified; consistent documents are not called authentic; face
   matching is evidence, not proof (no liveness); weak signals like shared networks only prompt a review; nobody is rejected
   automatically.
5. **Next steps (10 s).** SMS/email gateways, DigiLocker integration, liveness SDK, external anchoring of the evidence chain.

---

## DigiLocker comparison (added after Phase 6)

**Goal:** compare the certificate the candidate uploaded with the issuer's own copy in DigiLocker, field by field.
Code: `backend/app/verification/digilocker.py`, `backend/app/routers/digilocker.py`; migration `0006`.

**How it works:**

1. On **Verification → Education**, the candidate ticks the consent box and clicks **Connect DigiLocker**.
2. They are sent to DigiLocker, sign in, and allow access. DigiLocker redirects back to `/api/digilocker/callback`.
3. TrustTrace lists the issued documents (metadata only). The candidate clicks **Compare this** on their marksheet or degree.
4. The document is downloaded and its fields are read:
   - **XML** (where DigiLocker offers it): parsed directly. Issuer formats differ, so known field names are mapped
     (holder name, roll/register number, year of passing, CGPA, course, issuer).
   - **PDF:** read with the same text extraction and OCR as uploads.
5. The education check re-runs and adds the **comparison table**: name, register number, year, CGPA and degree, each
   Match / Mismatch / Not compared.

| Result | Live DigiLocker | Simulated |
|---|---|---|
| All key fields agree (name + register number or year) | Education becomes **Verified**; rule `EDU.DIGILOCKER_MATCH +8` | Shown, **not counted** (Pending) |
| A field disagrees | Critical finding, education **Inconsistent**; rule `EDU.DIGILOCKER_MISMATCH −15` (a recruiter can review/resolve it like any concern) | Info finding, **not counted** |
| Not enough fields to decide, or the download's integrity header failed | Needs review | Pending |

**Live mode (real DigiLocker, Requester / MeriPehchaan API v2.3):**

- OAuth 2.0 authorization code with **PKCE (S256)**: `/public/oauth2/1/authorize`, then token at `/public/oauth2/2/token`.
- Issued documents: `/public/oauth2/2/files/issued`. Files: `/public/oauth2/1/file/{uri}`. Certificate XML: `/public/oauth2/1/xml/{uri}`.
- Every download is checked against DigiLocker's `hmac` header (HMAC-SHA256 with the client secret). A match whose
  integrity can't be confirmed is never counted.
- The access token is stored **encrypted** (Fernet), only until it expires; "Disconnect" deletes the token, the list and
  the pulled copy. Withdrawing document consent and `erase-candidate` delete them too.
- **Needs:** an approved DigiLocker partner (Requester) app for your organisation — client ID, client secret, the
  redirect URI registered exactly, and approved document types. Put them in `.env`; nothing else changes.
- Tested with a fake DigiLocker server (PKCE check, token exchange, issued list, XML download with good and bad HMAC).
  It has **not** been run against the real DigiLocker, because that needs the partner credentials.

**Simulated mode (default without credentials, for demos):**

- Run `make-sample-docs "Name" demo-docs`, then `load-digilocker-records demo-docs/digilocker_records.csv`.
  Records match the candidate by mobile number, or by name when the CSV leaves the mobile blank.
- **Connect DigiLocker (simulated)** opens TrustTrace's own consent page, marked "SIMULATED DIGILOCKER – FOR TESTING ONLY".
- Everything is labelled SIMULATED and never changes the status, the score or the passport.

**Evidence chain:** `digilocker.connected`, `digilocker.document_pulled` (file SHA-256, issuer, HMAC result) and
`digilocker.disconnected` are recorded. **Passport:** a live DigiLocker match appears as "DigiLocker copy of the
certificate: Verified"; simulated ones as Pending.

**Also fixed:** a document that couldn't be read before OCR was installed is now read again on the next verification
run (previously the old "unreadable" result was reused). Passports are no longer superseded when only the scoring
ruleset version changes but the score and check statuses are the same.

---

## Phase 6 — Evidence chain, QR passport, integration and security (what was built)

### A. Evidence chain (`backend/app/evidence/chain.py`)

- One hash chain per candidate in the `evidence_events` table.
- **Recorded events:** registration (with consents), consent changes, profile updates (hash of the claims), document upload,
  replacement and removal (with the file's SHA-256), verification results (recorded when the outcome changes), face rechecks,
  application, assessment submission (score, integrity-event counts, hash of the answers), interview identity step, recruiter
  status changes, decisions, check reviews, alert reviews, issuer confirmations, reference requests and answers, "report reviewed",
  onboarding (status *hired*), and passport issue, revocation and supersession.
- **Hashing:**
  - `payload_hash = SHA-256(canonical JSON)`.
  - `event_hash = HMAC-SHA256(evidence key, canonical header)`. The header holds sequence, type, actor, time, application,
    organisation, payload hash and the previous event's hash.
  - The first event links to 64 zeros.
- **Minimal data:** payloads contain ids, statuses and hashes only. Never document text, photos, embeddings or contact
  details. Free-text notes are stored as their SHA-256; the note itself is kept in its own append-only table.
- **Verification** (`GET /api/recruiter/applicants/{id}/evidence`, `manage.py verify-chain`) recomputes every link. It reports:

  | Problem | Meaning |
  |---|---|
  | `payload_modified` | The stored payload no longer matches its hash |
  | `hash_mismatch` | Type, time, actor or links were changed |
  | `missing_events` / `broken_link` | Events were deleted or re-ordered |
  | `unknown_key` | The event was signed with a different evidence key |
  | `anchor_mismatch` | The history differs from the chain head pinned in an issued passport |

- **Database protection:** triggers refuse `UPDATE` and `DELETE` on `evidence_events` through the app's connection
  (migration `0005`).
- **Organisation privacy:** events specific to another organisation appear as "Activity at another organisation" with the
  details hidden. The whole chain is still verified.
- **UI:** the trust report has an **Audit Trail** tab: integrity status, "Verify again", and a newest-first timeline with
  hashes and links.
- **Honest limit:** a local hash chain is tamper-*evident*, not tamper-*proof*. Someone with full control of the server
  (database file *and* `evidence.key`) can drop the triggers and recompute every HMAC. Issued passports pin the chain head,
  so rewriting history before a passport was issued is detected against that passport. Publishing chain heads to an
  external timestamping service or write-once storage would close the rest of the gap.

### B. TrustTrace QR passport (`backend/app/evidence/passport.py`)

- **Issued by a recruiter** from the trust report (right column, *TrustTrace Passport*), only when the eligibility rules are met:
  1. Mobile number verified by OTP.
  2. Identity verified (selfie matched the ID photo).
  3. Education documents checked.
  4. Nothing in *Needs review* or *Inconsistent*, after the recruiter's own reviews. This includes open duplicate and pattern
     alerts.
  5. The application is not rejected.
  6. The evidence chain is intact.

  When the rules aren't met, the reasons are listed.
- **Token:** `TT1.<base64url(claims)>.<base64url(Ed25519 signature)>`. The public key is at `/api/passport/public-key`, so
  anyone can check a token offline.
- **Claims (minimal data):**
  - passport ID and a pseudonymous candidate reference (`TTC-…`, not the database id)
  - issuing organisation and job title
  - check statuses, plus the list of simulated items
  - skill-assessment summary (score, percent, number of integrity review signals)
  - issue and expiry time
  - report version (score record and ruleset version)
  - evidence-chain head

  **Not included:** photos, documents, embeddings, phone, email, date of birth, or the trust score.
- **Status wording:**
  - "Verified" only for checks actually completed (OTP, selfie–ID match, a real issuer or reference confirmation).
  - Document agreement is "Consistent (not independently confirmed)".
  - Pending and simulated checks are "Pending", and simulated ones are named as such.
- **QR code:** opens `<site>/verify/TTP-XXXXXXXXXX`, a controlled endpoint. The short link scans reliably. The candidate can
  also copy the full signed-token link. The QR is drawn with OpenCV's QR encoder, so no extra package is needed.
- **Server-side verification** (`GET /api/passport/verify/{id-or-token}`, public, rate limited) checks, in order:
  1. the signature
  2. whether the passport is known
  3. revocation
  4. supersession
  5. expiry
  6. the evidence chain, including the pinned head

  Possible results: `valid`, `invalid`, `unknown`, `revoked`, `superseded`, `expired`. The holder's name is shown only for a
  valid passport.
- **Lifecycle:**
  - **Revoke:** a recruiter of the issuing organisation can revoke; a reason is required and shown publicly.
  - **Supersede:** a passport is superseded automatically when the evidence changes (a new trust-report version).
  - **Regenerate:** issues a new passport and supersedes the old one.

  All three are recorded in the evidence chain.
- **Screens:**
  - Candidate *QR Passport* page: same card style as the reference screen, plus copy-link buttons and the chain status.
  - Public `/verify/:ref` page.
  - Recruiter passport panel.

### C. Final integration

- **Code audit:** every router, page, link and form was audited (report summarised below).
- **Links and data:** all link targets match routes, and the route smoke test opens all 30 routes with no errors.
- **No sample or fake data:** no mock arrays, hardcoded people, jobs or scores, or fake success responses remain. The last
  stub, the passport endpoint that always returned `null`, is now real.
- **Empty database:** a fresh database shows empty states everywhere. The demo test starts from an empty database.
- **Labels made honest:** settings that promised features which don't exist (automatic document deletion, email
  notifications) now say they are saved but not active in this prototype.

| Reference screen | Route | Backed by |
|---|---|---|
| (a) Landing / sign in | `/`, `/login` | `/api/auth/login`, `/api/auth/me` |
| (b) Candidate registration (OTP, webcam, consent) | `/register` | `/api/auth/otp`, `/api/candidates/register` |
| (c) Candidate dashboard | `/candidate` | `/api/candidate/dashboard` |
| (d) Available jobs | `/candidate/jobs` | `/api/jobs`, `/api/jobs/{id}/apply` |
| (e) Documents upload | `/candidate/documents` | `/api/candidate/documents` |
| (f) Education verification | `/candidate/verification/education` | `/api/candidate/verification/education` |
| (g) Employment verification | `/candidate/verification/employment` | `/api/candidate/verification/employment` |
| (h) Skill assessment | `/candidate/assessments/:id` | `/api/candidate/assessments/*` |
| (i) Interview identity step | `/candidate/interviews/:id` | `/api/candidate/interviews/{id}/entry` |
| (j) Recruiter dashboard | `/recruiter` | `/api/recruiter/dashboard` |
| (k) Candidate trust report | `/recruiter/applicants/:id` | `/api/recruiter/applicants/{id}/report`, `/evidence`, `/passport` |
| (l) QR passport | `/candidate/passport`, `/verify/:ref` | `/api/candidate/passport`, `/api/passport/verify/{ref}` |

### D. Security review and fixes

A separate read-only audit checked every endpoint for authorisation, cross-organisation data access (IDOR), uploads,
secrets, logging, rate limits and fake data. **No cross-organisation data access was found.** Every object fetched by id is
checked against the candidate or the organisation. Fixed in Phase 6:

| Finding | Fix |
|---|---|
| One organisation's alert review ("not a duplicate", pattern "reviewed – OK") changed every other organisation's view and score | Reviews are now **per organisation** (`alert_reviews` table, append-only); existing reviews were migrated to the reviewer's organisation |
| Another organisation's reviewer name, organisation name and referee comments were visible | Issuer attestations now say "recorded by a recruiter at a verified organisation"; references requested by another organisation show only the outcome |
| A huge or many-page PDF could stall the single verification worker; image decompression bombs | PDF limit of 15 pages, OCR of at most 5 pages, oversized pages skipped; images over 40 MP rejected at upload and before face decoding |
| Request bodies were read fully before size checks | Middleware rejects bodies over 12 MB (413) and chunked uploads without a length (411); multipart limited to 10 files and 20 fields |
| No rate limits on face checks, uploads, verification runs, public reference pages; login limited only per IP + email | New limits per candidate/recruiter/IP. Login also limited per account and per IP. Per-network limits are relaxed for local addresses so a single-laptop demo isn't blocked. Limiter memory is bounded |
| Shared-network pattern fired for everyone on `127.0.0.1` / office LAN | Only public addresses count for P4 |
| OTP codes were written to the application log | Removed (the console print for development delivery stays) |
| Withdrawing biometric consent left face-check history and the photo visible | Face checks deleted too; the enrolment photo is hidden from recruiters while consent is withdrawn |
| No Content-Security-Policy | Strict CSP (`script-src 'self'`, `frame-ancestors 'none'`, no inline scripts) on all pages except the API docs |
| Suspended organisations could still act | All recruiter endpoints refuse suspended organisations |
| Login `next=` parameter not validated | Only same-site paths are followed |
| No way to honour a deletion request | `manage.py erase-candidate EMAIL --yes` (see below) |

Verified OK in the audit (unchanged):

- **Authentication:** Argon2id passwords with timing-safe login, JWTs pinned to HS256 with server-side sessions, OTPs hashed with expiry and attempt limits.
- **Uploads:** file type detected from the content (magic bytes), random storage names, path-traversal protection, signed 10-minute download links bound to the user.
- **Biometric data:** face embeddings encrypted with Fernet and never returned.
- **Assessments:** answer keys never reach candidates.
- **Other:** no raw SQL, no CORS (same origin only), and list endpoints are paginated.

### E. Consent, retention and deletion

- **Consent:** registration records consent for biometric processing and document processing, with the policy version, time, IP
  address and browser. Candidates can withdraw either at any time (Verification page).
  - Withdrawing biometric consent deletes face templates and face-check results.
  - Withdrawing document consent deletes the stored text extractions.
- **Retention:** the organisation's retention period is saved, but there is **no automatic scheduler** in this prototype.
  An administrator runs:
  - `purge-extractions DAYS`
  - `purge-assessment-events DAYS`
  - `delete-biometrics EMAIL`
  - `erase-candidate EMAIL --yes`
- **Erasure (`erase-candidate`):**
  - **Deleted:** all uploaded files, text extractions, face data, device sightings, education, employment and reference
    entries, messages, and the extracted values in verification results.
  - **Changed:** name, email and phone are replaced, sign-in is disabled, and active passports are revoked.
  - **Kept:** applications (shown as "Erased candidate") and append-only audit rows. Those hold only ids, statuses and hashes,
    which is why the evidence chain stays valid after erasure.
- **Device signals:** the browser ID is a random value stored in the browser, not a fingerprint, and the candidate is told about it.
  The server stores only HMAC hashes of the browser ID and IP address.

### Phase 6 endpoints

| Method | Path | Who | Purpose |
|---|---|---|---|
| GET | `/api/recruiter/applicants/{id}/evidence` | recruiter (own org) | Timeline + fresh chain verification |
| GET | `/api/recruiter/applicants/{id}/passport` | recruiter (own org) | Eligibility, active passport, history |
| POST | `/api/recruiter/applicants/{id}/passport` | recruiter (own org) | Issue / regenerate (409 with reasons if not eligible) |
| POST | `/api/recruiter/applicants/{id}/passport/revoke` | recruiter (own org) | Revoke with a reason (≥ 10 characters) |
| GET | `/api/candidate/passport` | candidate | My passports and chain status |
| GET | `/api/passport/verify/{TTP-id or token}` | public, rate limited | Live verification |
| GET | `/api/passport/public-key` | public | Ed25519 public key and token format |

---

## Phase 5 — Fraud intelligence, explainable trust score, decision support (what was built)

Everything below is computed from saved evidence. Nothing is hardcoded, and **no candidate is ever rejected automatically**: the score and alerts are decision support for a recruiter.

### 1. Suspicious application patterns (`backend/app/fraud/patterns.py`)

Thresholds are in `backend/app/fraud/config.py` and can be overridden with the `TT_FRAUD_CONFIG` environment variable (JSON).

| Rule | Fires when (default) | Strength |
|---|---|---|
| `P1.RAPID_APPLICATIONS` | 5 or more applications within 10 minutes | weak |
| `P2.REPEATED_SUBMISSIONS` | 3 or more repeat attempts to apply to the same job within 10 minutes | weak |
| `P3.SHARED_DEVICE` | the same browser ID is used by 2 or more candidate accounts | medium |
| `P4.SHARED_NETWORK` | 3 or more candidate accounts on the same network address within 24 hours | weak |
| `P5.DOCUMENT_CHURN` | the same document type is uploaded 5 or more times within 24 hours | weak |

Each alert stores the rule id, the evidence, first and last time seen, a severity, a strength and a review status (`open`, `reviewed_ok` or `confirmed`). A recruiter must write a note of at least 10 characters to review an alert. Every alert shows innocent explanations (shared lab computers, college Wi-Fi and so on).

**Privacy of device signals.** The browser stores a random ID (`tt.device` in localStorage); it is not a fingerprint. The registration screen tells the candidate about it. The server keeps only HMAC hashes of that ID and of the IP address, never the raw values. Alerts about other accounts show only a masked reference such as "Candidate account …334fc1".

### 2. Relationship graph (`backend/app/fraud/graph.py`)

A NetworkX graph with candidate accounts and linking signals as nodes:

- **Strong:** the same OTP-verified mobile number; a very similar enrolled face (duplicate alert).
- **Medium:** the same browser ID.
- **Weak:** the same network address.

The recruiter sees a radial SVG diagram on the **Risk Analysis** tab, plus a list of linked accounts with the strongest signal for each. Accounts that didn't apply to the recruiter's organisation stay anonymous. The graph is always described as "a reason to look closer, not a confirmed fraud ring". The cluster size counts only strong and medium links.

*Deviation:* the brief suggested React Flow. npm packages can't be installed in this build environment, so the graph is a small custom SVG component with the same purpose and no extra download.

### 3. Explainable trust score (`backend/app/fraud/scoring.py`)

Score = **baseline 80** + the sum of the applied rules, clamped to 0–100. Each entry shows its rule id, weight, evidence (document, run, finding or alert, with links) and timestamp.

| Rule | Weight | Rule | Weight |
|---|---|---|---|
| `ID.PHONE_OTP` | +2 | `EMP.CONSISTENT` | +3 |
| `ID.FACE_ID_MATCH` | +6 | `EMP.INCONSISTENT` | −8 |
| `ID.FACE_ID_MISMATCH` | −8 | `EMP.REFERENCE_CONFIRMED` | +5 |
| `ID.RECHECK_MATCH` | +2 | `EMP.REFERENCE_DENIED` | −12 |
| `ID.RECHECK_MISMATCH` | −6 | `RES.CONSISTENT` | +2 |
| `EDU.CONSISTENT` | +4 | `RES.INCONSISTENT` | −6 |
| `EDU.INCONSISTENT` | −10 | `DUP.OPEN_ALERT` | −4 each (max 2) |
| `EDU.ISSUER_CONFIRMED` | +6 | `DUP.CONFIRMED` | −20 |
| `EDU.ISSUER_DENIED` | −15 | `PAT.OPEN_ALERT` | −2 each (max 3) |
| | | `PAT.CONFIRMED` | −8 |

Principles:

- **Statuses stay separate:** Verified, Consistent, Pending, Needs review, Inconsistent and Not started. Document consistency is never shown as "Verified".
- **No credit for checks that never ran.** Missing information is "Not started", not a penalty.
- **Simulated results** (simulated issuer registry, reference awaiting a reply) are clearly labelled Pending and earn no points.
- **Assessment performance is reported separately** and does not change the trust score.
- **Recruiter check reviews:** "Resolve" (explained) removes a penalty, and "Uphold" keeps it; both need a note. A resolution is tied to the exact evidence (a concern key). If the document or finding changes, the penalty returns until someone reviews it again.
- **Recompute:** the score is recomputed after verification runs, applications, assessments, interview entries, alert reviews and check reviews, and when the report is opened. A new score version is saved only when the result changes.
- **Review priority labels:** "Few concerns found" (75 or more, nothing to review), "Needs review", "Several concerns" (below 50). These are labels, not decisions.

### 4. Recruiter dashboard and applicant list

- The dashboard has real totals, a **Needs your attention** list (lowest score first), and a **Review queue** with applications needing review, open duplicate and pattern alerts, and pending checks. It also has a verification summary table and an assessment summary.
- **Applicants** has search, status filter, sorting (newest, oldest, score low→high, score high→low, name), a "Needs review only" filter, and a "To review" column.
- **Trust report:**
  - The **Summary** tab shows the score explanation and checks grouped by status.
  - The **Risk Analysis** tab shows linked profiles and application patterns.
  - The right column has **Review record** (Mark reviewed, score history) above the existing Next step and Decision actions.

### 5. Auditability

- **Tables:** `score_records` (each score version, with ruleset version, breakdown and trigger), `scoring_rulesets` (every ruleset version used), `check_reviews`, `report_reviews` (tied to the score version the reviewer saw) and `activity_events`.
- **Protection:** in SQLite these tables are protected by **append-only triggers** (migration `0004`), so updates and deletes fail with "audit records are append-only". The only exception is clearing a reviewer reference when a user account is deleted.

### New endpoints (all scoped to the recruiter's organisation)

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/recruiter/applicants/{id}/patterns/{alertId}/review` | Review a pattern alert (`reviewed_ok`, `confirmed` or `open`, with a note) |
| POST | `/api/recruiter/applicants/{id}/checks/{check}/review` | Resolve or uphold a check concern (with a note) |
| POST | `/api/recruiter/applicants/{id}/mark-reviewed` | Record a review of the current score version |
| GET | `/api/recruiter/applicants/{id}/score-history` | All score versions with explanations |
| GET | `/api/recruiter/applicants/{id}/graph` | Linked accounts (masked) |
| GET | `/api/recruiter/scoring/rules` | Current rules, weights, thresholds and version |

`GET /api/recruiter/applicants/{id}` now also returns `trust`, `scoreHistory`, `patternAlerts`, `graph` and `reportReviews`. `GET /api/recruiter/applicants` accepts `sort` and `attention`.

---

## Phase 4 — Proof of Skill, assessment integrity, interviews (what was built)

### A. Proof of Skill

- **Where the skills come from:**
  - **Claimed skills:** the candidate's profile, plus skills found in the uploaded resume (read in Phase 3).
  - **Required skills:** the recruiter's actual job posting.
- **Assessment builder:** **Jobs → Assessment** opens one builder per job.
  - **Draft with Gemini (AI):** shown only when `GEMINI_API_KEY` is set. Generated questions are validated: exactly 4 different options and exactly one answer. Malformed ones are thrown away.
  - **Draft from question bank:** a built-in, deterministic bank of 64 questions across 10 skill areas (Python, SQL, JavaScript, React, Java, HTML/CSS, Git, data structures and algorithms, C/C++, machine learning). The same job and skills always give the same questions, and no paid API is needed. Skills the bank doesn't cover are listed so the recruiter can write their own questions.
  - **Write my own question.**
- **Source labels:** every question shows where it came from (**AI-generated (Gemini)**, **Question bank** or **Written by recruiter**) and whether it was edited.
- **Review before publishing:**
  - Drafted questions start **unapproved**. The recruiter reviews each question and its answer key, edits if needed, and approves.
  - Editing a question removes its approval, so it must be approved again.
  - **Publish** is blocked until every question is approved.
- **After publishing:**
  - Questions are **locked**, so every candidate gets the same test.
  - The test is assigned to all current applicants, and to future applicants when they apply. Each candidate gets a message and the application moves to "Assessment".
- **Taking the test:**
  - Multiple choice, with a server-side timer and question navigation.
  - Answers autosave while the timer runs.
  - One submission only, scored on the server.
  - When time runs out, only the answers saved before the deadline count (30-second network grace period).
- **Results** are stored with timestamps, per-question correctness, per-skill scores and the submit reason. They are shown on the candidate's Assessments page and the recruiter's attempt page.
- **Claimed vs. demonstrated:** a Proof of Skill table (skill | profile | resume | required | assessed % | note) appears on the candidate's Assessments page and the recruiter's trust report (Assessment tab).
  - **A low score is never treated as dishonesty.** The note says: "One short test is not proof of the skill level, and never of dishonesty."
  - On the trust report, a score below the pass mark shows as **Needs review**, never Failed.

### B. Assessment integrity

- **Camera consent:**
  - Before the timer starts, the candidate chooses **Allow camera and start** or **Start without camera**. Either way the test can be taken.
  - Camera granted, denied, unavailable or declined is recorded.
- **Optional face re-verification:** one frame is compared with the enrolled face (SFace, threshold 0.363) a moment after the test starts, and again whenever the candidate clicks "Check my face again". The result goes into the timeline. Frames are never stored.
- **Events recorded:**
  - tab hidden or visible
  - window blur or focus
  - copy, cut and paste (the **number of characters only**, never the text)
  - start, resume, submit, time-up
  - each event has a server timestamp, the candidate's device time, and the candidate and attempt IDs
- **Event safeguards:** event types are whitelisted, with a limit of 400 per attempt. Events are accepted only while the test is running.
- **Recruiter view:** an **activity timeline** on the attempt page labels tab switches, focus loss and copy/paste as **"Review signal"**, with the explanation that they can have innocent causes and are **not proof of cheating**.
- **No hidden monitoring:** no keystroke logging, screen capture, recording or background tracking. The candidate sees the live counters while taking the test.

### C. Interviews

- **Scheduling:** the recruiter schedules an interview (date, time, length, mode, interviewer, meeting link) and can mark it **Completed** or **Cancelled**.
- **Candidate reply:** the candidate sees the invitation and can **Accept** it or **Ask for another time** (with a note). The recruiter sees the reply.
- **Identity step at entry:**
  - The candidate clicks **Verify identity & enter**. A live frame is compared with the consented enrolled face.
  - The meeting link is shown only after this step.
  - **Outcomes:**

    | Outcome | When |
    |---|---|
    | **Matched** | similarity ≥ 0.363 |
    | **Uncertain** | 0.25–0.363, no face found, or poor quality |
    | **Needs review** | below 0.25, **more than one face** in view, no camera, no enrolment, or no consent |
  - The candidate can always continue to the call. The interviewer confirms identity there.
- **No camera:** if the camera is denied or unavailable, the candidate uses **Continue without camera** and the result is recorded as Needs review.
- **Microphone level meter (EXPERIMENTAL):** it shows the input level on the candidate's device only. It cannot tell voices apart, is never saved, and is never used as evidence.
- **No video conferencing:** TrustTrace does **not** host the video call. This is stated on the screen. After the identity step the candidate joins the interviewer's own meeting link (Meet, Teams, Zoom…).

### D. UI integration

- **Layouts kept:** the Skill Assessment screen (question card + Live Proctoring / Monitoring panel) and the Interview screen (large video + Identity Check / Environment cards) keep the reference layout.
- **New recruiter screens:**
  - Assessment builder: `/recruiter/jobs/:id/assessment`
  - Attempt detail: `/recruiter/assessments/:id`
  - Proof of Skill on the trust report's Assessment tab
- **Interviews table:** now shows the candidate's reply, the entry identity outcome and similarity, and buttons to mark Completed or Cancel.
- **Dashboards:**
  - The candidate's "Assessments Pending" counter and the recruiter's "In Assessment" counter use the real data.
  - The trust report's Assessment and Interview tabs show scores, review-signal counts and entry outcomes.

### E. Security and data retention

- **Ownership:**
  - Candidates can only read, start, answer or submit their own attempts.
  - Recruiters only see attempts, timelines and interviews for their own organisation's jobs. Everything else returns 404.
- **Answer keys:** never sent to candidates. Questions are hidden until the timer starts, and answers are validated against the attempt's own questions.
- **No repeats or edits:** a second submission returns 409, and there is no endpoint to edit a score or result. Published questions can't be edited.
- **Nothing raw is stored:** no video, audio or camera frames. Only face-check results (decision, similarity, threshold) are kept.
- **Retention:**
  - Integrity events can be purged with `python backend/manage.py purge-assessment-events DAYS`. Scores and answers are kept.
  - Face data follows the Phase 3 deletion paths: `delete-biometrics`, or the candidate withdrawing consent.

### Phase 4 database additions (migration `0003`)

- New tables: `assessment_templates`, `template_questions`, `assessment_events`.
- New columns:
  - `assessments`: template, deadline, camera consent, score, max score, percent, per-skill scores, per-question results, submit reason.
  - `interviews`: candidate response, note, acknowledged time, entry outcome, entry check time.

Existing databases upgrade automatically. This was tested with existing assessment and interview rows, plus a downgrade and re-upgrade.

### New API endpoints

| Who | Endpoints |
|---|---|
| Recruiter | `GET/PUT /recruiter/jobs/{id}/assessment`, `POST …/assessment/generate`, `POST …/assessment/questions`, `PUT/DELETE /recruiter/assessment-questions/{id}`, `POST …/{id}/approve`, `POST /recruiter/jobs/{id}/assessment/publish`, `GET /recruiter/assessments`, `GET /recruiter/assessments/{id}`, `GET /recruiter/applicants/{id}/skills`, `GET /recruiter/interviews`, `POST /recruiter/interviews/{id}/status` |
| Candidate | `GET /candidate/assessments`, `GET /candidate/assessments/{id}`, `POST …/start`, `PUT …/answers`, `POST …/events`, `POST …/submit`, `GET /candidate/skills`, `POST /candidate/interviews/{id}/respond`, `POST /candidate/interviews/{id}/entry` |

---

## Phase 3 — Verification engine (what was built)

Every result comes from the candidate's actual uploaded files and saved profile. Nothing is hardcoded.

- Fixed Python rules decide whether things match. AI never declares fraud.
- An unclear reading is marked **Needs review**, never as a mismatch.
- Nothing blocks or rejects a candidate automatically. Every result is evidence for a person to review.

### Statuses used

| Status | Meaning |
|---|---|
| **Verified** | The documents agree with the profile **and** a real outside party confirmed it: a recruiter's recorded call to the university, or a referee's answer. |
| **Consistent** | The documents agree with the profile. No outside confirmation yet. |
| **Inconsistent** | A clear, high-confidence conflict, shown with the exact field and source text. |
| **Needs review** | Something unclear or worth checking: an unreadable scan, a face that doesn't match, an open duplicate alert. |
| **Pending** | Waiting for something: an upload, a check that is running, or a referee's answer. |
| **Not started** | Nothing to check yet. |

### 1. Resume and profile consistency

- **Reading the file:**
  - PDF text is read with **PyMuPDF**.
  - Pages with almost no text (scans) are rendered and read with **Tesseract OCR**, when installed.
  - Photos are OCR'd too.
- **Fields extracted:**
  - name, email, phone
  - education: degree, institution, years, score
  - employment: company, role, start and end months
  - skills
- **Stored for each field:** the value, a confidence score, the page and a short evidence snippet, and how it was read (`pymupdf`, `ocr`, `gemini`). Processing status and errors are stored too. Full document text is never stored or logged.
- **Comparison rules** check resume against profile:
  - name similarity
  - degree, university and graduation year
  - employers and dates, including overlapping full-time jobs
  - impossible timelines: work before age 14, graduation before age 15, end before start, future dates
  - employers listed in the profile but missing from the resume
- **Low-confidence or missing values** never create a mismatch. They are shown as "not found / needs review".
- **Gemini (optional):**
  - Set `GEMINI_API_KEY` on the server to turn it on. The key stays in the environment and is sent only as a request header; it is never logged and never sent to the browser.
  - Gemini can only fill fields the rules couldn't read. Its values carry a confidence below the rule threshold, so an AI value can **never** create a mismatch.

### 2. Education verification

- **Marksheets and degree certificates:** the name, register number, board or university, degree, year, total marks and CGPA/percentage are read. They are compared with the profile **and** the resume.
- **The screen shows each field** with the value in the document, the value the candidate entered, and a quote from the document.
- **Two separate statuses:**
  - **Document consistency:** do the details agree?
  - **Issuer authenticity:** did the issuer confirm it? The options are:
    - **Recruiter attestation:** a recruiter records what the university or board said (reference and notes required). This is the only path that can make education **Verified**.
    - **Simulated issuer registry** for hackathon testing: `python backend/manage.py load-issuer-records issuers.csv` (columns `issuer,register_number,student_name,qualification,year`). Results are labelled **SIMULATED** everywhere and never upgrade a check to Verified.
- Matching fields alone never claim a certificate is genuine.

### 3. Employment and reference verification

- **Experience letters:** the employee name, company, designation, joining and relieving dates are read and compared with the profile and resume. Duration is checked within ±1 month.
- **Reference workflow:**
  - On the trust report, the recruiter picks a reference from the candidate's profile (or types an HR contact) and creates a **one-time link** that expires in 14 days.
  - No email service is connected, so the recruiter copies the link and sends it. It is also printed in the server console.
  - The referee opens `/reference/<token>`, a public page that needs no account, and confirms or denies the company, title and dates, with comments.
  - Employment becomes **Verified** only after a real referee confirms. A denial makes it Inconsistent.
- **Simulate button:** for demos, a "Simulate" button records a clearly labelled **SIMULATED** answer, which never counts as verification.

### 4. Face enrolment and continuity (OpenCV YuNet + SFace)

- **Models:** bundled in `backend/models`. These are the official OpenCV Zoo files, checked against `SHA256SUMS` before loading.
- **Enrolment:**
  - The registration selfie is processed on the server.
  - The 128-number face template is stored **encrypted** (Fernet, which is AES-128-CBC with an HMAC-SHA256 check; the key is in `backend/data/`). The photo itself is not used for anything else.
  - Requires biometric consent.
- **Rechecks:**
  - The government ID photo is checked during verification.
  - A live webcam frame is checked when an **assessment** starts and in the **interview** room ("Verify my identity").
  - Each check is stored with the stage, the similarity score and the threshold.
- **Thresholds:**
  - Same person: cosine similarity **≥ 0.363**, OpenCV's published value for SFace.
  - Duplicate alerts use a stricter **≥ 0.50**.
- **Quality checks:** exactly one face, a minimum face size of 64 px, brightness between 50 and 215, and sharpness (Laplacian variance ≥ 20). Clear messages are shown for:
  - no face
  - more than one face
  - too dark or too bright
  - blurry
  - camera denied
  - no enrolment
  - no consent
- **Liveness is NOT implemented.** A printed photo or a screen held up to the camera can pass. This is said in the code, on screen and here. A face mismatch is **Needs review**, never an automatic rejection.

### 5. Duplicate profile detection

- **Triggers:** an alert is raised only for:
  - the **same OTP-verified, normalised mobile number** on two candidate accounts, or
  - a **very similar enrolled face** (≥ 0.50) between two consenting candidates.
- **A matching name alone never raises an alert.** This is tested.
- **What the alert shows:** the type of match, the similarity score where relevant, and a masked account reference (e.g. "Candidate account …fe9708"). It shows **no** name, email, phone or photo of the other account.
- **Review:** a person marks each alert *Not a duplicate* or *Confirmed duplicate*, with a required note.
  - Open alert: **Needs review**.
  - Confirmed: **Flagged**.
  - Nothing is blocked automatically.

### 6. Verification pipeline

- **Run verification:**
  - Candidates have the button on Verification, Education and Employment.
  - Recruiters have it on the trust report, for their own applicants only.
  - Admins can run `manage.py run-verification EMAIL`.
- **Job queue:** one background worker thread runs the jobs in order. Jobs left unfinished by a restart are picked up again. The screens show "Verifying…" and refresh when the job finishes.
- **Automatic re-runs:** when a document is uploaded or replaced, the profile changes, a reference answers, an issuer confirmation is recorded, or a duplicate alert is reviewed.
- **Results are saved per run:** extraction outputs, findings with evidence, timestamps and processing errors. They are shown on Education Verification, Employment Verification, Verification history and every tab of the Recruiter Trust Report.

### 7. Security, consent and deletion

- **Gemini key:** server-side environment variable only.
- **Logging:** logs never include document text, face templates or secrets.
- **Consent:**
  - Biometric consent is checked before any face processing.
  - Document-processing consent is checked before reading documents.
  - A candidate can **withdraw or re-give** either consent on My Profile. Each change is recorded with a timestamp.
  - Withdrawing biometric consent deletes the encrypted face template and the face-check history.
  - Withdrawing document consent deletes the stored extractions.
- **Admin deletion:**
  - `manage.py delete-biometrics EMAIL` deletes a candidate's face data.
  - `manage.py purge-extractions DAYS` deletes extractions older than DAYS days.
- **File access:** the Phase 2 rules still apply (owner, or a recruiter whose organisation the candidate applied to; signed 10-minute links).

### Phase 3 database additions (migration `0002`)

| Table | Holds |
|---|---|
| `verification_jobs` | Queue of verification jobs |
| `document_extractions` | Fields read from each document, with confidence and evidence |
| `face_enrollments` | Encrypted face templates |
| `face_checks` | Face rechecks with stage, score and threshold |
| `duplicate_alerts` | Potential duplicate alerts and their reviews |
| `issuer_records` | Simulated issuer registry |
| `issuer_confirmations` | Recruiter attestations and simulated registry results |
| `reference_requests` | One-time reference links and answers |

`verification_runs` was also extended. Existing Phase 2 databases upgrade automatically when `serve.py` starts.

### Optional settings added in Phase 3

| Variable | Purpose |
|---|---|
| `GEMINI_API_KEY` | Turn on Gemini-assisted extraction (optional) |
| `GEMINI_MODEL` | Gemini model name (default set in `backend/app/verification/gemini.py`) |
| `TT_VERIFICATION_SYNC=1` | Run verification jobs immediately instead of in the background (tests only) |

### OCR on Windows (optional)

PDFs with a text layer work without OCR. To read **scanned** PDFs and photos of documents:

1. Install Tesseract from https://github.com/UB-Mannheim/tesseract/wiki.
2. Add its folder to your PATH.
3. Restart `python serve.py`.

`manage.py doctor` shows whether OCR was found. Without it, scanned documents are marked **Needs review** ("couldn't be read"); they never produce false mismatches.

---

## Phase 2 — what was built

### Technology

| Requested | Used |
|---|---|
| Python 3.11+, FastAPI | FastAPI 0.142, Uvicorn |
| SQLAlchemy 2.x, SQLite | SQLAlchemy 2.0 (typed `Mapped` models), SQLite with foreign keys enforced |
| Alembic migrations | `backend/migrations/versions/0001 … 0004 (0004 = Phase 5 tables + append-only audit triggers)`, applied by `manage.py init-db` / `serve.py` |
| Pydantic schemas | Pydantic 2, camelCase JSON matching `frontend/src/api/types.ts` |
| Secure password hashing | **Argon2id** (`argon2-cffi`, library defaults) |
| JWT or secure sessions | HS256 JWT **plus** a server-side session row per token, so logout really revokes it |
| React integration | All Phase 1 screens now call the real API, and preview mode is off |

### A. Authentication

- **Registration:**
  - Candidates register in 4 steps: details, mobile OTP, webcam selfie, education/experience, government ID, consent.
  - Recruiters register with their organisation, which starts in "pending" status.
- **Login:**
  - Candidates and recruiters sign in with a role tab. A wrong-tab login is told which tab to use.
  - Unknown emails and wrong passwords get the same message, so the login page doesn't reveal which emails have accounts.
  - Password checks take the same time whether or not the account exists.
- **Logout** revokes the session on the server. Expired or revoked tokens return 401, and the app sends the user back to the login page.
- **Session persistence:** the token is kept in browser storage, and `/api/auth/me` restores the session after a refresh.
- **Role-based access:**
  - The server enforces roles on every endpoint: `/api/candidate/*` is candidate-only and `/api/recruiter/*` is recruiter-only.
  - The frontend redirects users to their own area.
- **Rate limits:** login (10 per 15 min per client and email), OTP requests (3 per 10 min per number) and registrations.
- **OTP:** the code is stored as an Argon2 hash, expires after 10 minutes, and allows at most 5 wrong attempts.
- **No hardcoded credentials or bypasses.** `PREVIEW_MODE` is now `false`.

### B. Candidate management

- Personal details, mobile number (OTP-verified at registration) and email.
- Education, previous employment, skills and references. All can be viewed, edited and saved on **My Profile**, and every field is validated on both the client and the server.
- If the candidate changes their mobile number, its "verified" status is removed.
- **Consent:** two separate consents, biometric and document processing, are recorded with policy version, time, IP address and browser, and are shown on the profile.
- Profile completeness is computed by the server.

### C. Recruiter management

- Company and recruiter registration, organisation settings (name, website, document retention, notifications) and the team list.
- Job postings: create, edit, close and list. Each has title, department, location, type, mode, experience and salary ranges, description, requirements, required skills, assessments, deadline and status.
- Recruiters only ever see their **own organisation's** jobs and applications. Another organisation's records return 404.

### D. Job applications

- Candidates browse only real jobs that are open, from an approved organisation, and not past their deadline. Search and filters work.
- **Apply:**
  - Duplicate applications are prevented by a database unique constraint plus a clear "You have already applied" message.
  - Jobs already applied to show **Applied** instead of the button.
- Status and timestamps are tracked with a full history (`application_events`).
- **Recruiter actions:**
  - Shortlist, Request clarification (message required), Move to assessment and Schedule interview.
  - Approve / Reject / Request re-verification, each with a required reason.
  - Every change sends the candidate a message in **Messages**.

### E. Document storage

- **Document types:** resume, marksheet, degree certificate, government ID, experience letter, other certificates, and the enrolment selfie.
- **Validation:**
  - File type is checked from the file's **actual bytes** (PDF, JPG or PNG), not from its name or browser label. Resumes must be PDF.
  - Maximum size is 5 MB. Empty and unknown files are rejected.
  - A batch upload is all-or-nothing.
- **Storage:**
  - Files are saved in `backend/data/uploads` under random names. That folder is **outside every public folder**.
  - Metadata is saved for each file: kind, original name, type, size, SHA-256 hash, upload time and owner.
- **Download:**
  - Files are served only through `/api/files/{id}` with a **signed link valid for 10 minutes**.
  - The candidate can open their own files.
  - A recruiter can open a file only if the candidate applied to that recruiter's organisation.
- **Replacement:**
  - Single-copy documents are replaced when a new file is uploaded. The old record is kept for audit and the old file is deleted.
  - Optional certificates can be removed.
- **Uploaded ≠ verified.** Every document is stored with status `pending` and is shown as "not verified yet". No screen marks anything verified in Phase 2.

### F. Database (21 tables, migration `0001`)

| Area | Tables |
|---|---|
| Accounts | `users`, `organizations`, `auth_sessions`, `otp_challenges` |
| Candidate profile | `candidates`, `education`, `employment`, `references`, `consent_records` |
| Hiring | `jobs`, `applications`, `application_events`, `review_decisions`, `messages` |
| Documents and checks | `documents`, `verification_runs`, `findings` |
| Assessment and interview | `assessments`, `interviews` |
| Scoring and audit | `trust_reports`, `activity_events` |

- Relationships and cascades are defined, and foreign keys are enforced in SQLite.
- Later phases add new migrations; they never edit `0001`.

### G. API

- REST under `/api`, with OpenAPI docs at `/api/docs` and the spec at `/api/openapi.json`.
- **Consistent errors:**
  - Every error returns `{"detail": "...", "code": "...", "fields": {...}}`.
  - Status codes: 400/422 validation, 401 not signed in, 403 wrong role, 404 not found or not yours, 409 duplicate, 413 too large, 415 wrong file type, 429 rate limited.
- **Pagination:** list endpoints accept `?limit=&offset=` and return the total in the `X-Total-Count` header.
- **Ownership:** every candidate query is scoped to the signed-in candidate, and every recruiter query to the recruiter's organisation.
- Security headers are set (`nosniff`, `X-Frame-Options: DENY`, `no-store` on API responses).

### H. Frontend integration

- Every Phase 1 form, counter, list, upload and action now uses the real API. The UI design was not changed; the only additions are fields and cards the new features need:
  - profile sections for education, experience and references
  - two consent checkboxes
  - document Replace/Remove buttons
  - the Next-step card, candidate details, documents and history on the trust report
  - a Requirements field and Close button for jobs
  - the pending-approval banner
- If the server is down, screens say **"Can't reach the server"** instead of showing empty data, and nothing claims to be saved.
- Signing in or out clears all cached data, so one account never sees another's.

---

## Tests (final run, Phase 6, 9 Oct 2026)

All results below are from actual runs in the build environment. Nothing failed in the final run.

| Test | Result |
|---|---|
| Backend tests, Phases 2–6 + DigiLocker (`cd backend` then `python -m pytest -q`) | ✅ **74 passed**, 0 failed (6 DigiLocker tests) |
| **Judge demo end-to-end** (`frontend/tests/e2e-demo.mjs`): empty database, real UI and server, random candidate name, fake webcam, simulated DigiLocker | ✅ **37/37 checks** (it also checks for zero page errors and zero CSP violations) |
| Phase 5 end-to-end, rerun | ✅ 21/21 |
| Phase 4 end-to-end, rerun | ✅ 27/27 |
| Phase 3 end-to-end, rerun | ✅ 20/20 |
| Phase 2 end-to-end, rerun | ✅ 24/24 |
| Route smoke test (30 routes, plus 3 on mobile width) | ✅ no errors, no horizontal overflow |
| Type check + production build | ✅ 0 errors; `app.js` 560 KB, `app.css` 54 KB |
| Migration `0005`: upgrade of a database with data, downgrade to `0004` and re-upgrade, Phase 5 review back-fill | ✅ |

During development, two test failures were found and fixed:

- **A demo-test timing issue:** the check read the score text before it had rendered.
- **A long QR payload that OpenCV's decoder couldn't always read:** this was fixed by pointing the QR code to the short
  `/verify/TTP-…` link.

**Coverage of the areas the brief lists:**

| Area | Covered by |
|---|---|
| Registration and persistence | e2e-phase2, e2e-demo (sign out / sign in, reload) |
| Upload and validation (type sniffing, size, pixels, page count) | test_phase2, test_phase6, e2e-phase2 |
| Extraction and mismatch detection | test_phase3, e2e-phase3, e2e-demo (wrong-year marksheet) |
| Duplicate detection (phone, face, per-organisation review) | test_phase3, e2e-phase3 |
| Assessment (server scoring, integrity events) | test_phase4, e2e-phase4, e2e-demo |
| Interview checks | test_phase4, e2e-phase4 |
| Score calculation (explainable, versioned, recomputed) | test_phase5, e2e-phase5, e2e-demo |
| Audit chain (records, links, tampering detected: payload, header, deletion, time) | test_phase6, e2e-demo |
| QR verification (valid, forged, wrong key, expired, revoked, superseded, unknown) | test_phase6, e2e-demo |
| Access control (other organisations get 404, candidates on recruiter endpoints get 403, signed out gets 401, suspended organisations get 403) | test_phase2–6 |

**The 10 Phase 6 backend tests** (synthetic data only) check:

- key events are recorded and linked, and payloads hold no contact details, names, document text or notes
- tampering is detected:
  - the app's own connection can't edit or delete events (triggers)
  - direct file edits are caught: payload change, payload-hash rewrite (HMAC), deleted event, changed timestamp
- other organisations see masked entries, and access control holds
- passport: issue, minimal claims, decodable QR, public verification, public key, candidate view
- passport: forged claims, wrong-key signature, expiry, revocation with a reason, regeneration, automatic supersession after
  a document change, and refusal while a concern is open
- an ineligible candidate gets reasons and no passport
- oversized requests, PDFs with too many pages and huge images are refused
- security headers are present and path traversal fails
- consent withdrawal, erasure, and suspended organisations

**How to run the end-to-end tests** (needs Node.js and Playwright, which are not needed to run the app): start a fresh server, then

```
cd frontend
BASE=http://localhost:5173 SERVER_LOG=../server.log INPUT=<folder with id.jpg and face.y4m> node tests/e2e-demo.mjs shots
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `can't open file 'serve.py'` | You're in the wrong folder. `cd` into `trusttrace` (the folder that contains `serve.py`, `backend`, `frontend`) |
| `Missing Python package (…)` | `python -m pip install -r backend\requirements.txt` |
| `pip` very slow / fails | Retry, or `python -m pip install --timeout 120 -r backend\requirements.txt`. Already-installed packages are not downloaded again |
| `doctor` says face models UNAVAILABLE | `trusttrace-phase6-model-part2.zip` must be extracted into the **same top folder** as the main zip, so `face_recognition_sface_2021dec.onnx.part2` ends up in `trusttrace\backend\models\` (not in a nested `trusttrace` folder) |
| `doctor` says OCR not installed | Optional. Install Tesseract (see "OCR on Windows" below) or set `TT_TESSERACT_CMD`. Without it, scanned documents go to "needs review" |
| OTP not received | It's printed in the window running `python serve.py` (no SMS provider) |
| Recruiter's job not visible to candidates | Approve the organisation: `python backend/manage.py approve-org <recruiter email>` |
| Camera doesn't start | Open `http://localhost:5173` (not an IP address), allow the camera in the browser, close other apps using the webcam |
| Identity says "no match" | The ID photo must show the same person as the webcam selfie, in good light, with the face large enough |
| "Too many … try again later" | Rate limits are in memory; restarting `serve.py` resets them |
| Port 5173 already in use | Set `PORT=5180` in `.env` (or `set PORT=5180` before `python serve.py`) |
| Passport button disabled | Read the "Not eligible yet" reasons in the passport panel; resolve or review the listed items first |
| "Chain: unknown key" after moving data | Copy `evidence.key` and `passport_ed25519.pem` along with the database (they're in `backend/data`) |
| Start again with an empty database | Stop the server, rename `backend\data` (keep it as a backup), start again |

---

## Tests (Phase 5 run on 9 Oct 2026)

| Test | Result |
|---|---|
| Backend tests (`cd backend && python -m pytest`), Phases 2–5 | ✅ **58 passed** |
| **Phase 5 end-to-end** (`frontend/tests/e2e-phase5.mjs`): real UI and server, empty database | ✅ **21/21 checks** |
| Phase 4 end-to-end, rerun | ✅ 27/27 (no regressions) |
| Phase 3 end-to-end, rerun | ✅ 20/20 (no regressions) |
| Phase 2 end-to-end, rerun | ✅ 24/24 (no regressions) |
| Route smoke test, all screens | ✅ no page errors |
| Type check + production build | ✅ 0 errors; `app.js` 535 KB |
| Migration `0004`: append-only triggers block update and delete; downgrade and re-upgrade | ✅ |

**The 10 Phase 5 backend tests** (synthetic data only) cover:

- a clean candidate vs. one with an inconsistent marksheet: the score is lower and the penalty names the finding
- every score entry matches saved evidence, and the score equals 80 plus the applied weights
- pending and simulated checks are not "Verified" and get no credit
- uploading a new document, or resolving a concern, recomputes the score; a changed document brings the penalty back
- assessment results reported separately and not added to the score
- clamping to 0–100 and versioned rulesets
- rapid applications (P1) and repeated submissions (P2)
- a shared browser (P3) gives both accounts an alert, and the graph masks the other account
- other organisations get 404; audit rows can't be updated or deleted
- dashboard counts, the review queue, and list sorting and filtering

**The Phase 5 end-to-end test** registers candidates through the UI on the same browser and runs verification. It checks:

- the score explanation, status groups, the pattern alert and the linked-profile graph
- resolving a concern with a note, which recomputes the score and adds a score version
- Mark reviewed, the dashboard cards, and sorting and filtering on the applicants list

## Tests (Phase 4 run on 9 Oct 2026)

| Test | Result |
|---|---|
| Backend tests (`cd backend && python -m pytest`): Phases 2, 3 and 4 | ✅ **48 passed** |
| Same suite without PyMuPDF | ✅ 37 passed, 11 PDF tests skipped |
| **Phase 4 end-to-end** (`frontend/tests/e2e-phase4.mjs`): real UI and server on an empty database, fake webcam | ✅ **27/27 checks** |
| Phase 3 end-to-end, rerun | ✅ 20/20 (no regressions) |
| Phase 2 end-to-end, rerun | ✅ 24/24 (no regressions) |
| Route smoke test, all screens | ✅ no page errors |
| Type check + production build | ✅ 0 errors; `app.js` 512 KB |
| Migration `0003` on a database with existing rows, plus downgrade and re-upgrade | ✅ |

**The 12 Phase 4 backend tests use synthetic data only.** They cover:

- question bank well-formed and deterministic; unknown skills reported
- Gemini output validated (a malformed question is dropped) and the bank used when Gemini fails
- drafted questions start unapproved; publishing blocked; editing removes approval; invalid questions rejected; other organisations get 404
- publishing assigns and locks; no questions before start; answer key never sent; correct/incorrect scoring (4/5 = 80%); invalid answers rejected; a second submission returns 409; results persist; recruiter sees answers; another candidate gets 404
- applying after publishing assigns the test and sends a message
- timer: late answers ignored, saved answers scored, `time_up` recorded
- integrity events:
  - recorded in order with timestamps, including camera denial
  - unknown types rejected
  - not accepted before start or after submit
  - other organisations get 404
- face recheck during the assessment (match, then a different face → uncertain or needs review), shown in the timeline
- Proof of Skill: claimed vs. demonstrated; a low score note never accuses; the trust report shows Needs review, not Failed
- interview invitation: accept or reschedule (note required), the recruiter sees the reply, another candidate gets 404, a closed interview gets 409
- interview entry without a camera → Needs review, and the meeting link is revealed
- interview entry outcomes: match → Matched; two faces → Needs review; no face → Uncertain; different person → Uncertain or Needs review; liveness "not_checked"

**Phase 4 end-to-end checks (27/27):**

1. The recruiter drafts questions from the bank in the UI. Publishing is disabled until every question is approved.
2. The recruiter writes their own question, approves all of them and publishes. The test is assigned to 2 applicants.
3. The candidate sees the test and the consent step, then chooses "Allow camera and start". The identity recheck shows **Matched**.
4. Answers autosave. A window-focus loss and a paste are simulated. The candidate submits and sees **4/5 (80%)**, which persists on the list along with Proof of Skill.
5. The recruiter sees the score and a timeline with review signals, their explanation, camera consent and the face recheck. The trust report shows Proof of Skill.
6. Two interviews are scheduled in the UI. The candidate accepts one.
7. The meeting link is hidden until the identity step. Verify & enter shows **Matched** and reveals the link.
8. A second candidate in a browser **with no camera** gets "Continue without camera", recorded as **Needs review**, and can start the assessment without a camera.
9. The recruiter sees "Accepted", "Matched" and "Needs review", and marks an interview completed.
10. There are no JavaScript errors.

### Phase 3 tests (9 Oct 2026)

| Test | Result |
|---|---|
| Backend tests (`cd backend && python -m pytest`): Phase 2 + Phase 3 | ✅ **36 passed** |
| Same suite without PyMuPDF installed | ✅ 25 passed, 11 PDF tests skipped. The server then reports "PyMuPDF missing" instead of guessing. |
| Phase 3 end-to-end through the real UI and server (`frontend/tests/e2e-phase3.mjs`), starting from an empty database | ✅ **20/20 checks** |
| Phase 2 end-to-end (`frontend/tests/e2e-phase2.mjs`), rerun after Phase 3 | ✅ **24/24 checks** (no regressions) |
| Route smoke test, all screens | ✅ no page errors |
| Type check + production build | ✅ 0 errors; `app.js` 470 KB |

**The 22 Phase 3 backend tests use synthetic documents generated in the test code**, plus 4 public LFW face images taken from OpenCV's own SFace test data. They cover:

- resume with a matching graduation year → consistent
- resume with a mismatching year → inconsistent with evidence, wording never accusatory
- replacing a document recomputes the results
- overlapping employment and impossible timelines
- marksheet consistent while issuer is "not checked"
- missing year → not a mismatch
- year mismatch plus a resume conflict
- simulated issuer registry stays labelled and never verifies; a recruiter attestation does verify
- experience-letter dates inconsistent
- reference request → real referee answer → verified; unknown and already-used links rejected
- simulated reference labelled and never verifies
- face enrolment and ID photo match
- ID photo of a different person → needs review
- rechecks, plus errors for no face, multiple faces, a very dark image, an invalid image and someone else's interview
- consent withdrawal deletes the face template
- duplicate phone → alert (needs review), a person dismisses or confirms it; a same name alone never alerts
- face duplicate alert
- scanned marksheet read with OCR
- unreadable PDF creates no findings
- Gemini suggestions can't create mismatches, and the key and document text are never logged
- recruiters can only run verification for their own applicants
- extraction regressions

**Phase 3 end-to-end checks (20/20).** These use real browser screens on a fresh database, with a fake webcam showing a test face:

1. A recruiter registers and creates a job.
2. A candidate registers through the UI.
3. Documents are uploaded and **automatic re-verification ran in the background**.
4. Identity is verified (selfie vs. ID photo).
5. An education year mismatch is shown with evidence, and issuer authenticity is shown separately.
6. The marksheet is replaced and education is recomputed to consistent.
7. The employment letter is compared.
8. A recruiter-triggered verification finishes.
9. A one-time reference link is created, the referee answers on the public page, and employment becomes **verified**.
10. A second account with the same number triggers a duplicate alert that shows no personal data of the other account, and a person reviews it.
11. A live identity recheck from the interview screen matches.
12. There are no JavaScript errors.

The Phase 2 test details follow.

### Phase 2 tests (8 Oct 2026)

| Test | Command | Result |
|---|---|---|
| Backend API tests | `cd backend && python -m pytest` | ✅ **14 passed** |
| End-to-end through the real UI and server, starting from an empty database | `node frontend/tests/e2e-phase2.mjs` (see the file header) | ✅ **24/24 checks passed** |
| Frontend type check | `tsc` (strict) | ✅ 0 errors — see note ¹ |
| Production build | `node frontend/scripts/build.mjs` | ✅ `app.js` 440 KB, `app.css` 48 KB |
| Route smoke test (all 29 routes plus 3 at phone width, live server) | `node frontend/tests/smoke-routes.mjs` | ✅ no page errors, no horizontal overflow |
| Data-filled screen render test (mocked API) | `node frontend/tests/render-with-fixtures.mjs` | ✅ passed |

**The 14 API tests cover:**
- the full requested scenario
- login failures, role guards, and forged or revoked tokens
- Argon2 hashes stored instead of passwords
- recruiter registration validation and duplicate emails
- pending organisations' jobs hidden
- OTP required and checked, and consent required
- invalid uploads: fake PDF, PNG sent as a resume, over 5 MB, empty, unknown type, mixed batch
- document ownership, signed links and replacement
- uploads not reachable as static files
- cross-organisation access blocked
- job edit, close and validation
- profile edit and validation
- interview scheduling
- zero counters on an empty database
- OpenAPI spec and unknown endpoints

**End-to-end checks (24/24), all through the browser:**
1. A signed-out user is redirected to login.
2. A recruiter registers with typed-in details. The pending banner shows, the admin CLI approves the organisation, and the banner clears after reload.
3. The recruiter creates a job through the form and it appears in the list.
4. A candidate registers: OTP read from the server console, webcam selfie, education, ID upload and both consents.
5. The candidate sees the real job, applies, and the job then shows **Applied**.
6. The candidate uploads a resume. It is listed as "not verified yet".
7. A fake PDF (an executable renamed to .pdf) is **rejected by the server**.
8. After a refresh, sign-out and sign-in, the dashboard counter, documents and application are still there.
9. A candidate opening `/recruiter` is redirected. The candidate's token gets **403** from a recruiter API, and an anonymous call gets **401**.
10. The recruiter sees the applicant and opens the trust report, which lists the uploaded resume, then requests clarification. The candidate receives the message.
11. No JavaScript errors occurred in the page.

¹ The build sandbox couldn't download packages (`@types/react`), so `tsc` used `tsconfig.sandbox.json` with a small React type shim. All app code was checked strictly, but HTML element attributes were only loosely checked. On a machine with npm, `npm install && npm run typecheck` uses the real types. For the same reason, FastAPI, SQLAlchemy and Alembic were loaded from source copies, and Argon2 was compiled from its official source. Your laptop uses the normal `pip install`.

---

## Known limitations (honest list)

**Phase 6:**

- **The evidence chain is tamper-evident, not tamper-proof.** Someone controlling the server (database file and `evidence.key`)
  can rewrite history and recompute HMACs. Issued passports pin the chain head, which exposes rewrites before that point;
  external anchoring (timestamping service or write-once storage) is not implemented.
- **Passport trust depends on the issuing organisation.** A recruiter decides to issue it once the objective rules pass. The
  passport states which organisation issued it.
- **Passports are per application.** There is no single cross-employer passport, by design (each organisation's reviews are its
  own).
- **The verification page shows the holder's name** for valid passports so a verifier can compare it with the person's ID.
  Anyone holding the link can see it. The link is shared by the candidate.
- **Rate limits are in memory** (reset on restart, single process). The per-network limits are relaxed for local or LAN
  addresses.
- **Shared third-party evidence:**
  - Issuer attestations and reference outcomes recorded by one approved organisation count for the candidate at other
    organisations too. Who recorded them is masked.
  - Only approved organisations can record them.
  - A recruiter receives the referee link (no email service), so a dishonest recruiter could answer it themselves. Simulated
    answers are always labelled and never counted.
- **A phone number changed after registration can't be re-verified** (OTP exists only at registration). The check then shows
  *Pending*.
- **Download links stay valid until they expire** (10 minutes), even after logout.
- **The API documentation page is public** (`/api/docs`). It lists endpoints only, no data.

**Phase 5:**

- **Rule weights and thresholds are heuristics** chosen for the demo, not learned from real fraud data. They are documented, versioned and configurable, and need tuning with real outcomes.
- **Device and network signals are weak.** Clearing browser storage gives a new browser ID. Network addresses are shared by colleges, offices and mobile carriers. Behind a proxy or load balancer, every request may show the proxy's address, so P4 would need the forwarded client address.
- **The relationship graph is rebuilt from all candidates** each time a report opens. That is fine for a demo, but a large deployment would cache it or build it incrementally.
- **Scores are recomputed when a report or list is viewed.** That keeps them current but costs time with many applicants.
- **Append-only protection uses SQLite triggers.** PostgreSQL would need equivalent triggers or database permissions. Someone with direct file access can still change the database.
- **The trust score is decision support.** It reflects only checks that ran and their evidence; it is not a measure of honesty.

**Phase 4:**

- **Integrity signals are weak evidence.** Tab and focus changes can come from notifications, a second monitor or a phone call. The browser can't see other devices or people in the room, so a determined person can still get outside help.
- **No liveness check in assessments or interviews.** A photo held to the camera can pass the face step.
- **The microphone meter is level-only** and labelled experimental. There is no speaker or voice detection.
- **No built-in video call.** The interview happens on the recruiter's own meeting link.
- **The question bank is small** (64 questions across 10 skill areas). Questions can become known over time, so recruiters should add their own. Gemini questions still need careful human review.
- **Multiple choice only.** There are no coding or written-answer questions, and no randomised question order per candidate.
- **Time limits use the server clock with a 30-second grace period.** A candidate who loses their connection keeps only the answers saved so far.
- **Interview reschedule requests are recorded but not automated.** The recruiter changes the time by scheduling again.

**Phase 3:**

- **No liveness or anti-spoofing.** A photo or screen held up to the camera can pass a face check. Only basic quality checks are done.
- **Face similarity is evidence, not proof.** SFace can make mistakes, especially in poor lighting, with large age gaps, or with low-quality ID photos. Every mismatch goes to a person.
- **No real issuer integration** (DigiLocker, university APIs). Issuer authenticity is either a recruiter's recorded attestation or a clearly labelled simulated registry.
- **No email or SMS service.** Reference links and OTPs are shown to the recruiter or printed in the server console.
- **Extraction uses fixed patterns.** Very unusual layouts may leave fields "not found" and need review. Gemini can help fill gaps but can't create mismatches.
- **OCR needs the Tesseract program** installed separately on Windows. Without it, scanned documents need manual review.
- **One background worker thread** suits a single-machine demo. A larger deployment would use a proper queue (Redis/RQ or Celery).
- **In this build sandbox,** PyMuPDF was compiled from source and the face models were taken from public mirrors and verified against OpenCV's official SHA-256 hashes. On your laptop, `pip install` gets PyMuPDF normally, and the models are included in the zip.

**From Phase 2:**

1. **OTP delivery is console-only.** There is no SMS gateway. Replace `deliver_otp()` in `backend/app/routers/auth.py` to send real SMS.
2. **Organisation approval uses the command line** (`manage.py approve-org`). There is no admin web screen yet.
3. **The session token is stored in browser `localStorage`.** That's simple and works with the existing app, but an httpOnly cookie would be safer against XSS (cross-site scripting). Tokens expire after 12 hours and are revoked on logout.
4. **Rate limits are kept in memory.** They reset when the server restarts and don't work across multiple server processes.
5. **Trust score:** done in Phase 5 (see above). The candidate trust passport with a QR code is not built yet.
6. **Assessments:** done in Phase 4 (see above).
7. **Interview times** are stored in UTC, and the candidate's message shows UTC time.
8. **Document retention:** the setting is saved, but automatic deletion isn't scheduled yet.
9. **Forgot password / change password** isn't built yet.
10. **SQLite** suits a hackathon or single-machine demo. For production, set `TT_DATABASE_URL` to PostgreSQL; the models are portable.

---

## Folder layout

```
trusttrace/
  serve.py                     one command: migrate DB + run API + serve website (port 5173); reads .env
  start.bat / start.sh         first run installs packages, then starts
  .env.example                 every setting, documented (copy to .env)
  README.md                    short overview
  PROJECT_STATUS.md
  backend/
    requirements.txt
    manage.py                  init-db | list-orgs | approve-org EMAIL | suspend-org EMAIL
    alembic.ini, migrations/   Alembic environment + versions/0001 … 0004 (0004 adds Phase 5 tables and append-only audit triggers)
    app/
      main.py                  FastAPI app, /api routers, security headers, SPA serving
      config.py db.py models.py schemas.py serialize.py security.py deps.py errors.py storage.py activity.py
      routers/                 auth.py candidate.py jobs.py recruiter.py files.py verification.py skills.py
      verification/            textract.py (PyMuPDF/OCR) fields.py (field extraction) rules.py (deterministic comparison)
                               face.py (YuNet/SFace) crypto.py duplicates.py gemini.py pipeline.py queue.py
      skills/                  bank.py (local question bank) generate.py (Gemini + fallback) service.py (scoring, timeline, Proof of Skill)
      fraud/                   config.py (rules, weights, thresholds) devices.py (hashed browser/network IDs) patterns.py (P1–P5)
                               graph.py (NetworkX relationship graph) scoring.py (explainable trust score, versions)
      routers/fraud.py         Phase 5 recruiter endpoints
      evidence/                chain.py (hash-linked evidence events, verification) passport.py (Ed25519 passport, QR, verify)
      routers/passport.py      Phase 6 evidence + passport endpoints (recruiter, candidate, public)
      ratelimit.py             shared in-memory rate limiter
      demo_docs.py             sample documents for any name (manage.py make-sample-docs)
    models/                    YuNet + SFace ONNX models (official OpenCV Zoo files, SHA256SUMS checked)
    tests/                     conftest.py, test_phase2.py (14), test_phase3.py (22), test_phase4.py (12), test_phase5.py (10), test_phase6.py (10), synth.py, fixtures/
    data/                      created at runtime: trusttrace.db, uploads/, secret.key  (git-ignored, never public)
  frontend/
    dist/                      built website
    src/                       React + TypeScript source (api/, auth/, components/, layouts/, lib/, pages/)
    tests/                     e2e-phase2.mjs, e2e-phase3.mjs, e2e-phase4.mjs, e2e-phase5.mjs, e2e-demo.mjs, smoke-routes.mjs, render-with-fixtures.mjs
```

## Phase 1 (done earlier)

- All 12 reference screens plus the supporting screens: 29 routes in total.
- Design tokens, accessibility, a responsive layout and camera features.
- See git history or the previous copy of this file for the screen-by-route table.

## Phase status

- **Phase 1:** ✅ reference UI (12 screens, 30 routes).
- **Phase 2:** ✅ accounts, jobs, applications, documents, database.
- **Phase 3:** ✅ verification engine, face continuity, duplicates, references, issuer records.
- **Phase 4:** ✅ Proof of Skill, assessment integrity, interview identity step.
- **Phase 5:** ✅ pattern alerts, relationship graph, explainable versioned trust score, review queue, append-only audit.
- **Phase 6:** ✅ evidence chain, signed QR passport, integration audit, security hardening, demo kit, documentation.
- **After the hackathon (not built):** SMS/email gateways, DigiLocker/issuer APIs, liveness detection, admin web screen,
  scheduled retention jobs, external anchoring of chain heads, httpOnly-cookie sessions, multi-process rate limiting.
