import { useMemo, useState } from "react";
import {
  LuBriefcase, LuBuilding2, LuCalendar, LuCircleCheck, LuClipboardList, LuClock, LuFileText, LuGraduationCap, LuScanFace, LuSearch, LuShieldCheck,
  LuSlidersHorizontal, LuCopy, LuUserCheck,
} from "react-icons/lu";
import { errorMessage, isUnavailable } from "../../api/client";
import { candidateApi, jobsApi } from "../../api/endpoints";
import type { Application, EmploymentType, Job, VerificationItem, WorkMode } from "../../api/types";
import { useAuth } from "../../auth/AuthContext";
import { DataState, NotLoaded } from "../../components/DataState";
import {
  ApplicationPill, Button, ButtonLink, Card, CardHeader, CheckPill, Chip, EmptyState, Notice, PageHeader, ProgressBar, ScoreBadge, Spinner, StatCard,
  Tabs, VerificationPill, cx, inputCls,
} from "../../components/ui";
import { formatDate, timeAgo } from "../../lib/format";
import { useMutation, useQuery } from "../../lib/query";
import { Link, useNavigate, useParams } from "../../lib/router";

export const employmentLabel: Record<EmploymentType, string> = { full_time: "Full Time", part_time: "Part Time", internship: "Internship", contract: "Contract" };
export const workModeLabel: Record<WorkMode, string> = { onsite: "On-site", remote: "Remote", hybrid: "Hybrid" };

function JobCard({ job, compact }: { job: Job; compact?: boolean }) {
  const navigate = useNavigate();
  const apply = useMutation(() => jobsApi.apply(job.id), { invalidates: ["candidate:", "jobs"], onSuccess: (a) => navigate(`/candidate/applications/${a.id}`) });
  if (apply.error && (apply.error as { code?: string }).code === "already_applied" && !job.applied) job = { ...job, applied: true };
  return (
    <article className={cx("rounded-xl border border-line bg-white", compact ? "p-3.5" : "p-4")}>
      <div className="flex items-start gap-3">
        <span className="grid size-10 shrink-0 place-items-center rounded-full bg-info-soft text-info">
          <LuBuilding2 className="size-5" aria-hidden />
        </span>
        <div className="min-w-0 flex-1">
          <h3 className="text-[14.5px] font-semibold text-ink">{job.title}</h3>
          <p className="mt-0.5 text-[12.5px] text-ink-3">
            {job.company} | {job.location} | {employmentLabel[job.employmentType]}
            {job.workMode !== "onsite" && ` | ${workModeLabel[job.workMode]}`}
          </p>
          {job.skills.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1.5">
              {job.skills.slice(0, 5).map((s) => <Chip key={s}>{s}</Chip>)}
            </div>
          )}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          {job.applied ? (
            <span className="inline-flex items-center gap-1 rounded-lg bg-brand-50 px-2.5 py-1.5 text-xs font-medium text-brand-700"><LuCircleCheck className="size-3.5" aria-hidden /> Applied</span>
          ) : (
            <Button size="sm" className="min-w-16" loading={apply.isPending} onClick={() => void apply.mutate(undefined)}>Apply</Button>
          )}
          {!compact && <span className="hidden text-xs text-ink-3 sm:block">Posted {timeAgo(job.postedAt)}</span>}
        </div>
      </div>
      {apply.error ? <div className="mt-3"><Notice tone="error">{errorMessage(apply.error)}</Notice></div> : null}
    </article>
  );
}

/* ------------------------------------------------------------------ (c) dashboard */

const VERIFICATION_KEYS: { key: VerificationItem["key"]; label: string; icon: typeof LuScanFace }[] = [
  { key: "identity", label: "Identity", icon: LuScanFace },
  { key: "education", label: "Education", icon: LuGraduationCap },
  { key: "employment", label: "Employment", icon: LuBriefcase },
  { key: "resume", label: "Resume Analysis", icon: LuFileText },
  { key: "duplicate", label: "Duplicate Check", icon: LuCopy },
];

