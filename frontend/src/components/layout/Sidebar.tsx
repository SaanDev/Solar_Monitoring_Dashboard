"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import useSWR from "swr";
import {
  LayoutDashboard,
  Radio,
  Radar,
  Image,
  Activity,
  Telescope,
  Compass,
  Bell,
  Archive,
  Settings,
  SlidersHorizontal,
} from "lucide-react";
import { clsx } from "clsx";

import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { useUnreadAlerts, unreadBadgeText } from "@/lib/useUnreadAlerts";
import type { SummaryLatest } from "@/lib/types";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/solar-radio", label: "Solar Radio", icon: Radio },
  { href: "/burst-predictor", label: "Burst Predictor", icon: Radar },
  { href: "/e-callisto-analyzer", label: "e-CALLISTO Analyzer", icon: SlidersHorizontal },
  { href: "/solar-images", label: "Solar Images", icon: Image },
  { href: "/xray-proton", label: "X-ray & Proton", icon: Activity },
  { href: "/coronagraph", label: "Coronagraph", icon: Telescope },
  { href: "/geomagnetic", label: "Geomagnetic", icon: Compass },
  { href: "/events", label: "Alerts", icon: Bell, badge: true },
  { href: "/archive", label: "Archive", icon: Archive },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarOpen } = useApp();
  const { data: summary } = useSWR("summary-latest", api.summaryLatest, {
    refreshInterval: 60000,
  });
  const { unreadCount } = useUnreadAlerts();

  return (
    <aside
      className={clsx(
        "flex h-screen shrink-0 flex-col overflow-hidden border-r border-surface-border bg-surface-card transition-[width] duration-200",
        sidebarOpen ? "w-56" : "w-0"
      )}
    >
      <div className="flex h-14 shrink-0 items-center px-4">
        <span className="text-sm font-bold uppercase tracking-widest text-accent-cyan">
          SWDash
        </span>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-2">
        {NAV.map(({ href, label, icon: Icon, badge }) => {
          const active = pathname === href;
          return (
            <Link
              key={href}
              href={href}
              className={clsx(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-accent-blue/20 text-accent-blue"
                  : "text-slate-400 hover:bg-surface-muted hover:text-slate-200"
              )}
            >
              <Icon className="h-4 w-4 shrink-0" />
              <span className="flex-1 truncate">{label}</span>
              {badge && unreadCount > 0 && (
                <span className="flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-red px-1 text-[10px] font-bold text-white">
                  {unreadBadgeText(unreadCount)}
                </span>
              )}
            </Link>
          );
        })}
      </nav>

      <QuickLook summary={summary} />

      <div className="border-t border-surface-border px-4 py-2">
        <p className="text-xs text-slate-600">Space Weather Dashboard</p>
        <p className="text-xs text-slate-700">v0.1.0</p>
      </div>
    </aside>
  );
}

function QuickLook({ summary }: { summary?: SummaryLatest }) {
  const num = (v: number | null | undefined, unit: string, digits = 0) =>
    v != null ? `${v.toFixed(digits)}${unit}` : "—";
  const rows: [string, string][] = [
    ["Sunspot Number", num(summary?.sunspot_number, "", 0)],
    ["Solar Wind Speed", num(summary?.solar_wind_speed, " km/s", 0)],
    ["IMF Bz", num(summary?.imf_bz, " nT", 1)],
    ["IMF Bt", num(summary?.imf_bt, " nT", 1)],
  ];
  const updated = summary?.timestamp
    ? new Date(summary.timestamp).toISOString().slice(11, 16) + " UTC"
    : "—";

  return (
    <div className="border-t border-surface-border px-4 py-3">
      <p className="mb-2 text-[10px] uppercase tracking-widest text-slate-500">Quick Look</p>
      <dl className="space-y-1">
        {rows.map(([k, v]) => (
          <div key={k} className="flex items-center justify-between text-xs">
            <dt className="text-slate-500">{k}</dt>
            <dd className="font-mono text-slate-300">{v}</dd>
          </div>
        ))}
      </dl>
      <p className="mt-2 text-[10px] text-slate-600">Last Updated: {updated}</p>
    </div>
  );
}
