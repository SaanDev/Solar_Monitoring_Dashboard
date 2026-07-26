import { EmptyState } from "./EmptyState";

export interface AsyncPanelProps {
  isLoading?: boolean;
  /** The SWR `error`. Supplying this is the whole point — see the note below. */
  error?: unknown;
  isEmpty?: boolean;
  /**
   * The panel's own existing skeleton, passed in rather than generated. Keeping
   * each caller's bespoke skeleton means adopting AsyncPanel can't shift layout.
   */
  skeleton?: React.ReactNode;
  emptyMessage?: string;
  errorMessage?: string;
  children: React.ReactNode;
}

/**
 * Branch selector for the three states an async panel can be in — loading,
 * failed, empty — plus the happy path.
 *
 * This exists because the codebase overwhelmingly wrote `data?.rows ?? []` and
 * dropped `error` on the floor, which renders a backend outage as a confident
 * "No data". On a space-weather dashboard that is the difference between "the
 * Sun is quiet" and "we are flying blind", so `error` is checked *before*
 * `isEmpty` and gets a visually distinct treatment.
 *
 * It is deliberately a branch selector, not a design change: pass the skeleton
 * you already had and the loaded output is byte-identical to before.
 */
export function AsyncPanel({
  isLoading,
  error,
  isEmpty,
  skeleton,
  emptyMessage = "No data available.",
  errorMessage = "Couldn't load this data. The feed may be unavailable.",
  children,
}: AsyncPanelProps) {
  // Errors win over "empty" — an empty render during an outage is a lie.
  if (error) return <EmptyState tone="error" message={errorMessage} />;
  if (isLoading) return <>{skeleton ?? null}</>;
  if (isEmpty) return <EmptyState message={emptyMessage} />;
  return <>{children}</>;
}
