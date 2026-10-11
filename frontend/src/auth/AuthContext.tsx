import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { getToken, onSessionExpired, setToken } from "../api/client";
import { authApi } from "../api/endpoints";
import { clearCache } from "../lib/query";
import { isUnavailable } from "../api/client";
import type { Role, SessionUser } from "../api/types";
import { PREVIEW_MODE } from "../config";
import { Redirect, useLocation } from "../lib/router";

type AuthState = {
  user: SessionUser | null;
  status: "loading" | "anonymous" | "authenticated";
  signIn: (role: Role, email: string, password: string) => Promise<SessionUser>;
  acceptSession: (token: string, user: SessionUser) => void;
  signOut: () => Promise<void>;
};

const AuthCtx = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<SessionUser | null>(null);
  const [status, setStatus] = useState<AuthState["status"]>(getToken() ? "loading" : "anonymous");

  useEffect(() => {
    if (!getToken()) return;
    authApi
      .me()
      .then((u) => (setUser(u), setStatus("authenticated")))
      .catch((err) => {
        if (!isUnavailable(err)) setToken(null);
        setStatus("anonymous");
      });
  }, []);

  useEffect(() => onSessionExpired(() => (setUser(null), setStatus("anonymous"))), []);

  const acceptSession = useCallback((token: string, u: SessionUser) => {
    clearCache();
    setToken(token);
    setUser(u);
    setStatus("authenticated");
  }, []);

  const signIn = useCallback(async (role: Role, email: string, password: string) => {
    const r = await authApi.login({ role, email, password });
    acceptSession(r.token, r.user);
    return r.user;
  }, [acceptSession]);

  const signOut = useCallback(async () => {
    await authApi.logout().catch(() => undefined);
    setToken(null);
    clearCache();
    setUser(null);
    setStatus("anonymous");
  }, []);

  const value = useMemo(() => ({ user, status, signIn, signOut, acceptSession }), [user, status, signIn, signOut, acceptSession]);
  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>;
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside AuthProvider");
  return ctx;
}

export const homeFor = (role: Role) => (role === "recruiter" ? "/recruiter" : "/candidate");

/** Role gate. In Phase 1 preview mode it lets everyone through (the shell shows a preview banner). */
export function RequireRole({ role, children }: { role: Role; children: ReactNode }) {
  const { user, status } = useAuth();
  const { pathname } = useLocation();
  if (PREVIEW_MODE) return <>{children}</>;
  if (status === "loading") return null;
  if (!user) return <Redirect to={`/login?role=${role}&next=${encodeURIComponent(pathname)}`} />;
  if (user.role !== role) return <Redirect to={homeFor(user.role)} />;
  return <>{children}</>;
}
