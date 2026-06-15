"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Radio,
  Image,
  Activity,
  Telescope,
  Compass,
  Bell,
  Archive,
  Settings,
} from "lucide-react";
import { clsx } from "clsx";

const NAV = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/solar-radio", label: "Solar Radio", icon: Radio },
  { href: "/solar-images", label: "Solar Images", icon: Image },
  { href: "/xray-proton", label: "X-ray & Proton", icon: Activity },
  { href: "/coronagraph", label: "Coronagraph", icon: Telescope },
  { href: "/geomagnetic", label: "Geomagnetic", icon: Compass },
  { href: "/events", label: "Events", icon: Bell },
  { href: "/archive", label: "Archive", icon: Archive },
  { href: "/settings", label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex h-screen w-56 flex-col border-r border-surface-border bg-surface-card">
      <div className="flex h-14 items-center px-4">
        <span className="text-sm font-bold tracking-widest text-accent-cyan uppercase">
          SWDash
        </span>
      </div>

      <nav className="flex-1 overflow-y-auto px-2 py-2">
        {NAV.map(({ href, label, icon: Icon }) => {
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
              {label}
            </Link>
          );
        })}
      </nav>

      <div className="border-t border-surface-border px-4 py-3">
        <p className="text-xs text-slate-600">Space Weather Dashboard</p>
        <p className="text-xs text-slate-700">v0.1.0</p>
      </div>
    </aside>
  );
}
