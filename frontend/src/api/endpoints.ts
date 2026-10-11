/** Typed API surface. Every screen talks to the server only through these functions. */
import { http } from "./client";
import type { DigiLockerStatus } from "./types";
import type {
  Application, AssessmentAttemptDetail, AssessmentBuilder, AssessmentSession, AssessmentSummary, AssessmentTemplate, ProofOfSkill, QuestionInput, TrustBundle, CandidateDashboard, CandidateProfile, DocumentVerification, Interview, InterviewInput,
  ApplicationStatus, CandidatePassports, EvidenceTimeline, Job, JobInput, Message, PassportAdmin, PassportVerification, ProfileInput, RecruiterDashboard, RecruiterSettings, ApplicantRow, ReviewDecision, Role, SessionUser, TrustReport,
  UploadedDocument, VerificationEvent, VerificationItem, IdentityCheckResult, IdentityResult, VerificationJob,
} from "./types";

export const authApi = {
  me: () => http.get<SessionUser>("/auth/me"),
  login: (body: { role: Role; email: string; password: string }) => http.post<{ token: string; user: SessionUser }>("/auth/login", body),
  logout: () => http.post<{ ok: true }>("/auth/logout"),
  registerRecruiter: (body: { fullName: string; organisation: string; email: string; phone: string; companySize: string; password: string }) =>
    http.post<{ token: string; user: SessionUser }>("/auth/register/recruiter", body),
  requestOtp: (phone: string) => http.post<{ sent: true }>("/auth/otp", { phone }),
};

export type CandidateRegistration = {
  fullName: string; email: string; phone: string; otp: string; dateOfBirth: string; password: string;
  education: { degree: string; institution: string; startYear: string; endYear: string; score: string }[];
  experience: { company: string; title: string; start: string; end: string; current: boolean }[];
  selfie: string; idDocument: File | null; consent: boolean; consentBiometric: boolean; consentDocuments: boolean;
};

export const candidateApi = {
  register: (data: CandidateRegistration) => {
    const form = new FormData();
    const { idDocument, ...rest } = data;
    form.append("payload", JSON.stringify(rest));
    if (idDocument) form.append("idDocument", idDocument);
    return http.post<{ token: string; user: SessionUser }>("/candidates/register", form);
  },
  dashboard: () => http.get<CandidateDashboard>("/candidate/dashboard"),
  profile: () => http.get<CandidateProfile>("/candidate/profile"),
  updateProfile: (body: ProfileInput) => http.put<CandidateProfile>("/candidate/profile", body),
  applications: () => http.get<Application[]>("/candidate/applications"),
  application: (id: string) => http.get<Application>(`/candidate/applications/${id}`),
  documents: () => http.get<UploadedDocument[]>("/candidate/documents"),
  uploadDocuments: (form: FormData) => http.post<UploadedDocument[]>("/candidate/documents", form),
  replaceDocument: (id: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return http.put<UploadedDocument>(`/candidate/documents/${id}`, form);
  },
  deleteDocument: (id: string) => http.del<{ ok: true }>(`/candidate/documents/${id}`),
  verification: () => http.get<VerificationItem[]>("/candidate/verification"),
  verificationHistory: () => http.get<VerificationEvent[]>("/candidate/verification/history"),
  education: () => http.get<DocumentVerification>("/candidate/verification/education"),
  employment: () => http.get<DocumentVerification>("/candidate/verification/employment"),
  assessments: () => http.get<AssessmentSummary[]>("/candidate/assessments"),
  assessment: (id: string) => http.get<AssessmentSession>(`/candidate/assessments/${id}`),
  startAssessment: (id: string, body: { cameraConsent: boolean; cameraState: "granted" | "denied" | "unavailable" | "declined" }) =>
    http.post<AssessmentSession>(`/candidate/assessments/${id}/start`, body),
  saveAnswers: (id: string, answers: Record<string, string>) => http.put<{ saved: number; remainingSeconds: number }>(`/candidate/assessments/${id}/answers`, { answers }),
  assessmentEvents: (id: string, events: { type: string; clientAt: string; detail?: Record<string, string | number | boolean> }[]) =>
    http.post<{ recorded: number }>(`/candidate/assessments/${id}/events`, { events }),
  submitAssessment: (id: string, answers: Record<string, string>) => http.post<AssessmentSummary>(`/candidate/assessments/${id}/submit`, { answers }),
  skills: () => http.get<ProofOfSkill>("/candidate/skills"),
  interviews: () => http.get<Interview[]>("/candidate/interviews"),
  interview: (id: string) => http.get<Interview>(`/candidate/interviews/${id}`),
  respondInterview: (id: string, body: { response: "accepted" | "reschedule_requested"; note: string }) => http.post<Interview>(`/candidate/interviews/${id}/respond`, body),
  interviewEntry: (id: string, body: { image?: string; camera: "ok" | "denied" | "unavailable" }) =>
    http.post<IdentityCheckResult & { interview: Interview }>(`/candidate/interviews/${id}/entry`, body),
  messages: () => http.get<Message[]>("/candidate/messages"),
  markRead: (id: string) => http.post<Message>(`/candidate/messages/${id}/read`),
  passports: () => http.get<CandidatePassports>("/candidate/passport"),
  runVerification: () => http.post<VerificationJob>("/candidate/verification/run"),
  verificationJob: () => http.get<VerificationJob | null>("/candidate/verification/job"),
  identity: () => http.get<IdentityResult>("/candidate/verification/identity"),
  identityCheck: (body: { stage: "assessment" | "interview" | "manual"; referenceId?: string; image: string }) =>
    http.post<IdentityCheckResult>("/candidate/identity/check", body),
  setConsent: (body: { purpose: "biometric" | "document_processing"; granted: boolean }) => http.post<CandidateProfile>("/candidate/consents", body),
};

