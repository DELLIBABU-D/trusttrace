import type { ReactNode } from "react";
import { LuCircleAlert, LuCircleMinus, LuClock, LuFileCheck, LuShieldCheck } from "react-icons/lu";
import type { PassportCheckStatus, PassportClaimsView } from "../api/types";
import { formatDate } from "../lib/format";
import { LogoMark } from "./Logo";
import { Pill, cx } from "./ui";

const STATUS: Record<PassportCheckStatus, { tone: "green" | "blue" | "gray" | "amber" | "red"; label: string; icon: ReactNode }> = {
  verified: { tone: "green", label: "Verified", icon: <LuShieldCheck className="size-4 text-ok" aria-hidden /> },
  consistent: { tone: "blue", label: "Consistent", icon: <LuFileCheck className="size-4 text-info" aria-hidden /> },
  pending: { tone: "gray", label: "Pending", icon: <LuClock className="size-4 text-ink-3" aria-hidden /> },
  not_started: { tone: "gray", label: "Not checked", icon: <LuCircleMinus className="size-4 text-ink-3" aria-hidden /> },
  needs_review: { tone: "amber", label: "Needs review", icon: <LuCircleAlert className="size-4 text-warn" aria-hidden /> },
  inconsistent: { tone: "red", label: "Inconsistent", icon: <LuCircleAlert className="size-4 text-bad" aria-hidden /> },
};

const CLEAR = new Set(["duplicates", "patterns"]);

/** The passport document itself (same card style as the reference QR passport screen). Shows only what is in the signed token. */
export function PassportCard({ p, holderName, qrDataUrl, verifyUrl, banner, className }: {
  p: PassportClaimsView; holderName?: string | null; qrDataUrl?: string | null; verifyUrl?: string; banner?: ReactNode; className?: string;
}) {
  return (
    <div className={cx("overflow-hidden rounded-2xl border border-line bg-white shadow-(--shadow-card) print:shadow-none", className)}>
      <div className="flex items-center gap-2 bg-navy-900 px-6 py-4 text-white">
        <LogoMark className="size-7" />
        <span className="font-semibold">TrustTrace Passport</span>
        <span className="ml-auto font-mono text-xs text-navy-200">{p.passportId}</span>
      </div>
      {banner}
      <div className="grid gap-6 p-6 sm:grid-cols-[1fr_auto]">
        <div className="min-w-0">
          <p className="text-lg font-semibold text-ink">{holderName || "Candidate"}</p>
          <p className="font-mono text-xs text-ink-3">Reference {p.candidateRef}</p>
          <p className="mt-1 text-[13px] text-ink-2">{p.role} · issued by {p.issuer}</p>
          <p className="text-[13px] text-ink-3">Issued {formatDate(p.issuedAt)} · Valid till {formatDate(p.expiresAt)}</p>
          <ul className="mt-4 divide-y divide-line rounded-lg border border-line">
            {p.checks.map((c) => (
              <li key={c.key} className="flex items-start gap-2.5 px-3 py-2 text-[13.5px]">
                <span className="mt-0.5">{STATUS[c.status]?.icon}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-ink">{c.label}</span>
                  {c.text !== STATUS[c.status]?.label && <span className="block text-xs text-ink-3">{c.text}</span>}
                </span>
                <Pill tone={STATUS[c.status]?.tone ?? "gray"}>{CLEAR.has(c.key) && c.status === "consistent" ? "Clear" : STATUS[c.status]?.label ?? c.status}</Pill>
              </li>
            ))}
          </ul>
          {p.skills.length > 0 && (
            <div className="mt-4">
              <p className="text-[13px] font-medium text-ink">Skill assessment</p>
              <ul className="mt-1 space-y-1 text-[13px] text-ink-2">
                {p.skills.map((s, i) => (
                  <li key={i}>{s.title}: <span className="font-semibold tabular-nums text-ink">{s.score}</span>{s.percent != null ? ` (${s.percent}%)` : ""}
                    {s.reviewSignals > 0 && <span className="text-ink-3"> · {s.reviewSignals} integrity review signal(s)</span>}</li>
                ))}
              </ul>
            </div>
          )}
          <p className="mt-4 text-[11.5px] leading-snug text-ink-3">
            “Verified” means the check was actually completed. “Consistent” means the documents agree with each other but were not confirmed with the
            issuer. Pending and simulated checks are never shown as verified. Report version {p.reportVersion}.
          </p>
        </div>
        {(qrDataUrl || verifyUrl) && (
          <div className="flex flex-col items-center">
            {qrDataUrl ? (
              <img src={qrDataUrl} alt={`QR code that opens ${verifyUrl}`} className="size-40 rounded-lg border border-line bg-white p-1" />
            ) : (
              <div className="grid size-40 place-items-center rounded-lg border border-dashed border-line-strong p-3 text-center text-xs text-ink-3">No QR: this passport is not active</div>
            )}
            <p className="mt-2 text-xs text-ink-3">Scan to verify</p>
            {verifyUrl && <a href={verifyUrl} className="mt-1 max-w-40 truncate text-xs font-medium text-brand-700 hover:underline">{verifyUrl.replace(/^https?:\/\//, "")}</a>}
          </div>
        )}
      </div>
    </div>
  );
}
