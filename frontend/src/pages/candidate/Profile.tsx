import { useEffect, useState } from "react";
import { z } from "zod";
import { LuDownload, LuFileUp, LuKeyRound, LuLink, LuMail, LuPlus, LuQrCode, LuShieldCheck, LuTrash2, LuX } from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { candidateApi } from "../../api/endpoints";
import type { CandidateProfile, EducationEntry, ExperienceEntry, ReferenceEntry } from "../../api/types";
import { DataState, NotLoaded } from "../../components/DataState";
import { PassportCard } from "../../components/PassportCard";
import { Avatar, Button, ButtonLink, Card, EmptyState, Field, Modal, Notice, PageHeader, ProgressBar, Spinner, cx, inputCls } from "../../components/ui";
import { useZodForm } from "../../lib/form";
import { formatDate, formatDateTime } from "../../lib/format";
import { useMutation, useQuery } from "../../lib/query";

/* ------------------------------------------------------------------ profile editing */

const profileSchema = z.object({
  fullName: z.string().trim().min(3, "Enter your full name"),
  email: z.string().trim().email("Enter a valid email address"),
  phone: z.string().trim().regex(/^[6-9][0-9]{9}$/, "Enter a 10-digit Indian mobile number"),
  location: z.string().trim().min(2, "Enter your city"),
  headline: z.string().trim().min(3, "Add a short headline, e.g. Frontend Developer").max(80, "Keep it under 80 characters"),
  linkedinUrl: z.union([z.literal(""), z.string().url("Enter a full URL starting with https://")]),
  githubUrl: z.union([z.literal(""), z.string().url("Enter a full URL starting with https://")]),
});
type ProfileValues = z.infer<typeof profileSchema>;

const yearRe = /^(19[7-9][0-9]|20[0-3][0-9])$/;
const eduRow = z.object({
  degree: z.string().trim().min(2, "Degree is required"),
  institution: z.string().trim().min(2, "Institution is required"),
  startYear: z.string().regex(yearRe, "Year like 2021"),
  endYear: z.string().regex(yearRe, "Year like 2025"),
  score: z.string().trim().max(20),
}).refine((e) => Number(e.endYear) >= Number(e.startYear), { path: ["endYear"], message: "Ends before it starts" });
const expRow = z.object({
  company: z.string().trim().min(2, "Company is required"),
  title: z.string().trim().min(2, "Job title is required"),
  start: z.string().regex(/^\d{4}-\d{2}$/, "Start month"),
  end: z.string(),
  current: z.boolean(),
}).refine((e) => e.current || /^\d{4}-\d{2}$/.test(e.end), { path: ["end"], message: "End month, or tick current" })
  .refine((e) => e.current || e.end >= e.start, { path: ["end"], message: "Ends before it starts" });
const refRow = z.object({
  name: z.string().trim().min(2, "Name is required"),
  relationship: z.string().trim().min(2, "e.g. Manager, Professor"),
  company: z.string().trim().max(160),
  email: z.union([z.literal(""), z.string().trim().email("Invalid email")]),
  phone: z.union([z.literal(""), z.string().trim().regex(/^\+?[0-9 ]{10,15}$/, "Invalid phone")]),
}).refine((r) => r.email || r.phone, { path: ["email"], message: "Give an email or phone" });

function rowErrors<T>(schema: z.ZodType<T>, rows: T[]): Record<string, string>[] {
  return rows.map((r) => {
    const res = schema.safeParse(r);
    return res.success ? {} : Object.fromEntries(res.error.issues.map((i) => [String(i.path[0]), i.message]));
  });
}

type Col<T> = { key: keyof T & string; label: string; type?: string; span?: number; placeholder?: string };

