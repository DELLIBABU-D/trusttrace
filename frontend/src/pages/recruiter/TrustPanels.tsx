import { useState } from "react";
import { LuCheck, LuCircleAlert, LuClock, LuEye, LuHistory, LuInfo, LuNetwork, LuShieldCheck } from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { recruiterApi } from "../../api/endpoints";
import type { CheckBucket, PatternAlertRow, RelationshipGraph, TrustReport, TrustCheckRow } from "../../api/types";
import { Button, Card, CardHeader, EmptyState, Field, Modal, Notice, Pill, cx, inputCls } from "../../components/ui";
import { formatDateTime } from "../../lib/format";
import { useMutation } from "../../lib/query";
import { Link } from "../../lib/router";

const BUCKET_META: Record<CheckBucket, { label: string; tone: "green" | "blue" | "amber" | "red" | "gray" }> = {
  verified: { label: "Verified", tone: "green" },
  consistent: { label: "Consistent – not independently confirmed", tone: "blue" },
  pending: { label: "Pending", tone: "gray" },
  needs_review: { label: "Needs review", tone: "amber" },
  inconsistent: { label: "Inconsistent", tone: "red" },
  not_started: { label: "Not started", tone: "gray" },
};
const ORDER: CheckBucket[] = ["inconsistent", "needs_review", "verified", "consistent", "pending", "not_started"];
const REVIEWABLE = new Set(["identity", "education", "employment", "resume"]);
export const riskMeta = (risk: string | null | undefined) =>
  risk === "low" ? { label: "Few concerns found", tone: "green" as const } : risk === "review" ? { label: "Needs review", tone: "amber" as const }
    : risk === "high" ? { label: "Several concerns", tone: "red" as const } : { label: "Not scored", tone: "gray" as const };

/* ------------------------------------------------------------------ score explanation */

export function ScoreExplanation({ r }: { r: TrustReport }) {
  const t = r.trust;
  const [showAll, setShowAll] = useState(false);
  if (!t) return null;
  const applied = t.entries.filter((e) => e.applied !== 0);
  const other = t.entries.filter((e) => e.applied === 0);
  const sum = applied.reduce((n, e) => n + e.applied, 0);
  return (
    <Card>
      <CardHeader title="How this score was calculated" sub={`Rules ${t.version} · computed ${formatDateTime(t.computedAt)}`} />
      <div className="px-5 pb-4">
        <p className="rounded-lg bg-surface px-3.5 py-2.5 text-[13.5px] tabular-nums text-ink">
          Baseline <strong>{t.baseline}</strong> {sum >= 0 ? "+" : "−"} {Math.abs(sum)} from {applied.length} rule{applied.length === 1 ? "" : "s"} = <strong>{t.rawScore}</strong>
          {t.rawScore !== t.score && <> → limited to <strong>{t.score}</strong></>}
        </p>
        <p className="mt-2 flex items-start gap-1.5 text-xs text-ink-3"><LuInfo className="mt-0.5 size-3.5 shrink-0" aria-hidden />{t.disclaimer}</p>
      </div>
      {applied.length === 0 ? (
        <p className="border-t border-line px-5 py-3 text-[13px] text-ink-3">No rule has fired yet, so the score is the baseline. {t.pendingCount} check(s) are pending and add nothing until completed.</p>
      ) : (
        <ul className="divide-y divide-line border-t border-line">
          {applied.map((e, i) => <EntryRow key={i} e={e} />)}
        </ul>
      )}
      {other.length > 0 && (
        <div className="border-t border-line px-5 py-3">
          <button className="text-[13px] font-medium text-brand-700 hover:underline" onClick={() => setShowAll((v) => !v)} aria-expanded={showAll}>
            {showAll ? "Hide" : "Show"} {other.length} resolved or capped item{other.length === 1 ? "" : "s"} (no effect on the score)
          </button>
          {showAll && <ul className="mt-2 divide-y divide-line rounded-lg border border-line">{other.map((e, i) => <EntryRow key={i} e={e} />)}</ul>}
        </div>
      )}
      {t.assessment.length > 0 && (
        <div className="border-t border-line px-5 py-3 text-[13px] text-ink-2">
          <p className="font-medium text-ink">Assessment results (reported separately, not part of the score)</p>
          {t.assessment.map((a) => <p key={a.id}>{a.title}: {a.score != null ? `${a.score}/${a.maxScore} (${a.percent}%)` : a.status.replace("_", " ")}{a.reviewSignals ? ` · ${a.reviewSignals} review signal(s)` : ""}</p>)}
        </div>
      )}
    </Card>
  );
}

