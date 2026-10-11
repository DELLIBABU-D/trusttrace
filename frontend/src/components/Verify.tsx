/** Shared pieces for verification results (candidate and recruiter screens). */
import { useEffect, useRef } from "react";
import { LuCircleAlert, LuCircleCheck, LuCircleMinus, LuCircleX, LuInfo, LuPlay, LuRefreshCw, LuTriangleAlert } from "react-icons/lu";
import { errorMessage } from "../api/client";
import type { FieldComparison, IssuerStatus, VerificationFinding, VerificationJob } from "../api/types";
import { formatDateTime } from "../lib/format";
import { invalidate, useMutation, useQuery } from "../lib/query";
import { Button, Notice, Pill, cx } from "./ui";

/** Shows the latest job and polls while it is queued/running; refreshes every query under `refreshPrefix` when it ends. */
export function useVerificationJob(key: string, fetchJob: () => Promise<VerificationJob | null>, run: () => Promise<VerificationJob>, refreshPrefix: string) {
  const job = useQuery(key, fetchJob);
  const active = job.data?.status === "queued" || job.data?.status === "running";
  const wasActive = useRef(false);
  useEffect(() => {
    if (!active) {
      if (wasActive.current) refreshPrefix.split(",").forEach((p) => invalidate(p));
      wasActive.current = false;
      return;
    }
    wasActive.current = true;
    const t = window.setTimeout(() => void job.refetch(), 1500);
    return () => window.clearTimeout(t);
  });
  const start = useMutation(() => run(), { onSuccess: () => void job.refetch() });
  return { job: job.data, active, start };
}

export function RunVerificationBar({ job, active, start, label = "Run verification" }: {
  job: VerificationJob | null | undefined; active: boolean; start: { mutate: (v: undefined) => Promise<unknown>; isPending: boolean; error: unknown }; label?: string;
}) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button icon={job ? LuRefreshCw : LuPlay} loading={active || start.isPending} onClick={() => void start.mutate(undefined)} disabled={active}>
        {active ? "Verifying…" : label}
      </Button>
      <span className="text-[13px] text-ink-3" aria-live="polite">
        {active ? "Reading documents and comparing details. This usually takes a few seconds." :
          job?.status === "failed" ? <span className="text-bad">Last run failed: {job.error}</span> :
            job?.finishedAt ? `Last run ${formatDateTime(job.finishedAt)}` : "Not run yet"}
      </span>
      {start.error ? <div className="w-full"><Notice tone="error">{errorMessage(start.error)}</Notice></div> : null}
    </div>
  );
}

export function ComparisonRows({ rows, empty }: { rows: FieldComparison[]; empty: string }) {
  if (!rows.length) return <p className="py-3 text-[13px] text-ink-3">{empty}</p>;
  return (
    <ul className="divide-y divide-line">
      {rows.map((c, i) => (
        <li key={c.field + i} className="py-2.5 text-[13.5px]">
          <div className="flex items-center gap-3">
            {c.match === true ? <LuCircleCheck className="size-4 shrink-0 text-ok" aria-hidden /> : c.match === false ? <LuCircleX className="size-4 shrink-0 text-bad" aria-hidden /> : <LuCircleMinus className="size-4 shrink-0 text-ink-3" aria-hidden />}
            <span className="flex-1 text-ink">{c.field}</span>
            <span className={cx("font-medium", c.match === true ? "text-ok" : c.match === false ? "text-bad" : "text-ink-3")}>
              {c.match === true ? "Match" : c.match === false ? "Mismatch" : "Not checked"}
            </span>
          </div>
          {(c.extracted != null || c.claimed != null || c.note) && (
            <div className="mt-1 ml-7 space-y-0.5 text-xs text-ink-3">
              {(c.extracted != null || c.claimed != null) && (
                <p>Document: <span className="text-ink-2">{c.extracted ?? "not found"}</span>{c.claimed != null && <> · Entered: <span className="text-ink-2">{c.claimed}</span></>}</p>
              )}
              {c.note && <p>{c.note}</p>}
              {c.evidence?.snippet && <p className="truncate">Evidence{c.evidence.page ? ` (page ${c.evidence.page})` : ""}: “{c.evidence.snippet}”{c.evidence.source === "gemini" ? " · AI-suggested" : ""}</p>}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}

const sevIcon = { critical: LuTriangleAlert, warning: LuCircleAlert, info: LuInfo } as const;
const sevCls = { critical: "text-bad", warning: "text-warn", info: "text-info" } as const;

export function FindingsList({ findings }: { findings: VerificationFinding[] | undefined }) {
  if (!findings?.length) return null;
  return (
    <ul className="space-y-2.5">
      {findings.map((f, i) => {
        const Icon = sevIcon[f.severity];
        return (
          <li key={f.code + i} className="flex gap-2.5 text-[13px]">
            <Icon className={cx("mt-0.5 size-4 shrink-0", sevCls[f.severity])} aria-hidden />
            <div>
              <p className="font-medium text-ink">{f.title}</p>
              {f.detail && <p className="text-ink-3">{f.detail}</p>}
              {f.evidence?.snippet && <p className="text-xs text-ink-3">Evidence{f.evidence.page ? ` (page ${f.evidence.page})` : ""}: “{f.evidence.snippet}”</p>}
            </div>
          </li>
        );
      })}
    </ul>
  );
}

export function IssuerBox({ issuer }: { issuer: IssuerStatus | undefined }) {
  if (!issuer) return null;
  const tone = issuer.status === "confirmed" ? (issuer.simulated ? "amber" : "green") : issuer.status === "denied" ? "red" : issuer.status === "no_record" ? "amber" : "gray";
  const text = { confirmed: "Confirmed", denied: "Not confirmed", no_record: "No record", not_checked: "Not checked" }[issuer.status];
  return (
    <div className="rounded-lg border border-line p-3.5">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[13.5px] font-medium text-ink">Issuer authenticity</p>
        <div className="flex gap-1.5">{issuer.simulated && <Pill tone="violet">Simulated</Pill>}<Pill tone={tone}>{text}</Pill></div>
      </div>
      <p className="mt-1 text-[13px] text-ink-3">{issuer.label}</p>
      {issuer.detail && <p className="mt-1 text-xs text-ink-3">{issuer.detail}</p>}
    </div>
  );
}

export const decisionText: Record<string, string> = {
  match: "Face matches", no_match: "Face does not match", no_face: "No face found", multiple_faces: "More than one face", poor_quality: "Photo quality too low",
  no_enrollment: "No enrolled face", no_consent: "Biometric consent not given", error: "Check unavailable", camera_unavailable: "No camera",
};

export const outcomeMeta: Record<string, { label: string; tone: "green" | "amber" | "red" }> = {
  matched: { label: "Matched", tone: "green" },
  uncertain: { label: "Uncertain", tone: "amber" },
  needs_review: { label: "Needs review", tone: "amber" },
};
