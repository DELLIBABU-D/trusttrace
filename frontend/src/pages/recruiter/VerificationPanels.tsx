import { DigiLockerCompare } from "../../components/DigiLockerCompare";
import { SkillEvidence } from "./Assessments";
import { useState } from "react";
import { LuCopy, LuLink, LuScanFace, LuShieldAlert, LuUserCheck } from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { recruiterApi } from "../../api/endpoints";
import type { DuplicateAlertRow, TrustReport as Report } from "../../api/types";
import { ComparisonRows, FindingsList, IssuerBox, RunVerificationBar, useVerificationJob } from "../../components/Verify";
import { Button, Card, CardHeader, Field, Modal, Notice, Pill, inputCls } from "../../components/ui";
import { formatDateTime } from "../../lib/format";
import { useMutation } from "../../lib/query";

export function RecruiterRunBar({ appId }: { appId: string }) {
  const v = useVerificationJob(`recruiter:job:${appId}`, () => recruiterApi.verificationJob(appId), () => recruiterApi.runVerification(appId),
    `recruiter:report:${appId},recruiter:dashboard,recruiter:applicants`);
  return (
    <Card className="mt-5 p-4">
      <RunVerificationBar {...v} label="Run verification" />
      <p className="mt-2 text-xs text-ink-3">Reads the candidate's uploaded documents and profile, compares them with fixed rules, rechecks face and duplicates. Results are evidence for your review; nothing is decided automatically.</p>
    </Card>
  );
}

export function SectionDetail({ tab, r, appId }: { tab: string; r: Report; appId: string }) {
  if (tab === "assessment") return <SkillEvidence appId={appId} />;
  const v = r.verification;
  if (!v) return null;
  if (tab === "education") {
    return (
      <>
        <Card>
          <CardHeader title="Document consistency" sub={v.education.summary ?? undefined} />
          <div className="px-5 pb-4"><ComparisonRows rows={v.education.comparison ?? []} empty="No marksheet or certificate compared yet." /></div>
          {v.education.findings?.length ? <div className="border-t border-line px-5 py-4"><FindingsList findings={v.education.findings} /></div> : null}
        </Card>
        {v.education.digilocker && !["off", "not_connected"].includes(v.education.digilocker.status) && (
          <Card>
            <CardHeader title="DigiLocker comparison" sub="The issuer's own copy, pulled by the candidate with consent, compared with the uploaded certificate." />
            <div className="px-5 pb-5"><DigiLockerCompare c={v.education.digilocker} /></div>
          </Card>
        )}
        <IssuerCard appId={appId} r={r} />
      </>
    );
  }
  if (tab === "employment") {
    return (
      <>
        <Card>
          <CardHeader title="Experience letter vs profile" sub={v.employment.summary ?? undefined} />
          <div className="px-5 pb-4"><ComparisonRows rows={v.employment.comparison ?? []} empty="No experience letter compared yet." /></div>
          {v.employment.findings?.length ? <div className="border-t border-line px-5 py-4"><FindingsList findings={v.employment.findings} /></div> : null}
        </Card>
        <Card>
          <CardHeader title="Resume vs profile" sub={v.resume.summary ?? undefined} />
          <div className="px-5 pb-4"><ComparisonRows rows={v.resume.comparison ?? []} empty="No resume compared yet." /></div>
          {v.resume.findings?.length ? <div className="border-t border-line px-5 py-4"><FindingsList findings={v.resume.findings} /></div> : null}
        </Card>
        <ReferenceCard appId={appId} r={r} />
      </>
    );
  }
  if (tab === "identity") {
    const id = v.identity;
    return (
      <Card>
        <CardHeader title="Face continuity" sub={id.summary ?? undefined} />
        <dl className="divide-y divide-line px-5 pb-4 text-[13.5px]">
          <div className="grid grid-cols-[150px_1fr] gap-3 py-2"><dt className="text-ink-3">Enrolment</dt><dd>{id.enrolment?.status === "enrolled" ? `Enrolled ${formatDateTime(id.enrolment.at ?? null)}` : "Not enrolled"}</dd></div>
          <div className="grid grid-cols-[150px_1fr] gap-3 py-2"><dt className="text-ink-3">ID document photo</dt><dd>{id.idDocument?.label ?? "Not compared"}{id.idDocument?.similarity != null && ` · similarity ${id.idDocument.similarity.toFixed(2)} (threshold ${id.idDocument.threshold})`}</dd></div>
          <div className="grid grid-cols-[150px_1fr] gap-3 py-2"><dt className="text-ink-3">Model</dt><dd>{id.enrolment?.model ?? "—"}</dd></div>
        </dl>
        <div className="border-t border-line px-5 py-3"><Notice tone="info">Liveness (anti-spoofing) is not checked. A printed photo or screen can pass. Treat face results as supporting evidence.</Notice></div>
      </Card>
    );
  }
  if (tab === "risk") return <DuplicateCard appId={appId} alerts={r.duplicateAlerts ?? []} />;
  return null;
}

