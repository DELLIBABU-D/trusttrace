import { useState, type ReactNode } from "react";
import {
  LuCircleAlert, LuClipboardCheck, LuFileText, LuMessageSquareWarning, LuStar,
  LuCalendarClock, LuCircleCheck, LuCircleX, LuClock, LuCircleMinus, LuMapPin, LuRefreshCw, LuShieldCheck, LuThumbsDown, LuThumbsUp,
} from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { recruiterApi } from "../../api/endpoints";
import type { ApplicationStatus, CheckStatus, ReviewDecision, TrustCheck, TrustReport as Report } from "../../api/types";
import { NotLoaded } from "../../components/DataState";
import { ApplicationPill, Avatar, Button, ButtonLink, Card, CardHeader, CheckPill, EmptyState, Field, Modal, Notice, PageHeader, Pill, RingScore, Spinner, Tabs, cx, inputCls } from "../../components/ui";
import { fileSize, formatDate, formatDateTime } from "../../lib/format";
import { useMutation, useQuery } from "../../lib/query";
import { useParams } from "../../lib/router";
import { CheckGroups, LinkedProfiles, PatternAlerts, ReviewTrail, ScoreExplanation, riskMeta } from "./TrustPanels";
import { RecruiterRunBar, SectionDetail } from "./VerificationPanels";
import { AuditTrail, PassportPanel } from "./EvidencePanels";

type Section = "summary" | keyof Report["sections"] | "audit";
const TABS: { id: Section; label: string }[] = [
  { id: "summary", label: "Summary" },
  { id: "identity", label: "Identity" },
  { id: "education", label: "Education" },
  { id: "employment", label: "Employment" },
  { id: "assessment", label: "Assessment" },
  { id: "interview", label: "Interview" },
  { id: "risk", label: "Risk Analysis" },
  { id: "audit", label: "Audit Trail" },
];

const icon: Record<CheckStatus, ReactNode> = {
  passed: <LuCircleCheck className="size-5 text-ok" aria-hidden />,
  failed: <LuCircleX className="size-5 text-bad" aria-hidden />,
  pending: <LuClock className="size-5 text-warn" aria-hidden />,
  not_started: <LuCircleMinus className="size-5 text-ink-3" aria-hidden />,
  review: <LuCircleAlert className="size-5 text-warn" aria-hidden />,
};

function CheckList({ checks }: { checks: TrustCheck[] }) {
  if (!checks.length) return <EmptyState compact icon={LuShieldCheck} title="No checks recorded in this section yet" />;
  return (
    <ul className="divide-y divide-line">
      {checks.map((c) => (
        <li key={c.key} className="flex items-start gap-3 px-5 py-3.5">
          <span className="mt-0.5">{icon[c.status]}</span>
          <div className="min-w-0 flex-1">
            <p className="text-[14px] font-medium text-ink">{c.title}</p>
            <p className="text-[13px] text-ink-3">{c.detail}</p>
          </div>
          {c.points != null && <span className={cx("text-[13px] font-semibold tabular-nums", c.points >= 0 ? "text-ok" : "text-bad")}>{c.points > 0 ? `+${c.points}` : c.points}</span>}
          <CheckPill status={c.status} />
        </li>
      ))}
    </ul>
  );
}

const decisionMeta: Record<ReviewDecision, { label: string; tone: "green" | "red" | "amber"; verb: string }> = {
  approve: { label: "Approved", tone: "green", verb: "Approve candidate" },
  reject: { label: "Rejected", tone: "red", verb: "Reject candidate" },
  reverify: { label: "Re-verification requested", tone: "amber", verb: "Request re-verification" },
};