function EntryRow({ e }: { e: NonNullable<TrustReport["trust"]>["entries"][number] }) {
  return (
    <li className="px-5 py-3 text-[13.5px]">
      <div className="flex items-start gap-3">
        <span className={cx("w-12 shrink-0 text-right font-semibold tabular-nums", e.applied > 0 ? "text-ok" : e.applied < 0 ? "text-bad" : "text-ink-3")}>
          {e.applied > 0 ? `+${e.applied}` : e.applied < 0 ? e.applied : "0"}
        </span>
        <div className="min-w-0 flex-1">
          <p className="font-medium text-ink">{e.label}</p>
          <p className="text-xs text-ink-3"><code>{e.ruleId}</code> · weight {e.weight > 0 ? `+${e.weight}` : e.weight}{e.at ? ` · evidence from ${formatDateTime(e.at)}` : ""}</p>
          <ul className="mt-1 space-y-0.5 text-xs text-ink-2">
            {e.evidence.map((x, j) => <li key={j}>• {x.label}{x.at ? ` (${formatDateTime(x.at)})` : ""} <span className="text-ink-3">[{x.type.replace(/_/g, " ")}]</span></li>)}
          </ul>
          {e.note && <p className="mt-1 text-xs text-ink-2">{e.note}</p>}
        </div>
        {e.status !== "applied" && <Pill tone={e.status === "resolved" ? "green" : "gray"}>{e.status === "resolved" ? "Resolved" : "Capped"}</Pill>}
      </div>
    </li>
  );
}

/* ------------------------------------------------------------------ checks grouped by status, with resolve/uphold */

export function CheckGroups({ r, appId }: { r: TrustReport; appId: string }) {
  const [target, setTarget] = useState<TrustCheckRow | null>(null);
  const [status, setStatus] = useState<"resolved" | "upheld">("resolved");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const review = useMutation((b: { check: string; status: "resolved" | "upheld"; note: string }) =>
    recruiterApi.reviewCheck(appId, b.check as "identity", { status: b.status, note: b.note }), {
    invalidates: [`recruiter:report:${appId}`, "recruiter:dashboard", "recruiter:applicants"], onSuccess: () => (setTarget(null), setNote("")),
  });
  const t = r.trust;
  if (!t) return null;
  const byBucket = (b: CheckBucket) => t.checks.filter((c) => c.bucket === b);
  return (
    <Card>
      <CardHeader title="Checks by status" sub="Only completed checks with real outside confirmation count as Verified. Simulated data is never counted." />
      <div className="space-y-4 px-5 pb-5">
        {ORDER.filter((b) => byBucket(b).length).map((b) => (
          <section key={b} aria-label={BUCKET_META[b].label}>
            <p className="mb-1.5"><Pill tone={BUCKET_META[b].tone}>{BUCKET_META[b].label} · {byBucket(b).length}</Pill></p>
            <ul className="divide-y divide-line rounded-lg border border-line">
              {byBucket(b).map((c) => (
                <li key={c.key} className="flex flex-wrap items-start gap-3 px-3.5 py-2.5 text-[13.5px]">
                  <div className="min-w-0 flex-1">
                    <p className="font-medium text-ink">{c.title}{c.simulated && <span className="ml-2 align-middle"><Pill tone="violet">Simulated</Pill></span>}</p>
                    <p className="text-[13px] text-ink-3">{c.detail}</p>
                    {c.review && <p className="mt-1 text-xs text-ink-2">{c.review.status === "resolved" ? "Resolved" : "Upheld"} by a reviewer {formatDateTime(c.review.at)}: “{c.review.note}”</p>}
                  </div>
                  {REVIEWABLE.has(c.key) && (b === "inconsistent" || b === "needs_review") && (
                    <Button size="sm" variant="secondary" onClick={() => (setTarget(c), setStatus("resolved"), setErr(""))}>{c.review ? "Review again" : "Review"}</Button>
                  )}
                </li>
              ))}
            </ul>
          </section>
        ))}
      </div>
      <Modal open={!!target} onClose={() => setTarget(null)} title={`Review: ${target?.title ?? ""}`} footer={<>
        <Button variant="secondary" onClick={() => setTarget(null)}>Cancel</Button>
        <Button loading={review.isPending} onClick={() => (note.trim().length < 10 ? setErr("Explain your decision in at least 10 characters. It's kept in the audit log.") : (setErr(""), void review.mutate({ check: target!.key, status, note: note.trim() })))}>Save review</Button>
      </>}>
        <fieldset className="space-y-2 text-[13.5px]">
          <legend className="mb-1 text-[13px] font-medium text-ink">Outcome</legend>
          <label className="flex items-start gap-2"><input type="radio" name="crv" checked={status === "resolved"} onChange={() => setStatus("resolved")} className="mt-1 size-4 accent-brand-600" />
            <span><strong>Resolved / explained</strong> – the concern has an acceptable explanation. Its penalty is removed; the evidence stays visible.</span></label>
          <label className="flex items-start gap-2"><input type="radio" name="crv" checked={status === "upheld"} onChange={() => setStatus("upheld")} className="mt-1 size-4 accent-brand-600" />
            <span><strong>Upheld</strong> – you checked it and the concern stands.</span></label>
        </fieldset>
        <Field label="Note" htmlFor="crv-note" error={err} required className="mt-3"><textarea id="crv-note" rows={3} className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        <p className="mt-2 text-xs text-ink-3">If the document or findings change later, this review no longer applies and the check is evaluated again.</p>
        {review.error ? <div className="mt-2"><Notice tone="error">{errorMessage(review.error)}</Notice></div> : null}
      </Modal>
    </Card>
  );
}

