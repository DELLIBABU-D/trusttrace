/**
 * Small history-based router (React Router style API: Link, NavLink, useNavigate, useParams, Routes).
 * Kept dependency-free so the app builds offline; the API mirrors React Router so it can be swapped later.
 */
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type AnchorHTMLAttributes, type MouseEvent, type ReactNode } from "react";

type Location = { pathname: string; search: string };
type Navigate = (to: string, opts?: { replace?: boolean }) => void;

const LocationCtx = createContext<{ location: Location; navigate: Navigate }>({
  location: { pathname: "/", search: "" },
  navigate: () => undefined,
});
const ParamsCtx = createContext<Record<string, string>>({});

function read(): Location {
  return { pathname: window.location.pathname, search: window.location.search };
}

export function RouterProvider({ children }: { children: ReactNode }) {
  const [location, setLocation] = useState<Location>(read);

  useEffect(() => {
    const onPop = () => setLocation(read());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, []);

  const navigate = useCallback<Navigate>((to, opts) => {
    if (opts?.replace) window.history.replaceState(null, "", to);
    else window.history.pushState(null, "", to);
    setLocation(read());
    const hash = to.split("#")[1];
    if (hash) requestAnimationFrame(() => document.getElementById(hash)?.scrollIntoView({ behavior: "smooth" }));
    else window.scrollTo(0, 0);
  }, []);

  const value = useMemo(() => ({ location, navigate }), [location, navigate]);
  return <LocationCtx.Provider value={value}>{children}</LocationCtx.Provider>;
}

export const useLocation = () => useContext(LocationCtx).location;
export const useNavigate = () => useContext(LocationCtx).navigate;
export const useParams = <T extends Record<string, string> = Record<string, string>>() => useContext(ParamsCtx) as T;

export function useSearchParam(name: string): string | null {
  return new URLSearchParams(useLocation().search).get(name);
}

/** "/recruiter/jobs/:id/edit" matched against a pathname. Returns params or null. */
export function matchPath(pattern: string, pathname: string): Record<string, string> | null {
  const p = pattern.split("/").filter(Boolean);
  const s = pathname.split("/").filter(Boolean);
  if (p.length !== s.length) return null;
  const params: Record<string, string> = {};
  for (let i = 0; i < p.length; i++) {
    if (p[i].startsWith(":")) params[p[i].slice(1)] = decodeURIComponent(s[i]);
    else if (p[i] !== s[i]) return null;
  }
  return params;
}

export type RouteDef = { path: string; element: ReactNode };

export function Routes({ routes, fallback }: { routes: RouteDef[]; fallback: ReactNode }) {
  const { pathname } = useLocation();
  for (const r of routes) {
    const params = matchPath(r.path, pathname);
    if (params) return <ParamsCtx.Provider value={params}>{r.element}</ParamsCtx.Provider>;
  }
  return <>{fallback}</>;
}

type LinkProps = Omit<AnchorHTMLAttributes<HTMLAnchorElement>, "href"> & { to: string; replace?: boolean };

export function Link({ to, replace, onClick, children, ...rest }: LinkProps) {
  const navigate = useNavigate();
  const handle = (e: MouseEvent<HTMLAnchorElement>) => {
    onClick?.(e);
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || rest.target === "_blank") return;
    if (/^(https?:|mailto:|tel:)/.test(to)) return;
    e.preventDefault();
    navigate(to, { replace });
  };
  return (
    <a href={to} onClick={handle} {...rest}>
      {children}
    </a>
  );
}

/** Link that knows whether it points at the current section. */
export function NavLink({ to, end, className, children, ...rest }: Omit<LinkProps, "className" | "children"> & { end?: boolean; className: (active: boolean) => string; children: ReactNode }) {
  const { pathname } = useLocation();
  const base = to.split("#")[0];
  const active = end ? pathname === base : pathname === base || pathname.startsWith(base + "/");
  return (
    <Link to={to} className={className(active)} aria-current={active ? "page" : undefined} {...rest}>
      {children}
    </Link>
  );
}

export function Redirect({ to }: { to: string }) {
  const navigate = useNavigate();
  useEffect(() => navigate(to, { replace: true }), [to, navigate]);
  return null;
}
