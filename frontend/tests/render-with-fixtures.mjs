/**
 * Render test: intercepts /api with TEST-ONLY fixtures (never shipped in the app) to check that
 * data-filled screens render without errors. Usage: node tests/render-with-fixtures.mjs <outDir>
 */
import { mkdirSync } from "node:fs";
const pw = await import(process.env.PLAYWRIGHT_PATH ?? "playwright");
const { chromium } = pw.default ?? pw;
const out = process.argv[2] ?? "test-shots";
mkdirSync(out, { recursive: true });
const now = new Date().toISOString();
const fx = {
  "/api/recruiter/applicants/t1/report": {
    applicationId: "t1", candidate: { id: "c", fullName: "Test Candidate", headline: "Fixture headline", location: "Fixture City" }, trustScore: 82, risk: "low",
    checks: [{ key: "id", title: "Face match", detail: "Fixture detail", status: "passed", points: 10 }, { key: "edu", title: "Education", detail: "Fixture detail", status: "pending" }, { key: "dup", title: "Duplicate check", detail: "Fixture detail", status: "failed", points: -15 }],
    sections: { identity: [], education: [], employment: [], assessment: [], interview: [], risk: [] }, decisions: [],
    status: "applied", jobTitle: "Fixture Role", appliedAt: now, documents: [], history: [],
  },
  "/api/candidate/assessments/t1": { id: "t1", title: "Fixture test", durationSeconds: 600, questions: [{ id: "q1", prompt: "Fixture question?", code: "const x = 1;", difficulty: "medium", options: [{ id: "a", text: "Option A" }, { id: "b", text: "Option B" }] }, { id: "q2", prompt: "Second?", difficulty: "easy", options: [{ id: "a", text: "Yes" }, { id: "b", text: "No" }] }] },
  "/api/candidate/verification/education": { documentId: "d", previewUrl: null, downloadUrl: null, fileName: null, extracted: [{ label: "Name", value: "Fixture" }], confidence: 90, comparison: [{ field: "Name", extracted: "a", claimed: "a", match: true }, { field: "Year", extracted: "a", claimed: "b", match: false }], matchScore: 88, summary: "Fixture summary", status: "verified" },
  "/api/candidate/passport": { passportId: "TT-TEST", candidateName: "Test Candidate", issuedOn: now, validTill: now, verifyUrl: "https://example.test/v/TT-TEST", qrDataUrl: null, credentials: [{ label: "Identity", status: "Verified" }], trustScore: 82 },
  "/api/recruiter/dashboard": { organisation: "Fixture Org", totalApplicants: 3, inAssessment: 1, interviewsScheduled: 1, offersSent: 0, recentApplications: [{ applicationId: "t1", candidateId: "c", candidateName: "Test Candidate", role: "Fixture Role", trustScore: 82, status: "assessment", appliedAt: now }] },
  "/api/recruiter/reports": { scoreBands: [{ band: "0-49", count: 1 }, { band: "50-74", count: 2 }, { band: "75-100", count: 4 }], flagsByCheck: [{ check: "Identity", count: 1 }, { check: "Duplicate", count: 2 }] },
};
const browser = await chromium.launch({ args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] });
const page = await (await browser.newContext({ viewport: { width: 1366, height: 900 }, permissions: ["camera", "microphone"] })).newPage();
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.addInitScript(() => localStorage.setItem("tt.session", "fixture-token"));
await page.route("**/api/**", (route) => {
  const p = new URL(route.request().url()).pathname;
  if (p === "/api/auth/me") {
    const role = page.url().includes("/recruiter") ? "recruiter" : "candidate";
    return route.fulfill({ json: { id: "u", role, fullName: "Fixture User", email: "fixture@example.test", organisation: role === "recruiter" ? "Fixture Org" : null, organisationStatus: role === "recruiter" ? "approved" : null } });
  }
  return fx[p] ? route.fulfill({ json: fx[p] }) : route.fulfill({ status: 503, json: { code: "backend_unavailable" } });
});
const pages = { "/recruiter/applicants/t1": "report", "/candidate/assessments/t1": "runner", "/candidate/verification/education": "education", "/candidate/passport": "passport", "/recruiter": "rdash", "/recruiter/reports": "reports" };
for (const [url, name] of Object.entries(pages)) {
  await page.goto("" + (process.env.BASE ?? "http://127.0.0.1:5173") + "" + url, { waitUntil: "networkidle" });
  await page.waitForTimeout(500);
  await page.screenshot({ path: `${out}/fx-${name}.png` });
}
// review action: reason required
await page.goto("" + (process.env.BASE ?? "http://127.0.0.1:5173") + "/recruiter/applicants/t1", { waitUntil: "networkidle" });
await page.getByRole("button", { name: "Approve" }).click();
await page.getByRole("button", { name: "Confirm" }).click();
const reasonErr = await page.locator("#reason-error").textContent().catch(() => null);
if (!reasonErr) errors.push("review modal: missing reason error");
await page.fill("#reason", "Fixture reason long enough");
await page.getByRole("button", { name: "Confirm" }).click();
await page.waitForTimeout(300);
if (!(await page.getByText("Decision not saved").count())) errors.push("review modal: unsaved decision not reported");
await page.screenshot({ path: `${out}/fx-review-modal.png` });
console.log(errors.length ? "FAIL\n" + errors.join("\n") : "PASS: fixture screens rendered, review action validates and reports not-saved");
await browser.close();
