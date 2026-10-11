import { useState } from "react";
import { z } from "zod";
import { LuCamera, LuFileUp, LuPlus, LuRotateCcw, LuTrash2, LuCircleCheck } from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { authApi, candidateApi, type CandidateRegistration } from "../../api/endpoints";
import { useAuth } from "../../auth/AuthContext";
import { CameraView, useCamera } from "../../components/Camera";
import { Button, Card, Field, Notice, PageHeader, Stepper, cx, inputCls } from "../../components/ui";
import { useZodForm } from "../../lib/form";
import { useMutation } from "../../lib/query";
import { useNavigate } from "../../lib/router";

const STEPS = ["Basic Details", "Education & Experience", "Identity Verification", "Complete"];

const today = new Date();
const basicSchema = z.object({
  fullName: z.string().trim().min(3, "Enter your full name as on your ID"),
  email: z.string().trim().email("Enter a valid email address"),
  phone: z.string().trim().regex(/^[6-9][0-9]{9}$/, "Enter a 10-digit mobile number"),
  otp: z.string().trim().regex(/^[0-9]{6}$/, "Enter the 6-digit OTP sent to your mobile"),
  dateOfBirth: z
    .string()
    .min(1, "Enter your date of birth")
    .refine((v) => {
      const d = new Date(v);
      const age = (today.getTime() - d.getTime()) / (365.25 * 24 * 3600 * 1000);
      return !Number.isNaN(d.getTime()) && age >= 16 && age < 80;
    }, "You must be at least 16 years old"),
  password: z.string().min(8, "Use at least 8 characters").regex(/[A-Z]/, "Include an uppercase letter").regex(/[0-9]/, "Include a number"),
});

const yearRe = /^(19[7-9][0-9]|20[0-3][0-9])$/;
const eduSchema = z.object({
  degree: z.string().trim().min(2, "Degree is required"),
  institution: z.string().trim().min(2, "Institution is required"),
  startYear: z.string().regex(yearRe, "Year like 2021"),
  endYear: z.string().regex(yearRe, "Year like 2025"),
  score: z.string().trim().max(20),
}).refine((e) => Number(e.endYear) >= Number(e.startYear), { path: ["endYear"], message: "Ends before it starts" });

const expSchema = z.object({
  company: z.string().trim().min(2, "Company is required"),
  title: z.string().trim().min(2, "Job title is required"),
  start: z.string().regex(/^\d{4}-\d{2}$/, "Start month"),
  end: z.string(),
  current: z.boolean(),
}).refine((e) => e.current || /^\d{4}-\d{2}$/.test(e.end), { path: ["end"], message: "End month, or tick 'I work here now'" })
  .refine((e) => e.current || e.end >= e.start, { path: ["end"], message: "Ends before it starts" });

type Edu = z.infer<typeof eduSchema>;
type Exp = z.infer<typeof expSchema>;
const emptyEdu: Edu = { degree: "", institution: "", startYear: "", endYear: "", score: "" };
const emptyExp: Exp = { company: "", title: "", start: "", end: "", current: false };

function issues<T>(schema: z.ZodType<T>, v: T): Record<string, string> {
  const r = schema.safeParse(v);
  if (r.success) return {};
  return Object.fromEntries(r.error.issues.map((i) => [String(i.path[0]), i.message]));
}

