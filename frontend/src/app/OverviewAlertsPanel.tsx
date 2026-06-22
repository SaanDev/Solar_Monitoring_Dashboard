"use client";

import useSWR from "swr";
import Link from "next/link";
import { clsx } from "clsx";

import { api } from "@/lib/api";
import { AlertFeed } from "@/components/alerts/AlertFeed";

export function OverviewAlertsPanel({
  className,
  limit,
}: {
  className?: string;
  /** Cap the rows shown in each dedicated area (full history is on the Events page). */
  limit?: number;
}) {
  const { data, isLoading } = useSWR("alerts-latest", api.alertsLatest, {
    refreshInterval: 60000,
  });
  const alerts = data ?? [];

  return (
    <div
      className={clsx(
        "flex flex-col rounded-lg border border-surface-border bg-surface-card p-4",
        className
      )}
    >
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">Alerts &amp; Event Feed</h3>
        <Link href="/events" className="text-xs text-accent-blue hover:underline">
          View All →
        </Link>
      </div>

      <div className="min-h-[16rem] flex-1 overflow-y-auto">
        {isLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <div key={i} className="h-12 animate-pulse rounded bg-surface-muted" />
            ))}
          </div>
        ) : (
          <AlertFeed alerts={alerts} perCategoryLimit={limit} />
        )}
      </div>
    </div>
  );
}
