/**
 * Minimal data-fetching cache with a TanStack Query style API (useQuery / useMutation / invalidate).
 * Each query key is fetched once, shared between components, and refetched when invalidated.
 */
import { useCallback, useEffect, useRef, useState } from "react";

type Entry = { data?: unknown; error?: unknown; status: "idle" | "loading" | "success" | "error" | "stale"; promise?: Promise<void> };
const cache = new Map<string, Entry>();
const listeners = new Map<string, Set<() => void>>();

function emit(key: string) {
  listeners.get(key)?.forEach((fn) => fn());
}

function run<T>(key: string, fn: () => Promise<T>): Promise<void> {
  const entry = cache.get(key) ?? { status: "idle" };
  const promise = fn()
    .then((data) => {
      cache.set(key, { data, status: "success" });
    })
    .catch((error) => {
      cache.set(key, { error, status: "error", data: cache.get(key)?.data });
    })
    .finally(() => emit(key));
  cache.set(key, { ...entry, status: "loading", promise });
  emit(key);
  return promise;
}

export type QueryResult<T> = { data: T | undefined; error: unknown; isLoading: boolean; isError: boolean; refetch: () => Promise<void> };

export function useQuery<T>(key: string, fn: () => Promise<T>, opts: { enabled?: boolean } = {}): QueryResult<T> {
  const enabled = opts.enabled ?? true;
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const [, force] = useState(0);

  useEffect(() => {
    const set = listeners.get(key) ?? new Set();
    const rerender = () => force((n) => n + 1);
    set.add(rerender);
    listeners.set(key, set);
    return () => {
      set.delete(rerender);
    };
  }, [key]);

  // Fetch on mount, when the key changes, and again after invalidate() marked the entry stale.
  useEffect(() => {
    const e = cache.get(key);
    if (enabled && (!e || e.status === "stale")) void run(key, () => fnRef.current());
  });

  const entry = cache.get(key);
  const refetch = useCallback(() => run(key, () => fnRef.current()), [key]);
  return {
    data: entry?.data as T | undefined,
    error: entry?.error,
    // Only "loading" while there is nothing to show yet; background refetches keep the current data on screen.
    isLoading: enabled && (!entry || (entry.status === "loading" && entry.data === undefined)),
    isError: entry?.status === "error",
    refetch,
  };
}

/** Mark cached results whose key starts with prefix as stale. Mounted queries refetch in the background and keep
 *  showing their current data meanwhile (so forms and panels on the page don't unmount and lose their state). */
export function invalidate(prefix: string) {
  for (const key of [...cache.keys()]) {
    const e = cache.get(key)!;
    if (key.startsWith(prefix) && e.status !== "loading") {
      cache.set(key, { ...e, status: "stale" });
      emit(key);
    }
  }
}

/** Forget everything (used on sign-in and sign-out so one account never sees another's data). */
export function clearCache() {
  const keys = [...cache.keys()];
  cache.clear();
  keys.forEach(emit);
}

export type MutationResult<TIn, TOut> = {
  mutate: (input: TIn) => Promise<TOut | undefined>;
  isPending: boolean;
  error: unknown;
  data: TOut | undefined;
  reset: () => void;
};

export function useMutation<TIn, TOut>(fn: (input: TIn) => Promise<TOut>, opts: { onSuccess?: (out: TOut) => void; invalidates?: string[] } = {}): MutationResult<TIn, TOut> {
  const [state, setState] = useState<{ isPending: boolean; error: unknown; data: TOut | undefined }>({ isPending: false, error: undefined, data: undefined });
  const mutate = async (input: TIn) => {
    setState({ isPending: true, error: undefined, data: undefined });
    try {
      const out = await fn(input);
      setState({ isPending: false, error: undefined, data: out });
      opts.invalidates?.forEach(invalidate);
      opts.onSuccess?.(out);
      return out;
    } catch (error) {
      setState({ isPending: false, error, data: undefined });
      return undefined;
    }
  };
  return { ...state, mutate, reset: () => setState({ isPending: false, error: undefined, data: undefined }) };
}
