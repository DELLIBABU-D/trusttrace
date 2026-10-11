import { useEffect, useId, useRef, type ButtonHTMLAttributes, type ComponentType, type ReactNode } from "react";
import { LuCircleAlert, LuCircleCheck, LuInfo, LuLoader, LuX } from "react-icons/lu";
import type { ApplicationStatus, CheckStatus, VerificationStatus } from "../api/types";
import { Link } from "../lib/router";

export type IconType = ComponentType<{ className?: string; "aria-hidden"?: boolean | "true" }>;

export function cx(...parts: (string | false | null | undefined)[]) {
  return parts.filter(Boolean).join(" ");
}

/* ------------------------------------------------------------------ buttons */

type Variant = "primary" | "secondary" | "ghost" | "danger" | "outline";
const variants: Record<Variant, string> = {
  primary: "bg-brand-600 text-white hover:bg-brand-700 shadow-sm disabled:bg-brand-600/50",
  secondary: "bg-white text-ink border border-line hover:bg-surface disabled:text-ink-3",
  outline: "bg-white text-brand-700 border border-brand-600 hover:bg-brand-50 disabled:opacity-50",
  ghost: "text-ink-2 hover:bg-surface hover:text-ink disabled:opacity-50",
  danger: "bg-bad text-white hover:bg-[#a72222] shadow-sm disabled:opacity-50",
};
const sizes = { sm: "h-8 px-3 text-[13px] gap-1.5", md: "h-10 px-4 text-sm gap-2", lg: "h-11 px-5 text-[15px] gap-2" };

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & { variant?: Variant; size?: keyof typeof sizes; loading?: boolean; icon?: IconType };

export function Button({ variant = "primary", size = "md", loading, icon: Icon, className, children, disabled, type = "button", ...rest }: ButtonProps) {
  return (
    <button type={type} disabled={disabled || loading} className={cx("inline-flex items-center justify-center rounded-lg font-medium whitespace-nowrap transition-colors", variants[variant], sizes[size], className)} {...rest}>
      {loading ? <LuLoader className="size-4 animate-spin" aria-hidden /> : Icon ? <Icon className="size-4" aria-hidden /> : null}
      {children}
    </button>
  );
}

export function ButtonLink({ to, variant = "primary", size = "md", icon: Icon, className, children }: { to: string; variant?: Variant; size?: keyof typeof sizes; icon?: IconType; className?: string; children: ReactNode }) {
  return (
    <Link to={to} className={cx("inline-flex items-center justify-center rounded-lg font-medium whitespace-nowrap transition-colors", variants[variant], sizes[size], className)}>
      {Icon && <Icon className="size-4" aria-hidden />}
      {children}
    </Link>
  );
}

/* ------------------------------------------------------------------ surfaces */

export function Card({ className, children, as: As = "section" }: { className?: string; children: ReactNode; as?: "section" | "div" | "article" }) {
  return <As className={cx("rounded-(--radius-card) border border-line bg-white shadow-(--shadow-card)", className)}>{children}</As>;
}

export function CardHeader({ title, action, sub }: { title: ReactNode; action?: ReactNode; sub?: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-3 px-5 pt-4 pb-3">
      <div>
        <h2 className="text-[15px] font-semibold text-ink">{title}</h2>
        {sub && <p className="mt-0.5 text-[13px] text-ink-3">{sub}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ title, sub, actions, back }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode; back?: { to: string; label: string } }) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        {back && (
          <Link to={back.to} className="mb-1 inline-block text-[13px] font-medium text-ink-3 hover:text-brand-700">
            ← {back.label}
          </Link>
        )}
        <h1 className="text-[22px] leading-tight font-semibold tracking-tight text-ink sm:text-2xl">{title}</h1>
        {sub && <p className="mt-1 text-sm text-ink-2">{sub}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  );
}

const tileTones = {
  blue: "bg-info-soft text-info",
  amber: "bg-warn-soft text-warn",
  violet: "bg-violet-soft text-violet",
  green: "bg-brand-50 text-brand-600",
};

