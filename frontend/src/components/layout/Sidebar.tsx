"use client";

import { useEffect, useRef, useState } from "react";
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
  Microscope,
  Wind,
  TrendingUp,
  CalendarRange,
  Orbit,
  BookOpen,
  BookOpenText,
} from "lucide-react";
import { clsx } from "clsx";

import { api } from "@/lib/api";
import { useApp } from "@/components/providers";
import { useUnreadAlerts, unreadBadgeText } from "@/lib/useUnreadAlerts";
import type { SummaryLatest } from "@/lib/types";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/solar-radio", label: "Solar Radio", icon: Radio },
  { href: "/burst-predictor", label: "Burst Detector", icon: Radar },
  { href: "/e-callisto-analyzer", label: "e-CALLISTO Analyzer", icon: SlidersHorizontal },
  { href: "/solar-images", label: "Solar Images", icon: Image },
  { href: "/data-analysis", label: "Data Analysis", icon: Microscope },
  { href: "/xray-proton", label: "X-ray & Proton", icon: Activity },
  { href: "/coronagraph", label: "Coronagraph", icon: Telescope },
  { href: "/geomagnetic", label: "Geomagnetic", icon: Compass },
  { href: "/solar-wind", label: "Solar Wind", icon: Wind },
  { href: "/forecast", label: "Forecast", icon: TrendingUp },
  { href: "/timeline", label: "Timeline", icon: CalendarRange },
  { href: "/solar-cycle", label: "Solar Cycle", icon: Orbit },
  { href: "/events", label: "Alerts", icon: Bell, badge: true },
  { href: "/archive", label: "Archive", icon: Archive },
  { href: "/reference", label: "Science Reference", icon: BookOpen },
  { href: "/user-guide", label: "User Guide", icon: BookOpenText },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  const { sidebarOpen, toggleSidebar } = useApp();

  // `sidebarOpen` defaults to true with no viewport check, which is right for
  // the desktop rail but would open the mobile drawer over the content on first
  // paint. Rather than change the provider's initial state (and with it every
  // other consumer), track the drawer locally: it starts closed, and each
  // toggle of the shared flag flips it. Desktop still reads sidebarOpen directly.
  const [mobileOpen, setMobileOpen] = useState(false);
  const prevSidebarOpen = useRef(sidebarOpen);
  useEffect(() => {
    // Compare against the previous value rather than using a "first run" flag:
    // StrictMode double-invokes mount effects in dev, which would consume such
    // a flag and leave the drawer open on load. This is idempotent.
    if (prevSidebarOpen.current === sidebarOpen) return;
    prevSidebarOpen.current = sidebarOpen;
    setMobileOpen((o) => !o);
  }, [sidebarOpen]);
  const { data: summary, error: summaryError } = useSWR(
    "summary-latest",
    api.summaryLatest,
    { refreshInterval: 60000 }
  );
  const { unreadCount } = useUnreadAlerts();

  return (
    <>
      {/* Mobile scrim. Below `md` the sidebar overlays content, so it needs a
          tap-anywhere-to-dismiss target. Hidden from md up, where the rail is
          part of the layout flow. */}
      {mobileOpen && (
        <div
          onClick={toggleSidebar}
          aria-hidden="true"
          className="fixed inset-0 z-30 bg-black/50 md:hidden"
        />
      )}

      <aside
        className={clsx(
          "z-40 flex h-screen shrink-0 flex-col border-r border-surface-border bg-surface-card transition-[width] duration-200",
          // Below md the rail becomes an overlay drawer, closed on first paint.
          // Closing it with `hidden` rather than an off-canvas transform is
          // deliberate: display:none also drops all 18 links out of the tab
          // order, which the old `w-0` collapse did not — it left them
          // invisible but still focusable.
          "max-md:fixed max-md:inset-y-0 max-md:left-0 max-md:w-56",
          !mobileOpen && "max-md:hidden",
          // From md up: full rail when open, icon rail when collapsed.
          sidebarOpen ? "md:w-56" : "md:w-14"
        )}
      >
        <div
          className={clsx(
            "flex h-14 shrink-0 items-center",
            sidebarOpen ? "px-4" : "md:justify-center md:px-0"
          )}
        >
          <span className="text-sm font-bold uppercase tracking-widest text-accent-cyan">
            {sidebarOpen ? "SWDash" : <span className="md:inline">SW</span>}
          </span>
        </div>

        <nav aria-label="Main" className="flex-1 overflow-y-auto overflow-x-hidden px-2 py-2">
          {NAV.map(({ href, label, icon: Icon, badge }) => {
            const active = pathname === href;
            return (
              <Link
                key={href}
                href={href}
                // `active` was already computed but never exposed; screen
                // readers had no way to tell which of the 18 routes was current.
                aria-current={active ? "page" : undefined}
                // In the collapsed icon rail the text is hidden, so the label
                // has to come from the title/aria-label instead.
                title={!sidebarOpen ? label : undefined}
                className={clsx(
                  "flex items-center gap-3 rounded-md py-2 text-sm transition-colors",
                  sidebarOpen ? "px-3" : "px-3 md:justify-center md:px-0",
                  active
                    ? "bg-accent-blue/20 text-accent-blue"
                    : "text-slate-400 hover:bg-surface-muted hover:text-slate-200"
                )}
              >
                <Icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                <span className={clsx("flex-1 truncate", !sidebarOpen && "md:hidden")}>
                  {label}
                </span>
                {badge && unreadCount > 0 && (
                  <span
                    className={clsx(
                      "flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-red px-1 text-[10px] font-bold text-white",
                      !sidebarOpen && "md:hidden"
                    )}
                  >
                    {unreadBadgeText(unreadCount)}
                  </span>
                )}
              </Link>
            );
          })}
        </nav>

        {/* Both footers are noise in a 56px rail — hide them there, not the nav. */}
        <div className={clsx(!sidebarOpen && "md:hidden")}>
          <QuickLook summary={summary} failed={Boolean(summaryError)} />

          <div className="border-t border-surface-border px-4 py-2">
            <p className="text-xs text-slate-600">Space Weather Dashboard</p>
            <p className="text-xs text-slate-700">v0.1.0</p>
          </div>
        </div>
      </aside>
    </>
  );
}

function QuickLook({
  summary,
  failed,
}: {
  summary?: SummaryLatest;
  failed?: boolean;
}) {
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
      {/* Every row above renders "—" when the fetch fails, which is
          indistinguishable from genuinely absent readings. Say which it is. */}
      {failed ? (
        <p className="mt-2 text-[10px] text-accent-red">Feed unavailable</p>
      ) : (
        <p className="mt-2 text-[10px] text-slate-600">Last Updated: {updated}</p>
      )}
    </div>
  );
}
