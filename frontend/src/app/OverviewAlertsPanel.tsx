"use client";

import useSWR from "swr";
import Link from "next/link";
import { clsx } from "clsx";

import { api } from "@/lib/api";
import { AlertFeed } from "@/components/alerts/AlertFeed";
import { AsyncPanel } from "@/components/ui/AsyncPanel";

export function OverviewAlertsPanel({
  className,
  limit,
}: {
  className?: string;
  /** Cap the rows shown in each dedicated area (full history is on the Events page). */
  limit?: number;
}) {
  const { data, isLoading, error } = useSWR("alerts-latest", api.alertsLatest, {
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
        {/* AlertFeed renders "No alerts" in every severity category when handed
            an empty array, so a dropped fetch used to read as ALL CLEAR on the
            primary screen. The error branch must win over that. */}
        <AsyncPanel
          isLoading={isLoading}
          error={error}
          errorMessage="Alert feed unavailable — this is a connection failure, not an all-clear."
          skeleton={
            <div className="space-y-2">
              {Array.from({ length: 6 }).map((_, i) => (
                <div key={i} className="h-12 animate-pulse rounded bg-surface-muted" />
              ))}
            </div>
          }
        >
          <AlertFeed alerts={alerts} perCategoryLimit={limit} />
        </AsyncPanel>
      </div>
    </div>
  );
}
