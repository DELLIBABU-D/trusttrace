import { useState, type ReactNode } from "react";
import { z } from "zod";
import { LuArrowRight, LuBriefcase, LuUser } from "react-icons/lu";
import { errorMessage } from "../../api/client";
import { authApi } from "../../api/endpoints";
import type { Role } from "../../api/types";
import { homeFor, useAuth } from "../../auth/AuthContext";
import { Logo } from "../../components/Logo";
import { Button, Field, Notice, Tabs, inputCls } from "../../components/ui";
import { PREVIEW_MODE } from "../../config";
import { useZodForm } from "../../lib/form";
import { Link, useNavigate, useSearchParam } from "../../lib/router";
import { useMutation } from "../../lib/query";

function AuthFrame({ children, wide }: { children: ReactNode; wide?: boolean }) {
  return (
    <div className="flex min-h-screen flex-col bg-gradient-to-b from-[#eef6f4] to-surface">
      <header className="mx-auto flex w-full max-w-[1200px] items-center px-4 py-5 sm:px-6">
        <Logo />
      </header>
      <main className="flex flex-1 items-start justify-center px-4 pt-4 pb-16 sm:pt-10">
        <div className={wide ? "w-full max-w-2xl" : "w-full max-w-md"}>{children}</div>
      </main>
    </div>
  );
}

/* ------------------------------------------------------------------ login */

const loginSchema = z.object({
  email: z.string().trim().min(1, "Enter your email").email("Enter a valid email address"),
  password: z.string().min(1, "Enter your password"),
});

export function Login() {
  const initial = (useSearchParam("role") as Role | null) ?? "candidate";
  const next = useSearchParam("next");
  const [role, setRole] = useState<Role>(initial === "recruiter" ? "recruiter" : "candidate");
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const form = useZodForm(loginSchema, { email: "", password: "" });
  const login = useMutation((v: z.infer<typeof loginSchema>) => signIn(role, v.email, v.password), {
    // only same-site paths: "/x" but never "//host" or "https://…"
    onSuccess: (u) => navigate(next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("/\\") ? next : homeFor(u.role)),
  });

  return (
    <AuthFrame>
      <div className="rounded-2xl border border-line bg-white p-7 shadow-(--shadow-card) sm:p-8">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="mt-1 text-sm text-ink-2">Welcome back. Choose how you use TrustTrace.</p>
        <div className="mt-5">
          <Tabs label="Account type" value={role} onChange={(r) => (setRole(r), login.reset())} tabs={[{ id: "candidate", label: "Candidate" }, { id: "recruiter", label: "Recruiter" }]} />
        </div>
        <form className="mt-5 space-y-4" onSubmit={form.handleSubmit((v) => void login.mutate(v))} noValidate>
          {login.error ? <Notice tone="error">{errorMessage(login.error)}</Notice> : null}
          <Field label={role === "recruiter" ? "Work email" : "Email"} htmlFor="email" error={form.errors.email}>
            <input type="email" autoComplete="username" className={inputCls} {...form.register("email")} />
          </Field>
          <Field label="Password" htmlFor="password" error={form.errors.password}>
            <input type="password" autoComplete="current-password" className={inputCls} {...form.register("password")} />
          </Field>
          <Button type="submit" className="w-full" size="lg" loading={login.isPending}>Sign in</Button>
        </form>
        <p className="mt-5 text-center text-[13px] text-ink-3">
          New to TrustTrace?{" "}
          {role === "recruiter" ? (
            <Link to="/recruiter/register" className="font-medium text-brand-700 hover:underline">Create a recruiter account</Link>
          ) : (
            <Link to="/register" className="font-medium text-brand-700 hover:underline">Register as a candidate</Link>
          )}
        </p>
      </div>
      {PREVIEW_MODE && (
        <div className="mt-5 rounded-xl border border-dashed border-line-strong bg-white/70 p-4 text-[13px] text-ink-2">
          <p className="font-medium text-ink">Phase 1 preview</p>
          <p className="mt-0.5">Accounts are created in Phase 2. Until then you can open each area directly:</p>
          <div className="mt-3 flex flex-wrap gap-2">
            <Link to="/candidate" className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-1.5 font-medium text-ink hover:border-brand-500"><LuUser className="size-4" aria-hidden /> Candidate area <LuArrowRight className="size-3.5" aria-hidden /></Link>
            <Link to="/recruiter" className="inline-flex items-center gap-1.5 rounded-lg border border-line bg-white px-3 py-1.5 font-medium text-ink hover:border-brand-500"><LuBriefcase className="size-4" aria-hidden /> Recruiter area <LuArrowRight className="size-3.5" aria-hidden /></Link>
          </div>
        </div>
      )}
    </AuthFrame>
  );
}