/* ------------------------------------------------------------------ suspicious patterns */

export function PatternAlerts({ alerts, appId }: { alerts: PatternAlertRow[]; appId: string }) {
  const [target, setTarget] = useState<PatternAlertRow | null>(null);
  const [status, setStatus] = useState<"reviewed_ok" | "confirmed">("reviewed_ok");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const review = useMutation((b: { id: string; status: "reviewed_ok" | "confirmed"; note: string }) => recruiterApi.reviewPattern(appId, b.id, { status: b.status, note: b.note }), {
    invalidates: [`recruiter:report:${appId}`, "recruiter:dashboard", "recruiter:applicants"], onSuccess: () => (setTarget(null), setNote("")),
  });
  const ev = (a: PatternAlertRow) => Object.entries(a.evidence).filter(([k]) => !["from", "to"].includes(k)).map(([k, v]) => `${k.replace(/([A-Z])/g, " $1").toLowerCase()}: ${Array.isArray(v) ? v.join(", ") : String(v)}`).join(" · ");
  return (
    <Card>
      <CardHeader title="Application patterns" sub="Rule-based signals from timestamps and (hashed) device identifiers. Weak signals: they prompt a review, they don't prove anything." />
      {alerts.length === 0 ? <EmptyState compact icon={LuShieldCheck} title="No unusual patterns found" /> : (
        <ul className="divide-y divide-line">
          {alerts.map((a) => (
            <li key={a.id} className="px-5 py-3 text-[13.5px]">
              <div className="flex flex-wrap items-center gap-2">
                <LuCircleAlert className={cx("size-4", a.reviewStatus === "open" ? "text-warn" : "text-ink-3")} aria-hidden />
                <span className="flex-1 font-medium text-ink">{a.label}</span>
                <Pill tone="gray">{a.strength} signal</Pill>
                <Pill tone={a.reviewStatus === "open" ? "amber" : a.reviewStatus === "confirmed" ? "red" : "green"}>{a.reviewStatus === "open" ? "Open" : a.reviewStatus === "confirmed" ? "Confirmed by reviewer" : "Reviewed – OK"}</Pill>
              </div>
              <p className="mt-1 text-xs text-ink-3"><code>{a.ruleId}</code> · {formatDateTime(a.firstSeen)}{a.lastSeen !== a.firstSeen ? ` – ${formatDateTime(a.lastSeen)}` : ""} · {ev(a)}</p>
              <p className="mt-0.5 text-xs text-ink-2">{a.explanation}</p>
              {a.reviewNote && <p className="mt-1 text-xs text-ink-2">Review: “{a.reviewNote}”</p>}
              {a.reviewStatus === "open" && <Button size="sm" variant="secondary" className="mt-2" onClick={() => (setTarget(a), setErr(""))}>Review</Button>}
            </li>
          ))}
        </ul>
      )}
      <Modal open={!!target} onClose={() => setTarget(null)} title={`Review: ${target?.label ?? ""}`} footer={<>
        <Button variant="secondary" onClick={() => setTarget(null)}>Cancel</Button>
        <Button loading={review.isPending} onClick={() => (note.trim().length < 10 ? setErr("Write at least 10 characters.") : (setErr(""), void review.mutate({ id: target!.id, status, note: note.trim() })))}>Save review</Button>
      </>}>
        <fieldset className="space-y-2 text-[13.5px]">
          <label className="flex items-start gap-2"><input type="radio" name="prv" checked={status === "reviewed_ok"} onChange={() => setStatus("reviewed_ok")} className="mt-1 size-4 accent-brand-600" /><span><strong>Reviewed – OK</strong> (innocent explanation)</span></label>
          <label className="flex items-start gap-2"><input type="radio" name="prv" checked={status === "confirmed"} onChange={() => setStatus("confirmed")} className="mt-1 size-4 accent-brand-600" /><span><strong>Confirmed</strong> – you independently confirmed misuse</span></label>
        </fieldset>
        <Field label="Note" htmlFor="prv-note" error={err} required className="mt-3"><textarea id="prv-note" rows={3} className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
        {review.error ? <div className="mt-2"><Notice tone="error">{errorMessage(review.error)}</Notice></div> : null}
      </Modal>
    </Card>
  );
}

