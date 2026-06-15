import type { Alert } from "@/lib/types";
import { formatUtcShort } from "@/lib/formatting";
import { clsx } from "clsx";

const severityColor = {
  info: "border-accent-blue/40 bg-accent-blue/5",
  watch: "border-accent-yellow/40 bg-accent-yellow/5",
  warning: "border-accent-orange/40 bg-accent-orange/5",
  critical: "border-accent-red/40 bg-accent-red/5",
};

export function AlertFeed({ alerts }: { alerts: Alert[] }) {
  if (!alerts.length) {
    return (
      <div className="flex h-20 items-center justify-center text-xs text-slate-700">
        No active alerts
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {alerts.map((a) => (
        <li
          key={a.id}
          className={clsx("rounded border px-3 py-2 text-xs", severityColor[a.severity])}
        >
          <div className="flex items-center justify-between mb-0.5">
            <span className="font-semibold text-slate-200">{a.type}</span>
            <span className="text-slate-600">{formatUtcShort(a.timestamp)}</span>
          </div>
          <p className="text-slate-400">{a.message}</p>
        </li>
      ))}
    </ul>
  );
}
