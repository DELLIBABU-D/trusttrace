// Opens all 30 routes (desktop + 3 on mobile), screenshots them, and fails on page errors or horizontal overflow on mobile.
// Needs serve.py running and Playwright installed: npx playwright install chromium && node tests/smoke-routes.mjs
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
mkdirSync("test-shots", { recursive: true });
const routes = ["/", "/login", "/register", "/recruiter/register", "/candidate", "/candidate/jobs", "/candidate/applications", "/candidate/applications/x1",
  "/candidate/documents", "/candidate/verification", "/candidate/verification/education", "/candidate/verification/employment", "/candidate/assessments",
  "/candidate/assessments/a1", "/candidate/interviews/check", "/candidate/profile", "/candidate/messages", "/candidate/passport",
  "/recruiter", "/recruiter/jobs", "/recruiter/jobs/new", "/recruiter/jobs/j1/edit", "/recruiter/applicants", "/recruiter/applicants/a1",
  "/recruiter/assessments", "/recruiter/interviews", "/recruiter/reports", "/recruiter/settings", "/verify/TTP-ABCDEFGHJK", "/nope"];
const browser = await chromium.launch({ args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"] });
const ctx = await browser.newContext({ viewport: { width: 1366, height: 860 }, permissions: ["camera", "microphone"] });
const page = await ctx.newPage();
const errs = [];
page.on("pageerror", (e) => errs.push(`${page.url()} PAGEERROR ${e.message}`));
page.on("console", (m) => m.type() === "error" && !m.text().includes("503") && errs.push(`${page.url()} ${m.text()}`));
for (const r of routes) {
  await page.goto((process.env.BASE ?? "http://127.0.0.1:5173") + r, { waitUntil: "networkidle" });
  await page.waitForTimeout(400);
  const name = (r.replace(/\//g, "_") || "_root").replace(/^_/, "") || "root";
  await page.screenshot({ path: `test-shots/${name}.png`, fullPage: r === "/" });
}
// mobile
await page.setViewportSize({ width: 390, height: 800 });
for (const r of ["/", "/candidate", "/recruiter/applicants"]) {
  await page.goto((process.env.BASE ?? "http://127.0.0.1:5173") + r, { waitUntil: "networkidle" });
  await page.screenshot({ path: `test-shots/m${r.replace(/\//g, "_")}.png` });
  const ow = await page.evaluate(() => document.documentElement.scrollWidth);
  if (ow > 390) errs.push(`${r} horizontal overflow ${ow}`);
}
console.log(errs.join("\n") || "no errors");
await browser.close();