function IssuerCard({ appId, r }: { appId: string; r: Report }) {
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState<"confirmed" | "denied" | "no_record">("confirmed");
  const [detail, setDetail] = useState("");
  const [reference, setReference] = useState("");
  const [err, setErr] = useState("");
  const save = useMutation(() => recruiterApi.issuerConfirmation(appId, { result, detail, reference }), {
    invalidates: [`recruiter:report:${appId}`, `recruiter:job:${appId}`], onSuccess: () => (setOpen(false), setDetail(""), setReference("")),
  });
  return (
    <Card className="p-5">
      <IssuerBox issuer={r.verification?.education.issuer} />
      <div className="mt-3 flex flex-wrap items-center gap-3">
        <Button variant="secondary" size="sm" icon={LuUserCheck} onClick={() => setOpen(true)}>Record issuer confirmation</Button>
        <span className="text-xs text-ink-3">Use this after you contact the university or board yourself.</span>
      </div>
      <Modal open={open} onClose={() => setOpen(false)} title="Record issuer confirmation" footer={<>
        <Button variant="secondary" onClick={() => setOpen(false)}>Cancel</Button>
        <Button loading={save.isPending} onClick={() => { if (detail.trim().length < 10) return setErr("Describe who confirmed it and how (at least 10 characters)."); setErr(""); void save.mutate(undefined); }}>Save</Button>
      </>}>
        <div className="space-y-4">
          <Field label="What did the issuer say?" htmlFor="issuer-result">
            <select id="issuer-result" className={inputCls} value={result} onChange={(e) => setResult(e.target.value as typeof result)}>
              <option value="confirmed">Confirmed the record is genuine</option>
              <option value="denied">Said the record is not genuine</option>
              <option value="no_record">Has no matching record</option>
            </select>
          </Field>
          <Field label="Details" htmlFor="issuer-detail" error={err} required hint="Who you contacted, how, and what they said. Stored in the audit log with your name.">
            <textarea id="issuer-detail" rows={3} className={inputCls} value={detail} onChange={(e) => setDetail(e.target.value)} />
          </Field>
          <Field label="Reference (optional)" htmlFor="issuer-ref" hint="e.g. email subject, letter number"><input id="issuer-ref" className={inputCls} value={reference} onChange={(e) => setReference(e.target.value)} /></Field>
          {save.error ? <Notice tone="error" title="Not saved">{errorMessage(save.error)}</Notice> : null}
        </div>
      </Modal>
    </Card>
  );
}