/* ------------------------------------------------------------------ relationship graph (SVG) */

const EDGE_STYLE = { strong: { w: 3, dash: "", color: "#c42b2b" }, medium: { w: 2, dash: "6 4", color: "#d49a1c" }, weak: { w: 1.5, dash: "2 4", color: "#77858f" } };
const SIGNAL_ICON: Record<string, string> = { phone: "☎", face: "☺", device: "▣", network: "⌁" };

export function LinkedProfiles({ g }: { g: RelationshipGraph }) {
  const W = 560, H = 320, cx0 = W / 2, cy0 = H / 2;
  const focal = g.nodes.find((n) => n.focal);
  const signals = g.nodes.filter((n) => n.kind !== "candidate");
  const others = g.nodes.filter((n) => n.kind === "candidate" && !n.focal);
  const pos: Record<string, { x: number; y: number }> = {};
  if (focal) pos[focal.id] = { x: cx0, y: cy0 };
  signals.forEach((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(1, signals.length) - Math.PI / 2;
    pos[n.id] = { x: cx0 + 95 * Math.cos(a), y: cy0 + 75 * Math.sin(a) };
  });
  others.forEach((n, i) => {
    const a = (2 * Math.PI * i) / Math.max(1, others.length) - Math.PI / 2 + 0.3;
    pos[n.id] = { x: cx0 + 220 * Math.cos(a), y: cy0 + 125 * Math.sin(a) };
  });
  return (
    <Card>
      <CardHeader title="Linked profiles" sub="Other candidate accounts that share a verified mobile number, face, browser or network with this candidate." />
      {g.linked.length === 0 ? <EmptyState compact icon={LuNetwork} title="No linked accounts">Nothing is shared with any other candidate account. A matching name alone is never a link.</EmptyState> : (
        <>
          <div className="overflow-x-auto px-5">
            <svg viewBox={`0 0 ${W} ${H}`} className="mx-auto w-full max-w-[560px]" role="img" aria-label={`Relationship graph: ${g.linked.length} linked account(s)`}>
              {g.edges.map((e, i) => {
                const a = pos[e.source], b = pos[e.target], s = EDGE_STYLE[e.strength];
                return a && b ? <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} stroke={s.color} strokeWidth={s.w} strokeDasharray={s.dash} opacity={0.85} /> : null;
              })}
              {signals.map((n) => (
                <g key={n.id} transform={`translate(${pos[n.id].x},${pos[n.id].y})`}>
                  <rect x={-14} y={-14} width={28} height={28} rx={6} fill="#fff" stroke="#cfd7db" />
                  <text textAnchor="middle" dy="5" fontSize="14">{SIGNAL_ICON[n.kind]}</text>
                </g>
              ))}
              {[focal, ...others].filter(Boolean).map((n) => (
                <g key={n!.id} transform={`translate(${pos[n!.id].x},${pos[n!.id].y})`}>
                  <circle r={n!.focal ? 22 : 17} fill={n!.focal ? "#047263" : n!.appliedToYourOrg ? "#d4eee7" : "#e3e8eb"} stroke="#fff" strokeWidth="2" />
                  <text textAnchor="middle" y={n!.focal ? 38 : 32} fontSize="11" fill="#4a5965" stroke="#fff" strokeWidth={4} paintOrder="stroke">{n!.label.length > 26 ? n!.label.slice(0, 25) + "…" : n!.label}</text>
                </g>
              ))}
            </svg>
          </div>
          <div className="flex flex-wrap gap-x-4 gap-y-1 px-5 pb-2 text-xs text-ink-3">
            <span><span className="mr-1 inline-block h-0.5 w-5 bg-bad align-middle" />Strong (same verified mobile / very similar face)</span>
            <span><span className="mr-1 inline-block h-0.5 w-5 border-t-2 border-dashed border-warn align-middle" />Medium (same browser)</span>
            <span><span className="mr-1 inline-block h-0.5 w-5 border-t-2 border-dotted border-ink-3 align-middle" />Weak (same network)</span>
            <span>☎ mobile · ☺ face · ▣ browser · ⌁ network</span>
          </div>
          <ul className="divide-y divide-line border-t border-line">
            {g.linked.map((l, i) => (
              <li key={i} className="flex flex-wrap items-center gap-2 px-5 py-2.5 text-[13.5px]">
                <span className="flex-1 font-medium text-ink">{l.account}</span>
                {l.signals.map((s, j) => <Pill key={j} tone={s.strength === "strong" ? "red" : s.strength === "medium" ? "amber" : "gray"}>{s.label}{s.review === "not_duplicate" ? " (dismissed)" : ""}</Pill>)}
                {l.applicationId && <Link to={`/recruiter/applicants/${l.applicationId}`} className="text-[13px] font-medium text-brand-700 hover:underline">Open report</Link>}
              </li>
            ))}
          </ul>
          <p className="px-5 py-3 text-xs text-ink-3">{g.note} Cluster size (strong and medium links): {g.clusterSize} account(s). Accounts that didn't apply to your organisation stay anonymous.</p>
        </>
      )}
    </Card>
  );
}

