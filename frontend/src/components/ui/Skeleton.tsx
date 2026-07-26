import { cn } from "@/lib/cn";

/**
 * Loading placeholder. ~30 sites inline `animate-pulse rounded bg-surface-muted`
 * with an ad-hoc height; this names the pattern without dictating dimensions,
 * so adopting it can't change any panel's layout.
 *
 * The pulse is disabled automatically under `prefers-reduced-motion` by the
 * global rule in styles/globals.css.
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <div
      aria-hidden="true"
      className={cn("animate-pulse rounded bg-surface-muted", className)}
    />
  );
}
