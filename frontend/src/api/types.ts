/** Domain types shared by the UI and the Phase 2 API. */

export type Role = "candidate" | "recruiter";
export type VerificationStatus = "not_started" | "pending" | "verified" | "failed" | "flagged" | "consistent" | "inconsistent" | "needs_review" | "processing";
export type CheckStatus = "passed" | "pending" | "failed" | "not_started" | "review";
export type ApplicationStatus = "applied" | "verification" | "assessment" | "interview" | "resume_review" | "shortlisted" | "clarification" | "offer" | "hired" | "rejected";
export type EmploymentType = "full_time" | "part_time" | "internship" | "contract";
export type WorkMode = "onsite" | "remote" | "hybrid";

export interface SessionUser {
  id: string;
  role: Role;
  fullName: string;
  email: string;
  organisation?: string | null;
  organisationStatus?: "pending" | "approved" | "suspended" | null;
  avatarUrl?: string | null;
}

export interface Job {
  id: string;
  title: string;
  company: string;
  department?: string;
  location: string;
  employmentType: EmploymentType;
  workMode: WorkMode;
  experienceMin: number;
  experienceMax: number;
  salaryMin?: number | null;
  salaryMax?: number | null;
  skills: string[];
  description: string;
  assessments: string[];
  deadline?: string | null;
  postedAt: string;
  requirements?: string;
  status: "draft" | "open" | "closed";
  applicantCount?: number;
  applied?: boolean;
}

export type JobInput = Omit<Job, "id" | "postedAt" | "applicantCount" | "company" | "applied">;

export interface Application {
  id: string;
  jobId: string;
  jobTitle: string;
  company: string;
  status: ApplicationStatus;
  appliedAt: string;
  trustScore: number | null;
  stages: { key: string; label: string; status: CheckStatus; at?: string | null }[];
  history?: { status: ApplicationStatus; note: string; at: string }[];
}

export interface CandidateProfile {
  id: string;
  fullName: string;
  email: string;
  phone: string;
  dateOfBirth: string;
  location: string;
  headline: string;
  linkedinUrl?: string;
  githubUrl?: string;
  skills: string[];
  photoUrl?: string | null;
  completeness: number; // 0-100, computed by the server
  phoneVerified?: boolean;
  education: EducationEntry[];
  experience: ExperienceEntry[];
  references: ReferenceEntry[];
  consents: { purpose: string; granted: boolean; policyVersion: string; recordedAt: string }[];
}

export interface EducationEntry { id?: string; degree: string; institution: string; startYear: string; endYear: string; score: string }
export interface ExperienceEntry { id?: string; company: string; title: string; start: string; end: string; current: boolean }
export interface ReferenceEntry { id?: string; name: string; relationship: string; company: string; email: string; phone: string }

export type ProfileInput = Pick<CandidateProfile, "fullName" | "email" | "phone" | "location" | "headline" | "linkedinUrl" | "githubUrl" | "skills"> & {
  education?: EducationEntry[];
  experience?: ExperienceEntry[];
  references?: ReferenceEntry[];
};

export interface VerificationItem {
  key: "identity" | "education" | "employment" | "resume" | "duplicate";
  label: string;
  status: VerificationStatus;
  updatedAt?: string | null;
  detail?: string | null;
}

export interface CandidateDashboard {
  appliedJobs: number;
  assessmentsPending: number;
  interviewsScheduled: number;
  trustScore: number | null;
  verification: VerificationItem[];
  recommendedJobs: Job[];
}

export interface UploadedDocument {
  id: string;
  kind: "resume" | "marksheet" | "education_certificate" | "id_document" | "experience_letter" | "certificate";
  fileName: string;
  sizeBytes: number;
  contentType?: string;
  sha256?: string;
  uploadedAt: string;
  previewUrl?: string | null;
  status: VerificationStatus;
}

export interface Evidence { documentId?: string | null; page?: number | null; snippet?: string | null; source?: string | null }

