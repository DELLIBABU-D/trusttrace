/**
 * Phase 3 end-to-end test: real UI + real server (background job queue), synthetic documents, fake webcam showing a test face.
 *
 *   python backend/tests/make_sample_docs.py DIR/docs --name "Arun Kumar" --company "Zoho Corporation"
 *   (put selfie.jpg, id.jpg and face.y4m (fake camera video of the same test face) into DIR)
 *   BASE=http://localhost:5173 SERVER_LOG=server.log INPUT=DIR node tests/e2e-phase3.mjs [screenshotDir]
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
mkdirSync(OUT, { recursive: true });
const stamp = Date.now().toString().slice(-6);
const results = [];
const check = (name, ok, extra = "") => { results.push({ name, ok }); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? `  (${extra})` : ""}`); };

async function api(method, p, token, body) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  let payload;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { payload = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  const res = await fetch(BASE + "/api" + p, { method, headers, body: payload });
  const data = await res.json().catch(() => null);
  return { status: res.status, data };
}
const otpFor = (phone) => [...readFileSync(LOG, "utf8").matchAll(new RegExp(`mobile ending ${phone.slice(-4)}: (\\d{6})`, "g"))].pop()?.[1];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
async function waitJob(token, p) {
  for (let i = 0; i < 120; i++) {
    const j = await api("GET", p, token);
    if (j.data && (j.data.status === "done" || j.data.status === "failed")) return j.data;
    await sleep(500);
  }
  return null;
}

// recruiter + job (API) -------------------------------------------------------------------------
const R = { email: `hr.${stamp}@nimbus.example`, password: "HireRight2026" };
const reg = await api("POST", "/auth/register/recruiter", null, { fullName: "Kavya Iyer", organisation: `Nimbus ${stamp}`, email: R.email, phone: "9876543210", companySize: "51-200", password: R.password });
check("recruiter registered", reg.status === 201);
execFileSync(process.env.PYTHON ?? "python3", [path.join(ROOT, "backend/manage.py"), "approve-org", R.email], { stdio: "pipe", env: process.env });
const rtoken = (await api("POST", "/auth/login", null, { role: "recruiter", email: R.email, password: R.password })).data.token;
const job = (await api("POST", "/recruiter/jobs", rtoken, { title: "Backend Developer", department: "Engineering", location: "Chennai", employmentType: "full_time",
  workMode: "hybrid", experienceMin: 0, experienceMax: 2, salaryMin: null, salaryMax: null, skills: ["Python", "SQL"], description: "Build APIs with FastAPI and SQL for our hiring platform.",
  requirements: "", assessments: [], deadline: null, status: "open" })).data;
check("job created", !!job?.id);

// candidate registers through the UI with the fake webcam ---------------------------------------
const browser = await chromium.launch({ args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-video-capture=${path.join(IN, "face.y4m")}`] });
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, permissions: ["camera", "microphone"] });
const page = await ctx.newPage();
const pageErrors = [];
page.on("pageerror", (e) => pageErrors.push(e.message));
const shot = (n) => page.screenshot({ path: `${OUT}/p3-${n}.png`, fullPage: true });
const sees = (text, ms = 15000) => page.waitForFunction((t) => document.querySelector("main")?.textContent.includes(t), text, { timeout: ms }).then(() => true, () => false);
const C = { name: "Arun Kumar", email: `arun.${stamp}@mail.example`, phone: `97${stamp}55`.slice(0, 10), password: "Candidate2026" };
try {
  await page.goto(BASE + "/register", { waitUntil: "networkidle" });
  await page.fill("#fullName", C.name); await page.fill("#email", C.email); await page.fill("#phone", C.phone);
  await page.fill("#dateOfBirth", "2004-05-17"); await page.fill("#password", C.password);
  await page.click("text=Verify OTP");
  await page.waitForSelector("#otp");
  await sleep(400);
  await page.fill("#otp", otpFor(C.phone) ?? "");
  await page.waitForFunction(() => document.querySelector("video")?.videoWidth > 0, null, { timeout: 10000 });
  await sleep(800);
  await page.click("button:has-text('Capture')");
  await page.click("button:has-text('Next')");
  await page.fill("#edu-degree-0", "B.E. Computer Science and Engineering"); await page.fill("#edu-inst-0", "Anna University");
  await page.fill("#edu-start-0", "2022"); await page.fill("#edu-end-0", "2026"); await page.fill("#edu-score-0", "8.4");
  await page.click("button:has-text('Add role')");
  await page.fill("#exp-company-0", "Zoho Corporation"); await page.fill("#exp-title-0", "Software Engineer Intern");
  await page.fill("#exp-start-0", "2025-05"); await page.fill("#exp-end-0", "2025-07");
  await page.click("button:has-text('Next')");
  await page.setInputFiles("input[type=file]", path.join(IN, "id.jpg"));
  for (const b of await page.$$("input[type=checkbox]")) await b.check();
  await page.click("button:has-text('Next')");
  await page.click("button:has-text('Submit registration')");
  await page.waitForURL("**/candidate", { timeout: 15000 });
  check("candidate registered through the UI", true);
  const ctoken = await page.evaluate(() => localStorage.getItem("tt.session"));

  // documents uploaded through the UI ------------------------------------------------------------
  await page.goto(BASE + "/candidate/documents", { waitUntil: "networkidle" });
  await page.setInputFiles("section[aria-labelledby=slot-resume] input[type=file]", path.join(IN, "docs/resume.pdf"));
  await page.setInputFiles("section[aria-labelledby=slot-marksheet] input[type=file]", path.join(IN, "docs/marksheet_wrong_year.pdf"));
  await page.setInputFiles("section[aria-labelledby=slot-experience_letter] input[type=file]", path.join(IN, "docs/experience_letter.pdf"));
  await page.click("button:has-text('Upload Documents')");
  check("documents uploaded", await sees("Uploaded 3 files"));
  const j1 = await waitJob(ctoken, "/candidate/verification/job");
  check("automatic re-verification job finished in the background", j1?.status === "done", j1?.status);

  // results on the candidate screens ---------------------------------------------------------------
  await page.goto(BASE + "/candidate/verification", { waitUntil: "networkidle" });
  check("identity verified (selfie vs ID photo)", await sees("Enrolment photo and ID photo show the same face"));
  await shot("01-candidate-verification");
  await page.goto(BASE + "/candidate/verification/education", { waitUntil: "networkidle" });
  check("education year mismatch shown with evidence", (await sees("Mismatch")) && (await sees("Year on the document differs")));
  check("issuer authenticity shown separately (not checked)", await sees("do not prove the certificate is genuine"));
  await shot("02-education-mismatch");

  // candidate replaces the marksheet with the correct one -> results recomputed
  const docs = (await api("GET", "/candidate/documents", ctoken)).data;
  const ms = docs.find((d) => d.kind === "marksheet");
  const fd = new FormData();
  fd.append("file", new Blob([readFileSync(path.join(IN, "docs/marksheet.pdf"))], { type: "application/pdf" }), "marksheet.pdf");
  check("marksheet replaced", (await api("PUT", `/candidate/documents/${ms.id}`, ctoken, fd)).status === 200);
  await waitJob(ctoken, "/candidate/verification/job");
  const edu = (await api("GET", "/candidate/verification/education", ctoken)).data;
  check("education recomputed to consistent after the change", edu.status === "consistent", edu.status);
  await page.goto(BASE + "/candidate/verification/employment", { waitUntil: "networkidle" });
  check("employment letter compared (company/designation/dates)", (await sees("Joining Date")) && (await sees("Match")));
  await shot("03-employment");

  // apply; recruiter runs verification and requests a reference --------------------------------
  const app = (await api("POST", `/jobs/${job.id}/apply`, ctoken)).data;
  const rctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const rpage = await rctx.newPage();
  rpage.on("pageerror", (e) => pageErrors.push(e.message));
  await rpage.addInitScript((t) => localStorage.setItem("tt.session", t), rtoken);
  await rpage.goto(`${BASE}/recruiter/applicants/${app.id}`, { waitUntil: "networkidle" });
  await rpage.click("button:has-text('Run verification')");
  await sleep(500);
  const j2 = await waitJob(rtoken, `/recruiter/applicants/${app.id}/verification/job`);
  check("recruiter-triggered verification finished", j2?.status === "done");
  await rpage.reload({ waitUntil: "networkidle" });
  await rpage.click("[role=tab]:has-text('Employment')");
  await rpage.fill("#ref-name", "Priya (HR)");
  await rpage.fill("#ref-contact", "hr@zoho.example");
  await rpage.click("button:has-text('Create confirmation link')");
  await rpage.waitForSelector("text=Send this link to the referee", { timeout: 10000 }).catch(async (e) => {
    await rpage.screenshot({ path: `${OUT}/p3-ref-debug.png`, fullPage: true });
    console.log((await rpage.textContent("main")).match(/Link not created.{0,200}/)?.[0]);
    throw e;
  });
  const link = (await rpage.textContent("text=/\\/reference\\//")).match(/https?:\/\/\S+\/reference\/[\w-]+/)?.[0];
  check("one-time reference link created", !!link);
  await rpage.screenshot({ path: `${OUT}/p3-04-recruiter-employment.png`, fullPage: true });

  // referee answers on the public page -------------------------------------------------------------
  const ref = await (await browser.newContext()).newPage();
  await ref.goto(link.replace(/^https?:\/\/[^/]+/, BASE), { waitUntil: "networkidle" });
  await ref.check("input[name=confirmed] >> nth=0");
  await ref.fill("#title", "Software Engineer Intern"); await ref.fill("#start", "2025-05"); await ref.fill("#end", "2025-07");
  await ref.fill("#responderName", "Priya (HR)");
  await ref.click("button:has-text('Send answer')");
  check("referee submitted the confirmation", await ref.waitForSelector("text=Thank you", { timeout: 10000 }).then(() => true, () => false));
  await ref.screenshot({ path: `${OUT}/p3-05-referee.png` });
  await waitJob(rtoken, `/recruiter/applicants/${app.id}/verification/job`);
  const rep = (await api("GET", `/recruiter/applicants/${app.id}/report`, rtoken)).data;
  check("employment verified after a real HR confirmation", rep.verification.employment.status === "verified", rep.verification.employment.status);

  // duplicate: second account with the same verified mobile number --------------------------------
  await api("POST", "/auth/otp", null, { phone: C.phone });
  await sleep(300);
  const fd2 = new FormData();
  fd2.append("payload", JSON.stringify({ fullName: "Different Name", email: `dup.${stamp}@mail.example`, phone: C.phone, otp: otpFor(C.phone), dateOfBirth: "2003-01-01",
    password: "Candidate2026", education: [{ degree: "BSc", institution: "Some College", startYear: "2020", endYear: "2023", score: "" }], experience: [],
    selfie: "data:image/jpeg;base64," + readFileSync(path.join(IN, "other.jpg")).toString("base64"), consent: true }));
  fd2.append("idDocument", new Blob([readFileSync(path.join(IN, "other.jpg"))], { type: "image/jpeg" }), "id.jpg");
  const dup = await api("POST", "/candidates/register", null, fd2);
  check("second account registered with the same number", dup.status === 201);
  await waitJob(dup.data.token, "/candidate/verification/job");
  await api("POST", `/recruiter/applicants/${app.id}/verification/run`, rtoken);
  await waitJob(rtoken, `/recruiter/applicants/${app.id}/verification/job`);
  await rpage.reload({ waitUntil: "networkidle" });
  await rpage.click("[role=tab]:has-text('Risk Analysis')");
  const riskText = await rpage.textContent("main");
  check("potential duplicate alert shown with evidence, no personal data of the other account",
    riskText.includes("Same verified mobile number") && riskText.includes("Candidate account …") && !riskText.includes("Different Name"));
  await rpage.click("button:has-text('Review') >> nth=0");
  await rpage.fill("#dup-note", "Checked with the candidate: shared family phone.");
  await rpage.click("button:has-text('Save review')");
  check("duplicate alert reviewed by a person", await rpage.waitForSelector("text=Not a duplicate", { timeout: 10000 }).then(() => true, () => false));
  await rpage.screenshot({ path: `${OUT}/p3-06-risk.png`, fullPage: true });

  // identity recheck from the interview screen ------------------------------------------------------
  await page.goto(BASE + "/candidate/interviews/check", { waitUntil: "networkidle" });
  await page.waitForFunction(() => document.querySelector("video")?.videoWidth > 0, null, { timeout: 10000 });
  await sleep(800);
  await page.click("button:has-text('Verify my identity')");
  check("live identity recheck matches the enrolled face", await sees("Face matches the enrolled photo"));
  await shot("07-interview-recheck");
} catch (err) {
  check("scenario ran to completion", false, err.message.split("\n")[0]);
  await page.screenshot({ path: `${OUT}/p3-error.png` }).catch(() => undefined);
}
check("no JavaScript errors in the page", pageErrors.length === 0, pageErrors.join(" | "));
await browser.close();
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
