import { useEffect, useMemo, useState } from "react";
import { z } from "zod";
import {
  LuShieldCheck, LuBriefcase, LuCalendarCheck, LuCalendarClock, LuChartColumn, LuClipboardCheck, LuFileCheck, LuPencil, LuPlus, LuSearch, LuUsers, LuX,
} from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { recruiterApi } from "../../api/endpoints";
import type { ApplicantRow, Interview, InterviewInput, Job, JobInput } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { DataState, NotLoaded } from "../../components/DataState";
import { outcomeMeta } from "../../components/Verify";
import {
  ApplicationPill, Avatar, Button, ButtonLink, Card, CardHeader, EmptyState, Field, Modal, Notice, PageHeader, Pill, ScoreBadge, Spinner, StatCard, Toggle, cx, inputCls,
} from "../../components/ui";
import { useZodForm } from "../../lib/form";
import { formatDate, formatDateTime } from "../../lib/format";
import { useMutation, useQuery } from "../../lib/query";
import { Link, useNavigate, useParams } from "../../lib/router";
import { employmentLabel, workModeLabel } from "../candidate/Jobs";

/* ------------------------------------------------------------------ shared applicants table */

export function ApplicantsTable({ rows }: { rows: ApplicantRow[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[760px] text-left text-[13.5px]">
        <thead className="border-y border-line bg-surface text-xs text-ink-3">
          <tr>
            <th className="px-5 py-2.5 font-medium">Candidate</th>
            <th className="px-5 py-2.5 font-medium">Role</th>
            <th className="px-5 py-2.5 font-medium">Trust Score</th>
            <th className="px-5 py-2.5 font-medium">To review</th>
            <th className="px-5 py-2.5 font-medium">Status</th>
            <th className="px-5 py-2.5 font-medium">Applied</th>
            <th className="px-5 py-2.5 font-medium"><span className="sr-only">Actions</span></th>
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {rows.map((r) => (
            <tr key={r.applicationId} className="hover:bg-surface/60">
              <td className="px-5 py-3">
                <div className="flex items-center gap-2.5"><Avatar name={r.candidateName} src={r.photoUrl} size={30} /><span className="font-medium text-ink">{r.candidateName}</span></div>
              </td>
              <td className="px-5 py-3 text-ink-2">{r.role}</td>
              <td className="px-5 py-3"><ScoreBadge score={r.trustScore} /></td>
              <td className="px-5 py-3 text-[13px]">
                {r.reviewCount ? <span className="font-medium text-warn" title={r.concerns?.join(", ")}>{r.reviewCount} concern{r.reviewCount === 1 ? "" : "s"}</span> : <span className="text-ink-3">—</span>}
                {r.pendingCount ? <span className="block text-xs text-ink-3">{r.pendingCount} pending</span> : null}
              </td>
              <td className="px-5 py-3"><ApplicationPill status={r.status} /></td>
              <td className="px-5 py-3 whitespace-nowrap text-ink-2">{formatDate(r.appliedAt)}</td>
              <td className="px-5 py-3 text-right"><Link to={`/recruiter/applicants/${r.applicationId}`} className="font-medium text-brand-700 hover:underline">View report</Link></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ------------------------------------------------------------------ (j) dashboard */

export function RecruiterDashboard() {
  const { user } = useAuth();
  const q = useQuery("recruiter:dashboard", recruiterApi.dashboard);
  const d = q.data;
  const org = d?.organisation ?? user?.organisation;
  const v = (n: number | undefined) => n ?? 0;
  return (
    <div>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">{org ? `Welcome, ${org}!` : "Welcome!"}</h1>
          <p className="mt-1 text-[15px] text-ink-2">Here's your hiring overview.</p>
        </div>
        <ButtonLink to="/recruiter/jobs/new" icon={LuPlus}>Post a Job</ButtonLink>
      </div>
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard icon={LuUsers} tone="blue" value={v(d?.totalApplicants)} label="Total Applicants" loading={q.isLoading} />
        <StatCard icon={LuClipboardCheck} tone="amber" value={v(d?.inAssessment)} label="In Assessment" loading={q.isLoading} />
        <StatCard icon={LuCalendarCheck} tone="violet" value={v(d?.interviewsScheduled)} label="Interviews Scheduled" loading={q.isLoading} />
        <StatCard icon={LuFileCheck} tone="green" value={v(d?.offersSent)} label="Offers Sent" loading={q.isLoading} />
      </div>
      <Card className="mt-5">
        <CardHeader title="Recent Applications" action={<Link to="/recruiter/applicants" className="text-[13px] font-medium text-brand-700 hover:underline">View all</Link>} />
        <DataState query={q} isEmpty={(x) => x.recentApplications.length === 0}
          empty={{ icon: LuUsers, title: "No applications yet", body: "Post a job and share it. Applications appear here with each candidate's trust score.", action: <ButtonLink to="/recruiter/jobs/new" size="sm" icon={LuPlus}>Post a Job</ButtonLink> }}>
          {(x) => <ApplicantsTable rows={x.recentApplications} />}
        </DataState>
      </Card>
      {d && d.totalApplicants > 0 && (
        <div className="mt-5 grid gap-5 lg:grid-cols-[1.4fr_1fr]">
          <Card>
            <CardHeader title="Needs your attention" sub="Applications with inconsistent or needs-review checks, lowest score first." action={<Link to="/recruiter/applicants?attention=1" className="text-[13px] font-medium text-brand-700 hover:underline">See all</Link>} />
            {d.needsAttention?.length ? (
              <ul className="divide-y divide-line">
                {d.needsAttention.map((r) => (
                  <li key={r.applicationId} className="flex flex-wrap items-center gap-3 px-5 py-3 text-[13.5px]">
                    <ScoreBadge score={r.trustScore} />
                    <div className="min-w-0 flex-1"><p className="font-medium text-ink">{r.candidateName} <span className="font-normal text-ink-3">· {r.role}</span></p>
                      <p className="truncate text-xs text-ink-3">{r.concerns?.join(" · ")}</p></div>
                    <Link to={`/recruiter/applicants/${r.applicationId}`} className="font-medium text-brand-700 hover:underline">Review</Link>
                  </li>
                ))}
              </ul>
            ) : <EmptyState compact icon={LuShieldCheck} title="Nothing waiting for review" />}
          </Card>
          <Card>
            <CardHeader title="Review queue" sub="Live counts from saved checks and alerts." />
            <dl className="divide-y divide-line px-5 pb-2 text-[13.5px]">
              {[["Applications needing review", d.reviewQueue?.applicationsNeedingReview], ["Open duplicate alerts", d.reviewQueue?.openDuplicateAlerts],
                ["Open pattern alerts", d.reviewQueue?.openPatternAlerts], ["Pending checks (no credit yet)", d.reviewQueue?.pendingChecks]].map(([k, val]) => (
                <div key={k as string} className="flex justify-between py-2"><dt className="text-ink-2">{k}</dt><dd className="font-semibold tabular-nums">{val ?? 0}</dd></div>
              ))}
            </dl>
            <div className="border-t border-line px-5 py-3 text-[13px]">
              <p className="mb-1.5 font-medium text-ink">Verification</p>
              {d.verificationSummary && (
                <table className="w-full text-[12.5px]">
                  <thead className="text-ink-3"><tr><th className="py-1 text-left font-medium">Check</th><th className="font-medium">Verified</th><th className="font-medium">Consistent</th><th className="font-medium">Pending</th><th className="font-medium">To review</th></tr></thead>
                  <tbody>
                    {(["identity", "education", "employment"] as const).map((k) => {
                      const b = d.verificationSummary![k];
                      return (
                        <tr key={k} className="text-center tabular-nums text-ink-2">
                          <td className="py-1 text-left capitalize">{k}</td><td className="text-ok">{b.verified}</td><td>{b.consistent}</td><td>{b.pending + b.not_started}</td>
                          <td className={b.needs_review + b.inconsistent ? "font-semibold text-warn" : ""}>{b.needs_review + b.inconsistent}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              )}
              <p className="mt-2 mb-1 font-medium text-ink">Assessments</p>
              <p className="text-ink-2">{d.assessmentSummary?.submitted ?? 0} of {d.assessmentSummary?.assigned ?? 0} submitted{d.assessmentSummary?.averagePercent != null ? ` · average ${d.assessmentSummary.averagePercent}%` : ""}</p>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ jobs list */

export function RecruiterJobs() {
  const q = useQuery("recruiter:jobs", recruiterApi.jobs);
  const close = useMutation((id: string) => recruiterApi.closeJob(id), { invalidates: ["recruiter:"] });
  return (
    <div>
      <PageHeader title="Job Postings" sub="Create roles and choose which checks and assessments each one requires." actions={<ButtonLink to="/recruiter/jobs/new" icon={LuPlus}>Post a Job</ButtonLink>} />
      {close.error ? <div className="mb-4"><Notice tone="error" title="Job not closed">{errorMessage(close.error)}</Notice></div> : null}
      <Card>
        <DataState query={q} isEmpty={(l) => l.length === 0} empty={{ icon: LuBriefcase, title: "No jobs posted yet", body: "Your first posting will appear here.", action: <ButtonLink to="/recruiter/jobs/new" size="sm" icon={LuPlus}>Post a Job</ButtonLink> }}>
          {(jobs) => (
            <ul className="divide-y divide-line">
              {jobs.map((j) => (
                <li key={j.id} className="flex flex-wrap items-center gap-4 px-5 py-4">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-ink">{j.title}</p>
                    <p className="text-[13px] text-ink-3">{j.location} · {employmentLabel[j.employmentType]} · {workModeLabel[j.workMode]} · posted {formatDate(j.postedAt)}</p>
                  </div>
                  <span className="text-[13px] text-ink-2 tabular-nums">{j.applicantCount ?? 0} applicants</span>
                  <Pill tone={j.status === "open" ? "green" : j.status === "draft" ? "gray" : "red"}>{j.status[0].toUpperCase() + j.status.slice(1)}</Pill>
                  <ButtonLink to={`/recruiter/jobs/${j.id}/assessment`} size="sm" variant="secondary" icon={LuClipboardCheck}>Assessment</ButtonLink>
                  <ButtonLink to={`/recruiter/jobs/${j.id}/edit`} size="sm" variant="secondary" icon={LuPencil}>Edit</ButtonLink>
                  {j.status !== "closed" && <Button size="sm" variant="ghost" loading={close.isPending} onClick={() => void close.mutate(j.id)}>Close</Button>}
                </li>
              ))}
            </ul>
          )}
        </DataState>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ job create / edit */

const ASSESSMENT_OPTIONS = ["Aptitude", "Coding (MCQ)", "Domain knowledge", "Communication"];
const jobSchema = z
  .object({
    title: z.string().trim().min(3, "Enter a job title"),
    department: z.string().trim(),
    location: z.string().trim().min(2, "Enter a location"),
    employmentType: z.enum(["full_time", "part_time", "internship", "contract"], { errorMap: () => ({ message: "Choose a type" }) }),
    workMode: z.enum(["onsite", "remote", "hybrid"], { errorMap: () => ({ message: "Choose a work mode" }) }),
    experienceMin: z.coerce.number({ invalid_type_error: "Enter a number" }).int().min(0, "Can't be negative").max(40),
    experienceMax: z.coerce.number({ invalid_type_error: "Enter a number" }).int().min(0).max(40, "40 years at most"),
    salaryMin: z.string().regex(/^\d*$/, "Digits only"),
    salaryMax: z.string().regex(/^\d*$/, "Digits only"),
    description: z.string().trim().min(30, "Describe the role in at least 30 characters"),
    requirements: z.string().trim().max(5000, "Keep it under 5000 characters"),
    deadline: z.string().refine((d) => !d || new Date(d) > new Date(), "Pick a future date"),
    status: z.enum(["draft", "open", "closed"]),
  })
  .refine((v) => v.experienceMax >= v.experienceMin, { path: ["experienceMax"], message: "Must be at least the minimum" })
  .refine((v) => !v.salaryMin || !v.salaryMax || Number(v.salaryMax) >= Number(v.salaryMin), { path: ["salaryMax"], message: "Must be at least the minimum" });
type JobValues = z.input<typeof jobSchema>;
const jobDefaults: JobValues = { title: "", department: "", location: "", employmentType: "full_time", workMode: "onsite", experienceMin: "0", experienceMax: "2", salaryMin: "", salaryMax: "", description: "", requirements: "", deadline: "", status: "open" } as unknown as JobValues;

export function JobForm() {
  const { id } = useParams();
  const editing = !!id;
  const navigate = useNavigate();
  const existing = useQuery(`recruiter:job:${id}`, () => recruiterApi.job(id!), { enabled: editing });
  const form = useZodForm(jobSchema as unknown as z.ZodType<JobValues>, jobDefaults);
  const [skills, setSkills] = useState<string[]>([]);
  const [skillDraft, setSkillDraft] = useState("");
  const [assessments, setAssessments] = useState<string[]>([]);
  const [skillError, setSkillError] = useState("");

  useEffect(() => {
    const j = existing.data;
    if (!j) return;
    form.setValues({
      title: j.title, department: j.department ?? "", location: j.location, employmentType: j.employmentType, workMode: j.workMode,
      experienceMin: String(j.experienceMin), experienceMax: String(j.experienceMax), salaryMin: j.salaryMin ? String(j.salaryMin) : "", salaryMax: j.salaryMax ? String(j.salaryMax) : "",
      description: j.description, requirements: j.requirements ?? "", deadline: j.deadline?.slice(0, 10) ?? "", status: j.status,
    } as unknown as JobValues);
    setSkills(j.skills);
    setAssessments(j.assessments);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [existing.data]);

  const save = useMutation((body: JobInput) => (editing ? recruiterApi.updateJob(id!, body) : recruiterApi.createJob(body)), {
    invalidates: ["recruiter:"],
    onSuccess: () => navigate("/recruiter/jobs"),
  });

  function addSkill() {
    const s = skillDraft.trim();
    if (s && !skills.some((x) => x.toLowerCase() === s.toLowerCase())) setSkills([...skills, s]);
    setSkillDraft("");
    setSkillError("");
  }

  function onValid(raw: JobValues) {
    if (skills.length === 0) return setSkillError("Add at least one skill");
    const v = jobSchema.parse(raw);
    void save.mutate({
      title: v.title, department: v.department || undefined, location: v.location, employmentType: v.employmentType, workMode: v.workMode,
      experienceMin: v.experienceMin, experienceMax: v.experienceMax, salaryMin: v.salaryMin ? Number(v.salaryMin) : null, salaryMax: v.salaryMax ? Number(v.salaryMax) : null,
      skills, description: v.description, requirements: v.requirements, assessments, deadline: v.deadline || null, status: v.status,
    });
  }

  if (editing && existing.isLoading) return <Spinner />;
  if (editing && !existing.data) return <><PageHeader title="Edit job" back={{ to: "/recruiter/jobs", label: "Jobs" }} /><Card><NotLoaded error={existing.error} what="job" /></Card></>;

  return (
    <div>
      <PageHeader title={editing ? "Edit job" : "Post a Job"} back={{ to: "/recruiter/jobs", label: "Jobs" }} />
      <Card className="max-w-4xl p-5 sm:p-6">
        <form className="grid gap-4 sm:grid-cols-2" noValidate onSubmit={form.handleSubmit(onValid)}>
          <Field label="Job title" htmlFor="title" error={form.errors.title} required><input className={inputCls} {...form.register("title")} /></Field>
          <Field label="Department" htmlFor="department" error={form.errors.department}><input className={inputCls} {...form.register("department")} /></Field>
          <Field label="Location" htmlFor="location" error={form.errors.location} required><input className={inputCls} placeholder="e.g. Chennai" {...form.register("location")} /></Field>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Type" htmlFor="employmentType" error={form.errors.employmentType} required>
              <select className={inputCls} {...form.register("employmentType")}>
                {Object.entries(employmentLabel).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </Field>
            <Field label="Work mode" htmlFor="workMode" error={form.errors.workMode} required>
              <select className={inputCls} {...form.register("workMode")}>
                {Object.entries(workModeLabel).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
              </select>
            </Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Min experience (yrs)" htmlFor="experienceMin" error={form.errors.experienceMin} required><input type="number" min={0} className={inputCls} {...form.register("experienceMin")} /></Field>
            <Field label="Max experience (yrs)" htmlFor="experienceMax" error={form.errors.experienceMax} required><input type="number" min={0} className={inputCls} {...form.register("experienceMax")} /></Field>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <Field label="Min salary (₹/yr)" htmlFor="salaryMin" error={form.errors.salaryMin}><input inputMode="numeric" className={inputCls} {...form.register("salaryMin")} /></Field>
            <Field label="Max salary (₹/yr)" htmlFor="salaryMax" error={form.errors.salaryMax}><input inputMode="numeric" className={inputCls} {...form.register("salaryMax")} /></Field>
          </div>
          <div className="sm:col-span-2">
            <label htmlFor="skill" className="mb-1.5 block text-[13px] font-medium text-ink">Required skills <span className="text-bad">*</span></label>
            <div className="flex gap-2">
              <input id="skill" value={skillDraft} onChange={(e) => setSkillDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addSkill())} className={inputCls} placeholder="Type a skill and press Enter" aria-invalid={skillError ? true : undefined} />
              <Button variant="secondary" icon={LuPlus} onClick={addSkill}>Add</Button>
            </div>
            {skillError && <p className="mt-1 text-xs text-bad">{skillError}</p>}
            {skills.length > 0 && (
              <ul className="mt-2 flex flex-wrap gap-1.5">
                {skills.map((s) => (
                  <li key={s} className="inline-flex items-center gap-1 rounded-md bg-brand-50 py-0.5 pr-1 pl-2 text-xs font-medium text-brand-800">
                    {s}
                    <button type="button" onClick={() => setSkills(skills.filter((x) => x !== s))} aria-label={`Remove ${s}`} className="rounded p-0.5 hover:bg-brand-100"><LuX className="size-3" aria-hidden /></button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          <Field label="Description" htmlFor="description" error={form.errors.description} required className="sm:col-span-2">
            <textarea rows={6} className={inputCls} {...form.register("description")} />
          </Field>
          <Field label="Requirements" htmlFor="requirements" error={form.errors.requirements} hint="Qualifications, certifications or other must-haves" className="sm:col-span-2">
            <textarea rows={3} className={inputCls} {...form.register("requirements")} />
          </Field>
          <fieldset className="sm:col-span-2">
            <legend className="mb-1.5 text-[13px] font-medium text-ink">Assessments for this role</legend>
            <div className="flex flex-wrap gap-2">
              {ASSESSMENT_OPTIONS.map((a) => {
                const on = assessments.includes(a);
                return (
                  <label key={a} className={cx("flex cursor-pointer items-center gap-2 rounded-lg border px-3 py-2 text-[13px]", on ? "border-brand-500 bg-brand-50 text-brand-800" : "border-line text-ink-2")}>
                    <input type="checkbox" checked={on} onChange={() => setAssessments(on ? assessments.filter((x) => x !== a) : [...assessments, a])} className="size-4 accent-brand-600" />
                    {a}
                  </label>
                );
              })}
            </div>
          </fieldset>
          <Field label="Application deadline" htmlFor="deadline" error={form.errors.deadline}><input type="date" className={inputCls} {...form.register("deadline")} /></Field>
          <Field label="Status" htmlFor="status" error={form.errors.status}>
            <select className={inputCls} {...form.register("status")}>
              <option value="open">Open – accepting applications</option>
              <option value="draft">Draft – not visible</option>
              <option value="closed">Closed</option>
            </select>
          </Field>
          {save.error ? <div className="sm:col-span-2"><Notice tone="error" title="Job not saved">{errorMessage(save.error)}</Notice></div> : null}
          <div className="flex justify-end gap-2 sm:col-span-2">
            <ButtonLink to="/recruiter/jobs" variant="secondary">Cancel</ButtonLink>
            <Button type="submit" loading={save.isPending}>{editing ? "Save changes" : "Publish job"}</Button>
          </div>
        </form>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ applicants */

export function Applicants() {
  const [sort, setSort] = useState("applied_desc");
  const [attention, setAttention] = useState(() => new URLSearchParams(window.location.search).get("attention") === "1");
  const q = useQuery(`recruiter:applicants:${sort}:${attention}`, () => recruiterApi.applicants({ sort, attention }));
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("");
  return (
    <div>
      <PageHeader title="Applicants" sub="Everyone who applied to your jobs, with their current trust score." />
      <Card>
        <div className="flex flex-wrap gap-3 p-4">
          <div className="relative min-w-52 flex-1">
            <LuSearch className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
            <input aria-label="Search applicants" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by name or role" className={cx(inputCls, "pl-9")} />
          </div>
          <select aria-label="Filter by status" value={status} onChange={(e) => setStatus(e.target.value)} className={cx(inputCls, "w-auto")}>
            <option value="">All statuses</option>
            <option value="verification">Verification</option>
            <option value="assessment">Assessment</option>
            <option value="interview">Interview</option>
            <option value="applied">Applied</option>
            <option value="shortlisted">Shortlisted</option>
            <option value="clarification">Clarification needed</option>
            <option value="offer">Offer</option>
            <option value="rejected">Rejected</option>
          </select>
          <select aria-label="Sort applicants" value={sort} onChange={(e) => setSort(e.target.value)} className={cx(inputCls, "w-auto")}>
            <option value="applied_desc">Newest first</option>
            <option value="applied_asc">Oldest first</option>
            <option value="score_asc">Trust score: low to high</option>
            <option value="score_desc">Trust score: high to low</option>
            <option value="name">Name A–Z</option>
          </select>
          <label className="flex items-center gap-2 text-[13px] text-ink-2"><input type="checkbox" checked={attention} onChange={(e) => setAttention(e.target.checked)} className="size-4 accent-brand-600" />Needs review only</label>
        </div>
        <p className="px-4 pb-3 text-xs text-ink-3">The trust score is decision support summarising saved evidence. It never rejects anyone automatically.</p>
        <DataState query={q} isEmpty={(l) => l.length === 0} empty={{ icon: LuUsers, title: "No applicants yet", body: "When candidates apply to your jobs they appear here." }}>
          {(rows) => {
            const s = search.toLowerCase();
            const filtered = rows.filter((r) => (!s || r.candidateName.toLowerCase().includes(s) || r.role.toLowerCase().includes(s)) && (!status || r.status === status));
            return filtered.length ? <ApplicantsTable rows={filtered} /> : <EmptyState compact icon={LuSearch} title="No applicants match these filters" />;
          }}
        </DataState>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ assessments */

// RecruiterAssessments moved to ./Assessments.tsx (Phase 4).

/* ------------------------------------------------------------------ interviews + scheduling */

const interviewSchema = z.object({
  applicationId: z.string().min(1, "Choose an applicant"),
  date: z.string().min(1, "Pick a date").refine((d) => new Date(d) >= new Date(new Date().toDateString()), "Pick today or a later date"),
  time: z.string().regex(/^\d{2}:\d{2}$/, "Pick a time"),
  durationMinutes: z.coerce.number().int().min(15, "At least 15 minutes").max(180, "At most 3 hours"),
  mode: z.enum(["video", "onsite"]),
  interviewer: z.string().trim().min(2, "Enter the interviewer's name"),
  meetingLink: z.union([z.literal(""), z.string().url("Enter a full URL")]),
});
type InterviewValues = z.input<typeof interviewSchema>;

function ScheduleModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const applicants = useQuery("recruiter:applicants", recruiterApi.applicants);
  const form = useZodForm(interviewSchema as unknown as z.ZodType<InterviewValues>, { applicationId: "", date: "", time: "", durationMinutes: "45", mode: "video", interviewer: "", meetingLink: "" } as unknown as InterviewValues);
  const schedule = useMutation((b: InterviewInput) => recruiterApi.scheduleInterview(b), { invalidates: ["recruiter:"], onSuccess: () => (form.reset(), onClose()) });
  const eligible = useMemo(() => (applicants.data ?? []).filter((a) => a.status !== "rejected" && a.status !== "hired"), [applicants.data]);

  function onValid(raw: InterviewValues) {
    const v = interviewSchema.parse(raw);
    void schedule.mutate({ applicationId: v.applicationId, scheduledAt: new Date(`${v.date}T${v.time}`).toISOString(), durationMinutes: v.durationMinutes, mode: v.mode, interviewer: v.interviewer, meetingLink: v.meetingLink || null });
  }

  return (
    <Modal open={open} onClose={onClose} title="Schedule interview" footer={<>
      <Button variant="secondary" onClick={onClose}>Cancel</Button>
      <Button type="submit" form="schedule-form" loading={schedule.isPending}>Schedule</Button>
    </>}>
      <form id="schedule-form" className="grid gap-4 sm:grid-cols-2" noValidate onSubmit={form.handleSubmit(onValid)}>
        <Field label="Applicant" htmlFor="applicationId" error={form.errors.applicationId} required className="sm:col-span-2">
          <select className={inputCls} {...form.register("applicationId")}>
            <option value="">{eligible.length ? "Select an applicant" : "No applicants available"}</option>
            {eligible.map((a) => <option key={a.applicationId} value={a.applicationId}>{a.candidateName} – {a.role}</option>)}
          </select>
        </Field>
        <Field label="Date" htmlFor="date" error={form.errors.date} required><input type="date" className={inputCls} {...form.register("date")} /></Field>
        <Field label="Time" htmlFor="time" error={form.errors.time} required><input type="time" className={inputCls} {...form.register("time")} /></Field>
        <Field label="Duration (min)" htmlFor="durationMinutes" error={form.errors.durationMinutes} required><input type="number" className={inputCls} {...form.register("durationMinutes")} /></Field>
        <Field label="Mode" htmlFor="mode" error={form.errors.mode}>
          <select className={inputCls} {...form.register("mode")}><option value="video">Video (with identity check)</option><option value="onsite">On-site</option></select>
        </Field>
        <Field label="Interviewer" htmlFor="interviewer" error={form.errors.interviewer} required><input className={inputCls} {...form.register("interviewer")} /></Field>
        <Field label="Meeting link" htmlFor="meetingLink" error={form.errors.meetingLink} hint="Optional"><input type="url" className={inputCls} {...form.register("meetingLink")} /></Field>
        {schedule.error ? <div className="sm:col-span-2"><Notice tone="error" title="Interview not scheduled">{errorMessage(schedule.error)}</Notice></div> : null}
      </form>
    </Modal>
  );
}

export function RecruiterInterviews() {
  const q = useQuery("recruiter:interviews", recruiterApi.interviews);
  const [open, setOpen] = useState(false);
  const setStatus = useMutation((b: { id: string; status: "completed" | "cancelled" }) => recruiterApi.setInterviewStatus(b.id, b.status), { invalidates: ["recruiter:"] });
  const tone = (s: Interview["status"]) => (s === "scheduled" ? "blue" : s === "completed" ? "green" : "gray");
  return (
    <div>
      <PageHeader title="Interviews" sub="Candidates acknowledge invitations and pass a camera identity step before joining your meeting link. TrustTrace does not host the call." actions={<Button icon={LuCalendarClock} onClick={() => setOpen(true)}>Schedule interview</Button>} />
      <Card>
        <DataState query={q} isEmpty={(l) => l.length === 0} empty={{ icon: LuCalendarClock, title: "No interviews scheduled", body: "Schedule one for an applicant who has cleared verification." }}>
          {(list) => (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[960px] text-left text-[13.5px]">
                <thead className="border-y border-line bg-surface text-xs text-ink-3">
                  <tr><th className="px-5 py-2.5 font-medium">Candidate</th><th className="px-5 py-2.5 font-medium">Role</th><th className="px-5 py-2.5 font-medium">When</th><th className="px-5 py-2.5 font-medium">Candidate reply</th><th className="px-5 py-2.5 font-medium">Entry identity check</th><th className="px-5 py-2.5 font-medium">Status</th><th className="px-5 py-2.5" /></tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {list.map((i) => {
                    const last = i.faceChecks?.[i.faceChecks.length - 1];
                    return (
                      <tr key={i.id} className="align-top">
                        <td className="px-5 py-3 font-medium text-ink"><Link to={`/recruiter/applicants/${i.applicationId}`} className="hover:underline">{i.candidateName}</Link></td>
                        <td className="px-5 py-3 text-ink-2">{i.jobTitle}<div className="text-xs text-ink-3">with {i.interviewer}</div></td>
                        <td className="px-5 py-3 whitespace-nowrap text-ink-2">{formatDateTime(i.scheduledAt)}<div className="text-xs text-ink-3">{i.durationMinutes} min · {i.mode}</div></td>
                        <td className="px-5 py-3 text-ink-2">{i.candidateResponse === "accepted" ? <Pill tone="green">Accepted</Pill> : i.candidateResponse === "reschedule_requested" ? <><Pill tone="amber">Asked to reschedule</Pill><div className="mt-1 max-w-48 text-xs">“{i.candidateNote}”</div></> : <span className="text-ink-3">No reply yet</span>}</td>
                        <td className="px-5 py-3">{i.entryOutcome ? <><Pill tone={outcomeMeta[i.entryOutcome].tone}>{outcomeMeta[i.entryOutcome].label}</Pill><div className="mt-1 text-xs text-ink-3">{last ? `${last.decision.replace(/_/g, " ")}${last.similarity != null ? ` · ${last.similarity.toFixed(2)}` : ""}` : ""}</div></> : <span className="text-ink-3">Not entered</span>}</td>
                        <td className="px-5 py-3"><Pill tone={tone(i.status)}>{i.status[0].toUpperCase() + i.status.slice(1)}</Pill></td>
                        <td className="px-5 py-3 whitespace-nowrap text-right">{i.status === "scheduled" && <>
                          <Button size="sm" variant="secondary" loading={setStatus.isPending} onClick={() => void setStatus.mutate({ id: i.id, status: "completed" })}>Completed</Button>{" "}
                          <Button size="sm" variant="ghost" onClick={() => void setStatus.mutate({ id: i.id, status: "cancelled" })}>Cancel</Button></>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </DataState>
      </Card>
      {setStatus.error ? <div className="mt-3"><Notice tone="error">{errorMessage(setStatus.error)}</Notice></div> : null}
      <ScheduleModal open={open} onClose={() => setOpen(false)} />
    </div>
  );
}

/* ------------------------------------------------------------------ reports */

function BarChart({ data, label }: { data: { name: string; value: number }[]; label: string }) {
  const max = Math.max(1, ...data.map((d) => d.value));
  return (
    <figure aria-label={label} className="px-5 pb-5">
      <div className="flex h-48 items-end gap-3 border-b border-line">
        {data.map((d) => (
          <div key={d.name} className="flex flex-1 flex-col items-center justify-end gap-1">
            <span className="text-xs font-medium text-ink-2 tabular-nums">{d.value}</span>
            <div className="w-full max-w-12 rounded-t-md bg-brand-500" style={{ height: `${(d.value / max) * 150}px` }} />
          </div>
        ))}
      </div>
      <div className="mt-2 flex gap-3">{data.map((d) => <span key={d.name} className="flex-1 text-center text-xs text-ink-3">{d.name}</span>)}</div>
      <figcaption className="sr-only">{data.map((d) => `${d.name}: ${d.value}`).join(", ")}</figcaption>
    </figure>
  );
}

export function RecruiterReports() {
  const q = useQuery("recruiter:reports", recruiterApi.reports);
  const empty = { icon: LuChartColumn, title: "Nothing to chart yet", body: "Charts fill in once candidates complete verification." };
  return (
    <div>
      <PageHeader title="Reports" sub="How trust scores and fraud flags are distributed across your applicants." />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title="Trust score distribution" />
          <DataState query={q} isEmpty={(r) => r.scoreBands.every((b) => b.count === 0)} empty={empty}>
            {(r) => <BarChart label="Applicants by trust score band" data={r.scoreBands.map((b) => ({ name: b.band, value: b.count }))} />}
          </DataState>
        </Card>
        <Card>
          <CardHeader title="Flags by check" />
          <DataState query={q} isEmpty={(r) => r.flagsByCheck.every((b) => b.count === 0)} empty={{ ...empty, title: "No flags raised" }}>
            {(r) => <BarChart label="Flags raised per check" data={r.flagsByCheck.map((b) => ({ name: b.check, value: b.count }))} />}
          </DataState>
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ settings */

const settingsSchema = z.object({
  organisation: z.string().trim().min(2, "Enter your organisation name"),
  website: z.union([z.literal(""), z.string().url("Enter a full URL starting with https://")]),
  retentionDays: z.coerce.number({ invalid_type_error: "Enter a number" }).int().min(30, "At least 30 days").max(730, "At most 2 years"),
});
type SettingsValues = z.input<typeof settingsSchema>;

export function RecruiterSettingsPage() {
  const q = useQuery("recruiter:settings", recruiterApi.settings);
  const form = useZodForm(settingsSchema as unknown as z.ZodType<SettingsValues>, { organisation: "", website: "", retentionDays: "180" } as unknown as SettingsValues);
  const [notifyOnFlag, setNotifyOnFlag] = useState(true);
  const [digest, setDigest] = useState(false);
  const save = useMutation((b: Parameters<typeof recruiterApi.updateSettings>[0]) => recruiterApi.updateSettings(b), { invalidates: ["recruiter:settings"] });

  useEffect(() => {
    const s = q.data;
    if (!s) return;
    form.setValues({ organisation: s.organisation, website: s.website, retentionDays: String(s.retentionDays) } as unknown as SettingsValues);
    setNotifyOnFlag(s.notifyOnFlag);
    setDigest(s.notifyDailyDigest);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.data]);

  if (q.isLoading) return <Spinner />;
  return (
    <div>
      <PageHeader title="Settings" sub="Organisation details, data retention and notifications." />
      <div className="grid gap-5 lg:grid-cols-[1.3fr_1fr]">
        <Card className="p-5 sm:p-6">
          <form className="space-y-4" noValidate onSubmit={form.handleSubmit((raw) => {
            const v = settingsSchema.parse(raw);
            void save.mutate({ ...v, notifyOnFlag, notifyDailyDigest: digest });
          })}>
            <h2 className="text-[15px] font-semibold">Organisation</h2>
            <Field label="Organisation name" htmlFor="organisation" error={form.errors.organisation} required><input className={inputCls} {...form.register("organisation")} /></Field>
            <Field label="Website" htmlFor="website" error={form.errors.website}><input type="url" className={inputCls} {...form.register("website")} /></Field>
            <Field label="Keep candidate documents for (days)" htmlFor="retentionDays" error={form.errors.retentionDays} hint="Saved as your organisation's policy. Automatic deletion isn't scheduled in this prototype; an administrator erases data with manage.py erase-candidate." required>
              <input type="number" className={inputCls} {...form.register("retentionDays")} />
            </Field>
            <h2 className="pt-2 text-[15px] font-semibold">Notifications</h2>
            <p className="text-xs text-ink-3">Preferences are saved. No email service is connected in this prototype, so nothing is sent yet; the dashboard's review queue shows the same items.</p>
            <Toggle checked={notifyOnFlag} onChange={setNotifyOnFlag} label="Email me when a candidate is flagged" description="When email is connected: sent as soon as any check fails or needs review." />
            <Toggle checked={digest} onChange={setDigest} label="Daily summary" description="When email is connected: one email each morning with new applicants and pending reviews." />
            {save.error ? <Notice tone="error" title="Settings not saved">{errorMessage(save.error)}</Notice> : null}
            {save.data ? <Notice tone="success">Settings saved.</Notice> : null}
            <div className="flex justify-end"><Button type="submit" loading={save.isPending}>Save settings</Button></div>
          </form>
        </Card>
        <Card>
          <CardHeader title="Team" sub="People who can review applicants." />
          {q.data?.team.length ? (
            <ul className="divide-y divide-line">
              {q.data.team.map((m) => (
                <li key={m.id} className="flex items-center gap-3 px-5 py-3">
                  <Avatar name={m.name} size={32} />
                  <div className="min-w-0 flex-1"><p className="text-[13.5px] font-medium text-ink">{m.name}</p><p className="truncate text-xs text-ink-3">{m.email}</p></div>
                  <Pill tone="gray">{m.role}</Pill>
                </li>
              ))}
            </ul>
          ) : (
            <EmptyState compact icon={LuUsers} title="No team members yet">Inviting teammates arrives with accounts in Phase 2.</EmptyState>
          )}
        </Card>
      </div>
    </div>
  );
}

export type { Job };
