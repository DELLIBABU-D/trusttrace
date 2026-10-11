import { useEffect, useState, type ReactNode } from "react";
import {
  LuBell, LuBriefcase, LuChartColumn, LuCalendarClock, LuClipboardCheck, LuHouse, LuLayoutDashboard, LuLogIn, LuLogOut, LuMenu, LuMessageSquare,
  LuSettings, LuShieldCheck, LuSquarePlus, LuUser, LuUsers, LuX, LuServerOff, LuEye,
} from "react-icons/lu";
import { onConnectivity } from "../api/client";
import type { Role } from "../api/types";
import { useAuth } from "../auth/AuthContext";
import { Logo } from "../components/Logo";
import { Avatar, cx, type IconType } from "../components/ui";
import { PREVIEW_MODE } from "../config";
import { Link, useLocation, useNavigate } from "../lib/router";

type NavItem = { label: string; to: string; icon: IconType; match?: string[]; end?: boolean };

const NAV: Record<Role, NavItem[]> = {
  candidate: [
    { label: "Home", to: "/candidate", icon: LuHouse, end: true },
    { label: "My Applications", to: "/candidate/applications", icon: LuBriefcase, match: ["/candidate/applications", "/candidate/jobs"] },
    { label: "Assessments", to: "/candidate/assessments", icon: LuClipboardCheck, match: ["/candidate/assessments", "/candidate/interviews"] },
    { label: "My Profile", to: "/candidate/profile", icon: LuUser, match: ["/candidate/profile", "/candidate/documents"] },
    { label: "Verification", to: "/candidate/verification", icon: LuShieldCheck, match: ["/candidate/verification", "/candidate/passport"] },
    { label: "Messages", to: "/candidate/messages", icon: LuMessageSquare },
  ],
  recruiter: [
    { label: "Dashboard", to: "/recruiter", icon: LuLayoutDashboard, end: true },
    { label: "Post a Job", to: "/recruiter/jobs", icon: LuSquarePlus },
    { label: "Applicants", to: "/recruiter/applicants", icon: LuUsers },
    { label: "Assessments", to: "/recruiter/assessments", icon: LuClipboardCheck },
    { label: "Interviews", to: "/recruiter/interviews", icon: LuCalendarClock },
    { label: "Reports", to: "/recruiter/reports", icon: LuChartColumn },
    { label: "Settings", to: "/recruiter/settings", icon: LuSettings },
  ],
};

function isActive(item: NavItem, pathname: string) {
  if (item.end) return pathname === item.to;
  return (item.match ?? [item.to]).some((m) => pathname === m || pathname.startsWith(m + "/"));
}

function useBackendConnected() {
  const [connected, setConnected] = useState<boolean | null>(null);
  useEffect(() => onConnectivity(setConnected) as () => void, []);
  return connected;
}