export function TrustReport() {
  const { id = "" } = useParams();
  const q = useQuery(`recruiter:report:${id}`, () => recruiterApi.report(id));
  const [tab, setTab] = useState<Section>("summary");
  const [decision, setDecision] = useState<ReviewDecision | null>(null);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState("");
  const [clarify, setClarify] = useState(false);
  const [note, setNote] = useState("");
  const [noteError, setNoteError] = useState("");
  const move = useMutation((b: { status: ApplicationStatus; note: string }) => recruiterApi.changeStatus(id, b), {
    invalidates: ["recruiter:"],
    onSuccess: () => (setClarify(false), setNote("")),
  });
  const decide = useMutation((b: { decision: ReviewDecision; reason: string }) => recruiterApi.decide(id, b), {
    invalidates: ["recruiter:"],
    onSuccess: () => (setDecision(null), setReason("")),
  });

  if (q.isLoading) return <Spinner label="Loading trust report" />;
  const r = q.data;
  if (!r)
    return (
      <>
        <PageHeader title="Candidate Trust Report" back={{ to: "/recruiter/applicants", label: "Applicants" }} />
        <Card><NotLoaded error={q.error} what="trust report" /></Card>
      </>
    );

  const { tone: riskTone, label: riskLabel } = riskMeta(r.risk);
  const checks = tab === "summary" ? r.checks : tab === "audit" ? [] : r.sections[tab];

  function confirm() {
    if (reason.trim().length < 10) return setReasonError("Give a reason of at least 10 characters. It's stored in the audit trail.");
    setReasonError("");
    void decide.mutate({ decision: decision!, reason: reason.trim() });
  }

  return (
    <div>
      <PageHeader title="Candidate Trust Report" back={{ to: "/recruiter/applicants", label: "Applicants" }}
        sub={`${r.jobTitle} · applied ${formatDate(r.appliedAt)}`}
        actions={<ApplicationPill status={r.status} />} />
      <Card className="p-5 sm:p-6">
        <div className="flex flex-wrap items-center gap-5">
          <Avatar name={r.candidate.fullName} src={r.candidate.photoUrl} size={72} />
          <div className="min-w-0 flex-1">
            <h2 className="text-xl font-semibold text-ink">{r.candidate.fullName}</h2>
            <p className="text-[14px] text-ink-2">{r.candidate.headline}</p>
            <p className="mt-1 flex items-center gap-1 text-[13px] text-ink-3"><LuMapPin className="size-3.5" aria-hidden /> {r.candidate.location}</p>
          </div>
          <div className="flex items-center gap-4">
            <RingScore value={r.trustScore} label="Trust score" sub="Trust Score" size={112} />
            <div className="space-y-1.5">
              <Pill tone={riskTone}>{riskLabel}</Pill>
              {r.trust && <p className="text-xs text-ink-3">{r.trust.reviewCount} to review · {r.trust.pendingCount} pending</p>}
              <p className="max-w-44 text-[11px] leading-snug text-ink-3">Decision support, not a verdict on honesty.</p>
            </div>
          </div>
        </div>
      </Card>

      <RecruiterRunBar appId={id} />

      <div className="mt-5"><Tabs label="Report sections" value={tab} onChange={setTab} tabs={TABS} /></div>

      <div className="mt-5 grid gap-5 lg:grid-cols-[1.5fr_1fr]">
        <div className="space-y-5">
        {tab === "summary" ? (
          <>
            <ScoreExplanation r={r} />
            <CheckGroups r={r} appId={id} />
          </>
        ) : tab === "audit" ? (
          <AuditTrail appId={id} />
        ) : (
          <Card>
            <CardHeader title={TABS.find((t) => t.id === tab)!.label} />
            <CheckList checks={checks} />
          </Card>
        )}
        {tab !== "audit" && <SectionDetail tab={tab} r={r} appId={id} />}
        {tab === "risk" && (
          <>
            {r.graph && <LinkedProfiles g={r.graph} />}
            <PatternAlerts alerts={r.patternAlerts ?? []} appId={id} />
          </>
        )}
        {tab === "summary" && <CandidateDetails r={r} />}
        </div>
        <div className="space-y-5">
          <ReviewTrail r={r} appId={id} />
          <PassportPanel appId={id} />
          <Card>
            <CardHeader title="Next step" sub="The candidate receives a message for every change." />
            <div className="grid gap-2 px-5 pb-5">
              <Button variant="secondary" icon={LuStar} loading={move.isPending} disabled={r.status === "shortlisted"} onClick={() => void move.mutate({ status: "shortlisted", note: "" })}>Shortlist</Button>
              <Button variant="secondary" icon={LuMessageSquareWarning} onClick={() => setClarify(true)}>Request clarification</Button>
              <Button variant="secondary" icon={LuClipboardCheck} loading={move.isPending} disabled={r.status === "assessment"} onClick={() => void move.mutate({ status: "assessment", note: "" })}>Move to assessment</Button>
              <ButtonLink to="/recruiter/interviews" variant="secondary" icon={LuCalendarClock}>Schedule interview</ButtonLink>
              {move.error && !clarify ? <Notice tone="error" title="Not updated">{errorMessage(move.error)}</Notice> : null}
            </div>
          </Card>
          <Card>
            <CardHeader title="Review decision" sub="Every decision needs a reason and is logged." />
            <div className="grid gap-2 px-5 pb-5">
              <Button icon={LuThumbsUp} onClick={() => setDecision("approve")}>Approve & shortlist</Button>
              <Button variant="outline" icon={LuRefreshCw} onClick={() => setDecision("reverify")}>Request re-verification</Button>
              <Button variant="danger" icon={LuThumbsDown} onClick={() => setDecision("reject")}>Reject</Button>
            </div>
          </Card>
          <Card>
            <CardHeader title="Decision history" />
            {r.decisions.length ? (
              <ul className="divide-y divide-line">
                {r.decisions.map((d) => (
                  <li key={d.id} className="px-5 py-3 text-[13px]">
                    <div className="flex items-center justify-between gap-2"><Pill tone={decisionMeta[d.decision].tone}>{decisionMeta[d.decision].label}</Pill><span className="text-ink-3">{formatDateTime(d.at)}</span></div>
                    <p className="mt-1.5 text-ink-2">{d.reason}</p>
                    <p className="mt-0.5 text-xs text-ink-3">by {d.reviewer}</p>
                  </li>
                ))}
              </ul>
            ) : (
              <p className="px-5 pb-5 text-[13px] text-ink-3">No decision yet.</p>
            )}
          </Card>
        </div>
      </div>

      <Modal open={clarify} onClose={() => (setClarify(false), move.reset(), setNoteError(""))} title="Request clarification" footer={<>
        <Button variant="secondary" onClick={() => setClarify(false)}>Cancel</Button>
        <Button loading={move.isPending} onClick={() => {
          if (note.trim().length < 10) return setNoteError("Write at least 10 characters so the candidate knows what to send.");
          setNoteError("");
          void move.mutate({ status: "clarification", note: note.trim() });
        }}>Send request</Button>
      </>}>
        <Field label="What should the candidate clarify?" htmlFor="note" error={noteError} required hint="Sent to the candidate's Messages and shown on their application.">
          <textarea id="note" rows={4} value={note} onChange={(e) => setNote(e.target.value)} className={inputCls} aria-invalid={noteError ? true : undefined} aria-describedby={noteError ? "note-error" : undefined} />
        </Field>
        {move.error && clarify ? <div className="mt-3"><Notice tone="error" title="Request not sent">{errorMessage(move.error)}</Notice></div> : null}
      </Modal>

      <Modal open={decision !== null} onClose={() => (setDecision(null), decide.reset(), setReasonError(""))} title={decision ? decisionMeta[decision].verb : ""} footer={<>
        <Button variant="secondary" onClick={() => setDecision(null)}>Cancel</Button>
        <Button variant={decision === "reject" ? "danger" : "primary"} loading={decide.isPending} onClick={confirm}>Confirm</Button>
      </>}>
        <Field label="Reason" htmlFor="reason" error={reasonError} required hint="Visible to your team and in the audit log.">
          <textarea id="reason" rows={4} value={reason} onChange={(e) => setReason(e.target.value)} className={inputCls} aria-invalid={reasonError ? true : undefined} aria-describedby={reasonError ? "reason-error" : undefined} />
        </Field>
        {decide.error ? <div className="mt-3"><Notice tone="error" title="Decision not saved">{errorMessage(decide.error)}</Notice></div> : null}
      </Modal>
    </div>
  );
}