export function StatCard({ icon: Icon, value, label, tone = "green", loading }: { icon: IconType; value: ReactNode; label: string; tone?: keyof typeof tileTones; loading?: boolean }) {
  return (
    <Card as="div" className="flex flex-col items-start gap-3 px-4 py-4 sm:flex-row sm:items-center">
      <span className={cx("grid size-10 shrink-0 place-items-center rounded-lg", tileTones[tone])}>
        <Icon className="size-5" aria-hidden />
      </span>
      <div className="min-w-0">
        <p className="text-2xl leading-none font-semibold text-ink tabular-nums">{loading ? <span className="inline-block h-6 w-8 animate-pulse rounded bg-line" /> : value}</p>
        <p className="mt-1 text-[13px] leading-snug text-ink-3">{label}</p>
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------------ status */

type Tone = "green" | "amber" | "red" | "gray" | "blue" | "violet";
const pillTones: Record<Tone, string> = {
  green: "bg-ok-soft text-ok",
  amber: "bg-warn-soft text-warn",
  red: "bg-bad-soft text-bad",
  gray: "bg-surface text-ink-2 border border-line",
  blue: "bg-info-soft text-info",
  violet: "bg-violet-soft text-violet",
};

export function Pill({ tone, children, className }: { tone: Tone; children: ReactNode; className?: string }) {
  return <span className={cx("inline-flex items-center rounded-md px-2 py-0.5 text-xs font-medium whitespace-nowrap", pillTones[tone], className)}>{children}</span>;
}

const verificationMap: Record<VerificationStatus, [Tone, string]> = {
  verified: ["green", "Verified"],
  pending: ["amber", "Pending"],
  not_started: ["gray", "Not started"],
  failed: ["red", "Failed"],
  flagged: ["red", "Flagged"],
  consistent: ["green", "Consistent"],
  inconsistent: ["red", "Inconsistent"],
  needs_review: ["amber", "Needs review"],
  processing: ["blue", "Processing"],
};
export const VerificationPill = ({ status }: { status: VerificationStatus }) => <Pill tone={verificationMap[status][0]}>{verificationMap[status][1]}</Pill>;

const checkMap: Record<CheckStatus, [Tone, string]> = {
  passed: ["green", "Passed"],
  pending: ["amber", "Pending"],
  failed: ["red", "Failed"],
  not_started: ["gray", "Not started"],
  review: ["amber", "Needs review"],
};
export const CheckPill = ({ status }: { status: CheckStatus }) => <Pill tone={checkMap[status][0]}>{checkMap[status][1]}</Pill>;

const appMap: Record<ApplicationStatus, [Tone, string]> = {
  applied: ["gray", "Applied"],
  verification: ["amber", "Verification"],
  clarification: ["amber", "Clarification needed"],
  assessment: ["blue", "Assessment"],
  interview: ["green", "Interview"],
  resume_review: ["amber", "Resume review"],
  shortlisted: ["green", "Shortlisted"],
  offer: ["violet", "Offer"],
  hired: ["green", "Hired"],
  rejected: ["red", "Rejected"],
};
export const ApplicationPill = ({ status }: { status: ApplicationStatus }) => <Pill tone={appMap[status][0]}>{appMap[status][1]}</Pill>;
export const applicationLabel = (s: ApplicationStatus) => appMap[s][1];

export function Chip({ children }: { children: ReactNode }) {
  return <span className="inline-flex items-center rounded-md bg-info-soft px-2 py-0.5 text-xs font-medium text-[#3a5a8c]">{children}</span>;
}

export function ScoreBadge({ score }: { score: number | null }) {
  if (score === null) return <span className="text-ink-3">—</span>;
  const tone = score >= 75 ? "bg-ok-soft text-ok" : score >= 50 ? "bg-warn-soft text-warn" : "bg-bad-soft text-bad";
  return <span className={cx("inline-flex min-w-9 justify-center rounded-md px-2 py-0.5 text-xs font-semibold tabular-nums", tone)}>{score}</span>;
}

/* ------------------------------------------------------------------ feedback */

export function EmptyState({ icon: Icon, title, children, action, compact }: { icon: IconType; title: string; children?: ReactNode; action?: ReactNode; compact?: boolean }) {
  return (
    <div className={cx("flex flex-col items-center text-center", compact ? "px-4 py-8" : "px-6 py-14")}>
      <span className="grid size-12 place-items-center rounded-full bg-surface text-ink-3">
        <Icon className="size-6" aria-hidden />
      </span>
      <p className="mt-3 text-[15px] font-semibold text-ink">{title}</p>
      {children && <p className="mt-1 max-w-sm text-[13px] text-ink-3">{children}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Notice({ tone = "info", title, children, onClose }: { tone?: "info" | "error" | "success" | "warn"; title?: string; children: ReactNode; onClose?: () => void }) {
  const styles = {
    info: ["bg-info-soft border-[#c9daf4] text-[#1f4a8f]", LuInfo],
    error: ["bg-bad-soft border-[#f3c4c1] text-[#8e1f1f]", LuCircleAlert],
    success: ["bg-ok-soft border-[#bfe5cc] text-[#145c2f]", LuCircleCheck],
    warn: ["bg-warn-soft border-[#f0dca2] text-[#7a4a06]", LuCircleAlert],
  } as const;
  const [cls, Icon] = styles[tone];
  return (
    <div role={tone === "error" ? "alert" : "status"} className={cx("flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-[13px]", cls)}>
      <Icon className="mt-0.5 size-4 shrink-0" aria-hidden />
      <div className="min-w-0 flex-1">
        {title && <p className="font-semibold">{title}</p>}
        <div>{children}</div>
      </div>
      {onClose && (
        <button onClick={onClose} className="rounded p-0.5 opacity-70 hover:opacity-100" aria-label="Dismiss">
          <LuX className="size-4" aria-hidden />
        </button>
      )}
    </div>
  );
}

export function Spinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-10 text-[13px] text-ink-3" role="status">
      <LuLoader className="size-4 animate-spin" aria-hidden /> {label}
    </div>
  );
}

export function Avatar({ name, src, size = 36 }: { name?: string | null; src?: string | null; size?: number }) {
  const initials = (name ?? "")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase())
    .join("");
  if (src) return <img src={src} alt="" width={size} height={size} className="shrink-0 rounded-full object-cover" style={{ width: size, height: size }} />;
  return (
    <span aria-hidden className="grid shrink-0 place-items-center rounded-full bg-brand-100 font-semibold text-brand-700" style={{ width: size, height: size, fontSize: size * 0.36 }}>
      {initials || "?"}
    </span>
  );
}

export function ProgressBar({ value, label }: { value: number; label: string }) {
  const v = Math.max(0, Math.min(100, value));
  return (
    <div role="progressbar" aria-label={label} aria-valuenow={v} aria-valuemin={0} aria-valuemax={100} className="h-2 w-full overflow-hidden rounded-full bg-line">
      <div className="h-full rounded-full bg-brand-600 transition-[width]" style={{ width: `${v}%` }} />
    </div>
  );
}

/** Circular score gauge (trust score, document match score). */
export function RingScore({ value, max = 100, size = 120, label, sub }: { value: number | null; max?: number; size?: number; label: string; sub?: string }) {
  const stroke = Math.max(8, size / 12);
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const pct = value === null ? 0 : Math.max(0, Math.min(1, value / max));
  const color = value === null ? "#cfd7db" : pct >= 0.75 ? "#0d8b76" : pct >= 0.5 ? "#d49a1c" : "#c42b2b";
  return (
    <div className="relative grid place-items-center" style={{ width: size, height: size }} role="img" aria-label={value === null ? `${label}: not available yet` : `${label}: ${value} out of ${max}`}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e8edef" strokeWidth={stroke} />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={color} strokeWidth={stroke} strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - pct)} />
      </svg>
      <div className="absolute inset-0 grid place-content-center text-center">
        <p className="font-semibold text-ink tabular-nums" style={{ fontSize: size * 0.2 }}>
          {value === null ? "—" : value}
          <span className="text-ink-3" style={{ fontSize: size * 0.1 }}>/{max}</span>
        </p>
        {sub && <p className="mx-auto max-w-[80%] leading-tight text-ink-3" style={{ fontSize: Math.max(10, size * 0.075) }}>{sub}</p>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ navigation widgets */

export function Tabs<T extends string>({ tabs, value, onChange, label }: { tabs: { id: T; label: string }[]; value: T; onChange: (v: T) => void; label: string }) {
  return (
    <div role="tablist" aria-label={label} className="flex gap-1 overflow-x-auto rounded-lg border border-line bg-white p-1">
      {tabs.map((t) => (
        <button
          key={t.id}
          role="tab"
          aria-selected={value === t.id}
          onClick={() => onChange(t.id)}
          className={cx("rounded-md px-3 py-1.5 text-[13px] font-medium whitespace-nowrap", value === t.id ? "bg-brand-600 text-white" : "text-ink-2 hover:bg-surface")}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Stepper({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className="flex w-full items-start">
      {steps.map((s, i) => {
        const done = i < current;
        const active = i === current;
        return (
          <li key={s} className="relative flex flex-1 flex-col items-center text-center">
            {i > 0 && <span aria-hidden className={cx("absolute top-4 right-1/2 h-0.5 w-full -translate-x-4", done || active ? "bg-brand-500" : "bg-line")} />}
            <span
              className={cx("relative z-10 grid size-8 place-items-center rounded-full text-[13px] font-semibold", done ? "bg-brand-600 text-white" : active ? "bg-brand-600 text-white ring-4 ring-brand-100" : "bg-[#8ea2ad] text-white")}
              aria-current={active ? "step" : undefined}
            >
              {done ? "✓" : i + 1}
            </span>
            <span className={cx("mt-2 text-xs", active ? "font-semibold text-ink" : "text-ink-3")}>{s}</span>
          </li>
        );
      })}
    </ol>
  );
}

/* ------------------------------------------------------------------ form fields */

export const inputCls =
  "w-full rounded-lg border border-line-strong bg-white px-3 py-2.5 text-sm text-ink placeholder:text-ink-3 focus:border-brand-500 focus:ring-2 focus:ring-brand-100 focus:outline-none aria-invalid:border-bad disabled:bg-surface";

export function Field({ label, htmlFor, error, hint, children, className, required }: { label: string; htmlFor: string; error?: string; hint?: string; children: ReactNode; className?: string; required?: boolean }) {
  return (
    <div className={className}>
      <label htmlFor={htmlFor} className="mb-1.5 block text-[13px] font-medium text-ink-2">
        {label}
        {required && <span className="text-bad"> *</span>}
      </label>
      {children}
      {error ? (
        <p id={`${htmlFor}-error`} className="mt-1 text-xs text-bad">{error}</p>
      ) : hint ? (
        <p className="mt-1 text-xs text-ink-3">{hint}</p>
      ) : null}
    </div>
  );
}

export function Toggle({ checked, onChange, label, description }: { checked: boolean; onChange: (v: boolean) => void; label: string; description?: string }) {
  const id = useId();
  return (
    <div className="flex items-start justify-between gap-4 py-3">
      <div>
        <label htmlFor={id} className="text-sm font-medium text-ink">{label}</label>
        {description && <p className="text-[13px] text-ink-3">{description}</p>}
      </div>
      <button id={id} role="switch" aria-checked={checked} onClick={() => onChange(!checked)} className={cx("relative h-6 w-11 shrink-0 rounded-full transition-colors", checked ? "bg-brand-600" : "bg-line-strong")}>
        <span className={cx("absolute top-0.5 size-5 rounded-full bg-white shadow transition-[left]", checked ? "left-[22px]" : "left-0.5")} />
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ modal */

export function Modal({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: string; children: ReactNode; footer?: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const prev = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>("input, textarea, select, button")?.focus();
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => (window.removeEventListener("keydown", onKey), prev?.focus());
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 grid place-items-center bg-navy-950/40 p-4" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div ref={ref} role="dialog" aria-modal="true" aria-label={title} className="w-full max-w-lg rounded-xl bg-white shadow-(--shadow-pop)">
        <div className="flex items-center justify-between border-b border-line px-5 py-4">
          <h2 className="text-base font-semibold">{title}</h2>
          <button onClick={onClose} className="rounded p-1 text-ink-3 hover:bg-surface" aria-label="Close">
            <LuX className="size-4" aria-hidden />
          </button>
        </div>
        <div className="px-5 py-4">{children}</div>
        {footer && <div className="flex justify-end gap-2 border-t border-line px-5 py-3">{footer}</div>}
      </div>
    </div>
  );
}
