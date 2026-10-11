/**
 * Phase 4 end-to-end test: real UI + real server. Recruiter builds, reviews and publishes an assessment; the candidate
 * takes it with the (fake) webcam; integrity events and the identity recheck appear on the recruiter's timeline;
 * interviews are scheduled, acknowledged and entered with a face check, plus a camera-unavailable path.
 *
 *   INPUT dir must contain selfie.jpg, id.jpg and face.y4m (fake camera video of the same synthetic test face).
 *   BASE=http://localhost:5173 SERVER_LOG=server.log INPUT=DIR node tests/e2e-phase4.mjs [screenshotDir]
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
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function api(method, p, token, body) {
  const headers = token ? { Authorization: `Bearer ${token}` } : {};
  let payload;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { payload = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  const res = await fetch(BASE + "/api" + p, { method, headers, body: payload });
  return { status: res.status, data: await res.json().catch(() => null) };
}
const otpFor = (phone) => [...readFileSync(LOG, "utf8").matchAll(new RegExp(`mobile ending ${phone.slice(-4)}: (\\d{6})`, "g"))].pop()?.[1];

async function registerCandidate(name, phone) {
  await api("POST", "/auth/otp", null, { phone });
  await sleep(300);
  const payload = { fullName: name, email: `${name.split(" ")[0].toLowerCase()}.${stamp}@mail.example`, phone, otp: otpFor(phone), dateOfBirth: "2003-03-03",
    password: "Candidate2026", education: [{ degree: "B.Tech IT", institution: "VIT", startYear: "2021", endYear: "2025", score: "8" }], experience: [],
    selfie: "data:image/jpeg;base64," + readFileSync(path.join(IN, "selfie.jpg")).toString("base64"), consent: true };
  const fd = new FormData();
  fd.append("payload", JSON.stringify(payload));
  fd.append("idDocument", new Blob([readFileSync(path.join(IN, "id.jpg"))], { type: "image/jpeg" }), "id.jpg");
  const r = await api("POST", "/candidates/register", null, fd);
  return r.data?.token;
}

// recruiter, job, candidates (API) -------------------------------------------------------------------
const R = { email: `hr.${stamp}@orbit.example`, password: "HireRight2026" };
await api("POST", "/auth/register/recruiter", null, { fullName: "Meera Nair", organisation: `Orbit Labs ${stamp}`, email: R.email, phone: "9876543210", companySize: "51-200", password: R.password });
execFileSync(process.env.PYTHON ?? "python3", [path.join(ROOT, "backend/manage.py"), "approve-org", R.email], { stdio: "pipe", env: process.env });
const rtoken = (await api("POST", "/auth/login", null, { role: "recruiter", email: R.email, password: R.password })).data.token;
const job = (await api("POST", "/recruiter/jobs", rtoken, { title: "Data Analyst", department: "Analytics", location: "Pune", employmentType: "full_time", workMode: "onsite",
  experienceMin: 0, experienceMax: 2, salaryMin: null, salaryMax: null, skills: ["Python", "SQL"], description: "Analyse product data with SQL and Python and present findings.",
  requirements: "", assessments: [], deadline: null, status: "open" })).data;
const ctoken = await registerCandidate("Divya Raman", `96${stamp}11`.slice(0, 10));
const ctoken2 = await registerCandidate("Karthik Suresh", `95${stamp}22`.slice(0, 10));
const app1 = (await api("POST", `/jobs/${job.id}/apply`, ctoken)).data;
const app2 = (await api("POST", `/jobs/${job.id}/apply`, ctoken2)).data;
check("recruiter, job, two candidates and applications created", !!(job?.id && ctoken && ctoken2 && app1?.id && app2?.id));

const browser = await chromium.launch({ args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream", `--use-file-for-fake-video-capture=${path.join(IN, "face.y4m")}`] });
const pageErrors = [];
async function pageFor(token, opts = {}) {
  const ctx = await (opts.browser ?? browser).newContext({ viewport: { width: 1366, height: 900 }, permissions: opts.noCamera ? [] : ["camera", "microphone"] });
  await ctx.addInitScript((t) => localStorage.setItem("tt.session", t), token);
  const p = await ctx.newPage();
  p.on("pageerror", (e) => pageErrors.push(e.message));
  return p;
}
const seesOn = (p, text, ms = 15000) => p.waitForFunction((t) => document.querySelector("main")?.textContent.includes(t), text, { timeout: ms }).then(() => true, () => false);

try {
  // 1. recruiter builds the assessment in the UI -------------------------------------------------------
  const rp = await pageFor(rtoken);
  await rp.goto(`${BASE}/recruiter/jobs`, { waitUntil: "networkidle" });
  await rp.click(`a[href='/recruiter/jobs/${job.id}/assessment']`);
  await rp.waitForURL("**/assessment");
  await rp.fill("#count", "4");
  await rp.click("button:has-text('Draft from question bank')");
  check("questions drafted from the question bank (unapproved)", await seesOn(rp, "Needs your review"));
  check("publish blocked until every question is approved", await rp.locator("button:has-text('Publish assessment')").isDisabled());
  await rp.click("button:has-text('Write my own question')");
  await rp.fill("#q-prompt", "Which SQL keyword removes duplicate rows from a result?");
  await rp.fill("#q-opt-a", "UNIQUE ROWS"); await rp.fill("#q-opt-b", "DISTINCT"); await rp.fill("#q-opt-c", "GROUP"); await rp.fill("#q-opt-d", "FILTER");
  await rp.check("input[aria-label='Option B is correct']");
  await rp.fill("#q-skill", "SQL");
  await rp.click("button:has-text('Save question')");
  check("recruiter-written question added", await seesOn(rp, "Written by recruiter"));
  for (let i = 0; i < 10 && (await rp.locator("button:has-text('Approve question & answer')").count()); i++) {
    await rp.locator("button:has-text('Approve question & answer')").first().click();
    await sleep(400);
  }
  check("all questions approved", (await rp.locator("text=Needs your review").count()) === 0);
  await rp.screenshot({ path: `${OUT}/p4-01-builder.png`, fullPage: true });
  await rp.click("button:has-text('Publish assessment')");
  await rp.locator("[role=dialog] button:has-text('Publish')").click();
  check("assessment published and assigned to both applicants", await seesOn(rp, "2 assigned"));

  // 2. candidate takes it with the camera ----------------------------------------------------------
  const cp = await pageFor(ctoken);
  await cp.goto(`${BASE}/candidate/assessments`, { waitUntil: "networkidle" });
  check("candidate sees the assigned assessment", await seesOn(cp, "Data Analyst – skill check"));
  await cp.click("a:has-text('Start')");
  check("consent step explains camera and review signals", await seesOn(cp, "review signals"));
  await cp.screenshot({ path: `${OUT}/p4-02-consent.png`, fullPage: true });
  await cp.click("button:has-text('Allow camera and start')");
  await cp.waitForSelector("text=Question 1 of 5", { timeout: 15000 });
  const tmpl = (await api("GET", `/recruiter/jobs/${job.id}/assessment`, rtoken)).data.template;
  const key = Object.fromEntries(tmpl.questions.map((q) => [q.prompt, q.correctOptionId]));
  for (let i = 0; i < 5; i++) {
    const prompt = (await cp.textContent("legend")).trim();
    const correct = key[prompt];
    const choose = i === 0 ? ({ a: "b", b: "c", c: "d", d: "a" })[correct] : correct; // first one wrong on purpose
    await cp.check(`input[type=radio][value=${choose}]`);
    if (i === 1) {
      await cp.evaluate(() => { window.dispatchEvent(new Event("blur")); window.dispatchEvent(new Event("focus")); });
      await cp.evaluate(() => document.dispatchEvent(new ClipboardEvent("paste", { clipboardData: new DataTransfer() })));
    }
    if (i < 4) await cp.click("button:has-text('Next')");
  }
  check("identity recheck during the assessment matched", await seesOn(cp, "Matched", 20000));
  check("answers autosaved", await seesOn(cp, "All answers saved"));
  await cp.screenshot({ path: `${OUT}/p4-03-runner.png`, fullPage: true });
  await sleep(3500); // let the event batch flush
  await cp.click("button:has-text('Submit')");
  await cp.locator("[role=dialog] button:has-text('Submit answers')").click();
  check("score shown after submitting (4/5)", await seesOn(cp, "Your score") && (await cp.textContent("main")).includes("80%"));
  await cp.screenshot({ path: `${OUT}/p4-04-result.png`, fullPage: true });
  await cp.goto(`${BASE}/candidate/assessments`, { waitUntil: "networkidle" });
  check("result persisted on the candidate's list", await seesOn(cp, "4/5 (80%)"));
  check("Proof of Skill shown to the candidate", await seesOn(cp, "Proof of Skill") && await seesOn(cp, "Demonstrated in the assessment"));

  // 3. recruiter sees result, timeline and Proof of Skill ------------------------------------------
  await rp.goto(`${BASE}/recruiter/assessments`, { waitUntil: "networkidle" });
  check("recruiter list shows the score", await seesOn(rp, "4/5 (80%)"));
  await rp.click("a:has-text('Details')");
  check("timeline shows review signals with explanation", await seesOn(rp, "Test window lost focus") && await seesOn(rp, "Pasted text") && await seesOn(rp, "not proof of cheating"));
  check("timeline shows camera consent and face recheck", await seesOn(rp, "Camera allowed") && await seesOn(rp, "Identity recheck – match"));
  await rp.screenshot({ path: `${OUT}/p4-05-attempt.png`, fullPage: true });
  await rp.goto(`${BASE}/recruiter/applicants/${app1.id}`, { waitUntil: "networkidle" });
  await rp.click("[role=tab]:has-text('Assessment')");
  check("trust report shows claimed vs demonstrated skills", await seesOn(rp, "Proof of Skill") && await seesOn(rp, "Details & timeline"));
  await rp.screenshot({ path: `${OUT}/p4-06-proof-of-skill.png`, fullPage: true });

  // 4. interviews: schedule (UI), acknowledge, enter with face check -------------------------------
  await rp.goto(`${BASE}/recruiter/interviews`, { waitUntil: "networkidle" });
  for (const [app, label] of [[app1, "Divya"], [app2, "Karthik"]]) {
    await rp.click("button:has-text('Schedule interview')");
    await rp.selectOption("#applicationId", app.id);
    await rp.fill("#date", "2099-03-01"); await rp.fill("#time", "10:30");
    await rp.fill("#interviewer", "Meera Nair"); await rp.fill("#meetingLink", "https://meet.example/orbit-" + label.toLowerCase());
    await rp.locator("[role=dialog] button:has-text('Schedule')").click();
    await seesOn(rp, label);
    await sleep(500);
  }
  check("two interviews scheduled", (await rp.locator("tbody tr").count()) === 2);
  await cp.goto(`${BASE}/candidate/assessments`, { waitUntil: "networkidle" });
  await cp.click("[role=tab]:has-text('Interviews')");
  await cp.click("button:has-text('Accept')");
  check("candidate acknowledged the invitation", await seesOn(cp, "You accepted this invitation"));
  await cp.click("a:has-text('Enter')");
  await cp.waitForFunction(() => document.querySelector("video")?.videoWidth > 0, null, { timeout: 15000 });
  await sleep(1200);
  check("meeting link hidden before the identity step", (await cp.locator("text=Join the interview call").count()) === 0);
  await cp.click("button:has-text('Verify identity & enter')");
  check("entry identity check matched and meeting link revealed", await seesOn(cp, "Matched") && await seesOn(cp, "Join the interview call"));
  await cp.screenshot({ path: `${OUT}/p4-07-interview-entry.png`, fullPage: true });

  // 5. camera unavailable path (second candidate, browser without a camera) --------------------------
  const plain = await chromium.launch();
  const np = await pageFor(ctoken2, { browser: plain, noCamera: true });
  await np.goto(`${BASE}/candidate/assessments`, { waitUntil: "networkidle" });
  await np.click("[role=tab]:has-text('Interviews')");
  await np.click("a:has-text('Enter')");
  const cont = await np.waitForSelector("button:has-text('Continue without camera')", { timeout: 15000 }).then(() => true, () => false);
  check("camera denied/unavailable handled", cont);
  await np.click("button:has-text('Continue without camera')");
  check("no-camera entry marked Needs review, candidate can still join", await seesOn(np, "Needs review") && await seesOn(np, "Join the interview call"));
  // second candidate starts the assessment without a camera
  await np.goto(`${BASE}/candidate/assessments`, { waitUntil: "networkidle" });
  await np.click("a:has-text('Start')");
  await np.click("button:has-text('Allow camera and start')");
  check("assessment starts without camera when permission is unavailable", await np.waitForSelector("text=Question 1 of 5", { timeout: 15000 }).then(() => true, () => false));
  await plain.close();

  await rp.goto(`${BASE}/recruiter/interviews`, { waitUntil: "networkidle" });
  check("recruiter sees acknowledgement and identity outcomes", await seesOn(rp, "Accepted") && await seesOn(rp, "Matched") && await seesOn(rp, "Needs review"));
  await rp.screenshot({ path: `${OUT}/p4-08-recruiter-interviews.png`, fullPage: true });
  await rp.click("button:has-text('Completed')");
  check("recruiter marked an interview completed", await seesOn(rp, "Completed"));
} catch (err) {
  check("scenario ran to completion", false, err.message.split("\n")[0]);
}
check("no JavaScript errors in the page", pageErrors.length === 0, pageErrors.join(" | "));
await browser.close();
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
