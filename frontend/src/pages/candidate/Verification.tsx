import { useState, type ReactNode } from "react";
import {
  LuBriefcase, LuDownload, LuEye, LuFileText, LuFileUp, LuGraduationCap, LuHistory, LuQrCode, LuScanFace, LuTrash2, LuUpload,
} from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { candidateApi } from "../../api/endpoints";
import type { DocumentVerification, UploadedDocument } from "../../api/types";
import { DataState } from "../../components/DataState";
import { DigiLockerCard } from "./DigiLocker";
import { ComparisonRows, FindingsList, IssuerBox, RunVerificationBar, decisionText, useVerificationJob } from "../../components/Verify";
import { Button, ButtonLink, Card, CardHeader, Notice, PageHeader, Pill, RingScore, Spinner, VerificationPill, cx } from "../../components/ui";
import { fileSize, formatDateTime } from "../../lib/format";
import { useMutation, useQuery } from "../../lib/query";
import { Link } from "../../lib/router";
import { VerificationList } from "./Jobs";

/* ------------------------------------------------------------------ (e) documents upload */

type Slot = { kind: UploadedDocument["kind"]; label: string; required?: boolean; accept: string; types: RegExp; multiple?: boolean };
const ANY = { accept: "application/pdf,image/jpeg,image/png", types: /^(application\/pdf|image\/(jpeg|png))$/ };
const SLOTS: Slot[] = [
  { kind: "resume", label: "Resume (PDF)", required: true, accept: "application/pdf", types: /^application\/pdf$/ },
  { kind: "marksheet", label: "Marksheet", required: true, ...ANY },
  { kind: "education_certificate", label: "Degree / Provisional Certificate (Optional)", ...ANY },
  { kind: "id_document", label: "Government ID", required: true, ...ANY },
  { kind: "experience_letter", label: "Experience Letter (Optional)", accept: "application/pdf,image/jpeg,image/png", types: /^(application\/pdf|image\/(jpeg|png))$/ },
  { kind: "certificate", label: "Other Certificates (Optional)", accept: "application/pdf,image/jpeg,image/png", types: /^(application\/pdf|image\/(jpeg|png))$/, multiple: true },
];
const MAX = 5 * 1024 * 1024;

function FileRow({ name, size, note, action }: { name: string; size: number; note?: string; action: ReactNode }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-line bg-white px-3 py-2.5">
      <span className="grid size-9 place-items-center rounded-md bg-bad-soft text-bad"><LuFileText className="size-5" aria-hidden /></span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13.5px] font-medium text-ink">{name}</p>
        <p className="text-xs text-ink-3">{fileSize(size)}{note ? ` · ${note}` : ""}</p>
      </div>
      {action}
    </div>
  );
}

