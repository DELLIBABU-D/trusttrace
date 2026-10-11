import type { ReactNode } from "react";
import { LuServerOff, LuTriangleAlert } from "react-icons/lu";
import { errorMessage, isUnavailable } from "../api/client";
import { Button, EmptyState, Spinner, type IconType } from "./ui";

/** Renders loading / error / empty / data for one query. */
export function DataState<T>({
  query,
  isEmpty,
  empty,
  children,
  loadingLabel,
}: {
  query: { data: T | undefined; error: unknown; isLoading: boolean; refetch: () => Promise<void> };
  isEmpty: (data: T) => boolean;
  empty: { icon: IconType; title: string; body?: ReactNode; action?: ReactNode };
  children: (data: T) => ReactNode;
  loadingLabel?: string;
}) {
  if (query.isLoading && query.data === undefined) return <Spinner label={loadingLabel} />;
  if (query.error && query.data === undefined) {
    if (isUnavailable(query.error))
      return (
        <EmptyState icon={LuServerOff} title="Can't reach the server" action={<Button variant="secondary" size="sm" onClick={() => void query.refetch()}>Try again</Button>}>
          Check that TrustTrace is running (python serve.py), then try again.
        </EmptyState>
      );
    return (
      <EmptyState icon={LuTriangleAlert} title="Couldn't load this" action={<Button variant="secondary" size="sm" onClick={() => void query.refetch()}>Try again</Button>}>
        {errorMessage(query.error)}
      </EmptyState>
    );
  }
  if (query.data === undefined || isEmpty(query.data))
    return (
      <EmptyState icon={empty.icon} title={empty.title} action={empty.action}>
        {empty.body}
      </EmptyState>
    );
  return <>{children(query.data)}</>;
}

/** Shown on a detail screen when the record can't be loaded. */
export function NotLoaded({ error, what }: { error: unknown; what: string }) {
  return (
    <EmptyState icon={LuServerOff} title={isUnavailable(error) ? "Can't reach the server" : `No ${what} to show`}>
      {isUnavailable(error) ? "Check that TrustTrace is running (python serve.py), then reload." : errorMessage(error)}
    </EmptyState>
  );
}
