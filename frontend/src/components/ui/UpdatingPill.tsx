import { clsx } from "clsx";

/**
 * Small non-blocking "updating" badge, shown while fresh data is in flight and
 * stale content is still on screen.
 *
 * Lifted verbatim from the treatment already used in
 * `components/analysis/PlotView.tsx`, which kept the previously-rendered image
 * visible instead of blanking to a skeleton. The charts now do the same via
 * `keepPreviousData`, so they need the same honesty marker: without it, a chart
 * silently shows the *previous* range's data during the fetch.
 *
 * `inline` places it in a card header (charts); the default absolute position
 * suits an image/canvas container, whose parent must be `relative`.
 */
export function UpdatingPill({
  show,
  inline = false,
  label = "updating",
}: {
  show?: boolean;
  inline?: boolean;
  label?: string;
}) {
  if (!show) return null;

  return (
    <span
      // Not aria-live: this fires on every poll, and announcing "updating"
      // repeatedly would be noise rather than information.
      className={clsx(
        "flex items-center gap-1 rounded bg-surface-card/80 px-2 py-0.5 text-[10px] text-slate-400",
        !inline && "absolute right-2 top-2 z-10"
      )}
    >
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-blue" />
      {label}
    </span>
  );
}
