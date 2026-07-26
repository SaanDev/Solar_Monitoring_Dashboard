import { clsx } from "clsx";
import type { LucideIcon } from "lucide-react";

interface MetricCardProps {
  label: string;
  value: string | number | null;
  unit?: string;
  icon?: LucideIcon;
  trend?: "up" | "down" | "neutral";
  /** `unknown` = the value could not be fetched; never render that as green. */
  severity?: "ok" | "watch" | "warning" | "critical" | "unknown";
  loading?: boolean;
}

const severityColor = {
  ok: "text-accent-green",
  watch: "text-accent-yellow",
  warning: "text-accent-orange",
  critical: "text-accent-red",
  // Neutral, not green — "we don't know" must not look like "all clear".
  unknown: "text-slate-500",
};

export function MetricCard({
  label,
  value,
  unit,
  icon: Icon,
  severity = "ok",
  loading = false,
}: MetricCardProps) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs text-slate-500 uppercase tracking-wider">{label}</span>
        {Icon && <Icon className="h-4 w-4 text-slate-600" />}
      </div>
      {loading ? (
        <div className="h-7 w-24 animate-pulse rounded bg-surface-muted" />
      ) : (
        <p className={clsx("text-2xl font-bold font-mono", severityColor[severity])}>
          {value ?? "—"}
          {unit && <span className="ml-1 text-sm font-normal text-slate-500">{unit}</span>}
        </p>
      )}
    </div>
  );
}