export function VerificationList({ items }: { items: VerificationItem[] | undefined }) {
  return (
    <ul className="divide-y divide-line">
      {VERIFICATION_KEYS.map((v) => {
        const item = items?.find((i) => i.key === v.key);
        return (
          <li key={v.key} className="flex items-center gap-3 py-3">
            <span className="grid size-8 place-items-center rounded-lg bg-brand-50 text-brand-600"><v.icon className="size-4" aria-hidden /></span>
            <span className="flex-1 text-[13.5px] font-medium text-ink">{v.label}</span>
            <VerificationPill status={item?.status ?? "not_started"} />
          </li>
        );
      })}
    </ul>
  );
}

export function CandidateDashboard() {
  const { user } = useAuth();
  const dash = useQuery("candidate:dashboard", candidateApi.dashboard);
  const profile = useQuery("candidate:profile", candidateApi.profile);
  const d = dash.data;
  const first = user?.fullName.split(" ")[0];
  const completeness = profile.data?.completeness ?? 0;

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight text-ink">{first ? `Welcome back, ${first}!` : "Welcome!"}</h1>
          <p className="mt-1 text-[15px] text-ink-2">Let's build your future.</p>
        </div>
        <Card as="div" className="w-full px-4 py-3 sm:w-72">
          <div className="mb-2 flex items-center justify-between text-[13px]">
            <span className="font-medium text-ink">Profile Completeness</span>
            <span className="font-semibold text-ink tabular-nums">{completeness}%</span>
          </div>
          <ProgressBar value={completeness} label="Profile completeness" />
          {completeness < 100 && <Link to="/candidate/profile" className="mt-2 inline-block text-xs font-medium text-brand-700 hover:underline">Complete your profile</Link>}
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatCard icon={LuBriefcase} tone="blue" value={d?.appliedJobs ?? 0} label="Applied Jobs" loading={dash.isLoading} />
        <StatCard icon={LuClipboardList} tone="amber" value={d?.assessmentsPending ?? 0} label="Assessments Pending" loading={dash.isLoading} />
        <StatCard icon={LuCalendar} tone="violet" value={d?.interviewsScheduled ?? 0} label="Interview Scheduled" loading={dash.isLoading} />
        <StatCard icon={LuShieldCheck} tone="green" value={d?.trustScore ?? "—"} label="Current Trust Score" loading={dash.isLoading} />
      </div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1.6fr_1fr]">
        <Card>
          <CardHeader title="Recommended Jobs" action={<Link to="/candidate/jobs" className="text-[13px] font-medium text-brand-700 hover:underline">Browse all</Link>} />
          <div className="px-5 pb-5">
            <DataState
              query={{ ...dash, data: d?.recommendedJobs }}
              isEmpty={(j) => j.length === 0}
              empty={{ icon: LuBriefcase, title: "No recommended jobs yet", body: "Jobs that match your skills appear here once recruiters post them.", action: <ButtonLink to="/candidate/jobs" variant="secondary" size="sm">Browse jobs</ButtonLink> }}
            >
              {(jobs) => <div className="space-y-3">{jobs.slice(0, 4).map((j) => <JobCard key={j.id} job={j} compact />)}</div>}
            </DataState>
          </div>
        </Card>
        <Card>
          <CardHeader title="Verification Status" action={<Link to="/candidate/verification" className="text-[13px] font-medium text-brand-700 hover:underline">Details</Link>} />
          <div className="px-5 pb-3">{dash.isLoading ? <Spinner /> : <VerificationList items={d?.verification} />}</div>
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ (d) available jobs */