export function Documents() {
  const docs = useQuery("candidate:documents", candidateApi.documents);
  const [picked, setPicked] = useState<Record<string, File[]>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const upload = useMutation((form: FormData) => candidateApi.uploadDocuments(form), {
    invalidates: ["candidate:"],
    onSuccess: () => setPicked({}),
  });
  const remove = useMutation((id: string) => candidateApi.deleteDocument(id), { invalidates: ["candidate:"] });

  function pick(slot: Slot, files: FileList | null) {
    const list = Array.from(files ?? []);
    const bad = list.find((f) => !slot.types.test(f.type) || f.size > MAX);
    if (bad) return setErrors((e) => ({ ...e, [slot.kind]: !slot.types.test(bad.type) ? `${bad.name}: this file type isn't accepted.` : `${bad.name} is larger than 5 MB.` }));
    setErrors((e) => ({ ...e, [slot.kind]: "" }));
    setPicked((p) => ({ ...p, [slot.kind]: slot.multiple ? [...(p[slot.kind] ?? []), ...list] : list.slice(0, 1) }));
  }

  function submit() {
    // Upload whatever was picked; missing required documents are shown in the list but don't block other uploads.
    const form = new FormData();
    Object.entries(picked).forEach(([kind, files]) => files.forEach((f) => form.append(kind, f)));
    void upload.mutate(form);
  }

  const missing = SLOTS.filter((s) => s.required && !docs.data?.some((d) => d.kind === s.kind)).map((s) => s.label.replace(" (PDF)", ""));
  const pickedCount = Object.values(picked).reduce((n, l) => n + l.length, 0);

  return (
    <div>
      <PageHeader title="Resume & Documents Upload" sub="Upload clear copies. Each document is read and compared with your profile." />
      <Card className="max-w-3xl p-5 sm:p-6">
        {docs.isLoading ? <Spinner /> : (
          <div className="space-y-6">
            {SLOTS.map((slot) => {
              const uploaded = docs.data?.filter((d) => d.kind === slot.kind) ?? [];
              const local = picked[slot.kind] ?? [];
              const showDrop = slot.multiple || (uploaded.length === 0 && local.length === 0);
              const canReplace = !slot.multiple && uploaded.length > 0 && local.length === 0;
              return (
                <section key={slot.kind} aria-labelledby={`slot-${slot.kind}`}>
                  <h2 id={`slot-${slot.kind}`} className="mb-2 text-sm font-semibold text-ink">{slot.label}</h2>
                  <div className="space-y-2">
                    {uploaded.map((d) => (
                      <FileRow key={d.id} name={d.fileName} size={d.sizeBytes} note={`uploaded ${formatDateTime(d.uploadedAt)} · not verified yet`} action={
                        <div className="flex items-center gap-1">
                          {d.previewUrl && <a href={d.previewUrl} target="_blank" rel="noreferrer" className="rounded-md p-2 text-ink-2 hover:bg-surface" aria-label={`Open ${d.fileName}`}><LuDownload className="size-4" aria-hidden /></a>}
                          {canReplace && (
                            <label className="cursor-pointer rounded-md px-2 py-1.5 text-xs font-medium text-brand-700 hover:bg-surface">
                              Replace
                              <input type="file" className="sr-only" accept={slot.accept} onChange={(e) => (pick(slot, e.target.files), (e.target.value = ""))} />
                            </label>
                          )}
                          {slot.multiple && <button onClick={() => void remove.mutate(d.id)} className="rounded-md p-2 text-ink-2 hover:bg-surface" aria-label={`Remove ${d.fileName}`}><LuTrash2 className="size-4" aria-hidden /></button>}
                        </div>
                      } />
                    ))}
                    {local.map((f, i) => (
                      <FileRow key={f.name + i} name={f.name} size={f.size} note={uploaded.length && !slot.multiple ? "selected, will replace the current file" : "selected, not uploaded yet"} action={
                        <button onClick={() => setPicked((p) => ({ ...p, [slot.kind]: local.filter((_, j) => j !== i) }))} className="rounded-md p-2 text-ink-2 hover:bg-surface" aria-label={`Remove ${f.name}`}><LuTrash2 className="size-4" aria-hidden /></button>
                      } />
                    ))}
                    {showDrop && (
                      <label className={cx("flex cursor-pointer flex-col items-center rounded-lg border border-dashed bg-surface px-4 py-5 text-center", errors[slot.kind] ? "border-bad" : "border-line-strong hover:border-brand-500")}>
                        <LuFileUp className="size-5 text-ink-3" aria-hidden />
                        <span className="mt-1 text-sm font-medium text-ink">Upload file</span>
                        <span className="text-xs text-ink-3">{slot.kind === "resume" ? "PDF (Max 5 MB)" : "PDF, JPG or PNG (Max 5 MB)"}</span>
                        <input type="file" className="sr-only" accept={slot.accept} multiple={slot.multiple} onChange={(e) => (pick(slot, e.target.files), (e.target.value = ""))} />
                      </label>
                    )}
                    {errors[slot.kind] && <p className="text-xs text-bad">{errors[slot.kind]}</p>}
                  </div>
                </section>
              );
            })}
            {upload.error ? <Notice tone="error" title="Documents not uploaded">{errorMessage(upload.error)}</Notice> : null}
            {remove.error ? <Notice tone="error" title="Not removed">{errorMessage(remove.error)}</Notice> : null}
            {upload.data ? <Notice tone="success">Uploaded {upload.data.length} file{upload.data.length === 1 ? "" : "s"}. They're stored privately and marked "not verified" until automated checks run in a later release.</Notice> : null}
            {missing.length > 0 && !docs.isLoading && <p className="text-[13px] text-ink-3">Still needed: {missing.join(", ")}.</p>}
            <Button className="w-full" size="lg" icon={LuUpload} loading={upload.isPending} onClick={submit} disabled={pickedCount === 0}>Upload Documents</Button>
          </div>
        )}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ (f)/(g) document verification */

function useCandidateJob() {
  return useVerificationJob("candidate:verification:job", candidateApi.verificationJob, candidateApi.runVerification, "candidate:verification,candidate:dashboard");
}

function DocVerification({ title, data, fields, summaryLabel, uploadHint, children }: {
  title: string; data: DocumentVerification | undefined; fields: string[]; summaryLabel: string; uploadHint: string; children?: ReactNode;
}) {
  const v = useCandidateJob();
  const extracted = data?.extracted?.length ? data.extracted : fields.map((label) => ({ label, value: null, confidence: null, page: null, snippet: null, source: null }));
  const problem = data?.extraction?.error || data?.error;
  return (
    <div>
      <PageHeader title={title} back={{ to: "/candidate/verification", label: "Verification" }} actions={data ? <VerificationPill status={data.status} /> : undefined} />
      <Card className="mb-5 p-4"><RunVerificationBar {...v} /></Card>
      {problem ? <div className="mb-5"><Notice tone="warn" title="Part of this document could not be read">{problem} Nothing is treated as a mismatch because of this.</Notice></div> : null}
      <div className="grid gap-5 lg:grid-cols-[1fr_1.15fr]">
        <Card className="flex flex-col items-center p-5">
          <div className="grid aspect-[4/3] w-full place-items-center overflow-hidden rounded-lg border border-line bg-surface">
            {data?.previewUrl ? (
              <img src={data.previewUrl} alt={`${title} document`} className="size-full object-contain" />
            ) : data?.downloadUrl ? (
              <div className="px-6 text-center text-[13px] text-ink-2">
                <LuFileText className="mx-auto mb-2 size-8 text-bad" aria-hidden />
                <p className="font-medium text-ink">{data.fileName}</p>
                <p className="mt-1 text-ink-3">PDF uploaded. Open it to view.</p>
              </div>
            ) : (
              <div className="px-6 text-center text-[13px] text-ink-3">
                <LuFileText className="mx-auto mb-2 size-8" aria-hidden />
                No document uploaded yet.
                <div className="mt-3"><ButtonLink to="/candidate/documents" size="sm" variant="secondary" icon={LuUpload}>{uploadHint}</ButtonLink></div>
              </div>
            )}
          </div>
          <Button variant="secondary" size="sm" icon={LuEye} className="mt-4" disabled={!data?.downloadUrl && !data?.previewUrl} onClick={() => { const u = data?.downloadUrl ?? data?.previewUrl; if (u) window.open(u, "_blank", "noopener"); }}>View Full Document</Button>
        </Card>
        <Card>
          <CardHeader title="Extracted Details (AI)" sub={data?.extraction ? `Read with ${data.extraction.method.replace(/_/g, " ")}` : undefined} />
          <dl className="mx-5 divide-y divide-line rounded-lg border border-line">
            {extracted.map((f) => (
              <div key={f.label} className="grid grid-cols-[140px_1fr] gap-3 px-3.5 py-2.5 text-[13.5px]">
                <dt className="text-ink-3">{f.label}</dt>
                <dd className="font-medium text-ink">
                  {f.value ?? "—"}
                  {f.value != null && f.confidence != null && <span className="ml-2 text-xs font-normal text-ink-3">{Math.round(f.confidence * 100)}%{f.source === "gemini" ? " · AI" : ""}</span>}
                </dd>
              </div>
            ))}
          </dl>
          <div className="px-5 py-4">
            <div className="mb-1.5 flex justify-between text-[13px]">
              <span className="font-medium text-info">AI Extraction Confidence</span>
              <span className="text-ink-2 tabular-nums">{data?.confidence != null ? `${data.confidence}%` : "—"}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-line" role="progressbar" aria-label="AI extraction confidence" aria-valuenow={data?.confidence ?? 0} aria-valuemin={0} aria-valuemax={100}>
              <div className="h-full rounded-full bg-info" style={{ width: `${data?.confidence ?? 0}%` }} />
            </div>
          </div>
        </Card>
      </div>
      <Card className="mt-5">
        <CardHeader title="Comparison Result" sub="What the document says compared with what you entered. Decided by fixed rules, not by AI." />
        <div className="grid gap-6 px-5 pb-5 md:grid-cols-[1.4fr_1fr]">
          <ComparisonRows rows={data?.comparison ?? []} empty={data?.documentId ? "Run verification to compare this document with your profile." : summaryLabel} />
          <div className="flex flex-col items-center justify-center">
            <RingScore value={data?.matchScore ?? null} label="Document match score" sub="Document Match Score" size={132} />
            <p className="mt-3 text-center text-[13px] text-ink-2">
              {data?.summary ?? (data?.documentId ? "Document received. Run verification to read and compare it." : summaryLabel)}
            </p>
          </div>
        </div>
        {data?.findings?.length ? <div className="border-t border-line px-5 py-4"><p className="mb-2 text-[13px] font-semibold text-ink">Points to review</p><FindingsList findings={data.findings} /></div> : null}
      </Card>
      {children}
    </div>
  );
}

export function EducationVerification() {
  const q = useQuery("candidate:verification:education", candidateApi.education);
  if (q.isLoading) return <Spinner />;
  return (
    <DocVerification
      title="Education Verification" data={q.data}
      fields={["Name", "Board / University", "Register Number", "Year", "Total Marks"]}
      summaryLabel="Upload your marksheet to compare it with your profile."
      uploadHint="Upload marksheet"
    >
      <Card className="mt-5 p-5">
        <IssuerBox issuer={q.data?.issuer ?? { status: "not_checked", label: "Not checked with the issuer. Matching fields do not prove the certificate is genuine." }} />
        <p className="mt-3 text-xs text-ink-3">Document consistency (above) and issuer authenticity are separate. Only the university or board can confirm a certificate is genuine.</p>
      </Card>
      <DigiLockerCard />
    </DocVerification>
  );
}

export function EmploymentVerification() {
  const q = useQuery("candidate:verification:employment", candidateApi.employment);
  if (q.isLoading) return <Spinner />;
  const refs = q.data?.references ?? [];
  return (
    <DocVerification
      title="Employment Verification" data={q.data}
      fields={["Company", "Designation", "Joining Date", "Relieving Date", "Experience Duration (months)"]}
      summaryLabel="Upload an experience letter to compare it with your resume."
      uploadHint="Upload experience letter"
    >
      <Card className="mt-5">
        <CardHeader title="Reference confirmations" sub="Recruiters can ask your HR contact or referee to confirm your employment through a one-time link." />
        {refs.length ? (
          <ul className="divide-y divide-line">
            {refs.map((r) => (
              <li key={r.id} className="flex flex-wrap items-center gap-3 px-5 py-3 text-[13.5px]">
                <span className="flex-1"><span className="font-medium text-ink">{r.referee}</span> <span className="text-ink-3">· {r.company || "employer"}</span></span>
                {r.simulated && <Pill tone="violet">Simulated</Pill>}
                <Pill tone={r.status === "sent" ? "amber" : r.status !== "responded" ? "gray" : r.confirmed ? "green" : "red"}>
                  {r.status === "sent" ? "Awaiting reply" : r.status !== "responded" ? r.status : r.confirmed ? "Confirmed" : "Not confirmed"}
                </Pill>
              </li>
            ))}
          </ul>
        ) : <p className="px-5 pb-5 text-[13px] text-ink-3">No reference requests yet.</p>}
      </Card>
    </DocVerification>
  );
}

/* ------------------------------------------------------------------ verification overview + history */

export function VerificationOverview() {
  const status = useQuery("candidate:verification", candidateApi.verification);
  const history = useQuery("candidate:verification:history", candidateApi.verificationHistory);
  const identity = useQuery("candidate:verification:identity", candidateApi.identity);
  const v = useCandidateJob();
  const id = identity.data;
  return (
    <div>
      <PageHeader title="Verification" sub="Every check on your profile, with the result and when it ran." actions={<ButtonLink to="/candidate/passport" variant="secondary" icon={LuQrCode}>My passport</ButtonLink>} />
      <Card className="mb-5 p-4">
        <RunVerificationBar {...v} />
        <p className="mt-2 text-xs text-ink-3">Checks also re-run automatically when you upload or replace a document or edit your profile. Results are evidence for a recruiter to review; nothing is rejected automatically.</p>
      </Card>
      <div className="grid gap-5 lg:grid-cols-[1fr_1.4fr]">
        <Card>
          <CardHeader title="Verification Status" />
          <div className="px-5 pb-3">{status.isLoading ? <Spinner /> : <VerificationList items={status.data} />}</div>
          <div className="grid gap-2 border-t border-line p-4 sm:grid-cols-2">
            <ButtonLink to="/candidate/verification/education" variant="secondary" icon={LuGraduationCap}>Education</ButtonLink>
            <ButtonLink to="/candidate/verification/employment" variant="secondary" icon={LuBriefcase}>Employment</ButtonLink>
            <ButtonLink to="/candidate/documents" variant="secondary" icon={LuUpload} className="sm:col-span-2">Upload documents</ButtonLink>
          </div>
        </Card>
        <Card className="lg:col-span-2 lg:order-last">
          <CardHeader title="Identity (face) checks" action={id ? <VerificationPill status={id.status} /> : undefined} />
          <div className="grid gap-4 px-5 pb-5 sm:grid-cols-3">
            <div className="rounded-lg border border-line p-3.5 text-[13px]">
              <p className="flex items-center gap-1.5 font-medium text-ink"><LuScanFace className="size-4 text-brand-600" aria-hidden /> Enrolment photo</p>
              <p className="mt-1 text-ink-3">{id?.enrolment?.status === "enrolled" ? "Enrolled from your registration selfie" : "Not enrolled yet"}</p>
            </div>
            <div className="rounded-lg border border-line p-3.5 text-[13px]">
              <p className="font-medium text-ink">ID document photo</p>
              <p className="mt-1 text-ink-3">{id?.idDocument?.label ?? "Not compared yet"}{id?.idDocument?.similarity != null && ` (similarity ${id.idDocument.similarity.toFixed(2)})`}</p>
            </div>
            <div className="rounded-lg border border-line p-3.5 text-[13px]">
              <p className="font-medium text-ink">Rechecks</p>
              <p className="mt-1 text-ink-3">{id?.rechecks?.length ? id.rechecks.slice(-3).map((r) => `${r.stage}: ${decisionText[r.decision] ?? r.decision}`).join(" · ") : "None yet – done at the start of assessments and interviews"}</p>
            </div>
          </div>
          <p className="px-5 pb-4 text-xs text-ink-3">{id?.summary ?? "Run verification to enrol your face."} Faces are compared with OpenCV YuNet + SFace; only an encrypted numeric face template is stored. Liveness (anti-spoofing) is not checked.</p>
        </Card>
        <Card>
          <CardHeader title="Verification History" />
          <DataState query={history} isEmpty={(h) => h.length === 0} empty={{ icon: LuHistory, title: "No checks have run yet", body: "Results appear here after you upload documents and complete each stage." }}>
            {(list) => (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-[13.5px]">
                  <thead className="border-y border-line bg-surface text-xs text-ink-3">
                    <tr><th className="px-5 py-2.5 font-medium">When</th><th className="px-5 py-2.5 font-medium">Check</th><th className="px-5 py-2.5 font-medium">Result</th><th className="px-5 py-2.5 font-medium">Detail</th></tr>
                  </thead>
                  <tbody className="divide-y divide-line">
                    {list.map((e) => (
                      <tr key={e.id}>
                        <td className="px-5 py-3 whitespace-nowrap text-ink-2">{formatDateTime(e.at)}</td>
                        <td className="px-5 py-3 font-medium text-ink">{e.check}</td>
                        <td className="px-5 py-3"><VerificationPill status={e.result} /></td>
                        <td className="px-5 py-3 text-ink-2">{e.detail}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </DataState>
        </Card>
      </div>
      <p className="mt-4 text-[13px] text-ink-3">Something wrong? <Link to="/candidate/messages" className="font-medium text-brand-700 hover:underline">Message the recruiter</Link> to ask for a re-check.</p>
    </div>
  );
}