export function AppShell({ role, children }: { role: Role; children: ReactNode }) {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const { user, signOut } = useAuth();
  const [open, setOpen] = useState(false);
  const connected = useBackendConnected();
  const home = role === "recruiter" ? "/recruiter" : "/candidate";

  useEffect(() => setOpen(false), [pathname]);

  const sidebar = (
    <nav aria-label={role === "recruiter" ? "Recruiter" : "Candidate"} className="flex h-full flex-col bg-navy-900 px-3 py-5">
      <div className="flex items-center justify-between px-2">
        <Logo to={home} tone="light" />
        <button className="rounded p-1 text-navy-300 lg:hidden" onClick={() => setOpen(false)} aria-label="Close menu">
          <LuX className="size-5" aria-hidden />
        </button>
      </div>
      <ul className="mt-8 space-y-1">
        {NAV[role].map((item) => {
          const active = isActive(item, pathname);
          return (
            <li key={item.to}>
              <Link
                to={item.to}
                aria-current={active ? "page" : undefined}
                className={cx(
                  "flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13.5px] font-medium transition-colors",
                  active ? "bg-gradient-to-r from-brand-600 to-brand-500 text-white shadow-sm" : "text-navy-200 hover:bg-navy-800 hover:text-white",
                )}
              >
                <item.icon className="size-[18px] shrink-0" aria-hidden />
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
      <div className="mt-auto border-t border-navy-700 pt-3">
        {user ? (
          <button onClick={() => void signOut().then(() => navigate("/login"))} className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-[13.5px] font-medium text-navy-200 hover:bg-navy-800 hover:text-white">
            <LuLogOut className="size-[18px]" aria-hidden /> Sign out
          </button>
        ) : (
          <Link to={`/login?role=${role}`} className="flex items-center gap-3 rounded-lg px-3 py-2.5 text-[13.5px] font-medium text-navy-200 hover:bg-navy-800 hover:text-white">
            <LuLogIn className="size-[18px]" aria-hidden /> Sign in
          </Link>
        )}
      </div>
    </nav>
  );

  return (
    <div className="min-h-screen bg-surface lg:pl-60">
      <aside className="fixed inset-y-0 left-0 z-30 hidden w-60 lg:block">{sidebar}</aside>
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div className="absolute inset-0 bg-navy-950/50" onClick={() => setOpen(false)} />
          <aside className="absolute inset-y-0 left-0 w-64">{sidebar}</aside>
        </div>
      )}

      <header className="sticky top-0 z-20 flex h-16 items-center gap-3 border-b border-line bg-white/90 px-4 backdrop-blur sm:px-6">
        <button className="rounded-lg p-2 text-ink-2 hover:bg-surface lg:hidden" onClick={() => setOpen(true)} aria-label="Open menu">
          <LuMenu className="size-5" aria-hidden />
        </button>
        <div className="lg:hidden">
          <Logo to={home} />
        </div>
        <div className="ml-auto flex items-center gap-2 sm:gap-4">
          <Link to={role === "candidate" ? "/candidate/messages" : "/recruiter/applicants"} className="relative rounded-lg p-2 text-ink-2 hover:bg-surface" aria-label="Notifications">
            <LuBell className="size-5" aria-hidden />
          </Link>
          {user ? (
            <div className="flex items-center gap-2.5">
              <Avatar name={user.fullName} src={user.avatarUrl} size={34} />
              <div className="hidden text-right leading-tight sm:block">
                <p className="text-[13px] font-semibold text-ink">{user.fullName}</p>
                <p className="text-xs text-ink-3 capitalize">{user.organisation ?? user.role}</p>
              </div>
            </div>
          ) : (
            <Link to={`/login?role=${role}`} className="rounded-lg border border-line px-3 py-1.5 text-[13px] font-medium text-ink-2 hover:bg-surface">
              Sign in
            </Link>
          )}
        </div>
      </header>

      {(PREVIEW_MODE && !user) || connected === false || (role === "recruiter" && user?.organisationStatus && user.organisationStatus !== "approved") ? (
        <div className="border-b border-[#f0dca2] bg-warn-soft px-4 py-2 text-[12.5px] text-[#7a4a06] sm:px-6">
          <div className="flex flex-wrap gap-x-5 gap-y-1">
            {PREVIEW_MODE && !user && (
              <span className="inline-flex items-center gap-1.5">
                <LuEye className="size-3.5" aria-hidden /> Preview mode: you are viewing this area without signing in. Sign-in is enforced from Phase 2.
              </span>
            )}
            {connected === false && (
              <span className="inline-flex items-center gap-1.5">
                <LuServerOff className="size-3.5" aria-hidden /> Can't reach the TrustTrace server. Changes can't be saved until it's running again.
              </span>
            )}
            {role === "recruiter" && user?.organisationStatus === "pending" && (
              <span className="inline-flex items-center gap-1.5">
                <LuEye className="size-3.5" aria-hidden /> Your organisation is awaiting approval. You can prepare jobs now; candidates see them once it's approved.
              </span>
            )}
            {role === "recruiter" && user?.organisationStatus === "suspended" && (
              <span className="inline-flex items-center gap-1.5">
                <LuServerOff className="size-3.5" aria-hidden /> Your organisation is suspended. Your jobs are hidden from candidates.
              </span>
            )}
          </div>
        </div>
      ) : null}

      <main className="mx-auto w-full max-w-[1240px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">{children}</main>
    </div>
  );
}
