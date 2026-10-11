/** HTTP client for /api. Distinguishes "backend not connected" from real request errors. */

export type ApiErrorKind = "unavailable" | "unauthorized" | "forbidden" | "validation" | "not_found" | "conflict" | "server";

export class ApiError extends Error {
  constructor(message: string, readonly status: number, readonly kind: ApiErrorKind, readonly code?: string, readonly fields?: Record<string, string>) {
    super(message);
  }
}

const TOKEN_KEY = "tt.session";
const listeners = new Set<(connected: boolean) => void>();
let connected: boolean | null = null;

function setConnected(value: boolean) {
  if (connected === value) return;
  connected = value;
  listeners.forEach((fn) => fn(value));
}

/** Subscribe to backend connectivity (null until the first request finishes). */
export function onConnectivity(fn: (connected: boolean) => void) {
  listeners.add(fn);
  if (connected !== null) fn(connected);
  return () => listeners.delete(fn);
}

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}
export function setToken(token: string | null) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* storage blocked: session lasts for this tab only */
  }
}

const UNAVAILABLE = "Can't reach the TrustTrace server, so nothing was saved. Check that `python serve.py` is running, then try again.";

/** Fired when the server rejects the stored session (expired, revoked or signed out elsewhere). */
const sessionListeners = new Set<() => void>();
export function onSessionExpired(fn: () => void) {
  sessionListeners.add(fn);
  return () => sessionListeners.delete(fn);
}

function detail(body: unknown): string | null {
  if (body && typeof body === "object" && "detail" in body) {
    const d = (body as { detail: unknown }).detail;
    if (typeof d === "string") return d;
    if (Array.isArray(d) && d[0] && typeof d[0] === "object" && "msg" in d[0]) return String((d[0] as { msg: unknown }).msg);
  }
  return null;
}

/** Random per-browser ID (no personal data). The server stores only a keyed hash of it, to notice several candidate
 *  accounts used from one browser. Explained in the registration consent text. */
function deviceId(): string | null {
  try {
    let id = localStorage.getItem("tt.device");
    if (!id) {
      id = typeof crypto !== "undefined" && "randomUUID" in crypto ? crypto.randomUUID() : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}-${Math.random().toString(36).slice(2)}`;
      localStorage.setItem("tt.device", id);
    }
    return id;
  } catch {
    return null;
  }
}

export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const device = deviceId();
  if (device) headers["X-TT-Device"] = device;
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  const isForm = typeof FormData !== "undefined" && body instanceof FormData;
  if (body !== undefined && !isForm) headers["Content-Type"] = "application/json";

  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method, headers, body: body === undefined ? undefined : isForm ? (body as FormData) : JSON.stringify(body) });
  } catch {
    setConnected(false);
    throw new ApiError(UNAVAILABLE, 0, "unavailable");
  }

  const isJson = (res.headers.get("content-type") || "").includes("application/json");
  const data: unknown = isJson ? await res.json().catch(() => null) : null;

  if (res.status === 503 || res.status === 502 || (!isJson && res.status >= 400)) {
    setConnected(false);
    throw new ApiError(UNAVAILABLE, res.status, "unavailable");
  }
  setConnected(true);
  if (res.ok) return data as T;
  const msg = detail(data) ?? `Request failed (${res.status}).`;
  const info = (data && typeof data === "object" ? data : {}) as { code?: string; fields?: Record<string, string> };
  if (res.status === 401) {
    if (token && !path.startsWith("/auth/login")) {
      setToken(null);
      sessionListeners.forEach((fn) => fn());
    }
    throw new ApiError(msg, 401, "unauthorized", info.code);
  }
  if (res.status === 403) throw new ApiError(msg, 403, "forbidden", info.code);
  if (res.status === 404) throw new ApiError(msg, 404, "not_found", info.code);
  if (res.status === 409) throw new ApiError(msg, 409, "conflict", info.code);
  if (res.status === 400 || res.status === 413 || res.status === 415 || res.status === 422) throw new ApiError(msg, res.status, "validation", info.code, info.fields);
  throw new ApiError(msg, res.status, "server", info.code);
}

export const http = {
  get: <T,>(path: string) => request<T>("GET", path),
  post: <T,>(path: string, body?: unknown) => request<T>("POST", path, body ?? {}),
  put: <T,>(path: string, body: unknown) => request<T>("PUT", path, body),
  del: <T,>(path: string) => request<T>("DELETE", path),
};

export function isUnavailable(err: unknown): boolean {
  return err instanceof ApiError && err.kind === "unavailable";
}

export function errorMessage(err: unknown): string {
  return err instanceof Error ? err.message : "Something went wrong. Try again.";
}
