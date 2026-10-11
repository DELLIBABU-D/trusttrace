import { useState } from "react";
import {
  LuArrowRight, LuBadgeCheck, LuBrainCircuit, LuBriefcase, LuCircleCheck, LuCopy, LuFileSearch, LuFingerprint, LuGraduationCap, LuMenu, LuNetwork,
  LuScanFace, LuShieldCheck, LuX, LuQrCode, LuLock, LuUserCheck, LuClipboardCheck, LuVideo,
} from "react-icons/lu";
import { Logo } from "../../components/Logo";
import { ButtonLink, cx } from "../../components/ui";
import { BASE_TRUST_SCORE } from "../../config";
import { Link } from "../../lib/router";

const NAV = [
  { label: "About", to: "/#about" },
  { label: "Features", to: "/#features" },
  { label: "For Recruiters", to: "/#recruiters" },
  { label: "For Candidates", to: "/#candidates" },
];

export function PublicNav() {
  const [open, setOpen] = useState(false);
  return (
    <header className="sticky top-0 z-30 border-b border-line/70 bg-white/90 backdrop-blur">
      <div className="mx-auto flex h-16 max-w-[1200px] items-center gap-6 px-4 sm:px-6">
        <Logo />
        <nav aria-label="Main" className="ml-auto hidden items-center gap-7 md:flex">
          {NAV.map((n) => (
            <Link key={n.to} to={n.to} className="text-[13.5px] font-medium text-ink-2 hover:text-brand-700">
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="ml-auto flex items-center gap-2 md:ml-4">
          <ButtonLink to="/login" variant="secondary" size="sm" className="hidden sm:inline-flex">Login</ButtonLink>
          <ButtonLink to="/register" size="sm">Get Started</ButtonLink>
          <button className="rounded-lg p-2 text-ink-2 md:hidden" onClick={() => setOpen((o) => !o)} aria-label={open ? "Close menu" : "Open menu"} aria-expanded={open}>
            {open ? <LuX className="size-5" aria-hidden /> : <LuMenu className="size-5" aria-hidden />}
          </button>
        </div>
      </div>
      {open && (
        <nav aria-label="Mobile" className="border-t border-line px-4 py-3 md:hidden">
          {[...NAV, { label: "Login", to: "/login" }].map((n) => (
            <Link key={n.to} to={n.to} onClick={() => setOpen(false)} className="block rounded-lg px-2 py-2.5 text-sm font-medium text-ink-2 hover:bg-surface">
              {n.label}
            </Link>
          ))}
        </nav>
      )}
    </header>
  );
}

const CHECKS = ["Identity Verified", "Education Checked", "Skills Validated", "Fraud Detection", "Trust Score"];

function HeroVisual() {
  return (
    <div className="relative mx-auto aspect-[5/4] w-full max-w-[520px]">
      <div className="absolute inset-[6%] rounded-full bg-gradient-to-br from-brand-100 via-brand-50 to-white" />
      <div className="absolute top-[14%] left-[8%] w-[58%] rounded-2xl border border-line bg-white p-5 shadow-(--shadow-pop)">
        <div className="flex items-center gap-3">
          <div className="relative grid size-14 place-items-center rounded-xl bg-brand-50">
            <LuScanFace className="size-8 text-brand-600" aria-hidden />
            {["top-0 left-0 border-t-2 border-l-2", "top-0 right-0 border-t-2 border-r-2", "bottom-0 left-0 border-b-2 border-l-2", "bottom-0 right-0 border-b-2 border-r-2"].map((c) => (
              <span key={c} className={cx("absolute size-3 rounded-[2px] border-brand-500", c)} aria-hidden />
            ))}
          </div>
          <div>
            <p className="text-[13px] font-semibold text-ink">Live identity match</p>
            <p className="text-xs text-ink-3">Same face, every stage</p>
          </div>
        </div>
        <div className="mt-4 space-y-2">
          {["Application", "Assessment", "Interview", "Joining day"].map((s, i) => (
            <div key={s} className="flex items-center gap-2 text-[12.5px] text-ink-2">
              <span className={cx("size-2 rounded-full", i < 3 ? "bg-brand-500" : "bg-line-strong")} />
              {s}
            </div>
          ))}
        </div>
      </div>
      <div className="absolute right-[4%] bottom-[10%] w-[46%] rounded-2xl border border-line bg-white p-4 shadow-(--shadow-pop)">
        <ul className="space-y-2.5">
          {CHECKS.map((c) => (
            <li key={c} className="flex items-center gap-2 text-[12.5px] font-medium text-ink">
              <LuCircleCheck className="size-4 shrink-0 text-brand-500" aria-hidden />
              {c}
            </li>
          ))}
        </ul>
      </div>
      <div className="absolute top-[6%] right-[10%] grid size-14 place-items-center rounded-2xl bg-navy-900 shadow-(--shadow-pop)">
        <LuShieldCheck className="size-7 text-brand-400" aria-hidden />
      </div>
    </div>
  );
}

const FEATURES = [
  { icon: LuScanFace, title: "Identity continuity", body: "The face verified at registration is re-checked during the test, the interview and on joining day." },
  { icon: LuGraduationCap, title: "Education verification", body: "Marksheets and degree certificates are read and compared with what the candidate entered." },
  { icon: LuBriefcase, title: "Employment verification", body: "Experience letters are matched against the claimed company, designation and dates." },
  { icon: LuCopy, title: "Duplicate detection", body: "Profiles sharing a face, phone, device or near-identical resume are linked for review." },
  { icon: LuFileSearch, title: "Resume consistency", body: "Overlapping jobs, impossible experience and date conflicts are flagged with the evidence." },
  { icon: LuClipboardCheck, title: "Assessment integrity", body: "Webcam checks, tab switches and copy-paste are recorded during skill tests." },
  { icon: LuVideo, title: "Interview identity", body: "The person on camera is compared with the verified face throughout the interview." },
  { icon: LuBrainCircuit, title: "Explainable trust score", body: `Every applicant starts at ${BASE_TRUST_SCORE}; each check adds or removes points with a written reason.` },
];

const STAGES = ["Apply", "Identity", "Documents", "Assessment", "Interview", "Review", "Onboarding"];

export function Landing() {
  return (
    <div className="min-h-screen bg-white">
      <PublicNav />

      <section className="relative overflow-hidden bg-gradient-to-b from-[#f2f8f7] to-white">
        <div className="mx-auto grid max-w-[1200px] items-center gap-10 px-4 pt-14 pb-16 sm:px-6 lg:grid-cols-[1.05fr_1fr] lg:pt-20 lg:pb-24">
          <div>
            <h1 className="text-[38px] leading-[1.08] font-bold tracking-tight text-ink sm:text-5xl lg:text-[54px]">
              Build a Safer, More Trustworthy <span className="text-brand-600">Hiring Ecosystem</span>
            </h1>
            <p className="mt-5 max-w-lg text-[17px] leading-relaxed text-ink-2">AI-powered candidate verification, skill validation and fraud detection for trusted hiring.</p>
            <div className="mt-8 flex flex-wrap gap-3">
              <ButtonLink to="/register" size="lg" className="min-w-40">I'm a Candidate</ButtonLink>
              <ButtonLink to="/recruiter/register" size="lg" variant="outline" className="min-w-40">I'm a Recruiter</ButtonLink>
            </div>
          </div>
          <HeroVisual />
        </div>

        <div className="mx-auto max-w-[1200px] px-4 pb-14 sm:px-6">
          <dl className="grid grid-cols-2 gap-6 border-t border-line pt-8 md:grid-cols-4">
            {[
              [`${BASE_TRUST_SCORE}+`, "Base Trust Score"],
              ["8", "Verification Modules"],
              ["100%", "Explainable Results"],
              ["End-to-End", "Hiring Security"],
            ].map(([v, l]) => (
              <div key={l}>
                <dt className="sr-only">{l}</dt>
                <dd className="text-3xl font-bold tracking-tight text-ink">{v}</dd>
                <dd className="mt-1 text-[13px] text-ink-3">{l}</dd>
              </div>
            ))}
          </dl>
        </div>
      </section>

      <section id="features" className="scroll-mt-20 bg-surface py-20">
        <div className="mx-auto max-w-[1200px] px-4 sm:px-6">
          <h2 className="text-3xl font-bold tracking-tight text-ink">Eight checks, one connected trail</h2>
          <p className="mt-2 max-w-2xl text-ink-2">Each module covers one way hiring fraud happens. Together they follow the same person from application to the first day at work.</p>
          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {FEATURES.map((f) => (
              <article key={f.title} className="rounded-xl border border-line bg-white p-5">
                <span className="grid size-10 place-items-center rounded-lg bg-brand-50 text-brand-600">
                  <f.icon className="size-5" aria-hidden />
                </span>
                <h3 className="mt-4 text-[15px] font-semibold text-ink">{f.title}</h3>
                <p className="mt-1.5 text-[13.5px] leading-relaxed text-ink-2">{f.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section id="about" className="scroll-mt-20 py-20">
        <div className="mx-auto max-w-[1200px] px-4 sm:px-6">
          <h2 className="text-3xl font-bold tracking-tight text-ink">Verified at every stage, not just once</h2>
          <p className="mt-2 max-w-2xl text-ink-2">Most tools check a candidate at the start and trust them after that. TrustTrace keeps checking, records each result in a tamper-evident trail, and leaves the final decision to a person.</p>
          <ol className="mt-10 grid gap-3 sm:grid-cols-4 lg:grid-cols-7">
            {STAGES.map((s, i) => (
              <li key={s} className="rounded-xl border border-line bg-white px-4 py-4">
                <span className="text-xs font-semibold text-brand-600">Step {i + 1}</span>
                <p className="mt-1 text-[14px] font-semibold text-ink">{s}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="bg-navy-900 py-20 text-white">
        <div className="mx-auto grid max-w-[1200px] gap-6 px-4 sm:px-6 md:grid-cols-2">
          <article id="recruiters" className="scroll-mt-24 rounded-2xl bg-navy-800 p-8">
            <LuUserCheck className="size-8 text-brand-400" aria-hidden />
            <h2 className="mt-4 text-2xl font-semibold">For recruiters</h2>
            <ul className="mt-4 space-y-2.5 text-[14px] text-navy-200">
              {["One dashboard for every applicant and every check", "Trust reports that explain each flag with its evidence", "Review queue: approve, reject or ask for re-verification", "Nothing is rejected automatically"].map((t) => (
                <li key={t} className="flex gap-2"><LuCircleCheck className="mt-0.5 size-4 shrink-0 text-brand-400" aria-hidden />{t}</li>
              ))}
            </ul>
            <ButtonLink to="/recruiter/register" className="mt-6" icon={LuArrowRight}>Create a recruiter account</ButtonLink>
          </article>
          <article id="candidates" className="scroll-mt-24 rounded-2xl bg-navy-800 p-8">
            <LuBadgeCheck className="size-8 text-brand-400" aria-hidden />
            <h2 className="mt-4 text-2xl font-semibold">For candidates</h2>
            <ul className="mt-4 space-y-2.5 text-[14px] text-navy-200">
              {["Verify once and carry a signed TrustTrace passport", "See exactly what was checked and why", "Using AI to polish your resume is never held against you", "Consent first; photos are not stored"].map((t) => (
                <li key={t} className="flex gap-2"><LuCircleCheck className="mt-0.5 size-4 shrink-0 text-brand-400" aria-hidden />{t}</li>
              ))}
            </ul>
            <ButtonLink to="/register" className="mt-6" icon={LuArrowRight}>Register as a candidate</ButtonLink>
          </article>
        </div>
      </section>

      <footer className="border-t border-line py-10">
        <div className="mx-auto flex max-w-[1200px] flex-wrap items-center justify-between gap-4 px-4 text-[13px] text-ink-3 sm:px-6">
          <Logo />
          <div className="flex flex-wrap gap-5">
            <span className="inline-flex items-center gap-1.5"><LuLock className="size-3.5" aria-hidden /> Consent-first data handling</span>
            <span className="inline-flex items-center gap-1.5"><LuFingerprint className="size-3.5" aria-hidden /> No photos stored</span>
            <span className="inline-flex items-center gap-1.5"><LuNetwork className="size-3.5" aria-hidden /> Fraud-ring detection</span>
            <span className="inline-flex items-center gap-1.5"><LuQrCode className="size-3.5" aria-hidden /> Verifiable passport</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