function ReferenceCard({ appId, r }: { appId: string; r: Report }) {
  const refs = r.verification?.employment.references ?? [];
  const profileRefs = r.profile?.references ?? [];
  const [choice, setChoice] = useState(profileRefs[0]?.id ?? "manual");
  const [name, setName] = useState("");
  const [contact, setContact] = useState("");
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const create = useMutation(() => recruiterApi.referenceRequest(appId, choice === "manual" ? { refereeName: name, refereeContact: contact } : { referenceId: choice }), {
    invalidates: [`recruiter:report:${appId}`], onSuccess: (res) => (setLink(res.link), setCopied(false)),
  });
  const simulate = useMutation((p: { id: string; confirmed: boolean }) => recruiterApi.simulateReference(appId, p.id, { confirmed: p.confirmed, comments: "" }), {
    invalidates: [`recruiter:report:${appId}`, `recruiter:job:${appId}`],
  });
  return (
    <Card>
      <CardHeader title="Reference / HR confirmation" sub="Send a one-time link. Employment counts as confirmed only when the referee actually answers." />
      <div className="space-y-3 px-5 pb-5">
        {refs.length > 0 && (
          <ul className="divide-y divide-line rounded-lg border border-line">
            {refs.map((x) => (
              <li key={x.id} className="flex flex-wrap items-center gap-2 px-3.5 py-2.5 text-[13px]">
                <span className="flex-1"><span className="font-medium text-ink">{x.referee}</span> <span className="text-ink-3">· {x.company || "employer"}{x.respondedAt ? ` · ${formatDateTime(x.respondedAt)}` : ""}</span></span>
                {x.simulated && <Pill tone="violet">Simulated</Pill>}
                <Pill tone={x.status === "sent" ? "amber" : x.status !== "responded" ? "gray" : x.confirmed ? "green" : "red"}>
                  {x.status === "sent" ? "Awaiting reply" : x.status !== "responded" ? x.status : x.confirmed ? "Confirmed" : "Not confirmed"}
                </Pill>
                {x.status === "sent" && (
                  <span className="flex gap-1">
                    <Button size="sm" variant="ghost" onClick={() => void simulate.mutate({ id: x.id, confirmed: true })} title="Hackathon testing only">Simulate yes</Button>
                    <Button size="sm" variant="ghost" onClick={() => void simulate.mutate({ id: x.id, confirmed: false })} title="Hackathon testing only">Simulate no</Button>
                  </span>
                )}
              </li>
            ))}
          </ul>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Who should confirm?" htmlFor="ref-choice" className="sm:col-span-2">
            <select id="ref-choice" className={inputCls} value={choice} onChange={(e) => setChoice(e.target.value)}>
              {profileRefs.map((p) => <option key={p.id} value={p.id}>{p.name} ({p.relationship}{p.company ? `, ${p.company}` : ""})</option>)}
              <option value="manual">Another HR contact…</option>
            </select>
          </Field>
          {choice === "manual" && <>
            <Field label="HR / referee name" htmlFor="ref-name"><input id="ref-name" className={inputCls} value={name} onChange={(e) => setName(e.target.value)} /></Field>
            <Field label="Email or phone" htmlFor="ref-contact"><input id="ref-contact" className={inputCls} value={contact} onChange={(e) => setContact(e.target.value)} /></Field>
          </>}
        </div>
        <Button variant="secondary" icon={LuLink} loading={create.isPending} onClick={() => void create.mutate(undefined)}>Create confirmation link</Button>
        {create.error ? <Notice tone="error" title="Link not created">{errorMessage(create.error)}</Notice> : null}
        {simulate.error ? <Notice tone="error">{errorMessage(simulate.error)}</Notice> : null}
        {link && (
          <Notice tone="success" title="Send this link to the referee">
            <span className="break-all">{link}</span>
            <button className="ml-2 inline-flex items-center gap-1 font-medium underline" onClick={() => void navigator.clipboard?.writeText(link).then(() => setCopied(true))}>
              <LuCopy className="size-3.5" aria-hidden /> {copied ? "Copied" : "Copy"}
            </button>
            <span className="mt-1 block text-xs">No email service is connected, so share it yourself (email or WhatsApp). It works once and expires in 14 days.</span>
          </Notice>
        )}
        <p className="text-xs text-ink-3">"Simulate" buttons are for hackathon demos only. Simulated answers are labelled and never count as verification.</p>
      </div>
    </Card>
  );
}

function DuplicateCard({ appId, alerts }: { appId: string; alerts: DuplicateAlertRow[] }) {
  const [target, setTarget] = useState<DuplicateAlertRow | null>(null);
  const [status, setStatus] = useState<"not_duplicate" | "confirmed_duplicate">("not_duplicate");
  const [note, setNote] = useState("");
  const [err, setErr] = useState("");
  const review = useMutation(() => recruiterApi.reviewDuplicate(appId, target!.id, { status, note }), {
    invalidates: [`recruiter:report:${appId}`, `recruiter:job:${appId}`], onSuccess: () => (setTarget(null), setNote("")),
  });
  return (
    <Card>
      <CardHeader title="Potential duplicate profiles" sub="Raised only for the same verified mobile number or a very similar enrolled face. A matching name never raises an alert." />
      {alerts.length === 0 ? <p className="px-5 pb-5 text-[13px] text-ink-3">No duplicate alerts.</p> : (
        <ul className="divide-y divide-line">
          {alerts.map((a) => (
            <li key={a.id} className="flex flex-wrap items-start gap-3 px-5 py-3.5 text-[13.5px]">
              {a.kind === "face" ? <LuScanFace className="mt-0.5 size-5 text-warn" aria-hidden /> : <LuShieldAlert className="mt-0.5 size-5 text-warn" aria-hidden />}
              <div className="min-w-0 flex-1">
                <p className="font-medium text-ink">{a.kind === "face" ? "Very similar enrolled face" : "Same verified mobile number"} · {a.otherAccount}</p>
                <p className="text-[13px] text-ink-3">
                  {a.evidence.reason}{a.similarity != null && ` · similarity ${a.similarity.toFixed(2)} (alert threshold ${a.evidence.threshold})`}{a.evidence.phoneLast4 && ` · number ending ${a.evidence.phoneLast4}`}
                </p>
                {a.reviewNote && <p className="mt-1 text-xs text-ink-3">Review: {a.reviewNote}</p>}
              </div>
              <Pill tone={a.reviewStatus === "open" ? "amber" : a.reviewStatus === "confirmed_duplicate" ? "red" : "green"}>
                {a.reviewStatus === "open" ? "Needs review" : a.reviewStatus === "confirmed_duplicate" ? "Confirmed duplicate" : "Not a duplicate"}
              </Pill>
              <Button size="sm" variant="secondary" onClick={() => (setTarget(a), setStatus("not_duplicate"))}>Review</Button>
            </li>
          ))}
        </ul>
      )}
      <Modal open={target !== null} onClose={() => setTarget(null)} title="Review duplicate alert" footer={<>
        <Button variant="secondary" onClick={() => setTarget(null)}>Cancel</Button>
        <Button loading={review.isPending} onClick={() => { if (note.trim().length < 10) return setErr("Explain your decision (at least 10 characters)."); setErr(""); void review.mutate(undefined); }}>Save review</Button>
      </>}>
        <div className="space-y-4">
          <Field label="Your conclusion" htmlFor="dup-status">
            <select id="dup-status" className={inputCls} value={status} onChange={(e) => setStatus(e.target.value as typeof status)}>
              <option value="not_duplicate">Not a duplicate (e.g. family members sharing a phone)</option>
              <option value="confirmed_duplicate">Confirmed: same person with two accounts</option>
            </select>
          </Field>
          <Field label="Reason" htmlFor="dup-note" error={err} required><textarea id="dup-note" rows={3} className={inputCls} value={note} onChange={(e) => setNote(e.target.value)} /></Field>
          <p className="text-xs text-ink-3">The candidate is not blocked automatically either way.</p>
          {review.error ? <Notice tone="error" title="Not saved">{errorMessage(review.error)}</Notice> : null}
        </div>
      </Modal>
    </Card>
  );
}