export interface FieldComparison {
  field: string;
  extracted: string | null;
  claimed: string | null;
  match: boolean | null;
  note?: string;
  evidence?: Evidence;
}

export interface VerificationFinding { code: string; severity: "info" | "warning" | "critical"; title: string; detail: string; evidence?: Evidence & Record<string, unknown> }

export interface IssuerStatus { status: "not_checked" | "confirmed" | "denied" | "no_record"; method?: string | null; simulated?: boolean; label: string; detail?: string; reference?: string }

export interface ReferenceRow {
  id: string; referee: string; company: string; status: "sent" | "responded" | "expired" | "cancelled"; simulated: boolean;
  confirmed: boolean | null; respondedAt: string | null; response: { title?: string; start?: string; end?: string; comments?: string } | null;
}

export interface VerificationJob { id: string; status: "queued" | "running" | "done" | "failed"; reason: string; createdAt: string; startedAt: string | null; finishedAt: string | null; error: string | null }

export interface IdentityResult {
  status: VerificationStatus; summary: string; at: string | null; error?: string | null;
  enrolment?: { status: string; quality?: Record<string, unknown>; model?: string; at?: string };
  idDocument?: { status: string; similarity?: number; threshold?: number; label: string };
  rechecks?: { stage: string; decision: string; similarity: number | null; at: string }[];
  findings?: VerificationFinding[];
}

export type FaceOutcome = "matched" | "uncertain" | "needs_review";
export interface IdentityCheckResult {
  decision: "match" | "no_match" | "no_face" | "multiple_faces" | "poor_quality" | "no_enrollment" | "no_consent" | "error" | "camera_unavailable";
  outcome: FaceOutcome; message: string; similarity: number | null; threshold?: number; liveness?: "not_checked";
}

export interface DuplicateAlertRow {
  id: string; kind: "phone" | "face"; similarity: number | null; evidence: { reason?: string; phoneLast4?: string; threshold?: number };
  otherAccount: string; reviewStatus: "open" | "not_duplicate" | "confirmed_duplicate"; reviewNote: string; reviewedAt: string | null; createdAt: string;
}

export interface DocumentVerification {
  documentId: string | null;
  previewUrl: string | null;
  downloadUrl?: string | null;
  fileName?: string | null;
  extracted: { label: string; value: string | null; confidence?: number | null; page?: number | null; snippet?: string | null; source?: string | null }[];
  confidence: number | null; // 0-100
  comparison: FieldComparison[];
  matchScore: number | null; // 0-100
  summary: string | null;
  status: VerificationStatus;
  findings?: VerificationFinding[];
  issuer?: IssuerStatus;
  digilocker?: DigiLockerComparison | null;
  references?: ReferenceRow[] | null;
  extraction?: { method: string; status: string; error: string; pages: number } | null;
  consistency?: string;
  at?: string | null;
  error?: string | null;
}

export interface VerificationEvent {
  id: string;
  at: string;
  check: string;
  result: VerificationStatus;
  detail: string;
}

export type AssessmentStatus = "assigned" | "in_progress" | "submitted";
export type SignalKind = "visibility_hidden" | "window_blur" | "copy" | "paste" | "cut" | "fullscreen_exit";

export interface AssessmentSummary {
  id: string;
  applicationId: string;
  title: string;
  skill?: string;
  jobTitle: string;
  questionCount: number;
  durationMinutes: number;
  status: AssessmentStatus;
  dueAt?: string | null;
  startedAt: string | null;
  submittedAt: string | null;
  submitReason: "submitted" | "time_up" | null;
  score: number | null;
  maxScore: number | null;
  percent: number | null;
  passPercent: number | null;
  perSkill: Record<string, { correct: number; total: number; percent: number }>;
  cameraConsent: boolean | null;
  signals: Record<SignalKind, number>;
  candidateName?: string;
}

export interface AssessmentEventRow { kind: string; at: string; clientAt: string | null; detail: Record<string, unknown>; reviewSignal: boolean; label: string | null }
export interface FaceCheckRow { decision: string; outcome: FaceOutcome; similarity: number | null; threshold: number | null; at: string }

