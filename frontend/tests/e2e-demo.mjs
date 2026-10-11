/**
 * Judge demo, end to end, on an EMPTY database, through the real UI and server (background verification queue).
 * Nothing is predefined: the recruiter, job, candidate and documents are created during the run, and the candidate's
 * name is chosen at random from a list each run. Documents are generated for that name with `manage.py make-sample-docs`.
 *
 *   INPUT dir must contain id.jpg and face.y4m (fake webcam video of the same synthetic test face as id.jpg).
 *   BASE=http://localhost:5173 SERVER_LOG=server.log INPUT=DIR node tests/e2e-demo.mjs [screenshotDir]
 *
 * Steps follow the judge demo script in PROJECT_STATUS.md (sections E1–E14).
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync } from "node:fs";
import path from "node:path";

const pw = await import(process.env.PLAYWRIGHT_PATH ?? "playwright");
const { chromium } = pw.default ?? pw;
const BASE = process.env.BASE ?? "http://localhost:5173";
const LOG = process.env.SERVER_LOG ?? "server.log";
const IN = process.env.INPUT ?? "e2e-input";
const OUT = process.argv[2] ?? "test-shots";
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
const PY = process.env.PYTHON ?? "python3";
mkdirSync(OUT, { recursive: true });
const stamp = Date.now().toString().slice(-6);
const results = [];
const check = (name, ok, extra = "") => { results.push({ name, ok }); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? `  (${extra})` : ""}`); };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const manage = (...args) => execFileSync(PY, [path.join(ROOT, "backend/manage.py"), ...args], { stdio: "pipe", env: process.env }).toString();

async function api(method, p, token, body) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  let payload;
  if (body !== undefined) { payload = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  const res = await fetch(BASE + "/api" + p, { method, headers, body: payload });
  return { status: res.status, data: await res.json().catch(() => null) };
}
const otpFor = (phone) => [...readFileSync(LOG, "utf8").matchAll(new RegExp(`mobile ending ${phone.slice(-4)}: (\\d{6})`, "g"))].pop()?.[1];
async function waitJob(token, p) {
  for (let i = 0; i < 160; i++) {
    const j = await api("GET", p, token);
    if (j.data && ["done", "failed"].includes(j.data.status)) return j.data;
    await sleep(500);
  }
  return null;
}

const NAMES = ["Priya Sharma", "Rahul Verma", "Fatima Khan", "Joseph Mathew", "Ananya Iyer", "Vikram Singh"];
const C = { name: NAMES[Number(stamp) % NAMES.length], phone: `9${stamp}${Math.floor(Math.random() * 900 + 100)}`.slice(0, 10), password: "Candidate2026" };
C.email = `${C.name.split(" ")[0].toLowerCase()}.${stamp}@mail.example`;
const R = { name: "Recruiter " + stamp, org: `Demo Hiring Co ${stamp}`, email: `hr.${stamp}@demohiring.example`, phone: "9876501234", password: "HireRight2026" };
const JOB = "Python Developer";
const DOCS = path.join(OUT, "docs");
manage("make-sample-docs", C.name, DOCS);

const browser = await chromium.launch({ args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-video-capture=${path.join(IN, "face.y4m")}`] });
const pageErrors = [];
const cspErrors = [];
async function newPage(token) {
  const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, permissions: ["camera", "microphone"] });
  if (token) await ctx.addInitScript((t) => localStorage.setItem("tt.session", t), token);
  const p = await ctx.newPage();
  p.on("pageerror", (e) => pageErrors.push(e.message));
  p.on("console", (m) => { if (m.type() === "error" && /Content Security Policy/i.test(m.text())) cspErrors.push(m.text()); });
  return p;
}
const seesOn = (p, text, ms = 20000) => p.waitForFunction((t) => (document.querySelector("main") ?? document.body)?.textContent.includes(t), text, { timeout: ms }).then(() => true, () => false);

const rp = await newPage();
const shotR = (n) => rp.screenshot({ path: `${OUT}/demo-${n}.png`, fullPage: true });
let cp;
const shotC = (n) => cp.screenshot({ path: `${OUT}/demo-${n}.png`, fullPage: true });

try {
  // E0. empty database: honest empty states ---------------------------------------------------------
  const jobsBefore = await api("GET", "/health");
  check("server up on an empty database", jobsBefore.status === 200);

  // E1. recruiter registers manually ----------------------------------------------------------------
  await rp.goto(BASE + "/recruiter/register", { waitUntil: "networkidle" });
  await rp.fill("#fullName", R.name); await rp.fill("#organisation", R.org); await rp.fill("#email", R.email); await rp.fill("#phone", R.phone);
  await rp.selectOption("#companySize", "51-200"); await rp.fill("#password", R.password); await rp.fill("#confirm", R.password);
  await rp.check("#terms");
  await rp.click("button[type=submit]");
  await rp.waitForURL("**/recruiter", { timeout: 15000 });
  check("E1 recruiter registered through the form", await seesOn(rp, R.org));
  manage("approve-org", R.email);
  await rp.reload({ waitUntil: "networkidle" });
  check("E1 fresh dashboard shows zero applicants (no sample data)", await seesOn(rp, "Total Applicants") && (await rp.textContent("main")).includes("0"));
  await shotR("01-empty-dashboard");

  // E2. job ------------------------------------------------------------------------------------------
  await rp.goto(BASE + "/recruiter/jobs/new", { waitUntil: "networkidle" });
  await rp.fill("#title", JOB); await rp.fill("#department", "Engineering"); await rp.fill("#location", "Chennai");
  await rp.selectOption("#workMode", "hybrid");
  await rp.fill("#experienceMin", "0"); await rp.fill("#experienceMax", "2");
  for (const s of ["Python", "SQL", "FastAPI"]) { await rp.fill("#skill", s); await rp.keyboard.press("Enter"); }
  await rp.fill("#description", "Build REST APIs in Python (FastAPI), write SQL and tests, and review code with the team.");
  await rp.click("button[type=submit]");
  await rp.waitForURL("**/recruiter/jobs", { timeout: 15000 });
  check("E2 Python Developer job created through the form", await seesOn(rp, JOB));
  const job = (await api("GET", "/recruiter/jobs", (await api("POST", "/auth/login", null, { role: "recruiter", email: R.email, password: R.password })).data.token)).data.find((j) => j.title === JOB);
  const rtoken = await rp.evaluate(() => localStorage.getItem("tt.session"));

  // recruiter prepares a short skill assessment (question bank, every question approved by a person)
  await rp.click(`a[href='/recruiter/jobs/${job.id}/assessment']`);
  await rp.waitForURL("**/assessment");
  await rp.fill("#count", "4");
  await rp.click("button:has-text('Draft from question bank')");
  await seesOn(rp, "Needs your review");
  for (let i = 0; i < 10 && (await rp.locator("button:has-text('Approve question & answer')").count()); i++) {
    await rp.locator("button:has-text('Approve question & answer')").first().click();
    await sleep(400);
  }
  await rp.click("button:has-text('Publish assessment')");
  await rp.locator("[role=dialog] button:has-text('Publish')").click();
  check("E10 short assessment drafted, approved by the recruiter and published", await seesOn(rp, "Published"));

  // E3–E4. candidate registers manually with webcam, education and employment -----------------------
  cp = await newPage();
  await cp.goto(BASE + "/register", { waitUntil: "networkidle" });
  await cp.fill("#fullName", C.name); await cp.fill("#email", C.email); await cp.fill("#phone", C.phone);
  await cp.fill("#dateOfBirth", "2004-05-17"); await cp.fill("#password", C.password);
  await cp.click("text=Verify OTP");
  await cp.waitForSelector("#otp");
  await sleep(500);
  await cp.fill("#otp", otpFor(C.phone) ?? "");
  await cp.waitForFunction(() => document.querySelector("video")?.videoWidth > 0, null, { timeout: 15000 });
  await sleep(800);
  await cp.click("button:has-text('Capture')");
  await cp.click("button:has-text('Next')");
  await cp.fill("#edu-degree-0", "B.E. Computer Science and Engineering"); await cp.fill("#edu-inst-0", "Anna University");
  await cp.fill("#edu-start-0", "2022"); await cp.fill("#edu-end-0", "2026"); await cp.fill("#edu-score-0", "8.4");
  await cp.click("button:has-text('Add role')");
  await cp.fill("#exp-company-0", "Zoho Corporation"); await cp.fill("#exp-title-0", "Software Engineer Intern");
  await cp.fill("#exp-start-0", "2025-05"); await cp.fill("#exp-end-0", "2025-07");
  await cp.click("button:has-text('Next')");
  await cp.setInputFiles("input[type=file]", path.join(IN, "id.jpg"));
  for (const b of await cp.$$("input[type=checkbox]")) await b.check();
  await cp.click("button:has-text('Next')");
  await cp.click("button:has-text('Submit registration')");
  await cp.waitForURL("**/candidate", { timeout: 20000 });
  check(`E3 candidate "${C.name}" registered (OTP, webcam selfie with consent, ID, education, employment)`, await seesOn(cp, C.name.split(" ")[0]));
  const ctoken = await cp.evaluate(() => localStorage.getItem("tt.session"));

  // E5. upload resume + education certificate (deliberately with the wrong year first) + experience letter
  await cp.goto(BASE + "/candidate/documents", { waitUntil: "networkidle" });
  await cp.setInputFiles("section[aria-labelledby=slot-resume] input[type=file]", path.join(DOCS, "resume.pdf"));
  await cp.setInputFiles("section[aria-labelledby=slot-marksheet] input[type=file]", path.join(DOCS, "marksheet_wrong_year.pdf"));
  await cp.setInputFiles("section[aria-labelledby=slot-experience_letter] input[type=file]", path.join(DOCS, "experience_letter.pdf"));
  await cp.click("button:has-text('Upload Documents')");
  check("E5 documents uploaded through the UI", await seesOn(cp, "Uploaded 3 files"));
  await shotC("02-documents");

  // E6. apply ----------------------------------------------------------------------------------------
  await cp.goto(BASE + "/candidate/jobs", { waitUntil: "networkidle" });
  await cp.click(`article:has-text("${JOB}") button:has-text("Apply")`);
  await cp.waitForURL("**/candidate/applications/**", { timeout: 15000 });
  check("E6 applied to the Python Developer job", await seesOn(cp, JOB));
  const app = (await api("GET", "/candidate/applications", ctoken)).data[0];

  // E7–E8. verification runs; extracted values are compared ------------------------------------------
  const j1 = await waitJob(ctoken, "/candidate/verification/job");
  check("E7 verification ran in the background", j1?.status === "done", j1?.status);
  await rp.goto(`${BASE}/recruiter/applicants/${app.id}`, { waitUntil: "networkidle" });
  await rp.click("button:has-text('Run verification')");
  await sleep(500);
  const j2 = await waitJob(rtoken, `/recruiter/applicants/${app.id}/verification/job`);
  check("E7 recruiter re-ran verification from the report", j2?.status === "done");
  await cp.goto(BASE + "/candidate/verification/education", { waitUntil: "networkidle" });
  check("E8 mismatching extracted value shown (year of passing)", await seesOn(cp, "Mismatch") && await seesOn(cp, "Year on the document differs"));
  await shotC("03-education-mismatch");
  // E8b. DigiLocker comparison (SIMULATED mode: no partner credentials in tests) ---------------------------------
  manage("load-digilocker-records", path.join(DOCS, "digilocker_records.csv"));
  await cp.goto(BASE + "/candidate/verification/education", { waitUntil: "networkidle" });
  check("E8b DigiLocker card shown, clearly in SIMULATED mode", await seesOn(cp, "Compare with DigiLocker") && await seesOn(cp, "SIMULATED mode"));
  await cp.check("text=You will be sent to DigiLocker");
  await cp.click("button:has-text('Connect DigiLocker (simulated)')");
  await cp.waitForURL("**/digilocker-simulated**", { timeout: 15000 });
  check("E8b simulated consent screen labelled as testing only", await seesOn(cp, "SIMULATED DIGILOCKER") && await seesOn(cp, "Consolidated Mark Sheet"));
  await cp.click("button:has-text('Allow')");
  await cp.waitForURL("**/candidate/verification/education?digilocker=connected**", { timeout: 15000 });
  await cp.click("button:has-text('Compare this')");
  await waitJob(ctoken, "/candidate/verification/job");
  await sleep(500);
  await cp.reload({ waitUntil: "networkidle" });
  check("E8b DigiLocker copy differs from the uploaded certificate (year) and is labelled SIMULATED",
    await seesOn(cp, "Differs from DigiLocker") && await seesOn(cp, "Year of passing") && await seesOn(cp, "never counts as verification"));
  await shotC("03b-digilocker-compare");
  await cp.goto(BASE + "/candidate/verification/employment", { waitUntil: "networkidle" });
  check("E8 matching extracted values shown (experience letter)", await seesOn(cp, "Match"));
  await cp.goto(BASE + "/candidate/verification", { waitUntil: "networkidle" });
  check("E9 identity: enrolment selfie matched the ID photo", await seesOn(cp, "Enrolment photo and ID photo show the same face"));

  // E9. face recheck with consent ----------------------------------------------------------------------
  await cp.goto(BASE + "/candidate/interviews/check", { waitUntil: "networkidle" });
  await cp.waitForFunction(() => document.querySelector("video")?.videoWidth > 0, null, { timeout: 15000 });
  await sleep(800);
  await cp.click("button:has-text('Verify my identity')");
  check("E9 live face recheck matches the enrolled face", await seesOn(cp, "Face matches the enrolled photo"));

  // E10–E11. short assessment with integrity events ------------------------------------------------------
  await cp.goto(`${BASE}/candidate/assessments`, { waitUntil: "networkidle" });
  await cp.click("a:has-text('Start')");
  await cp.click("button:has-text('Allow camera and start')");
  await cp.waitForSelector("text=/Question 1 of \\d/", { timeout: 15000 });
  const tmpl = (await api("GET", `/recruiter/jobs/${job.id}/assessment`, rtoken)).data.template;
  const keyOf = Object.fromEntries(tmpl.questions.map((q) => [q.prompt, q.correctOptionId]));
  const total = tmpl.questions.length;
  for (let i = 0; i < total; i++) {
    const prompt = (await cp.textContent("legend")).trim();
    await cp.check(`input[type=radio][value=${keyOf[prompt]}]`);
    if (i === 1) {
      await cp.evaluate(() => { window.dispatchEvent(new Event("blur")); window.dispatchEvent(new Event("focus")); });
      await cp.evaluate(() => document.dispatchEvent(new ClipboardEvent("paste", { clipboardData: new DataTransfer() })));
    }
    if (i < total - 1) await cp.click("button:has-text('Next')");
  }
  await seesOn(cp, "All answers saved");
  await sleep(3500);
  await cp.click("button:has-text('Submit')");
  await cp.locator("[role=dialog] button:has-text('Submit answers')").click();
  check("E10 assessment submitted and scored on the server", await seesOn(cp, "Your score") && await seesOn(cp, "100%"));
  await rp.goto(`${BASE}/recruiter/assessments`, { waitUntil: "networkidle" });
  await rp.click("a:has-text('Details')");
  check("E11 integrity events shown as review signals (focus lost, paste)", await seesOn(rp, "Test window lost focus") && await seesOn(rp, "Pasted text") && await seesOn(rp, "not proof of cheating"));
  await shotR("04-assessment-integrity");

  // E12. recruiter dashboard ---------------------------------------------------------------------------
  await rp.goto(`${BASE}/recruiter`, { waitUntil: "networkidle" });
  check("E12 dashboard shows the real applicant and review queue", await seesOn(rp, C.name) && await seesOn(rp, "Review queue"));
  await shotR("05-dashboard");

  // E13. trust report with evidence; passport not yet eligible -------------------------------------------
  await rp.goto(`${BASE}/recruiter/applicants/${app.id}`, { waitUntil: "networkidle" });
  check("E13 explainable score: baseline and evidence-backed rules", await seesOn(rp, "Baseline 80") && await seesOn(rp, "EDU.INCONSISTENT"));
  check("E13 passport blocked while a concern is open (with reasons)", await seesOn(rp, "Not eligible yet") && await seesOn(rp, "still need a reviewer's decision"));
  await shotR("06-trust-report");
  await rp.click("button:has-text('Request clarification')");
  await rp.fill("#note", "The year on your marksheet differs from your profile. Please upload the final consolidated marksheet.");
  await rp.click("button:has-text('Send request')");
  check("E13 recruiter review action: clarification requested", await seesOn(rp, "Clarification"));

  // candidate uploads the correct marksheet; everything is recomputed from evidence
  await cp.goto(BASE + "/candidate/documents", { waitUntil: "networkidle" });
  await cp.setInputFiles("section[aria-labelledby=slot-marksheet] input[type=file]", path.join(DOCS, "marksheet.pdf"));
  await cp.click("button:has-text('Upload Documents')");
  await seesOn(cp, "Uploaded 1 file");
  await waitJob(ctoken, "/candidate/verification/job");
  await rp.reload({ waitUntil: "networkidle" });
  check("E13 corrected document recomputed the report (EDU.CONSISTENT)", await seesOn(rp, "EDU.CONSISTENT"));
  await rp.click("[role=tab]:has-text('Education')");
  check("E13 recruiter sees the DigiLocker comparison now matching (still SIMULATED, not counted)", await seesOn(rp, "DigiLocker comparison") && await seesOn(rp, "Matches DigiLocker"));
  await rp.click("[role=tab]:has-text('Summary')");
  await rp.click("button:has-text('Mark reviewed')");
  check("E13 report marked reviewed", await seesOn(rp, "This version was reviewed by"));
  await rp.click("button:has-text('Shortlist')");
  await seesOn(rp, "Shortlisted");

  // E14. audit chain + passport ----------------------------------------------------------------------------
  await rp.click("[role=tab]:has-text('Audit Trail')");
  check("E14 evidence chain verified intact", await seesOn(rp, "Chain intact"));
  if (await rp.locator("button:has-text('Show all')").count()) await rp.click("button:has-text('Show all')");
  check("E14 timeline lists the key events", await seesOn(rp, "Candidate registered") && await seesOn(rp, "Document replaced") && await seesOn(rp, "Assessment submitted")
    && await seesOn(rp, "Face recheck") && await seesOn(rp, "Application status changed") && await seesOn(rp, "Document pulled from DigiLocker"));
  await shotR("07-audit-trail");
  await rp.click("button:has-text('Issue passport')");
  check("E14 passport issued by the recruiter", await seesOn(rp, "Open verification page"));
  const pv = (await api("GET", `/recruiter/applicants/${app.id}/passport`, rtoken)).data.active;
  await rp.click("[role=tab]:has-text('Audit Trail')").catch(() => undefined);
  await shotR("08-passport-issued");

  await cp.goto(BASE + "/candidate/passport", { waitUntil: "networkidle" });
  check("E14 candidate sees the passport with a QR code", await seesOn(cp, pv.passportId) && (await cp.locator("img[alt^='QR code']").count()) === 1);
  check("E14 passport labels: identity Verified, education only Consistent", await seesOn(cp, "Identity (selfie vs ID document)") && await seesOn(cp, "Consistent"));
  await shotC("09-candidate-passport");

  const vp = await newPage();
  await vp.goto(pv.verifyUrl.replace(/^https?:\/\/[^/]+/, BASE), { waitUntil: "networkidle" });
  check("E14 QR link opens the public verification page: valid", await seesOn(vp, "Valid TrustTrace passport") && await seesOn(vp, C.name));
  await vp.screenshot({ path: `${OUT}/demo-10-verify-valid.png`, fullPage: true });
  const forged = pv.token.slice(0, -4) + (pv.token.endsWith("AAAA") ? "BBBB" : "AAAA");
  await vp.goto(`${BASE}/verify/${forged}`, { waitUntil: "networkidle" });
  check("E14 a tampered token is rejected", await seesOn(vp, "could not be verified"));

  // revocation is reflected immediately
  await rp.click("button:has-text('Revoke')");
  await rp.fill("#revoke-reason", "Demo: revoking to show the live status check.");
  await rp.locator("[role=dialog] button:has-text('Revoke')").click();
  await seesOn(rp, "revoked");
  await vp.goto(pv.verifyUrl.replace(/^https?:\/\/[^/]+/, BASE), { waitUntil: "networkidle" });
  check("E14 revoked passport shows as revoked with the reason", await seesOn(vp, "Passport revoked") && await seesOn(vp, "live status check"));
  await vp.screenshot({ path: `${OUT}/demo-11-verify-revoked.png`, fullPage: true });
  const chain = manage("verify-chain", C.email);
  check("CLI verify-chain reports the chain intact", chain.includes("INTACT"), chain.split("\n")[0]);
} catch (err) {
  check("scenario ran to completion", false, err.message.split("\n")[0]);
  await rp.screenshot({ path: `${OUT}/demo-error-recruiter.png`, fullPage: true }).catch(() => undefined);
  await cp?.screenshot({ path: `${OUT}/demo-error-candidate.png`, fullPage: true }).catch(() => undefined);
}
check("no JavaScript errors in any page", pageErrors.length === 0, pageErrors.join(" | "));
check("no Content-Security-Policy violations", cspErrors.length === 0, cspErrors.slice(0, 2).join(" | "));
await browser.close();
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