export const jobsApi = {
  list: (q: { search?: string; location?: string; type?: string; mode?: string } = {}) => {
    const params = new URLSearchParams(Object.entries(q).filter(([, v]) => v) as [string, string][]);
    return http.get<Job[]>(`/jobs${params.toString() ? `?${params}` : ""}`);
  },
  get: (id: string) => http.get<Job>(`/jobs/${id}`),
  apply: (id: string) => http.post<Application>(`/jobs/${id}/apply`),
};

export const recruiterApi = {
  dashboard: () => http.get<RecruiterDashboard>("/recruiter/dashboard"),
  jobs: () => http.get<Job[]>("/recruiter/jobs"),
  job: (id: string) => http.get<Job>(`/recruiter/jobs/${id}`),
  createJob: (body: JobInput) => http.post<Job>("/recruiter/jobs", body),
  updateJob: (id: string, body: JobInput) => http.put<Job>(`/recruiter/jobs/${id}`, body),
  closeJob: (id: string) => http.post<Job>(`/recruiter/jobs/${id}/close`),
  applicants: (q: { search?: string; status?: string; sort?: string; attention?: boolean } = {}) => {
    const p = new URLSearchParams(Object.entries(q).filter(([, v]) => v !== undefined && v !== "" && v !== false).map(([k, v]) => [k, String(v)]));
    return http.get<ApplicantRow[]>(`/recruiter/applicants${p.toString() ? `?${p}` : ""}`);
  },
  reviewPattern: (appId: string, alertId: string, body: { status: "reviewed_ok" | "confirmed" | "open"; note: string }) =>
    http.post<TrustBundle>(`/recruiter/applicants/${appId}/patterns/${alertId}/review`, body),
  reviewCheck: (appId: string, check: "identity" | "education" | "employment" | "resume", body: { status: "resolved" | "upheld"; note: string }) =>
    http.post<TrustBundle>(`/recruiter/applicants/${appId}/checks/${check}/review`, body),
  markReviewed: (appId: string, note: string) => http.post<TrustBundle>(`/recruiter/applicants/${appId}/mark-reviewed`, { note }),
  report: (applicationId: string) => http.get<TrustReport>(`/recruiter/applicants/${applicationId}/report`),
  changeStatus: (applicationId: string, body: { status: ApplicationStatus; note: string }) =>
    http.post<TrustReport>(`/recruiter/applicants/${applicationId}/status`, body),
  decide: (applicationId: string, body: { decision: ReviewDecision; reason: string }) => http.post<TrustReport>(`/recruiter/applicants/${applicationId}/decision`, body),
  assessments: () => http.get<AssessmentSummary[]>("/recruiter/assessments"),
  assessmentAttempt: (id: string) => http.get<AssessmentAttemptDetail>(`/recruiter/assessments/${id}`),
  applicantSkills: (applicationId: string) => http.get<ProofOfSkill>(`/recruiter/applicants/${applicationId}/skills`),
  builder: (jobId: string) => http.get<AssessmentBuilder>(`/recruiter/jobs/${jobId}/assessment`),
  generateQuestions: (jobId: string, body: { count: number; durationMinutes: number; passPercent: number; title: string; source: "auto" | "bank"; replace: boolean }) =>
    http.post<AssessmentTemplate>(`/recruiter/jobs/${jobId}/assessment/generate`, body),
  updateAssessment: (jobId: string, body: { title: string; durationMinutes: number; passPercent: number }) =>
    http.put<AssessmentTemplate>(`/recruiter/jobs/${jobId}/assessment`, body),
  addQuestion: (jobId: string, body: QuestionInput) => http.post<AssessmentTemplate>(`/recruiter/jobs/${jobId}/assessment/questions`, body),
  editQuestion: (qid: string, body: QuestionInput) => http.put<AssessmentTemplate>(`/recruiter/assessment-questions/${qid}`, body),
  approveQuestion: (qid: string) => http.post<AssessmentTemplate>(`/recruiter/assessment-questions/${qid}/approve`),
  deleteQuestion: (qid: string) => http.del<AssessmentTemplate>(`/recruiter/assessment-questions/${qid}`),
  publishAssessment: (jobId: string) => http.post<AssessmentTemplate>(`/recruiter/jobs/${jobId}/assessment/publish`),
  interviews: () => http.get<Interview[]>("/recruiter/interviews"),
  setInterviewStatus: (id: string, status: "completed" | "cancelled" | "scheduled") => http.post<Interview>(`/recruiter/interviews/${id}/status`, { status }),
  scheduleInterview: (body: InterviewInput) => http.post<Interview>("/recruiter/interviews", body),
  reports: () => http.get<{ scoreBands: { band: string; count: number }[]; flagsByCheck: { check: string; count: number }[] }>("/recruiter/reports"),
  runVerification: (applicationId: string) => http.post<VerificationJob>(`/recruiter/applicants/${applicationId}/verification/run`),
  verificationJob: (applicationId: string) => http.get<VerificationJob | null>(`/recruiter/applicants/${applicationId}/verification/job`),
  reviewDuplicate: (applicationId: string, alertId: string, body: { status: "not_duplicate" | "confirmed_duplicate" | "open"; note: string }) =>
    http.post<{ ok: true }>(`/recruiter/applicants/${applicationId}/duplicates/${alertId}/review`, body),
  issuerConfirmation: (applicationId: string, body: { result: "confirmed" | "denied" | "no_record"; detail: string; reference: string }) =>
    http.post<{ ok: true }>(`/recruiter/applicants/${applicationId}/issuer-confirmation`, body),
  referenceRequest: (applicationId: string, body: { referenceId?: string; employmentId?: string; refereeName?: string; refereeContact?: string }) =>
    http.post<{ id: string; link: string; expiresAt: string; refereeName: string; refereeContact: string }>(`/recruiter/applicants/${applicationId}/reference-requests`, body),
  simulateReference: (applicationId: string, requestId: string, body: { confirmed: boolean; comments: string }) =>
    http.post<{ ok: true }>(`/recruiter/applicants/${applicationId}/reference-requests/${requestId}/simulate`, body),
  evidence: (applicationId: string) => http.get<EvidenceTimeline>(`/recruiter/applicants/${applicationId}/evidence`),
  passport: (applicationId: string) => http.get<PassportAdmin>(`/recruiter/applicants/${applicationId}/passport`),
  issuePassport: (applicationId: string) => http.post<PassportAdmin>(`/recruiter/applicants/${applicationId}/passport`),
  revokePassport: (applicationId: string, reason: string) => http.post<PassportAdmin>(`/recruiter/applicants/${applicationId}/passport/revoke`, { reason }),
  settings: () => http.get<RecruiterSettings>("/recruiter/settings"),
  updateSettings: (body: Omit<RecruiterSettings, "team">) => http.put<RecruiterSettings>("/recruiter/settings", body),
};