export interface AssessmentAttemptDetail extends AssessmentSummary {
  candidateName: string;
  timeline: AssessmentEventRow[];
  faceChecks: FaceCheckRow[];
  answers?: { id: string; skill: string; prompt: string; options: { id: string; text: string }[]; chosen: string | null; correctOptionId: string; correct: boolean; source: string }[];
}

export interface AssessmentQuestion {
  id: string;
  skill?: string;
  prompt: string;
  code?: string | null;
  difficulty: "easy" | "medium" | "hard";
  options: { id: string; text: string }[];
}

export interface AssessmentSession {
  id: string;
  title: string;
  status: AssessmentStatus;
  durationSeconds: number;
  remainingSeconds: number;
  questionCount: number;
  cameraConsent: boolean | null;
  questions: AssessmentQuestion[];
  savedAnswers: Record<string, string>;
}

export interface TemplateQuestion {
  id: string; position: number; skill: string; difficulty: "easy" | "medium" | "hard"; prompt: string; code: string | null;
  options: { id: string; text: string }[]; correctOptionId: string; explanation: string;
  source: "gemini" | "question_bank" | "recruiter"; edited: boolean; approved: boolean; approvedAt: string | null;
}
export interface AssessmentTemplate {
  id: string; jobId: string; title: string; durationMinutes: number; passPercent: number; status: "draft" | "published"; generationNote: string;
  publishedAt: string | null; questions: TemplateQuestion[]; approvedCount: number; questionCount: number; assignedCount: number; submittedCount: number;
}
export interface AssessmentBuilder { job: { id: string; title: string; skills: string[] }; template: AssessmentTemplate | null; geminiConfigured: boolean }
export interface QuestionInput { skill: string; difficulty: "easy" | "medium" | "hard"; prompt: string; code: string; options: string[]; correctOptionId: string; explanation: string }

export interface SkillRow { skill: string; profile: boolean; resume: boolean; required: boolean; assessed: { correct: number; total: number; percent: number } | null; note: string }
export interface ProofOfSkill { skills: SkillRow[]; attempts: number; disclaimer: string; attemptsForThisJob?: AssessmentSummary[] }

export interface Interview {
  id: string;
  applicationId: string;
  candidateName: string;
  jobTitle: string;
  scheduledAt: string;
  durationMinutes: number;
  mode: "video" | "onsite";
  interviewer: string;
  meetingLink?: string | null;
  status: "scheduled" | "completed" | "cancelled";
  candidateResponse?: "accepted" | "reschedule_requested" | null;
  candidateNote?: string | null;
  acknowledgedAt?: string | null;
  entryOutcome?: FaceOutcome | null;
  entryCheckedAt?: string | null;
  faceChecks?: FaceCheckRow[];
}

export type InterviewInput = Pick<Interview, "applicationId" | "scheduledAt" | "durationMinutes" | "mode" | "interviewer" | "meetingLink">;

export interface RecruiterDashboard {
  needsAttention?: ApplicantRow[];
  reviewQueue?: { applicationsNeedingReview: number; openDuplicateAlerts: number; openPatternAlerts: number; pendingChecks: number };
  verificationSummary?: Record<"identity" | "education" | "employment", Record<CheckBucket, number>>;
  assessmentSummary?: { assigned: number; submitted: number; averagePercent: number | null };
  organisation: string;
  organisationStatus?: "pending" | "approved" | "suspended";
  openJobs?: number;
  totalApplicants: number;
  inAssessment: number;
  interviewsScheduled: number;
  offersSent: number;
  recentApplications: ApplicantRow[];
}

export interface ApplicantRow {
  risk?: "low" | "review" | "high";
  reviewCount?: number;
  pendingCount?: number;
  concerns?: string[];
  applicationId: string;
  candidateId: string;
  candidateName: string;
  photoUrl?: string | null;
  role: string;
  trustScore: number | null;
  status: ApplicationStatus;
  appliedAt: string;
}

