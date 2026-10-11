import { useState } from "react";
import { LuBan, LuCircleAlert, LuExternalLink, LuLink2, LuQrCode, LuRefreshCw, LuShieldCheck, LuShieldX } from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { recruiterApi } from "../../api/endpoints";
import type { EvidenceEventRow } from "../../api/types";
import { NotLoaded } from "../../components/DataState";
import { Button, Card, CardHeader, EmptyState, Field, Modal, Notice, Pill, Spinner, cx, inputCls } from "../../components/ui";
import { formatDate, formatDateTime } from "../../lib/format";
import { useMutation, useQuery } from "../../lib/query";

const ACTOR: Record<EvidenceEventRow["actorRole"], string> = { candidate: "Candidate", recruiter: "Recruiter", system: "System", referee: "Referee" };
const short = (h: string) => `${h.slice(0, 10)}…`;

/* ------------------------------------------------------------------ evidence chain timeline */

export function AuditTrail({ appId }: { appId: string }) {
  const key = `recruiter:evidence:${appId}`;
  const q = useQuery(key, () => recruiterApi.evidence(appId));
  const [all, setAll] = useState(false);
  const [checking, setChecking] = useState(false);
  if (q.isLoading) return <Card><Spinner label="Checking the evidence chain" /></Card>;
  const d = q.data;
  if (!d) return <Card><NotLoaded error={q.error} what="evidence chain" /></Card>;
  const v = d.verification;
  const events = [...d.events].reverse();
  const shown = all ? events : events.slice(0, 25);
  return (
    <Card>
      <CardHeader title="Evidence chain"
        sub="Every important step is recorded as a hashed event linked to the one before it. Verification recomputes every link."
        action={<Button size="sm" variant="secondary" icon={LuRefreshCw} loading={checking} onClick={() => (setChecking(true), void q.refetch().finally(() => setChecking(false)))}>Verify again</Button>} />
      <div className="px-5 pb-4">
        {v.intact ? (
          <Notice tone="success" title="Chain intact">
            {v.events} event(s) checked {formatDateTime(v.checkedAt)}. Head #{v.head?.seq} · <span className="font-mono">{v.head ? short(v.head.hash) : "—"}</span>
          </Notice>
        ) : (
          <Notice tone="error" title="Tampering detected">
            <ul className="mt-1 list-disc space-y-0.5 pl-4">
              {v.problems.map((p, i) => <li key={i}>Event #{p.seq ?? "?"}: {p.detail}</li>)}
            </ul>
          </Notice>
        )}
      </div>
      {events.length === 0 ? (
        <EmptyState compact icon={LuLink2} title="No events recorded yet" />
      ) : (
        <ol className="divide-y divide-line border-t border-line" aria-label="Evidence events, newest first">
          {shown.map((e) => {
            const broken = v.problems.some((p) => p.seq === e.seq);
            return (
              <li key={e.seq} className={cx("grid grid-cols-[44px_1fr] gap-2 px-5 py-2.5 text-[13px]", e.hidden && "bg-surface/60", broken && "bg-bad-soft/40")}>
                <span className="pt-0.5 font-mono text-xs text-ink-3">#{e.seq}</span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
                    <span className={cx("font-medium", e.hidden ? "text-ink-3" : "text-ink")}>{e.label}</span>
                    <span className="text-xs text-ink-3">{ACTOR[e.actorRole]} · {formatDateTime(e.at)}</span>
                    {broken && <Pill tone="red">Changed</Pill>}
                  </div>
                  {e.detail && <p className="truncate text-xs text-ink-2" title={e.detail}>{e.detail}</p>}
                  <p className="font-mono text-[11px] text-ink-3" title={`hash ${e.hash}\nprevious ${e.prevHash}`}>hash {short(e.hash)} ← {short(e.prevHash)}</p>
                </div>
              </li>
            );
          })}
        </ol>
      )}
      {events.length > 25 && (
        <div className="border-t border-line px-5 py-2.5">
          <Button size="sm" variant="ghost" onClick={() => setAll(!all)}>{all ? "Show fewer" : `Show all ${events.length} events`}</Button>
        </div>
      )}
      <p className="border-t border-line px-5 py-3 text-[11.5px] leading-snug text-ink-3">{d.note}</p>
    </Card>
  );
}

/* ------------------------------------------------------------------ passport (issue / revoke) */

export function PassportPanel({ appId }: { appId: string }) {
  const key = `recruiter:passport:${appId}`;
  const q = useQuery(key, () => recruiterApi.passport(appId));
  const [revoking, setRevoking] = useState(false);
  const [reason, setReason] = useState("");
  const [reasonError, setReasonError] = useState("");
  const refresh = [key, `recruiter:evidence:${appId}`, `recruiter:report:${appId}`];
  const issue = useMutation(() => recruiterApi.issuePassport(appId), { invalidates: refresh });
  const revoke = useMutation((r: string) => recruiterApi.revokePassport(appId, r), {
    invalidates: refresh, onSuccess: () => (setRevoking(false), setReason("")),
  });
  if (q.isLoading) return <Card><Spinner label="Loading passport" /></Card>;
  const d = q.data;
  if (!d) return <Card><NotLoaded error={q.error} what="passport" /></Card>;
  const p = d.active;
  return (
    <Card>
      <CardHeader title="TrustTrace Passport" sub="A signed, minimal summary the candidate can share. No photos, documents, contact details or score." />
      <div className="space-y-3 px-5 pb-5">
        {p ? (
          <div className="flex items-start gap-3">
            {p.qrDataUrl && <img src={p.qrDataUrl} alt="Passport QR code" className="size-20 shrink-0 rounded-md border border-line p-0.5" />}
            <div className="min-w-0 text-[13px]">
              <p className="flex items-center gap-1.5 font-medium text-ink"><LuShieldCheck className="size-4 text-ok" aria-hidden />Active · <span className="font-mono">{p.passportId}</span></p>
              <p className="text-xs text-ink-3">Issued {formatDate(p.issuedAt)} · valid till {formatDate(p.expiresAt)}</p>
              <a href={p.verifyUrl} target="_blank" rel="noreferrer" className="mt-1 inline-flex items-center gap-1 text-xs font-medium text-brand-700 hover:underline">
                <LuExternalLink className="size-3.5" aria-hidden />Open verification page
              </a>
            </div>
          </div>
        ) : d.eligibility.eligible ? (
          <p className="text-[13px] text-ink-2">Eligible. Issuing signs the current check statuses; pending and simulated checks stay “pending”.</p>
        ) : (
          <Notice tone="warn" title="Not eligible yet">
            <ul className="mt-1 list-disc space-y-0.5 pl-4">{d.eligibility.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
          </Notice>
        )}
        <div className="grid gap-2">
          <Button icon={LuQrCode} variant={p ? "secondary" : "primary"} disabled={!d.eligibility.eligible} loading={issue.isPending}
            onClick={() => void issue.mutate(undefined)}>{p ? "Regenerate passport" : "Issue passport"}</Button>
          {p && <Button variant="outline" icon={LuBan} onClick={() => setRevoking(true)}>Revoke</Button>}
        </div>
        {issue.error ? <Notice tone="error" title="Not issued">{errorMessage(issue.error)}</Notice> : null}
      </div>
      {d.history.length > 0 && (
        <ul className="divide-y divide-line border-t border-line">
          {d.history.map((h) => (
            <li key={h.passportId} className="px-5 py-2 text-xs text-ink-2">
              <span className="font-mono">{h.passportId}</span> · {formatDate(h.issuedAt)} ·{" "}
              <span className={cx("font-medium", h.status === "active" ? "text-ok" : h.status === "revoked" ? "text-bad" : "text-ink-3")}>{h.status}</span>
              {h.reason && <span className="block text-ink-3">{h.reason}</span>}
            </li>
          ))}
        </ul>
      )}
      <Modal open={revoking} onClose={() => (setRevoking(false), revoke.reset(), setReasonError(""))} title="Revoke passport" footer={<>
        <Button variant="secondary" onClick={() => setRevoking(false)}>Cancel</Button>
        <Button variant="danger" icon={LuShieldX} loading={revoke.isPending} onClick={() => {
          if (reason.trim().length < 10) return setReasonError("Give a reason of at least 10 characters. Anyone verifying the passport will see it.");
          setReasonError("");
          void revoke.mutate(reason.trim());
        }}>Revoke</Button>
      </>}>
        <Field label="Reason" htmlFor="revoke-reason" error={reasonError} required hint="Shown on the public verification page and recorded in the evidence chain.">
          <textarea id="revoke-reason" rows={3} value={reason} onChange={(e) => setReason(e.target.value)} className={inputCls} />
        </Field>
        {revoke.error ? <div className="mt-3"><Notice tone="error" title="Not revoked">{errorMessage(revoke.error)}</Notice></div> : null}
        <p className="mt-3 flex items-start gap-1.5 text-xs text-ink-3"><LuCircleAlert className="mt-0.5 size-3.5 shrink-0" aria-hidden />Revoking can't be undone. You can issue a new passport later if the candidate is still eligible.</p>
      </Modal>
    </Card>
  );
}