function CandidateDetails({ r }: { r: Report }) {
  const p = r.profile;
  const row = (k: string, v: ReactNode) => (
    <div className="grid grid-cols-[130px_1fr] gap-3 py-2 text-[13.5px]"><dt className="text-ink-3">{k}</dt><dd className="min-w-0 text-ink">{v}</dd></div>
  );
  return (
    <>
      <Card>
        <CardHeader title="Candidate details" sub="As entered by the candidate. Not verified unless a check above says so." />
        <dl className="divide-y divide-line px-5 pb-4">
          {row("Email", r.candidate.email ?? "—")}
          {row("Mobile", <>{r.candidate.phone ?? "—"} {r.candidate.phoneVerified && <span className="ml-1 text-xs text-ok">(OTP verified)</span>}</>)}
          {row("Date of birth", p?.dateOfBirth ? formatDate(p.dateOfBirth) : "—")}
          {row("Skills", p?.skills.length ? p.skills.join(", ") : "—")}
          {row("Education", p?.education.length ? <ul className="space-y-1">{p.education.map((e, i) => <li key={i}>{e.degree}, {e.institution} ({e.startYear}–{e.endYear}){e.score ? ` · ${e.score}` : ""}</li>)}</ul> : "—")}
          {row("Experience", p?.experience.length ? <ul className="space-y-1">{p.experience.map((e, i) => <li key={i}>{e.title}, {e.company} ({e.start} – {e.current ? "present" : e.end})</li>)}</ul> : "None")}
          {row("References", p?.references.length ? <ul className="space-y-1">{p.references.map((x, i) => <li key={i}>{x.name} ({x.relationship}{x.company ? `, ${x.company}` : ""}) · {x.email || x.phone}</li>)}</ul> : "None")}
          {(p?.linkedinUrl || p?.githubUrl) && row("Links", <span className="flex flex-wrap gap-3">{p?.linkedinUrl && <a className="text-brand-700 hover:underline" href={p.linkedinUrl} target="_blank" rel="noreferrer noopener">LinkedIn</a>}{p?.githubUrl && <a className="text-brand-700 hover:underline" href={p.githubUrl} target="_blank" rel="noreferrer noopener">GitHub</a>}</span>)}
        </dl>
      </Card>
      <Card>
        <CardHeader title="Documents" sub="Uploaded by the candidate. Uploading does not verify a document." />
        {r.documents?.length ? (
          <ul className="divide-y divide-line">
            {r.documents.map((d) => (
              <li key={d.id} className="flex items-center gap-3 px-5 py-3">
                <LuFileText className="size-5 text-ink-3" aria-hidden />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[13.5px] font-medium text-ink">{d.fileName}</p>
                  <p className="text-xs text-ink-3">{d.kind.replace(/_/g, " ")} · {fileSize(d.sizeBytes)} · {formatDateTime(d.uploadedAt)}</p>
                </div>
                {d.previewUrl && <a href={d.previewUrl} target="_blank" rel="noreferrer" className="text-[13px] font-medium text-brand-700 hover:underline">Open</a>}
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState compact icon={LuFileText} title="No documents uploaded yet" />
        )}
      </Card>
      {r.history && r.history.length > 0 && (
        <Card>
          <CardHeader title="Application history" />
          <ul className="divide-y divide-line">
            {[...r.history].reverse().map((h, i) => (
              <li key={i} className="px-5 py-3 text-[13px]">
                <div className="flex items-center justify-between gap-2"><ApplicationPill status={h.status} /><span className="text-ink-3">{formatDateTime(h.at)}</span></div>
                {h.note && <p className="mt-1 text-ink-2">{h.note}</p>}
              </li>
            ))}
          </ul>
        </Card>
      )}
    </>
  );
}