export interface TrustCheck {
  key: string;
  title: string;
  detail: string;
  status: CheckStatus;
  points?: number;
  severity?: "info" | "warning" | "critical";
}

export interface TrustReport extends Partial<TrustBundle> {
  applicationId: string;
  status: ApplicationStatus;
  jobTitle: string;
  appliedAt: string;
  candidate: { id: string; fullName: string; headline: string; location: string; photoUrl?: string | null; email?: string; phone?: string; phoneVerified?: boolean };
  profile?: { skills: string[]; education: EducationEntry[]; experience: ExperienceEntry[]; references: ReferenceEntry[]; dateOfBirth: string | null; linkedinUrl: string; githubUrl: string };
  documents?: UploadedDocument[];
  history?: { status: ApplicationStatus; note: string; at: string }[];
  verification?: Record<"identity" | "education" | "employment" | "resume" | "duplicate", DocumentVerification & IdentityResult & { alerts?: DuplicateAlertRow[] }>;
  duplicateAlerts?: DuplicateAlertRow[];
  job?: VerificationJob | null;
  trustScore: number | null;
  risk: "low" | "review" | "high" | null;
  checks: TrustCheck[];
  sections: Record<"identity" | "education" | "employment" | "assessment" | "interview" | "risk", TrustCheck[]>;
  decisions: { id: string; decision: ReviewDecision; reason: string; reviewer: string; at: string }[];
}

export type ReviewDecision = "approve" | "reject" | "reverify";

/* ------------------------------------------------------------------ Phase 6: evidence chain & QR passport */

export type PassportCheckStatus = "verified" | "consistent" | "pending" | "not_started" | "needs_review" | "inconsistent";

export interface PassportClaimsView {
  passportId: string;
  candidateRef: string;
  issuer: string;
  role: string;
  checks: { key: string; label: string; status: PassportCheckStatus; text: string }[];
  skills: { title: string; score: string; percent: number | null; reviewSignals: number }[];
  reportVersion: string;
  chainHead: string;
  issuedAt: string;
  expiresAt: string;
}

export interface Passport extends PassportClaimsView {
  id: string;
  status: "active" | "revoked" | "superseded";
  statusReason: string | null;
  statusChangedAt: string | null;
  expired: boolean;
  verifyUrl: string;
  tokenUrl: string;
  qrDataUrl: string | null;
  token: string;
  jobTitle?: string;
  organisation?: string;
}

export interface CandidatePassports {
  passports: Passport[];
  candidateRef: string;
  candidateName: string;
  chain: { intact: boolean; events: number };
}

export interface PassportAdmin {
  eligibility: { eligible: boolean; reasons: string[]; chainIntact: boolean };
  active: Passport | null;
  history: { passportId: string; status: Passport["status"]; reason: string | null; issuedAt: string; expiresAt: string; changedAt: string | null }[];
}

export interface PassportVerification {
  result: "valid" | "invalid" | "expired" | "revoked" | "superseded" | "unknown";
  message: string;
  signature?: "valid";
  holderName?: string | null;
  passport?: PassportClaimsView;
  chain?: { intact: boolean; events?: number };
}

export interface ChainProblem { seq: number | null; eventId: string | null; reason: string; detail: string }

export interface ChainVerification {
  intact: boolean;
  events: number;
  keyId: string;
  checkedAt: string;
  head: { seq: number; hash: string; at: string } | null;
  problems: ChainProblem[];
}

export interface EvidenceEventRow {
  seq: number;
  type: string;
  label: string;
  detail: string;
  actorRole: "candidate" | "recruiter" | "system" | "referee";
  applicationId: string | null;
  at: string;
  hash: string;
  prevHash: string;
  hidden: boolean;
}

export interface EvidenceTimeline { events: EvidenceEventRow[]; verification: ChainVerification; note: string }

export interface RecruiterSettings {
  organisation: string;
  organisationStatus?: "pending" | "approved" | "suspended";
  website: string;
  retentionDays: number;
  notifyOnFlag: boolean;
  notifyDailyDigest: boolean;
  team: { id: string; name: string; email: string; role: string }[];
}