/* ------------------------------------------------------------------ recruiter registration */

const recruiterSchema = z
  .object({
    fullName: z.string().trim().min(3, "Enter your full name"),
    organisation: z.string().trim().min(2, "Enter your company name"),
    email: z.string().trim().email("Enter a valid work email"),
    phone: z.string().trim().regex(/^\+?[0-9 ]{10,15}$/, "Enter a valid phone number"),
    companySize: z.string().min(1, "Choose a company size"),
    password: z.string().min(8, "Use at least 8 characters").regex(/[A-Z]/, "Include an uppercase letter").regex(/[0-9]/, "Include a number"),
    confirm: z.string(),
    terms: z.boolean().refine((v) => v, "Accept the data processing terms to continue"),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords don't match" });

export function RecruiterRegister() {
  const navigate = useNavigate();
  const { acceptSession } = useAuth();
  const form = useZodForm(recruiterSchema, { fullName: "", organisation: "", email: "", phone: "", companySize: "", password: "", confirm: "", terms: false });
  const create = useMutation(({ confirm: _c, terms: _t, ...body }: z.infer<typeof recruiterSchema>) => authApi.registerRecruiter(body), {
    onSuccess: (r) => (acceptSession(r.token, r.user), navigate("/recruiter")),
  });

  return (
    <AuthFrame wide>
      <div className="rounded-2xl border border-line bg-white p-7 shadow-(--shadow-card) sm:p-8">
        <h1 className="text-2xl font-semibold tracking-tight">Create a recruiter account</h1>
        <p className="mt-1 text-sm text-ink-2">Post roles, review verified applicants and make decisions with full evidence.</p>
        <form className="mt-6 grid gap-4 sm:grid-cols-2" onSubmit={form.handleSubmit((v) => void create.mutate(v))} noValidate>
          {create.error ? <div className="sm:col-span-2"><Notice tone="error">{errorMessage(create.error)}</Notice></div> : null}
          <Field label="Full name" htmlFor="fullName" error={form.errors.fullName} required>
            <input autoComplete="name" className={inputCls} {...form.register("fullName")} />
          </Field>
          <Field label="Company" htmlFor="organisation" error={form.errors.organisation} required>
            <input autoComplete="organization" className={inputCls} {...form.register("organisation")} />
          </Field>
          <Field label="Work email" htmlFor="email" error={form.errors.email} required>
            <input type="email" autoComplete="email" className={inputCls} {...form.register("email")} />
          </Field>
          <Field label="Phone" htmlFor="phone" error={form.errors.phone} required>
            <input type="tel" autoComplete="tel" className={inputCls} {...form.register("phone")} />
          </Field>
          <Field label="Company size" htmlFor="companySize" error={form.errors.companySize} required className="sm:col-span-2">
            <select className={inputCls} {...form.register("companySize")}>
              <option value="">Select</option>
              <option value="1-50">1–50 employees</option>
              <option value="51-200">51–200 employees</option>
              <option value="201-1000">201–1,000 employees</option>
              <option value="1000+">More than 1,000 employees</option>
            </select>
          </Field>
          <Field label="Password" htmlFor="password" error={form.errors.password} hint="At least 8 characters with an uppercase letter and a number" required>
            <input type="password" autoComplete="new-password" className={inputCls} {...form.register("password")} />
          </Field>
          <Field label="Confirm password" htmlFor="confirm" error={form.errors.confirm} required>
            <input type="password" autoComplete="new-password" className={inputCls} {...form.register("confirm")} />
          </Field>
          <div className="sm:col-span-2">
            <label className="flex items-start gap-2.5 text-[13px] text-ink-2">
              <input className="mt-0.5 size-4 accent-brand-600" {...form.checkbox("terms")} />
              I agree to process candidate data only with their consent and to review every flag before deciding.
            </label>
            {form.errors.terms && <p className="mt-1 text-xs text-bad">{form.errors.terms}</p>}
          </div>
          <div className="flex flex-wrap items-center justify-between gap-3 sm:col-span-2">
            <p className="text-[13px] text-ink-3">
              Already registered? <Link to="/login?role=recruiter" className="font-medium text-brand-700 hover:underline">Sign in</Link>
            </p>
            <Button type="submit" size="lg" loading={create.isPending}>Create account</Button>
          </div>
        </form>
      </div>
    </AuthFrame>
  );
}
