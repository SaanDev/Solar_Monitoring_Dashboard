"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import useSWR from "swr";
import { Bell, Calendar, Circle, Menu, Search } from "lucide-react";

import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { ThemeToggle } from "./ThemeToggle";

const BRAND = "ACCIMT Space Weather Dashboard";

function StatusBadge({ label, value, ok }: { label: string; value: string; ok: boolean }) {
  return (
    <div className="hidden flex-col items-end leading-tight sm:flex">
      <span className="text-[9px] uppercase tracking-wider text-slate-500">{label}</span>
      <span className={ok ? "text-xs font-semibold text-accent-green" : "text-xs font-semibold text-accent-orange"}>
        {value}
      </span>
    </div>
  );
}

export function Header({ title }: { title?: string }) {
  const { toggleSidebar } = useApp();
  const [utc, setUtc] = useState("");
  const { data: summary } = useSWR("summary-latest", api.summaryLatest, {
    refreshInterval: 60000,
  });

  useEffect(() => {
    const tick = () => setUtc(new Date().toISOString().slice(0, 19).replace("T", " "));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  const alerts = summary?.active_alerts ?? 0;
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

        <div className="relative hidden xl:block">
          <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search data, events…"
            className="h-7 w-44 rounded-md border border-surface-border bg-surface-muted pl-8 pr-3 text-xs text-slate-300 placeholder-slate-500 outline-none focus:border-accent-blue"
          />
        </div>

        <StatusBadge label="Data Feed" value="LIVE" ok />
        <StatusBadge label="SWPC Status" value={alerts === 0 ? "Normal" : "Active"} ok={alerts === 0} />

        <Link
          href="/events"
          aria-label="Alerts"
          className="relative flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-surface-muted hover:text-slate-200"
        >
          <Bell className="h-4 w-4" />
          {alerts > 0 && (
            <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-red px-1 text-[10px] font-bold text-white">
              {alerts}
            </span>
          )}
        </Link>

        <ThemeToggle />
      </div>
    </header>
  );
}