export interface Message {
  id: string;
  from: string;
  subject: string;
  body: string;
  at: string;
  read: boolean;
}


/* ------------------------------------------------------------------ Phase 5: explainable trust score & fraud intelligence */

export type CheckBucket = "verified" | "consistent" | "pending" | "needs_review" | "inconsistent" | "not_started";
export interface ScoreEvidence { type: string; id: string | null; label: string; at: string | null }
export interface ScoreEntry {
  ruleId: string; label: string; category: string; weight: number; applied: number; status: "applied" | "resolved" | "capped";
  evidence: ScoreEvidence[]; at: string | null; note: string;
}
export interface TrustCheckRow {
  key: string; title: string; bucket: CheckBucket; label: string; detail: string; simulated: boolean; runId: string | null; at: string | null;
  concernKey?: string | null; review: { status: "resolved" | "upheld"; note: string; at: string } | null;
}
export interface TrustBreakdown {
  version: string; baseline: number; score: number; rawScore: number; risk: "low" | "review" | "high";
  entries: ScoreEntry[]; checks: TrustCheckRow[]; groups: Record<CheckBucket, string[]>; pendingCount: number; reviewCount: number;
  assessment: { id: string; title: string; status: string; score: number | null; maxScore: number | null; percent: number | null; reviewSignals: number }[];
  disclaimer: string; scoreRecordId: string; computedAt: string; trigger: string;
}
export interface PatternAlertRow {
  id: string; ruleId: string; label: string; explanation: string; severity: "info" | "warning"; strength: "weak" | "medium";
  evidence: Record<string, unknown>; firstSeen: string; lastSeen: string; reviewStatus: "open" | "reviewed_ok" | "confirmed"; reviewNote: string | null; reviewedAt: string | null;
}
export interface GraphNode { id: string; kind: "candidate" | "phone" | "face" | "device" | "network"; label: string; focal?: boolean; applicationId?: string | null; appliedToYourOrg?: boolean; strength?: string; review?: string | null }
export interface GraphEdge { source: string; target: string; kind: string; strength: "strong" | "medium" | "weak" }
export interface RelationshipGraph {
  nodes: GraphNode[]; edges: GraphEdge[]; clusterSize: number; note: string;
  linked: { account: string; applicationId: string | null; strongest: "strong" | "medium" | "weak"; signals: { kind: string; label: string; strength: string; review?: string | null }[] }[];
}
export interface TrustBundle {
  trust: TrustBreakdown;
  scoreHistory: { id: string; score: number; version: string; trigger: string; at: string }[];
  patternAlerts: PatternAlertRow[];
  graph: RelationshipGraph;
  reportReviews: { id: string; note: string; reviewer: string; at: string; score: number | null; current: boolean }[];
}

/* ------------------------------------------------------------------ DigiLocker comparison */

export interface DigiLockerComparison {
  status: "match" | "mismatch" | "partial" | "no_upload" | "not_connected" | "off";
  mode?: "live" | "simulated";
  simulated?: boolean;
  documentId?: string;
  title?: string;
  issuer?: string;
  doctype?: string;
  issuedOn?: string;
  fetchedAt?: string;
  hmacVerified?: boolean;
  sha256?: string;
  summary?: string;
  rows?: { field: string; uploaded: string | null; digilocker: string | null; match: boolean | null }[];
}

export interface DigiLockerIssued { name: string; issuer: string; doctype: string; date: string; mime: string; uri: string; description: string; likelyEducation: boolean }

export interface DigiLockerStatus {
  mode: "live" | "simulated" | "off";
  enabled: boolean;
  simulated: boolean;
  connected: boolean;
  sessionExpired: boolean;
  issued: DigiLockerIssued[];
  document: { id: string; title: string; issuer: string; doctype: string; issuedOn: string; simulated: boolean; hmacVerified: boolean; fetchedAt: string; sha256: string; fields: Record<string, string | number | null> } | null;
  comparison: DigiLockerComparison | null;
  consentText: string;
}
