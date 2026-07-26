"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { Bell, Calendar, Circle, Menu } from "lucide-react";

import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { useUnreadAlerts, unreadBadgeText } from "@/lib/useUnreadAlerts";
import type { SourceStatus } from "@/lib/types";
import { ThemeToggle } from "./ThemeToggle";

const BRAND = "ACCIMT Space Weather Dashboard";

function StatusBadge({
  label,
  value,
  ok,
  title,
}: {
  label: string;
  value: string;
  ok: boolean;
  title?: string;
}) {
  return (
    <div className="hidden flex-col items-end leading-tight sm:flex" title={title}>
      <span className="text-[9px] uppercase tracking-wider text-slate-500">{label}</span>
      <span className={ok ? "text-xs font-semibold text-accent-green" : "text-xs font-semibold text-accent-orange"}>
        {value}
      </span>
    </div>
  );
}

/**
 * Roll the per-source health list up into the single Data Feed badge.
 *
 * This badge used to be hardcoded to "LIVE", so it asserted a healthy feed even
 * during a total backend outage — the one place on screen a user would look to
 * check exactly that. `api.sourcesStatus()` and this shape already existed in
 * the repo but were never called.
 *
 * "unknown" sources are ignored rather than counted as failures: several feeds
 * report unknown simply because nothing has polled them yet.
 */
function feedHealth(
  sources: SourceStatus[] | undefined,
  failed: boolean
): { value: string; ok: boolean; title: string } {
  if (failed) {
    return { value: "OFFLINE", ok: false, title: "Cannot reach the dashboard API" };
  }
  if (!sources?.length) {
    return { value: "—", ok: true, title: "Source health not yet reported" };
  }
  const bad = sources.filter((s) => s.status === "error" || s.status === "degraded");
  if (bad.length) {
    return {
      value: "DEGRADED",
      ok: false,
      title: bad.map((s) => `${s.name}: ${s.status}`).join("\n"),
    };
  }
  return {
    value: "LIVE",
    ok: true,
    title: `${sources.filter((s) => s.status === "ok").length}/${sources.length} sources reporting OK`,
  };
}

export function Header({ title }: { title?: string }) {
  const { toggleSidebar } = useApp();
  const [utc, setUtc] = useState("");
  const { data: summary, error: summaryError } = useSWR(
    "summary-latest",
    api.summaryLatest,
    { refreshInterval: 60000 }
  );
  const { data: sources, error: sourcesError } = useSWR(
    "sources-status",
    api.sourcesStatus,
    { refreshInterval: 60000 }
  );
  const { unreadCount } = useUnreadAlerts();
  const feed = feedHealth(sources?.sources, Boolean(sourcesError || summaryError));

  useEffect(() => {
    const tick = () => setUtc(new Date().toISOString().slice(0, 19).replace("T", " "));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const activeAlerts = summary?.active_alerts ?? 0;
  const today = new Date().toISOString().slice(0, 10);

  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b border-surface-border bg-surface-card px-4">
      <div className="flex min-w-0 items-center gap-3">
        <button
          onClick={toggleSidebar}
          aria-label="Toggle sidebar"
          className="flex h-8 w-8 items-center justify-center rounded-md text-slate-400 hover:bg-surface-muted hover:text-slate-200"
        >
          <Menu className="h-5 w-5" />
        </button>
        <h1 className="truncate text-sm font-semibold text-slate-200 sm:text-base">
          {BRAND}
          {title ? <span className="ml-2 font-normal text-slate-500">· {title}</span> : null}
        </h1>
      </div>

      <div className="hidden items-center gap-2 lg:flex">
        <span className="flex items-center gap-1 text-[10px] font-semibold uppercase tracking-wider text-accent-green">
          <Circle className="h-2 w-2 animate-pulse fill-accent-green text-accent-green" /> Live UTC
        </span>
        <span className="font-mono text-sm text-slate-300">{utc}</span>
      </div>

      <div className="flex items-center gap-2 sm:gap-3">
        <span className="hidden items-center gap-1.5 rounded-md border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-400 md:flex">
          <Calendar className="h-3.5 w-3.5" />
          {today}
        </span>

{/* A search input used to sit here. It had no value, no onChange and no
    handler — you could type in it and nothing happened, and it couldn't even
    retain text across a re-render. Removed rather than left as a dead
    affordance; a real command palette over the nav routes and the reference /
    user-guide content is tracked as a separate opt-in feature. */}

        <StatusBadge
          label="Data Feed"
          value={feed.value}
          ok={feed.ok}
          title={feed.title}
        />
        <StatusBadge
          label="SWPC Status"
          value={summaryError ? "—" : activeAlerts === 0 ? "Normal" : "Active"}
          ok={!summaryError && activeAlerts === 0}
        />

        <Link
          href="/events"
          aria-label={unreadCount > 0 ? `Alerts (${unreadCount} unread)` : "Alerts"}
          className="relative flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-surface-muted hover:text-slate-200"
        >
          <Bell className="h-4 w-4" />
          {unreadCount > 0 && (
            <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-red px-1 text-[10px] font-bold text-white">
              {unreadBadgeText(unreadCount)}
            </span>
          )}
        </Link>

        <ThemeToggle />
      </div>
    </header>
  );
}