export type ReferenceView = { status: "sent" | "responded" | "expired" | "cancelled"; candidateName: string; company: string; claimedTitle: string; claimedStart: string; claimedEnd: string; refereeName: string; expiresAt: string };

export const referenceApi = {
  view: (token: string) => http.get<ReferenceView>(`/reference/${encodeURIComponent(token)}`),
  respond: (token: string, body: { confirmed: boolean; title: string; start: string; end: string; comments: string; responderName: string; responderRole: string }) =>
    http.post<{ ok: true }>(`/reference/${encodeURIComponent(token)}`, body),
};

export const passportApi = {
  verify: (ref: string) => http.get<PassportVerification>(`/passport/verify/${encodeURIComponent(ref)}`),
};

export const digilockerApi = {
  status: () => http.get<DigiLockerStatus>("/candidate/digilocker"),
  start: () => http.post<{ authorizeUrl: string; mode: string }>("/candidate/digilocker/start", { consent: true }),
  fetch: (uri: string) => http.post<{ document: DigiLockerStatus["document"] }>("/candidate/digilocker/fetch", { uri }),
  remove: () => http.del<{ ok: true }>("/candidate/digilocker"),
  simView: (state: string) => http.get<{ simulated: true; documents: { name: string; issuer: string; doctype: string }[] }>(`/digilocker/simulated/${encodeURIComponent(state)}`),
  simDecide: (state: string, allow: boolean) => http.post<{ redirect: string }>(`/digilocker/simulated/${encodeURIComponent(state)}`, { allow }),
};
