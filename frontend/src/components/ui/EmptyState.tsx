import { clsx } from "clsx";
import { AlertTriangle, type LucideIcon } from "lucide-react";

export interface EmptyStateProps {
  /** The sentence shown to the user. Say what's missing, not just "no data". */
  message: string;
  icon?: LucideIcon;
  /**
   * `empty` — the query succeeded and there genuinely is nothing (dashed, muted).
   * `error`  — the request failed; this must never be mistaken for "all clear".
   */
  tone?: "empty" | "error";
  /** Optional retry button or link. */
  action?: React.ReactNode;
  className?: string;
}

/**
 * The two ways a panel can have nothing to show, styled so they can't be
 * confused with one another.
 *
 * Before this, ~9 different inline phrasings/styles covered "empty", and a
 * failed fetch usually rendered through the *same* one — so an outage read as
 * quiet space weather. The dashed `empty` treatment is lifted from the one good
 * instance that already existed (app/timeline/TimelineClient.tsx); the tinted
 * `error` treatment from components/analyzer/shock/ShockAnalysisPanel.tsx.
 */
export function EmptyState({
  message,
  icon: Icon,
  tone = "empty",
  action,
  className,
}: EmptyStateProps) {
  const isError = tone === "error";
  const ResolvedIcon = Icon ?? (isError ? AlertTriangle : undefined);

  return (
    <div
      // Errors are announced; a genuine empty result is not worth interrupting for.
      role={isError ? "alert" : undefined}
      className={clsx(
        "flex h-full w-full flex-col items-center justify-center gap-1.5 rounded-lg p-6 text-center",
        isError
          ? "border border-accent-red/40 bg-accent-red/10"
          : "border border-dashed border-surface-border",
        className
      )}
    >
      {ResolvedIcon && (
        <ResolvedIcon
          className={clsx(
            "h-4 w-4 shrink-0",
            isError ? "text-accent-red" : "text-slate-500"
          )}
        />
      )}
      <p
        className={clsx(
          "max-w-prose text-xs leading-relaxed",
          isError ? "text-accent-red" : "text-slate-500"
        )}
      >
        {message}
      </p>
      {action}
    </div>
  );
}
