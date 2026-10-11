/**
 * Phase 5 end-to-end test: explainable trust score, pattern alerts, relationship graph and recruiter review actions,
 * through the real UI and server (background verification queue). Synthetic data only.
 *
 *   INPUT dir must contain selfie.jpg, id.jpg and docs/{resume.pdf, marksheet.pdf, marksheet_wrong_year.pdf}
 *   BASE=http://localhost:5173 SERVER_LOG=server.log INPUT=DIR node tests/e2e-phase5.mjs [screenshotDir]
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

async function api(method, p, token, body, extraHeaders = {}) {
  const headers = { ...(token ? { Authorization: `Bearer ${token}` } : {}), ...extraHeaders };
  let payload;
  if (body instanceof FormData) payload = body;
  else if (body !== undefined) { payload = JSON.stringify(body); headers["Content-Type"] = "application/json"; }
  const res = await fetch(BASE + "/api" + p, { method, headers, body: payload });
  return { status: res.status, data: await res.json().catch(() => null) };
}
const otpFor = (phone) => [...readFileSync(LOG, "utf8").matchAll(new RegExp(`mobile ending ${phone.slice(-4)}: (\\d{6})`, "g"))].pop()?.[1];
const pdf = (name) => new Blob([readFileSync(path.join(IN, "docs", name))], { type: "application/pdf" });
async function waitJob(token) {
  for (let i = 0; i < 120; i++) {
    const j = await api("GET", "/candidate/verification/job", token);
    if (j.data && ["done", "failed"].includes(j.data.status)) return j.data;
    await sleep(500);
  }
  return null;
}
async function registerCandidate(name, phone, device) {
  await api("POST", "/auth/otp", null, { phone });
  await sleep(300);
  const payload = { fullName: name, email: `${name.split(" ")[0].toLowerCase()}.${stamp}.${Math.random().toString(36).slice(2, 6)}@mail.example`, phone, otp: otpFor(phone),
    dateOfBirth: "2004-05-17", password: "Candidate2026",
    education: [{ degree: "B.E. Computer Science and Engineering", institution: "Anna University", startYear: "2022", endYear: "2026", score: "8.4" }],
    experience: [], selfie: "data:image/jpeg;base64," + readFileSync(path.join(IN, "selfie.jpg")).toString("base64"), consent: true };
  const fd = new FormData();
  fd.append("payload", JSON.stringify(payload));
  fd.append("idDocument", new Blob([readFileSync(path.join(IN, "id.jpg"))], { type: "image/jpeg" }), "id.jpg");
  return (await api("POST", "/candidates/register", null, fd, { "X-TT-Device": device })).data?.token;
}

// setup through the API ------------------------------------------------------------------------------
const R = { email: `hr.${stamp}@vertex.example`, password: "HireRight2026" };
await api("POST", "/auth/register/recruiter", null, { fullName: "Anjali Rao", organisation: `Vertex Systems ${stamp}`, email: R.email, phone: "9876543210", companySize: "51-200", password: R.password });
execFileSync(process.env.PYTHON ?? "python3", [path.join(ROOT, "backend/manage.py"), "approve-org", R.email], { stdio: "pipe", env: process.env });
const rtoken = (await api("POST", "/auth/login", null, { role: "recruiter", email: R.email, password: R.password })).data.token;
const mkJob = async (title) => (await api("POST", "/recruiter/jobs", rtoken, { title, department: "Engineering", location: "Chennai", employmentType: "full_time", workMode: "hybrid",
  experienceMin: 0, experienceMax: 2, salaryMin: null, salaryMax: null, skills: ["Python", "SQL"], description: "Build and maintain data services with Python and SQL for our platform.",
  requirements: "", assessments: [], deadline: null, status: "open" })).data;
const job = await mkJob("Backend Engineer");
const extra = [];
for (let i = 0; i < 4; i++) extra.push(await mkJob(`Platform Engineer ${i + 1}`));

const device = `browser-${stamp}-${Math.random().toString(36).slice(2, 12)}`;
const phone = `93${stamp}44`.slice(0, 10);
const tA = await registerCandidate("Arun Kumar", phone, device);
const fdA = new FormData();
fdA.append("resume", pdf("resume.pdf"), "resume.pdf");
fdA.append("marksheet", pdf("marksheet_wrong_year.pdf"), "marksheet.pdf");
await api("POST", "/candidate/documents", tA, fdA);
await waitJob(tA);
const appA = (await api("POST", `/jobs/${job.id}/apply`, tA, undefined, { "X-TT-Device": device })).data;
const tB = await registerCandidate("Bala Murugan", phone, device); // same browser AND same verified number as A
const tC = await registerCandidate("Chitra Devi", `92${stamp}55`.slice(0, 10), `other-${stamp}-${Math.random().toString(36).slice(2, 12)}`);
for (const j of [job, ...extra]) await api("POST", `/jobs/${j.id}/apply`, tC); // 5 applications in seconds -> P1
await waitJob(tB);
check("setup: recruiter, 5 jobs, 3 candidates, applications", !!(appA?.id && tB && tC));

const browser = await chromium.launch();
const pageErrors = [];
const ctx = await browser.newContext({ viewport: { width: 1366, height: 900 } });
await ctx.addInitScript((t) => localStorage.setItem("tt.session", t), rtoken);
const page = await ctx.newPage();
page.on("pageerror", (e) => pageErrors.push(e.message));
const sees = (text, ms = 15000) => page.waitForFunction((t) => document.querySelector("main")?.textContent.includes(t), text, { timeout: ms }).then(() => true, () => false);
const scoreOf = async () => Number((await page.locator("[role=img][aria-label^='Trust score']").getAttribute("aria-label")).match(/(\d+) out of/)?.[1]);

try {
  // dashboard
  await page.goto(`${BASE}/recruiter`, { waitUntil: "networkidle" });
  check("dashboard: needs-attention list and live review queue", await sees("Needs your attention") && await sees("Arun Kumar") && await sees("Open pattern alerts"));
  await page.screenshot({ path: `${OUT}/p5-01-dashboard.png`, fullPage: true });

  // applicants: sort + filter
  await page.goto(`${BASE}/recruiter/applicants`, { waitUntil: "networkidle" });
  await page.selectOption("select[aria-label='Sort applicants']", "score_asc");
  await sleep(800);
  const firstScore = Number(await page.locator("tbody tr").first().locator("td").nth(2).textContent());
  const lastScore = Number(await page.locator("tbody tr").last().locator("td").nth(2).textContent());
  check("applicants sorted by trust score (low to high)", firstScore <= lastScore, `${firstScore} … ${lastScore}`);
  await page.check("text=Needs review only");
  await sleep(800);
  check("'needs review only' filter works", (await page.locator("tbody tr").count()) >= 1 && await sees("concern"));

  // trust report: explanation
  await page.goto(`${BASE}/recruiter/applicants/${appA.id}`, { waitUntil: "networkidle" });
  check("score explanation: baseline + rules", await sees("How this score was calculated") && await sees("Baseline 80"));
  check("inconsistent education shown with its rule and evidence", await sees("EDU.INCONSISTENT") && await sees("Inconsistent"));
  check("pending checks get no credit (issuer not checked)", await sees("Issuer authenticity") && await sees("Pending"));
  check("decision-support disclaimer shown", await sees("not a measure of a person's honesty"));
  const before = await scoreOf();
  await page.screenshot({ path: `${OUT}/p5-02-explanation.png`, fullPage: true });

  // resolve the education concern
  await page.locator("section[aria-label='Inconsistent'] li:has-text('Education documents') button:has-text('Review')").click();
  await page.fill("#crv-note", "Candidate showed the revaluation certificate; the 2024 date is the original exam sitting.");
  await page.click("button:has-text('Save review')");
  await page.waitForFunction((b) => {
    const m = document.querySelector("[role=img][aria-label^='Trust score']")?.getAttribute("aria-label")?.match(/(\d+) out of/);
    return m && Number(m[1]) !== b;
  }, before, { timeout: 15000 }).catch(() => undefined);
  const after = await scoreOf();
  check("resolving the concern recomputes the score (+10) and keeps the evidence", after === before + 10 && await sees("Resolved by a reviewer"), `${before} → ${after}`);

  // risk tab: graph + patterns
  await page.click("[role=tab]:has-text('Risk Analysis')");
  check("relationship graph links the shared browser and the shared verified number", await sees("Linked profiles") && await sees("Same browser") && await sees("Same verified mobile number"));
  check("linked account is anonymous (did not apply to this organisation)", await sees("Candidate account …") && !(await page.textContent("main")).includes("Bala Murugan"));
  check("graph explains it is not a confirmed fraud ring", await sees("not a confirmed fraud ring"));
  check("shared-browser pattern alert shown as a weak/medium signal", await sees("Browser shared with other candidate accounts"));
  await page.screenshot({ path: `${OUT}/p5-03-risk.png`, fullPage: true });
  await page.locator("li:has-text('Browser shared with other candidate accounts') button:has-text('Review')").click();
  await page.fill("#prv-note", "Siblings share one laptop; verified both identities separately.");
  await page.click("button:has-text('Save review')");
  check("pattern alert reviewed", await sees("Reviewed – OK"));

  // mark reviewed
  await page.click("[role=tab]:has-text('Summary')");
  await page.click("button:has-text('Mark reviewed')");
  check("report marked reviewed (tied to the score version)", await sees("This version was reviewed by Anjali Rao"));

  // a document change recomputes the report
  const docs = (await api("GET", "/candidate/documents", tA)).data;
  const ms = docs.find((d) => d.kind === "marksheet");
  const fd = new FormData();
  fd.append("file", pdf("marksheet.pdf"), "marksheet.pdf");
  await api("PUT", `/candidate/documents/${ms.id}`, tA, fd);
  await waitJob(tA);
  await page.reload({ waitUntil: "networkidle" });
  check("document update recomputed: education now consistent (EDU.CONSISTENT)", await sees("EDU.CONSISTENT"));
  check("score history recorded each change", (await page.locator("text=Score history").count()) === 1);
  await page.screenshot({ path: `${OUT}/p5-04-recomputed.png`, fullPage: true });

  // rapid applications on the third candidate
  const appsC = (await api("GET", "/recruiter/applicants?search=Chitra", rtoken)).data;
  await page.goto(`${BASE}/recruiter/applicants/${appsC[0].applicationId}`, { waitUntil: "networkidle" });
  await page.click("[role=tab]:has-text('Risk Analysis')");
  check("rapid-application pattern detected from real timestamps", await sees("Many applications in a short time") && await sees("P1.RAPID_APPLICATIONS"));

  // access control
  const other = await api("POST", "/auth/register/recruiter", null, { fullName: "Other Org", organisation: `Other ${stamp}`, email: `o.${stamp}@other.example`, phone: "9876543211", companySize: "1-50", password: "OtherPass2026" });
  check("another organisation cannot open the report or graph",
    (await api("GET", `/recruiter/applicants/${appA.id}/report`, other.data.token)).status === 404 && (await api("GET", `/recruiter/applicants/${appA.id}/graph`, other.data.token)).status === 404);
  check("candidates cannot open recruiter scoring endpoints", (await api("GET", "/recruiter/scoring/rules", tA)).status === 403);
} catch (err) {
  check("scenario ran to completion", false, err.message.split("\n")[0]);
  await page.screenshot({ path: `${OUT}/p5-error.png`, fullPage: true }).catch(() => undefined);
}
check("no JavaScript errors in the page", pageErrors.length === 0, pageErrors.join(" | "));
await browser.close();
const failed = results.filter((r) => !r.ok).length;
console.log(`\n${results.length - failed}/${results.length} checks passed`);
process.exit(failed ? 1 : 0);
