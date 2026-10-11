import type { ReactNode } from "react";
import { LuCompass } from "react-icons/lu";
import type { Role } from "./api/types";
import { RequireRole } from "./auth/AuthContext";
import { Logo } from "./components/Logo";
import { ButtonLink, EmptyState } from "./components/ui";
import { AppShell } from "./layouts/AppShell";
import { Link, Routes, type RouteDef } from "./lib/router";
import { Assessments, AssessmentRunner, InterviewVerification } from "./pages/candidate/Assessment";
import { ApplicationDetail, AvailableJobs, CandidateDashboard, MyApplications } from "./pages/candidate/Jobs";
import { Messages, PassportPage, Profile } from "./pages/candidate/Profile";
import { CandidateRegister } from "./pages/candidate/Register";
import { Documents, EducationVerification, EmploymentVerification, VerificationOverview } from "./pages/candidate/Verification";
import { Login, RecruiterRegister } from "./pages/public/Auth";
import { Landing } from "./pages/public/Landing";
import { ReferenceResponse } from "./pages/public/ReferenceResponse";
import { VerifyPassport } from "./pages/public/VerifyPassport";
import { SimulatedDigiLocker } from "./pages/candidate/DigiLocker";
import {
  Applicants, JobForm, RecruiterDashboard, RecruiterInterviews, RecruiterJobs, RecruiterReports, RecruiterSettingsPage,
} from "./pages/recruiter/Recruiter";
import { TrustReport } from "./pages/recruiter/TrustReport";
import { AssessmentBuilderPage, AttemptDetailPage, RecruiterAssessments } from "./pages/recruiter/Assessments";

const area = (role: Role, page: ReactNode) => (
  <RequireRole role={role}>
    <AppShell role={role}>{page}</AppShell>
  </RequireRole>
);
const c = (path: string, page: ReactNode): RouteDef => ({ path: `/candidate${path}`, element: area("candidate", page) });
const r = (path: string, page: ReactNode): RouteDef => ({ path: `/recruiter${path}`, element: area("recruiter", page) });

const routes: RouteDef[] = [
  { path: "/", element: <Landing /> },
  { path: "/login", element: <Login /> },
  { path: "/register", element: <PublicFrame><CandidateRegister /></PublicFrame> },
  { path: "/recruiter/register", element: <RecruiterRegister /> },
  { path: "/reference/:token", element: <ReferenceResponse /> },
  { path: "/verify/:ref", element: <VerifyPassport /> },
  { path: "/digilocker-simulated", element: <SimulatedDigiLocker /> },

  c("", <CandidateDashboard />),
  c("/jobs", <AvailableJobs />),
  c("/applications", <MyApplications />),
  c("/applications/:id", <ApplicationDetail />),
  c("/documents", <Documents />),
  c("/verification", <VerificationOverview />),
  c("/verification/education", <EducationVerification />),
  c("/verification/employment", <EmploymentVerification />),
  c("/assessments", <Assessments />),
  c("/assessments/:id", <AssessmentRunner />),
  c("/interviews/:id", <InterviewVerification />),
  c("/profile", <Profile />),
  c("/messages", <Messages />),
  c("/passport", <PassportPage />),

  r("", <RecruiterDashboard />),
  r("/jobs", <RecruiterJobs />),
  r("/jobs/new", <JobForm />),
  r("/jobs/:id/edit", <JobForm />),
  r("/jobs/:id/assessment", <AssessmentBuilderPage />),
  r("/applicants", <Applicants />),
  r("/applicants/:id", <TrustReport />),
  r("/assessments", <RecruiterAssessments />),
  r("/assessments/:id", <AttemptDetailPage />),
  r("/interviews", <RecruiterInterviews />),
  r("/reports", <RecruiterReports />),
  r("/settings", <RecruiterSettingsPage />),
];

function PublicFrame({ children }: { children: ReactNode }) {
  return (
    <div className="min-h-screen bg-surface">
      <header className="border-b border-line bg-white">
        <div className="mx-auto flex max-w-[1180px] items-center justify-between px-4 py-3.5 sm:px-6">
          <Logo />
          <p className="text-[13px] text-ink-3">
            Already registered? <Link to="/login" className="font-medium text-brand-700 hover:underline">Sign in</Link>
          </p>
        </div>
      </header>
      <main className="mx-auto max-w-[1180px] px-4 py-8 sm:px-6">{children}</main>
    </div>
  );
}

function NotFound() {
  return (
    <div className="grid min-h-screen place-items-center bg-surface px-4">
      <EmptyState icon={LuCompass} title="Page not found" action={<ButtonLink to="/">Go to home</ButtonLink>}>
        The link may be mistyped, or the page has moved.
      </EmptyState>
    </div>
  );
}

export function App() {
  return <Routes routes={routes} fallback={<NotFound />} />;
}
