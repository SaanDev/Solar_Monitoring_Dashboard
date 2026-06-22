import Link from "next/link";
import { clsx } from "clsx";

import type { Alert } from "@/lib/types";
import { formatUtcShort } from "@/lib/formatting";
import {
  ALERT_CATEGORIES,
  alertHref,
  alertLabel,
  categoryOf,
  type AlertCategoryKey,
} from "@/lib/alerts";

const sevText = {
  info: "text-accent-blue",
  watch: "text-accent-yellow",
  warning: "text-accent-orange",
  critical: "text-accent-red",
} as const;

const sevBorder = {
  info: "border-accent-blue/40 bg-accent-blue/5",
  watch: "border-accent-yellow/40 bg-accent-yellow/5",
  warning: "border-accent-orange/40 bg-accent-orange/5",
  critical: "border-accent-red/40 bg-accent-red/5",
} as const;

/**
 * Alerts grouped into a dedicated area per type (Flare / Radio Bursts /
 * Geomagnetic Storm / Proton Event). Each row deep-links to the visualization
 * of that event. `perCategoryLimit` caps the rows shown in each area (the count
 * badge still reflects the true total).
 */
export function AlertFeed({
  alerts,
  perCategoryLimit,
}: {
  alerts: Alert[];
  perCategoryLimit?: number;
}) {
  const buckets: Record<AlertCategoryKey, Alert[]> = {
    xray_flare: [],
    radio_burst: [],
    geomagnetic_storm: [],
    proton_event: [],
  };
  for (const a of alerts) {
    const key = categoryOf(a.type);
    if (key) buckets[key].push(a);
  }

  return (
    <div className="space-y-4">
      {ALERT_CATEGORIES.map((cat) => {
        const all = buckets[cat.key];
        const items = perCategoryLimit ? all.slice(0, perCategoryLimit) : all;
        const Icon = cat.icon;
        return (
          <section key={cat.key}>
            <div className="mb-1.5 flex items-center gap-2">
              <Icon className={clsx("h-3.5 w-3.5 shrink-0", cat.accent)} />
              <h4 className="flex-1 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
                {cat.title}
              </h4>
              <span className="rounded bg-surface-muted px-1.5 py-0.5 text-[10px] text-slate-500">
                {all.length}
              </span>
            </div>

            {items.length === 0 ? (
              <p className="pl-5 text-[11px] text-slate-600">No alerts</p>
            ) : (
              <ul className="space-y-1.5">
                {items.map((a) => (
                  <li key={a.id}>
                    <Link
                      href={alertHref(a.type, a.timestamp)}
                      className={clsx(
                        "block rounded border px-3 py-2 text-xs transition-opacity hover:opacity-80",
                        sevBorder[a.severity]
                      )}
                    >
                      <div className="mb-0.5 flex items-center justify-between gap-2">
                        <span className={clsx("font-semibold", sevText[a.severity])}>
                          {alertLabel(a.type)}
                        </span>
                        <span className="shrink-0 text-[10px] text-slate-600">
                          {formatUtcShort(a.timestamp)}
                        </span>
                      </div>
                      <p className="truncate text-slate-400">{a.message}</p>
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </section>
        );
      })}
    </div>
  );
}
