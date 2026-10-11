/**
 * Phase 2 end-to-end test through the real UI and the real backend (no mocks, no fixtures).
 *
 *   Terminal 1:  python serve.py   (start with an EMPTY data folder, e.g. TT_DATA_DIR=/tmp/tt-e2e, and log to a file)
 *   Terminal 2:  BASE=http://localhost:5173 SERVER_LOG=server.log node tests/e2e-phase2.mjs [screenshotDir]
 *
 * The OTP is read from the server log because no SMS provider is configured (development delivery).
 * Organisation approval is done with the admin CLI: python backend/manage.py approve-org <email>.
 */
import { execFileSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import path from "node:path";

const pw = await import(process.env.PLAYWRIGHT_PATH ?? "playwright");
const { chromium } = pw.default ?? pw;
const BASE = process.env.BASE ?? "http://localhost:5173";
const LOG = process.env.SERVER_LOG ?? "server.log";
const OUT = process.argv[2] ?? "test-shots";
const ROOT = path.resolve(path.dirname(new URL(import.meta.url).pathname), "../..");
mkdirSync(OUT, { recursive: true });
const stamp = Date.now().toString().slice(-6);
const R = { name: "Kavya Iyer", org: `Nimbus Analytics ${stamp}`, email: `kavya.${stamp}@nimbus.example`, phone: "9876543210", password: "HireRight2026" };
const C = { name: "Rahul Menon", email: `rahul.${stamp}@mail.example`, phone: `98${stamp}12`.slice(0, 10), dob: "2004-08-21", password: "Candidate2026" };
const JOB = "Junior Data Engineer";

const results = [];
const check = (name, ok, extra = "") => { results.push({ name, ok, extra }); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? `  (${extra})` : ""}`); };

const browser = await chromium.launch({ args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] });
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 }, permissions: ["camera", "microphone"] });
const page = await ctx.newPage();
const pageErrors = [];
page.on("pageerror", (e) => pageErrors.push(e.message));
const shot = (n) => page.screenshot({ path: `${OUT}/e2e-${n}.png`, fullPage: true });
const go = (p) => page.goto(BASE + p, { waitUntil: "networkidle" });
const fill = (sel, v) => page.fill(sel, v);
/** Wait until text appears inside <main> (SPA navigation does not trigger page loads). */
const sees = (text, ms = 8000) => page.waitForFunction((t) => document.querySelector("main")?.textContent.includes(t), text, { timeout: ms }).then(() => true, () => false);

// fixture files written to disk for the file pickers
const pdf = path.join(OUT, "resume.pdf");
writeFileSync(pdf, "%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n");
const idPng = path.join(OUT, "id.png");
writeFileSync(idPng, Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), Buffer.alloc(64)]));
const fakePdf = path.join(OUT, "virus.pdf");
writeFileSync(fakePdf, "MZ this is not a pdf");

try {
  // 0. protected pages need sign-in
  await go("/candidate");
  check("signed-out user is sent to login", page.url().includes("/login"), page.url());

  // 1. recruiter registers with manually entered details
  await go("/recruiter/register");
  await fill("#fullName", R.name); await fill("#organisation", R.org); await fill("#email", R.email); await fill("#phone", R.phone);
  await page.selectOption("#companySize", "51-200"); await fill("#password", R.password); await fill("#confirm", R.password);
  await page.check("#terms");
  await page.click("button[type=submit]");
  await page.waitForURL("**/recruiter", { timeout: 10000 });
  await page.waitForLoadState("networkidle");
  check("recruiter registered and signed in", await sees(R.org));
  check("pending-approval banner shown", (await page.textContent("body")).includes("awaiting approval"));
  await shot("01-recruiter-pending");

  // admin approves the organisation (CLI)
  execFileSync(process.env.PYTHON ?? "python3", [path.join(ROOT, "backend/manage.py"), "approve-org", R.email], { stdio: "pipe", env: process.env });
  await page.reload({ waitUntil: "networkidle" });
  check("approval picked up after reload", !(await page.textContent("body")).includes("awaiting approval"));

  // 2. create a job
  await go("/recruiter/jobs/new");
  await fill("#title", JOB); await fill("#department", "Data"); await fill("#location", "Bengaluru");
  await page.selectOption("#workMode", "hybrid");
  await fill("#experienceMin", "0"); await fill("#experienceMax", "2"); await fill("#salaryMin", "500000"); await fill("#salaryMax", "800000");
  for (const s of ["Python", "SQL", "Airflow"]) { await fill("#skill", s); await page.keyboard.press("Enter"); }
  await fill("#description", "Build and maintain batch data pipelines, write SQL transformations and monitor data quality.");
  await fill("#requirements", "B.E./B.Tech in CS or related field");
  await page.click("button[type=submit]");
  await page.waitForURL("**/recruiter/jobs", { timeout: 10000 });
  await page.waitForLoadState("networkidle");
  check("job created and listed", await sees(JOB));
  await shot("02-recruiter-jobs");

  // sign out
  await page.click("text=Sign out");
  await page.waitForURL("**/login**");

  // 3. candidate registers (OTP from server log, webcam selfie, ID upload, consent)
  await go("/register");
  await fill("#fullName", C.name); await fill("#email", C.email); await fill("#phone", C.phone);
  await fill("#dateOfBirth", C.dob); await fill("#password", C.password);
  await page.click("text=Verify OTP");
  await page.waitForSelector("#otp", { timeout: 10000 });
  await page.waitForTimeout(500);
  const otp = [...readFileSync(LOG, "utf8").matchAll(new RegExp(`mobile ending ${C.phone.slice(-4)}: (\\d{6})`, "g"))].pop()?.[1];
  check("OTP delivered to server console", !!otp);
  await fill("#otp", otp ?? "");
  await page.waitForFunction(() => document.querySelector("video")?.videoWidth > 0, null, { timeout: 10000 });
  await page.click("button:has-text('Capture')");
  await page.click("button:has-text('Next')");
  await fill("#edu-degree-0", "B.Tech Information Technology"); await fill("#edu-inst-0", "VIT Vellore");
  await page.fill("[id^=edu-start]", "2022").catch(() => undefined);
  const yearInputs = await page.$$("input[id^='edu-']");
  for (const el of yearInputs) {
    const id = await el.getAttribute("id");
    if (/start/i.test(id)) await el.fill("2022");
    else if (/end/i.test(id)) await el.fill("2026");
    else if (/score/i.test(id)) await el.fill("8.7");
  }
  await page.click("button:has-text('Next')");
  await page.setInputFiles("input[type=file]", idPng);
  const boxes = await page.$$("input[type=checkbox]");
  for (const b of boxes) await b.check();
  await page.click("button:has-text('Next')");
  await shot("03-candidate-review");
  await page.click("button:has-text('Submit registration')");
  await page.waitForURL("**/candidate", { timeout: 15000 });
  await page.waitForLoadState("networkidle");
  check("candidate registered and signed in", await sees("Rahul"));

  // 4. candidate sees the real job and applies
  await go("/candidate/jobs");
  check("candidate sees the recruiter's job", await sees(JOB));
  await page.click(`article:has-text("${JOB}") button:has-text("Apply")`);
  await page.waitForURL("**/candidate/applications/**", { timeout: 10000 });
  await page.waitForLoadState("networkidle");
  check("application created", await sees(JOB));
  await go("/candidate/jobs");
  check("job now shows Applied (no second Apply button)", (await page.locator(`article:has-text("${JOB}") button:has-text("Apply")`).count()) === 0);

  // 5. upload a document, then try an invalid one
  await go("/candidate/documents");
  await page.setInputFiles("section[aria-labelledby=slot-resume] input[type=file]", pdf);
  await page.click("button:has-text('Upload Documents')");
  check("resume uploaded (success message)", await sees("Uploaded 1 file"));
  check("resume listed as uploaded and not verified", await page.waitForFunction(() => /resume\.pdf[^]*?uploaded[^]*?not verified/.test(document.querySelector("#slot-resume")?.parentElement?.textContent ?? ""), null, { timeout: 8000 }).then(() => true, () => false));
  await page.setInputFiles("section[aria-labelledby=slot-marksheet] input[type=file]", fakePdf).catch(() => undefined);
  // the browser check accepts .pdf by type, so the server must reject the fake content
  await page.click("button:has-text('Upload Documents')");
  await page.waitForTimeout(800);
  const body = await page.textContent("main");
  check("fake PDF rejected by the server", body.includes("Documents not uploaded") && body.includes("isn't a valid"), body.match(/virus\.pdf[^.]*\./)?.[0]);
  await shot("04-documents");

  // 6. refresh, sign out, sign back in: data persists
  await page.reload({ waitUntil: "networkidle" });
  check("still signed in after refresh", (await sees("resume.pdf")) && page.url().includes("/candidate/documents"));
  await page.click("text=Sign out");
  await page.waitForURL("**/login**");
  await fill("#email", C.email); await fill("#password", C.password);
  await page.click("button[type=submit]");
  await page.waitForURL("**/candidate", { timeout: 10000 });
  await page.waitForLoadState("networkidle");
  await sees("Applied Jobs");
  await page.waitForTimeout(500);
  const appliedCount = await page.locator("text=Applied Jobs").locator("xpath=../..").textContent();
  check("dashboard counter persisted after re-login", /^\s*1\s*Applied Jobs/.test(appliedCount), appliedCount.trim());
  await shot("05-candidate-dashboard");
  await go("/candidate/applications");
  check("application persisted after re-login", await sees(JOB));

  // 7. unauthorised access
  await go("/recruiter");
  check("candidate cannot open recruiter area", page.url().endsWith("/candidate"), page.url());
  const token = await page.evaluate(() => localStorage.getItem("tt.session"));
  const forbidden = await page.evaluate(async (t) => (await fetch("/api/recruiter/applicants", { headers: { Authorization: `Bearer ${t}` } })).status, token);
  check("candidate token rejected by recruiter API (403)", forbidden === 403, String(forbidden));
  const anon = await page.evaluate(async () => (await fetch("/api/candidate/profile")).status);
  check("anonymous API call rejected (401)", anon === 401, String(anon));

  // 8. recruiter reviews the application and requests clarification
  await page.click("text=Sign out");
  await page.waitForURL("**/login**");
  await page.click("[role=tab]:has-text('Recruiter')");
  await fill("#email", R.email); await fill("#password", R.password);
  await page.click("button[type=submit]");
  await page.waitForURL("**/recruiter", { timeout: 10000 });
  await page.waitForLoadState("networkidle");
  check("recruiter dashboard shows the applicant", await sees(C.name));
  await shot("06-recruiter-dashboard");
  await page.click("text=View report");
  await page.waitForLoadState("networkidle");
  check("trust report shows uploaded resume", await sees("resume.pdf"));
  await page.click("button:has-text('Request clarification')");
  await fill("#note", "Please upload your semester 6 marksheet.");
  await page.click("button:has-text('Send request')");
  await page.waitForTimeout(800);
  check("application moved to clarification", await sees("Clarification needed"));
  await shot("07-trust-report");

  // 9. candidate receives the message
  await page.click("text=Sign out");
  await page.waitForURL("**/login**");
  await fill("#email", C.email); await fill("#password", C.password);
  await page.click("button[type=submit]");
  await page.waitForURL("**/candidate");
  await go("/candidate/messages");
  check("candidate received the clarification message", await sees("Clarification requested"));
  await shot("08-candidate-messages");
} catch (err) {
  check("scenario ran to completion", false, err.message.split("\n")[0]);
  await shot("error");
}
check("no JavaScript errors in the page", pageErrors.length === 0, pageErrors.join(" | "));
await browser.close();
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