function RowsEditor<T extends object>({ title, rows, setRows, cols, blankRow, errors, showErrors, addLabel, max }: {
  title: string; rows: T[]; setRows: (r: T[]) => void; cols: Col<T>[]; blankRow: T; errors: Record<string, string>[]; showErrors: boolean; addLabel: string; max: number;
}) {
  const update = (i: number, key: keyof T, value: unknown) => setRows(rows.map((r, j) => (j === i ? { ...r, [key]: value } : r)));
  const slug = title.toLowerCase().replace(/\W+/g, "-");
  return (
    <section className="sm:col-span-2" aria-labelledby={`${slug}-h`}>
      <div className="mb-2 flex items-center justify-between">
        <h2 id={`${slug}-h`} className="text-[15px] font-semibold">{title}</h2>
        <Button variant="secondary" size="sm" icon={LuPlus} disabled={rows.length >= max} onClick={() => setRows([...rows, { ...blankRow }])}>{addLabel}</Button>
      </div>
      {rows.length === 0 && <p className="rounded-lg border border-dashed border-line px-4 py-3 text-[13px] text-ink-3">None added.</p>}
      <div className="space-y-3">
        {rows.map((row, i) => (
          <div key={i} className="grid gap-3 rounded-lg border border-line p-3.5 sm:grid-cols-6">
            {cols.map((c) => {
              const id = `${slug}-${i}-${c.key}`;
              const err = showErrors ? errors[i]?.[c.key] : undefined;
              return c.type === "checkbox" ? (
                <label key={c.key} className="flex items-center gap-2 self-end pb-2 text-[13px] text-ink-2 sm:col-span-1">
                  <input type="checkbox" className="size-4 accent-brand-600" checked={Boolean((row as Record<string, unknown>)[c.key])} onChange={(e) => update(i, c.key, e.target.checked)} /> {c.label}
                </label>
              ) : (
                <Field key={c.key} label={c.label} htmlFor={id} error={err} className={c.span === 3 ? "sm:col-span-3" : c.span === 2 ? "sm:col-span-2" : "sm:col-span-1"}>
                  <input id={id} type={c.type ?? "text"} placeholder={c.placeholder} className={inputCls} value={String((row as Record<string, unknown>)[c.key] ?? "")}
                    disabled={c.key === "end" && Boolean((row as Record<string, unknown>).current)} onChange={(e) => update(i, c.key, e.target.value)} />
                </Field>
              );
            })}
            <div className="flex items-end justify-end sm:col-span-6">
              <button type="button" onClick={() => setRows(rows.filter((_, j) => j !== i))} className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-bad hover:bg-bad-soft">
                <LuTrash2 className="size-3.5" aria-hidden /> Remove
              </button>
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

const blankEdu: EducationEntry = { degree: "", institution: "", startYear: "", endYear: "", score: "" };
const blankExp: ExperienceEntry = { company: "", title: "", start: "", end: "", current: false };
const blankRef: ReferenceEntry = { name: "", relationship: "", company: "", email: "", phone: "" };
const strip = <T extends { id?: string }>(rows: T[]) => rows.map(({ id: _id, ...r }) => r as T);
const blank: ProfileValues = { fullName: "", email: "", phone: "", location: "", headline: "", linkedinUrl: "", githubUrl: "" };

export function Profile() {
  const q = useQuery("candidate:profile", candidateApi.profile);
  const form = useZodForm(profileSchema, blank);
  const [skills, setSkills] = useState<string[]>([]);
  const [skillDraft, setSkillDraft] = useState("");
  const [edu, setEdu] = useState<EducationEntry[]>([]);
  const [exp, setExp] = useState<ExperienceEntry[]>([]);
  const [refs, setRefs] = useState<ReferenceEntry[]>([]);
  const [rowsTouched, setRowsTouched] = useState(false);
  const eduErr = rowErrors(eduRow, edu);
  const expErr = rowErrors(expRow, exp);
  const refErr = rowErrors(refRow, refs);
  const rowsOk = edu.length > 0 && [...eduErr, ...expErr, ...refErr].every((e) => Object.keys(e).length === 0);
  const save = useMutation((v: ProfileValues) => candidateApi.updateProfile({ ...v, skills, education: strip(edu), experience: strip(exp), references: strip(refs) }), { invalidates: ["candidate:"] });

  useEffect(() => {
    if (!q.data) return;
    const p: CandidateProfile = q.data;
    form.setValues({ fullName: p.fullName, email: p.email, phone: p.phone, location: p.location, headline: p.headline, linkedinUrl: p.linkedinUrl ?? "", githubUrl: p.githubUrl ?? "" });
    setSkills(p.skills);
    setEdu(p.education ?? []);
    setExp(p.experience ?? []);
    setRefs(p.references ?? []);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q.data]);

  function addSkill() {
    const s = skillDraft.trim();
    if (s && !skills.some((x) => x.toLowerCase() === s.toLowerCase()) && skills.length < 20) setSkills([...skills, s]);
    setSkillDraft("");
  }

  if (q.isLoading) return <Spinner />;
  const completeness = q.data?.completeness ?? 0;

  return (
    <div>
      <PageHeader title="My Profile" sub="Keep this matching your documents. Mismatches lower your trust score." actions={<ButtonLink to="/candidate/documents" variant="secondary" icon={LuFileUp}>Documents</ButtonLink>} />
      <div className="grid gap-5 lg:grid-cols-[280px_1fr]">
        <Card className="h-fit p-5 text-center">
          <div className="flex justify-center"><Avatar name={form.values.fullName} src={q.data?.photoUrl} size={88} /></div>
          <p className="mt-3 font-semibold text-ink">{form.values.fullName || "Your name"}</p>
          <p className="text-[13px] text-ink-3">{form.values.headline || "No headline yet"}</p>
          <div className="mt-5 text-left">
            <div className="mb-1.5 flex justify-between text-[13px]"><span className="text-ink-2">Profile completeness</span><span className="font-medium tabular-nums">{completeness}%</span></div>
            <ProgressBar value={completeness} label="Profile completeness" />
          </div>
          <p className="mt-4 text-xs text-ink-3">Your photo comes from the selfie taken at registration and can't be changed here.</p>
          <div className="mt-4 border-t border-line pt-4 text-left">
            <p className="text-[13px] font-medium text-ink">Mobile number</p>
            <p className="text-xs text-ink-3">{q.data?.phoneVerified ? "Verified by OTP" : "Not verified"}</p>
            <ConsentControls consents={q.data?.consents ?? []} />
          </div>
        </Card>
        <Card className="p-5 sm:p-6">
          <form className="grid gap-4 sm:grid-cols-2" noValidate onSubmit={(e) => {
            setRowsTouched(true);
            if (!rowsOk) {
              e.preventDefault();
              return;
            }
            form.handleSubmit((v) => void save.mutate(v))(e);
          }}>
            {!q.data && <div className="sm:col-span-2"><Notice tone="info">No saved profile was found. Complete registration first, or fill this in once the server is connected.</Notice></div>}
            <Field label="Full name" htmlFor="fullName" error={form.errors.fullName} required><input className={inputCls} autoComplete="name" {...form.register("fullName")} /></Field>
            <Field label="Email" htmlFor="email" error={form.errors.email} required><input type="email" className={inputCls} autoComplete="email" {...form.register("email")} /></Field>
            <Field label="Mobile number" htmlFor="phone" error={form.errors.phone} required><input type="tel" inputMode="numeric" className={inputCls} autoComplete="tel-national" {...form.register("phone")} /></Field>
            <Field label="City" htmlFor="location" error={form.errors.location} required><input className={inputCls} autoComplete="address-level2" {...form.register("location")} /></Field>
            <Field label="Headline" htmlFor="headline" error={form.errors.headline} required className="sm:col-span-2"><input className={inputCls} {...form.register("headline")} /></Field>
            <Field label="LinkedIn URL" htmlFor="linkedinUrl" error={form.errors.linkedinUrl}><input type="url" className={inputCls} placeholder="https://linkedin.com/in/…" {...form.register("linkedinUrl")} /></Field>
            <Field label="GitHub URL" htmlFor="githubUrl" error={form.errors.githubUrl}><input type="url" className={inputCls} placeholder="https://github.com/…" {...form.register("githubUrl")} /></Field>
            <div className="sm:col-span-2">
              <label htmlFor="skill" className="mb-1.5 block text-[13px] font-medium text-ink">Skills</label>
              <div className="flex gap-2">
                <input id="skill" value={skillDraft} onChange={(e) => setSkillDraft(e.target.value)} onKeyDown={(e) => e.key === "Enter" && (e.preventDefault(), addSkill())} className={inputCls} placeholder="Type a skill and press Enter" />
                <Button variant="secondary" icon={LuPlus} onClick={addSkill}>Add</Button>
              </div>
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
            <RowsEditor title="Education" rows={edu} setRows={setEdu} blankRow={blankEdu} errors={eduErr} showErrors={rowsTouched} addLabel="Add education" max={10}
              cols={[{ key: "degree", label: "Degree / Course", span: 3 }, { key: "institution", label: "Institution / Board", span: 3 }, { key: "startYear", label: "Start year", span: 2 }, { key: "endYear", label: "End year", span: 2 }, { key: "score", label: "CGPA / %", span: 2 }]} />
            {rowsTouched && edu.length === 0 && <p className="text-xs text-bad sm:col-span-2">Keep at least one education entry.</p>}
            <RowsEditor title="Work Experience" rows={exp} setRows={setExp} blankRow={blankExp} errors={expErr} showErrors={rowsTouched} addLabel="Add experience" max={20}
              cols={[{ key: "company", label: "Company", span: 3 }, { key: "title", label: "Job title", span: 3 }, { key: "start", label: "Start", type: "month", span: 2 }, { key: "end", label: "End", type: "month", span: 2 }, { key: "current", label: "I work here now", type: "checkbox" }]} />
            <RowsEditor title="References" rows={refs} setRows={setRefs} blankRow={blankRef} errors={refErr} showErrors={rowsTouched} addLabel="Add reference" max={5}
              cols={[{ key: "name", label: "Name", span: 3 }, { key: "relationship", label: "Relationship", span: 3, placeholder: "Manager, Professor…" }, { key: "company", label: "Company / Institution", span: 2 }, { key: "email", label: "Email", type: "email", span: 2 }, { key: "phone", label: "Phone", type: "tel", span: 2 }]} />
            {save.error ? <div className="sm:col-span-2"><Notice tone="error" title="Profile not saved">{errorMessage(save.error)}</Notice></div> : null}
            {save.data ? <div className="sm:col-span-2"><Notice tone="success">Profile saved.</Notice></div> : null}
            <div className="flex justify-end sm:col-span-2"><Button type="submit" loading={save.isPending}>Save changes</Button></div>
          </form>
        </Card>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ consent */

function ConsentControls({ consents }: { consents: CandidateProfile["consents"] }) {
  const latest = (purpose: string) => [...consents].filter((c) => c.purpose === purpose).sort((a, b) => a.recordedAt.localeCompare(b.recordedAt)).pop();
  const [confirm, setConfirm] = useState<null | { purpose: "biometric" | "document_processing"; granted: boolean }>(null);
  const change = useMutation((b: { purpose: "biometric" | "document_processing"; granted: boolean }) => candidateApi.setConsent(b), {
    invalidates: ["candidate:"], onSuccess: () => setConfirm(null),
  });
  const items = [
    { purpose: "biometric" as const, label: "Face checks (biometric)", withdrawText: "Your encrypted face template is deleted and face checks stop. Recruiters will see identity as not verified." },
    { purpose: "document_processing" as const, label: "Document reading", withdrawText: "Stored document extractions are deleted and your documents are no longer read or compared." },
  ];
  return (
    <>
      <p className="mt-3 text-[13px] font-medium text-ink">Consent</p>
      <ul className="mt-1 space-y-2 text-xs">
        {items.map((it) => {
          const c = latest(it.purpose);
          return (
            <li key={it.purpose} className="flex items-center justify-between gap-2">
              <span className="text-ink-3">{it.label}: <span className={c?.granted ? "text-ok" : "text-bad"}>{c?.granted ? "given" : "not given"}</span>{c && `, ${formatDate(c.recordedAt)}`}</span>
              <button className="font-medium text-brand-700 hover:underline" onClick={() => setConfirm({ purpose: it.purpose, granted: !c?.granted })}>{c?.granted ? "Withdraw" : "Give"}</button>
            </li>
          );
        })}
      </ul>
      <Modal open={confirm !== null} onClose={() => setConfirm(null)} title={confirm?.granted ? "Give consent" : "Withdraw consent"} footer={<>
        <Button variant="secondary" onClick={() => setConfirm(null)}>Cancel</Button>
        <Button variant={confirm?.granted ? "primary" : "danger"} loading={change.isPending} onClick={() => confirm && void change.mutate(confirm)}>{confirm?.granted ? "Give consent" : "Withdraw"}</Button>
      </>}>
        <p className="text-sm text-ink-2">{confirm && (confirm.granted ? "Checks that need this consent will run again." : items.find((i) => i.purpose === confirm.purpose)!.withdrawText)}</p>
        {change.error ? <div className="mt-3"><Notice tone="error">{errorMessage(change.error)}</Notice></div> : null}
      </Modal>
    </>
  );
}

/* ------------------------------------------------------------------ messages */

export function Messages() {
  const q = useQuery("candidate:messages", candidateApi.messages);
  const [openId, setOpenId] = useState<string | null>(null);
  const markRead = useMutation((id: string) => candidateApi.markRead(id), { invalidates: ["candidate:messages"] });
  return (
    <div>
      <PageHeader title="Messages" sub="Updates from recruiters and the verification team." />
      <Card>
        <DataState query={q} isEmpty={(l) => l.length === 0} empty={{ icon: LuMail, title: "No messages yet", body: "Recruiters' messages about your applications will appear here." }}>
          {(list) => (
            <ul className="divide-y divide-line">
              {list.map((m) => (
                <li key={m.id}>
                  <button onClick={() => { setOpenId(openId === m.id ? null : m.id); if (!m.read) void markRead.mutate(m.id); }} aria-expanded={openId === m.id} className="flex w-full items-start gap-3 px-5 py-4 text-left hover:bg-surface">
                    <Avatar name={m.from} size={36} />
                    <div className="min-w-0 flex-1">
                      <p className={cx("text-[14px]", m.read ? "text-ink-2" : "font-semibold text-ink")}>{m.subject}</p>
                      <p className="truncate text-[13px] text-ink-3">{m.from} · {formatDateTime(m.at)}</p>
                      {openId === m.id && <p className="mt-2 text-[13.5px] whitespace-pre-line text-ink-2">{m.body}</p>}
                    </div>
                    {!m.read && <span className="mt-2 size-2 rounded-full bg-brand-500" aria-label="Unread" />}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </DataState>
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ (l) QR passport */

export function PassportPage() {
  const q = useQuery("candidate:passport", candidateApi.passports);
  const [copied, setCopied] = useState("");
  if (q.isLoading) return <Spinner />;
  const d = q.data;
  const active = d?.passports.filter((p) => p.status === "active" && !p.expired) ?? [];
  const copy = (text: string, what: string) =>
    void navigator.clipboard?.writeText(text).then(() => setCopied(what), () => setCopied(""));
  return (
    <div>
      <PageHeader title="TrustTrace QR Passport" sub="A portable, verifiable record of your checks. Share the link or QR with any employer."
        back={{ to: "/candidate/verification", label: "Verification" }}
        actions={active.length ? <Button variant="secondary" icon={LuDownload} onClick={() => window.print()}>Download PDF</Button> : undefined} />
      {!d ? (
        <Card><NotLoaded error={q.error} what="passport" /></Card>
      ) : d.passports.length === 0 ? (
        <Card>
          <EmptyState icon={LuQrCode} title="Your passport hasn't been issued yet"
            action={<ButtonLink to="/candidate/verification" icon={LuShieldCheck}>See my verification</ButtonLink>}>
            A recruiter you applied to issues it once your identity is verified (your photo matched your ID) and any open questions on your
            application have been reviewed. It never contains your photo, documents, phone number, email or trust score.
          </EmptyState>
        </Card>
      ) : (
        <div className="mx-auto max-w-2xl space-y-6">
          <p className="flex items-center gap-1.5 text-[13px] text-ink-2">
            <LuShieldCheck className={cx("size-4", d.chain.intact ? "text-ok" : "text-bad")} aria-hidden />
            Evidence history {d.chain.intact ? "intact" : "failed its integrity check"} · {d.chain.events} recorded event(s)
          </p>
          {d.passports.map((p) => {
            const inactive = p.status !== "active" || p.expired;
            return (
              <div key={p.id} className={cx(inactive && "opacity-80 print:hidden")}>
                <PassportCard p={p} holderName={d.candidateName} qrDataUrl={p.qrDataUrl} verifyUrl={inactive ? undefined : p.verifyUrl}
                  banner={inactive ? (
                    <div className="border-b border-line bg-warn-soft px-6 py-2.5 text-[13px] text-warn">
                      {p.expired && p.status === "active" ? "Expired. Ask the recruiter to issue a new one." :
                        p.status === "revoked" ? `Revoked: ${p.statusReason}` : `Superseded: ${p.statusReason ?? "a newer passport replaced it."}`}
                    </div>
                  ) : undefined} />
                {!inactive && (
                  <div className="mt-3 flex flex-wrap items-center gap-2 print:hidden">
                    <Button size="sm" variant="secondary" icon={LuLink} onClick={() => copy(p.verifyUrl, p.id + "link")}>
                      {copied === p.id + "link" ? "Link copied" : "Copy link"}</Button>
                    <Button size="sm" variant="ghost" icon={LuKeyRound} onClick={() => copy(p.tokenUrl, p.id + "token")}>
                      {copied === p.id + "token" ? "Signed link copied" : "Copy signed link (works offline with the public key)"}</Button>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