export function AvailableJobs() {
  const [search, setSearch] = useState("");
  const [applied, setApplied] = useState("");
  const [showFilters, setShowFilters] = useState(false);
  const [filters, setFilters] = useState({ location: "", type: "", mode: "" });
  const key = `jobs:${applied}|${filters.location}|${filters.type}|${filters.mode}`;
  const jobs = useQuery(key, () => jobsApi.list({ search: applied, ...filters }));
  const activeFilters = Object.values(filters).filter(Boolean).length;

  return (
    <div>
      <PageHeader title="Available Jobs" actions={<ButtonLink to="/candidate/applications" variant="secondary" size="sm">My applications</ButtonLink>} />
      <form className="mb-4 flex gap-3" role="search" onSubmit={(e) => (e.preventDefault(), setApplied(search.trim()))}>
        <div className="relative flex-1">
          <LuSearch className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-ink-3" aria-hidden />
          <label htmlFor="job-search" className="sr-only">Search jobs</label>
          <input id="job-search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Search by role, company or skills..." className={cx(inputCls, "pl-9")} />
        </div>
        <Button variant="secondary" icon={LuSlidersHorizontal} onClick={() => setShowFilters((s) => !s)} aria-expanded={showFilters}>
          Filters{activeFilters ? ` (${activeFilters})` : ""}
        </Button>
      </form>
      {showFilters && (
        <Card className="mb-4 grid gap-3 p-4 sm:grid-cols-4">
          <div>
            <label htmlFor="f-loc" className="mb-1 block text-xs font-medium text-ink-2">Location</label>
            <input id="f-loc" className={inputCls} value={filters.location} onChange={(e) => setFilters({ ...filters, location: e.target.value })} placeholder="Any city" />
          </div>
          <div>
            <label htmlFor="f-type" className="mb-1 block text-xs font-medium text-ink-2">Job type</label>
            <select id="f-type" className={inputCls} value={filters.type} onChange={(e) => setFilters({ ...filters, type: e.target.value })}>
              <option value="">Any</option>
              {Object.entries(employmentLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="f-mode" className="mb-1 block text-xs font-medium text-ink-2">Work mode</label>
            <select id="f-mode" className={inputCls} value={filters.mode} onChange={(e) => setFilters({ ...filters, mode: e.target.value })}>
              <option value="">Any</option>
              {Object.entries(workModeLabel).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
            </select>
          </div>
          <div className="flex items-end">
            <Button variant="ghost" onClick={() => setFilters({ location: "", type: "", mode: "" })} disabled={!activeFilters}>Clear filters</Button>
          </div>
        </Card>
      )}
      <DataState
        query={jobs}
        isEmpty={(j) => j.length === 0}
        empty={{ icon: LuBriefcase, title: applied || activeFilters ? "No jobs match your search" : "No jobs posted yet", body: applied || activeFilters ? "Try a different role, company or skill." : "Open roles appear here as soon as recruiters publish them." }}
      >
        {(list) => <div className="space-y-3">{list.map((j) => <JobCard key={j.id} job={j} />)}</div>}
      </DataState>
    </div>
  );
}

/* ------------------------------------------------------------------ my applications */

export function MyApplications() {
  const apps = useQuery("candidate:applications", candidateApi.applications);
  const [tab, setTab] = useState<"active" | "closed">("active");
  const filtered = useMemo(() => (apps.data ?? []).filter((a) => (tab === "closed" ? ["rejected", "hired"].includes(a.status) : !["rejected", "hired"].includes(a.status))), [apps.data, tab]);

  return (
    <div>
      <PageHeader title="My Applications" sub="Track each application and the checks it has passed." actions={<ButtonLink to="/candidate/jobs" icon={LuSearch}>Find jobs</ButtonLink>} />
      <div className="mb-4 w-fit"><Tabs label="Application status" value={tab} onChange={setTab} tabs={[{ id: "active", label: "In progress" }, { id: "closed", label: "Closed" }]} /></div>
      <Card>
        <DataState
          query={{ ...apps, data: apps.data ? filtered : undefined }}
          isEmpty={(a) => a.length === 0}
          empty={{ icon: LuBriefcase, title: tab === "active" ? "You haven't applied to any jobs yet" : "No closed applications", body: tab === "active" ? "Browse open roles and apply. Your progress will appear here." : undefined, action: tab === "active" ? <ButtonLink to="/candidate/jobs" size="sm">Browse jobs</ButtonLink> : undefined }}
        >
          {(list) => (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-[13.5px]">
                <thead className="border-b border-line text-xs text-ink-3">
                  <tr><th className="px-5 py-3 font-medium">Role</th><th className="px-5 py-3 font-medium">Applied</th><th className="px-5 py-3 font-medium">Trust score</th><th className="px-5 py-3 font-medium">Status</th><th className="px-5 py-3" /></tr>
                </thead>
                <tbody className="divide-y divide-line">
                  {list.map((a) => (
                    <tr key={a.id}>
                      <td className="px-5 py-3"><p className="font-medium text-ink">{a.jobTitle}</p><p className="text-xs text-ink-3">{a.company}</p></td>
                      <td className="px-5 py-3 text-ink-2">{formatDate(a.appliedAt)}</td>
                      <td className="px-5 py-3"><ScoreBadge score={a.trustScore} /></td>
                      <td className="px-5 py-3"><ApplicationPill status={a.status} /></td>
                      <td className="px-5 py-3 text-right"><Link to={`/candidate/applications/${a.id}`} className="font-medium text-brand-700 hover:underline">View</Link></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </DataState>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ application details */

export function ApplicationDetail() {
  const { id } = useParams<{ id: string }>();
  const app = useQuery(`candidate:application:${id}`, () => candidateApi.application(id));

  return (
    <div>
      <PageHeader back={{ to: "/candidate/applications", label: "My applications" }} title={app.data ? app.data.jobTitle : "Application details"} sub={app.data ? `${app.data.company} · applied ${formatDate(app.data.appliedAt)}` : undefined} actions={app.data ? <ApplicationPill status={app.data.status} /> : undefined} />
      {app.isLoading ? <Spinner /> : !app.data ? (
        <Card><NotLoaded error={app.error} what="application" /></Card>
      ) : (
        <AppTimeline app={app.data} />
      )}
    </div>
  );
}

function AppTimeline({ app }: { app: Application }) {
  return (
    <div className="grid gap-5 lg:grid-cols-[1.6fr_1fr]">
      <Card>
        <CardHeader title="Progress" sub="Every stage is verified before the next one opens." />
        <ol className="px-5 pb-5">
          {app.stages.length === 0 ? (
            <EmptyState compact icon={LuClock} title="No stages recorded yet" />
          ) : (
            app.stages.map((s, i) => (
              <li key={s.key} className="relative flex gap-3 pb-5 last:pb-0">
                {i < app.stages.length - 1 && <span aria-hidden className="absolute top-7 left-[13px] h-[calc(100%-20px)] w-0.5 bg-line" />}
                <span className={cx("relative grid size-7 shrink-0 place-items-center rounded-full", s.status === "passed" ? "bg-brand-600 text-white" : "bg-surface text-ink-3 ring-1 ring-line")}>
                  {s.status === "passed" ? <LuCircleCheck className="size-4" aria-hidden /> : <span className="text-xs font-semibold">{i + 1}</span>}
                </span>
                <div className="flex flex-1 flex-wrap items-center justify-between gap-2 pt-0.5">
                  <div>
                    <p className="text-[13.5px] font-medium text-ink">{s.label}</p>
                    {s.at && <p className="text-xs text-ink-3">{formatDate(s.at)}</p>}
                  </div>
                  <CheckPill status={s.status} />
                </div>
              </li>
            ))
          )}
        </ol>
      </Card>
      <Card className="p-5">
        <p className="text-[13px] text-ink-3">Current trust score</p>
        <p className="mt-1 text-3xl font-semibold tabular-nums">{app.trustScore ?? "—"}</p>
        {app.history && app.history.length > 0 && (
          <div className="mt-4 border-t border-line pt-4">
            <p className="mb-2 text-[13px] font-medium text-ink">Updates</p>
            <ul className="space-y-2.5">
              {[...app.history].reverse().map((h, i) => (
                <li key={i} className="text-[13px]">
                  <div className="flex items-center justify-between gap-2"><ApplicationPill status={h.status} /><span className="text-xs text-ink-3">{formatDate(h.at)}</span></div>
                  {h.note && <p className="mt-1 text-ink-2">{h.note}</p>}
                </li>
              ))}
            </ul>
          </div>
        )}
        <div className="mt-4 space-y-2">
          <ButtonLink to="/candidate/verification" variant="secondary" className="w-full" icon={LuUserCheck}>Verification details</ButtonLink>
          <ButtonLink to="/candidate/assessments" variant="secondary" className="w-full" icon={LuClipboardList}>Assessments</ButtonLink>
        </div>
      </Card>
    </div>
  );
}

export { JobCard, isUnavailable };