export function CandidateRegister() {
  const navigate = useNavigate();
  const { acceptSession } = useAuth();
  const [step, setStep] = useState(0);
  const form = useZodForm(basicSchema, { fullName: "", email: "", phone: "", otp: "", dateOfBirth: "", password: "" });
  const cam = useCamera(true);
  const [selfie, setSelfie] = useState<string | null>(null);
  const [selfieError, setSelfieError] = useState<string | null>(null);
  const [otpNote, setOtpNote] = useState<{ tone: "error" | "success"; text: string } | null>(null);
  const [education, setEducation] = useState<Edu[]>([{ ...emptyEdu }]);
  const [experience, setExperience] = useState<Exp[]>([]);
  const [listErrors, setListErrors] = useState(false);
  const [idDoc, setIdDoc] = useState<File | null>(null);
  const [idError, setIdError] = useState<string | null>(null);
  const [consentBio, setConsentBio] = useState(false);
  const [consentDocs, setConsentDocs] = useState(false);
  const [consentError, setConsentError] = useState(false);
  const consent = consentBio && consentDocs;

  const otp = useMutation((phone: string) => authApi.requestOtp(phone), {
    onSuccess: () => setOtpNote({ tone: "success", text: "OTP sent. Enter the 6-digit code below. (No SMS provider is connected yet, so the code appears in the window where the TrustTrace server is running.)" }),
  });
  const submit = useMutation((data: CandidateRegistration) => candidateApi.register(data), {
    onSuccess: (r) => (acceptSession(r.token, r.user), navigate("/candidate")),
  });

  async function sendOtp() {
    if (!form.validateFields(["phone"])) return;
    setOtpNote(null);
    await otp.mutate(form.values.phone);
  }

  function next() {
    if (step === 0) {
      if (!otp.data) setOtpNote({ tone: "error", text: "Verify your mobile number: tap Verify OTP and enter the code." });
      const ok = form.validateFields(["fullName", "email", "phone", "otp", "dateOfBirth", "password"]) && !!otp.data;
      if (!selfie) setSelfieError("Capture a clear photo of your face to continue.");
      if (ok && selfie) setStep(1);
    } else if (step === 1) {
      setListErrors(true);
      const ok = education.length > 0 && education.every((e) => eduSchema.safeParse(e).success) && experience.every((e) => expSchema.safeParse(e).success);
      if (ok) setStep(2);
    } else if (step === 2) {
      if (!idDoc) setIdError("Upload a photo or PDF of a government ID.");
      setConsentError(!consent);
      if (idDoc && consent) setStep(3);
    }
  }

  function takePhoto() {
    const shot = cam.capture();
    if (!shot) return setSelfieError("The camera isn't ready yet.");
    setSelfie(shot);
    setSelfieError(null);
  }

  function pickId(file: File | undefined) {
    setIdError(null);
    if (!file) return;
    if (!/^(image\/(jpeg|png)|application\/pdf)$/.test(file.type)) return setIdError("Use a JPG, PNG or PDF file.");
    if (file.size > 5 * 1024 * 1024) return setIdError("The file must be smaller than 5 MB.");
    setIdDoc(file);
  }

  return (
    <div>
      <PageHeader title="Create Your Registration" />
      <div className="mx-auto mb-8 max-w-3xl">
        <Stepper steps={STEPS} current={step} />
      </div>

      {step === 0 && (
        <div className="grid gap-5 lg:grid-cols-[1.35fr_1fr]">
          <Card className="p-5 sm:p-6">
            <div className="space-y-4">
              <Field label="Full Name" htmlFor="fullName" error={form.errors.fullName} required>
                <input autoComplete="name" className={inputCls} {...form.register("fullName")} />
              </Field>
              <Field label="Email" htmlFor="email" error={form.errors.email} required>
                <input type="email" autoComplete="email" className={inputCls} {...form.register("email")} />
              </Field>
              <Field label="Mobile Number" htmlFor="phone" error={form.errors.phone} required>
                <div className="flex gap-3">
                  <input type="tel" inputMode="numeric" autoComplete="tel-national" className={inputCls} {...form.register("phone")} />
                  <Button onClick={() => void sendOtp()} loading={otp.isPending} className="shrink-0">Verify OTP</Button>
                </div>
              </Field>
              {otp.error ? <Notice tone="error">{errorMessage(otp.error)}</Notice> : null}
              {otpNote && <Notice tone={otpNote.tone}>{otpNote.text}</Notice>}
              {otp.data && (
                <Field label="OTP" htmlFor="otp" error={form.errors.otp}>
                  <input inputMode="numeric" maxLength={6} className={inputCls} {...form.register("otp")} />
                </Field>
              )}
              <Field label="Date of Birth" htmlFor="dateOfBirth" error={form.errors.dateOfBirth} required>
                <input type="date" max={today.toISOString().slice(0, 10)} className={inputCls} {...form.register("dateOfBirth")} />
              </Field>
              <Field label="Set Password" htmlFor="password" error={form.errors.password} hint="At least 8 characters with an uppercase letter and a number" required>
                <input type="password" autoComplete="new-password" className={inputCls} {...form.register("password")} />
              </Field>
            </div>
          </Card>
          <Card className="flex flex-col items-center p-5 sm:p-6">
            <p className="text-sm font-semibold text-ink">Capture Your Photo</p>
            <p className="mt-0.5 text-center text-xs text-ink-3">Face the camera in good light. This photo becomes your reference for every later check.</p>
            <CameraView cam={cam} still={selfie} className="mt-4 aspect-[4/3] w-full" />
            {selfieError && <p className="mt-2 text-xs text-bad">{selfieError}</p>}
            <div className="mt-4 flex gap-2">
              {selfie ? (
                <Button variant="secondary" icon={LuRotateCcw} onClick={() => setSelfie(null)}>Retake</Button>
              ) : (
                <Button icon={LuCamera} onClick={takePhoto} disabled={cam.state !== "ready"} className="min-w-40">Capture</Button>
              )}
            </div>
          </Card>
        </div>
      )}

      {step === 1 && (
        <div className="space-y-5">
          <Card className="p-5 sm:p-6">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-[15px] font-semibold">Education</h2>
              <Button variant="secondary" size="sm" icon={LuPlus} onClick={() => setEducation((l) => [...l, { ...emptyEdu }])}>Add education</Button>
            </div>
            <div className="space-y-4">
              {education.map((e, i) => {
                const err = listErrors ? issues(eduSchema, e) : {};
                const set = (k: keyof Edu, v: string) => setEducation((l) => l.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
                return (
                  <div key={i} className="grid gap-3 rounded-lg border border-line p-4 sm:grid-cols-6">
                    <Field label="Degree / Course" htmlFor={`edu-degree-${i}`} error={err.degree} className="sm:col-span-3">
                      <input id={`edu-degree-${i}`} className={inputCls} value={e.degree} onChange={(ev) => set("degree", ev.target.value)} />
                    </Field>
                    <Field label="Institution / Board" htmlFor={`edu-inst-${i}`} error={err.institution} className="sm:col-span-3">
                      <input id={`edu-inst-${i}`} className={inputCls} value={e.institution} onChange={(ev) => set("institution", ev.target.value)} />
                    </Field>
                    <Field label="Start year" htmlFor={`edu-start-${i}`} error={err.startYear} className="sm:col-span-2">
                      <input id={`edu-start-${i}`} inputMode="numeric" maxLength={4} className={inputCls} value={e.startYear} onChange={(ev) => set("startYear", ev.target.value)} />
                    </Field>
                    <Field label="End year" htmlFor={`edu-end-${i}`} error={err.endYear} className="sm:col-span-2">
                      <input id={`edu-end-${i}`} inputMode="numeric" maxLength={4} className={inputCls} value={e.endYear} onChange={(ev) => set("endYear", ev.target.value)} />
                    </Field>
                    <Field label="Marks / CGPA" htmlFor={`edu-score-${i}`} className="sm:col-span-2">
                      <div className="flex gap-2">
                        <input id={`edu-score-${i}`} className={inputCls} value={e.score} onChange={(ev) => set("score", ev.target.value)} />
                        {education.length > 1 && (
                          <Button variant="ghost" aria-label="Remove education" onClick={() => setEducation((l) => l.filter((_, j) => j !== i))}><LuTrash2 className="size-4" aria-hidden /></Button>
                        )}
                      </div>
                    </Field>
                  </div>
                );
              })}
            </div>
          </Card>
          <Card className="p-5 sm:p-6">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h2 className="text-[15px] font-semibold">Work experience</h2>
                <p className="text-xs text-ink-3">Leave empty if you are a fresher.</p>
              </div>
              <Button variant="secondary" size="sm" icon={LuPlus} onClick={() => setExperience((l) => [...l, { ...emptyExp }])}>Add role</Button>
            </div>
            {experience.length === 0 ? (
              <p className="rounded-lg border border-dashed border-line-strong px-4 py-6 text-center text-[13px] text-ink-3">No work experience added.</p>
            ) : (
              <div className="space-y-4">
                {experience.map((e, i) => {
                  const err = listErrors ? issues(expSchema, e) : {};
                  const set = (k: keyof Exp, v: string | boolean) => setExperience((l) => l.map((x, j) => (j === i ? { ...x, [k]: v } : x)));
                  return (
                    <div key={i} className="grid gap-3 rounded-lg border border-line p-4 sm:grid-cols-6">
                      <Field label="Company" htmlFor={`exp-company-${i}`} error={err.company} className="sm:col-span-3">
                        <input id={`exp-company-${i}`} className={inputCls} value={e.company} onChange={(ev) => set("company", ev.target.value)} />
                      </Field>
                      <Field label="Job title" htmlFor={`exp-title-${i}`} error={err.title} className="sm:col-span-3">
                        <input id={`exp-title-${i}`} className={inputCls} value={e.title} onChange={(ev) => set("title", ev.target.value)} />
                      </Field>
                      <Field label="Started" htmlFor={`exp-start-${i}`} error={err.start} className="sm:col-span-2">
                        <input id={`exp-start-${i}`} type="month" className={inputCls} value={e.start} onChange={(ev) => set("start", ev.target.value)} />
                      </Field>
                      <Field label="Ended" htmlFor={`exp-end-${i}`} error={err.end} className="sm:col-span-2">
                        <input id={`exp-end-${i}`} type="month" disabled={e.current} className={inputCls} value={e.current ? "" : e.end} onChange={(ev) => set("end", ev.target.value)} />
                      </Field>
                      <div className="flex items-end justify-between gap-2 sm:col-span-2">
                        <label className="flex items-center gap-2 pb-2.5 text-[13px] text-ink-2">
                          <input type="checkbox" className="size-4 accent-brand-600" checked={e.current} onChange={(ev) => set("current", ev.target.checked)} /> I work here now
                        </label>
                        <Button variant="ghost" aria-label="Remove role" onClick={() => setExperience((l) => l.filter((_, j) => j !== i))}><LuTrash2 className="size-4" aria-hidden /></Button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </Card>
        </div>
      )}

      {step === 2 && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card className="p-5 sm:p-6">
            <h2 className="text-[15px] font-semibold">Government ID</h2>
            <p className="mt-0.5 text-[13px] text-ink-3">Aadhaar, PAN, passport or driving licence. The face on it is compared with your photo.</p>
            <label className={cx("mt-4 flex cursor-pointer flex-col items-center rounded-lg border-2 border-dashed px-4 py-8 text-center", idError ? "border-bad" : "border-line-strong hover:border-brand-500")}>
              <LuFileUp className="size-7 text-ink-3" aria-hidden />
              <span className="mt-2 text-sm font-medium text-ink">{idDoc ? idDoc.name : "Upload ID"}</span>
              <span className="text-xs text-ink-3">{idDoc ? `${(idDoc.size / 1024 / 1024).toFixed(1)} MB, selected (uploads when you submit)` : "JPG, PNG or PDF (max 5 MB)"}</span>
              <input type="file" accept="image/jpeg,image/png,application/pdf" className="sr-only" onChange={(e) => pickId(e.target.files?.[0])} />
            </label>
            {idError && <p className="mt-2 text-xs text-bad">{idError}</p>}
          </Card>
          <Card className="p-5 sm:p-6">
            <h2 className="text-[15px] font-semibold">Consent</h2>
            <ul className="mt-3 list-disc space-y-1.5 pl-5 text-[13px] text-ink-2">
              <li>Your photo and ID are stored privately on the TrustTrace server. Only you and recruiters of jobs you apply to can open them.</li>
              <li>From a later release, your ID photo is compared with your live photo, and the same face is checked during tests and interviews.</li>
              <li>Your documents are read and compared with the details you entered. Uploading a document does not mark it as verified.</li>
              <li>This browser gets a random ID (no personal data). Only a scrambled form of it, and of your network address, is stored, to notice several accounts used from one device. On its own this is never treated as wrongdoing.</li>
              <li>A person reviews every flag. No decision is made automatically. Your consent is recorded with the date and time.</li>
            </ul>
            <label className="mt-4 flex items-start gap-2.5 text-[13px] font-medium text-ink">
              <input type="checkbox" className="mt-0.5 size-4 accent-brand-600" checked={consentBio} onChange={(e) => (setConsentBio(e.target.checked), setConsentError(false))} />
              I consent to my photo and face being used for identity checks (biometric processing).
            </label>
            <label className="mt-3 flex items-start gap-2.5 text-[13px] font-medium text-ink">
              <input type="checkbox" className="mt-0.5 size-4 accent-brand-600" checked={consentDocs} onChange={(e) => (setConsentDocs(e.target.checked), setConsentError(false))} />
              I consent to my documents being stored and processed for verification.
            </label>
            {consentError && <p className="mt-1 text-xs text-bad">Both consents are required to continue.</p>}
          </Card>
        </div>
      )}

      {step === 3 && (
        <Card className="mx-auto max-w-2xl p-6">
          <h2 className="text-[15px] font-semibold">Review and submit</h2>
          <dl className="mt-4 grid gap-x-6 gap-y-3 text-[13.5px] sm:grid-cols-2">
            {[
              ["Name", form.values.fullName],
              ["Email", form.values.email],
              ["Mobile", form.values.phone],
              ["Date of birth", form.values.dateOfBirth],
              ["Education entries", String(education.length)],
              ["Work experience entries", String(experience.length)],
              ["Government ID", idDoc?.name ?? ""],
              ["Photo", selfie ? "Captured" : "Missing"],
            ].map(([k, v]) => (
              <div key={k}>
                <dt className="text-ink-3">{k}</dt>
                <dd className="font-medium text-ink">{v}</dd>
              </div>
            ))}
          </dl>
          {submit.error ? <div className="mt-5"><Notice tone="error" title="Registration not saved">{errorMessage(submit.error)}</Notice></div> : null}
          <div className="mt-6 flex items-center gap-2 text-[13px] text-ink-3">
            <LuCircleCheck className="size-4 text-brand-600" aria-hidden /> Your details are only saved when you submit.
          </div>
        </Card>
      )}

      <div className="mt-6 flex justify-between gap-3">
        <Button variant="secondary" onClick={() => setStep((s) => Math.max(0, s - 1))} className={step === 0 ? "invisible" : ""}>Back</Button>
        {step < 3 ? (
          <Button onClick={next} className="min-w-28">Next</Button>
        ) : (
          <Button
            loading={submit.isPending}
            onClick={() =>
              void submit.mutate({ ...form.values, education, experience, selfie: selfie ?? "", idDocument: idDoc, consent, consentBiometric: consentBio, consentDocuments: consentDocs })
            }
          >
            Submit registration
          </Button>
        )}
      </div>
    </div>
  );
}
