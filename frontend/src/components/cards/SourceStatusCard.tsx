import { clsx } from "clsx";
import type { SourceStatus } from "@/lib/types";

const dot = {
  ok: "bg-accent-green",
  degraded: "bg-accent-yellow",
  error: "bg-accent-red",
  unknown: "bg-slate-600",
};

export function SourceStatusCard({ sources }: { sources: SourceStatus[] }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4">
      <h3 className="text-xs text-slate-500 uppercase tracking-wider mb-3">Data Sources</h3>
      <ul className="space-y-2">
        {sources.map((s) => (
          <li key={s.name} className="flex items-center justify-between text-xs">
            <span className="text-slate-300">{s.name}</span>
            <span className="flex items-center gap-1.5 text-slate-500">
              <span className={clsx("h-2 w-2 rounded-full", dot[s.status])} />
              {s.status}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}