/* ------------------------------------------------------------------ mark reviewed & score history */

export function ReviewTrail({ r, appId }: { r: TrustReport; appId: string }) {
  const [note, setNote] = useState("");
  const mark = useMutation(() => recruiterApi.markReviewed(appId, note.trim()), { invalidates: [`recruiter:report:${appId}`], onSuccess: () => setNote("") });
  const current = r.reportReviews?.find((x) => x.current);
  return (
    <Card>
      <CardHeader title="Review record" sub="Each review is tied to the exact score version you saw. Audit records can't be edited." />
      <div className="space-y-2 px-5 pb-4">
        {current ? <Notice tone="success" title="Reviewed">This version was reviewed by {current.reviewer} on {formatDateTime(current.at)}.</Notice>
          : <p className="flex items-center gap-1.5 text-[13px] text-ink-2"><LuClock className="size-4 text-ink-3" aria-hidden />The current version hasn't been reviewed.</p>}
        <label htmlFor="mr-note" className="sr-only">Review note</label>
        <input id="mr-note" className={inputCls} placeholder="Optional note" value={note} onChange={(e) => setNote(e.target.value)} />
        <Button className="w-full" variant="secondary" icon={LuEye} loading={mark.isPending} onClick={() => void mark.mutate(undefined)}>Mark reviewed</Button>
        {mark.error ? <Notice tone="error">{errorMessage(mark.error)}</Notice> : null}
      </div>
      {(r.scoreHistory?.length ?? 0) > 0 && (
        <div className="border-t border-line px-5 py-3">
          <p className="mb-1.5 flex items-center gap-1.5 text-[13px] font-medium text-ink"><LuHistory className="size-4 text-ink-3" aria-hidden />Score history</p>
          <ul className="space-y-1 text-xs text-ink-2">
            {r.scoreHistory!.slice(0, 6).map((h) => <li key={h.id} className="flex justify-between gap-2"><span>{formatDateTime(h.at)} · {h.trigger.replace(/_/g, " ")}</span><span className="font-semibold tabular-nums">{h.score}</span></li>)}
          </ul>
        </div>
      )}
      {(r.reportReviews?.length ?? 0) > 0 && (
        <ul className="divide-y divide-line border-t border-line">
          {r.reportReviews!.map((x) => <li key={x.id} className="px-5 py-2 text-xs text-ink-2"><LuCheck className="mr-1 inline size-3.5 text-ok" aria-hidden />{x.reviewer} · {formatDateTime(x.at)} · score {x.score}{x.note ? ` · “${x.note}”` : ""}</li>)}
        </ul>
      )}
    </Card>
  );
}
