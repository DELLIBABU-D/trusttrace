import { Link } from "../lib/router";
import { cx } from "./ui";

export function LogoMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 32 32" className={cx("size-7", className)} aria-hidden>
      <path d="M16 3.5l10 3.8v7.4c0 6.3-4.2 11.7-10 13.8-5.8-2.1-10-7.5-10-13.8V7.3z" fill="#0d8b76" />
      <path d="M16 3.5l10 3.8v7.4c0 6.3-4.2 11.7-10 13.8z" fill="#2eb497" />
      <path d="M11.5 15.8l3.2 3.2 5.8-6.4" fill="none" stroke="#fff" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

export function Logo({ to = "/", tone = "dark", className }: { to?: string; tone?: "dark" | "light"; className?: string }) {
  return (
    <Link to={to} className={cx("flex items-center gap-2 text-[17px] font-semibold tracking-tight", tone === "light" ? "text-white" : "text-ink", className)} aria-label="TrustTrace home">
      <LogoMark />
      TrustTrace
    </Link>
  );
}
