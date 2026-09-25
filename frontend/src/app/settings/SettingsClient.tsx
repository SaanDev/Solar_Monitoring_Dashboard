"use client";

import { Monitor, Moon, Sun } from "lucide-react";
import { clsx } from "clsx";
import { useApp, type Theme } from "@/components/providers";
import { NotificationSettingsCard } from "@/components/settings/NotificationSettingsCard";
import { BurstDetectionModelCard } from "@/components/settings/BurstDetectionModelCard";
import { BurstBackfillCard } from "@/components/settings/BurstBackfillCard";

const OPTIONS: { key: Theme; label: string; icon: typeof Sun }[] = [
  { key: "light", label: "Light", icon: Sun },
  { key: "dark", label: "Dark", icon: Moon },
  { key: "system", label: "System", icon: Monitor },
];

export function SettingsClient() {
  const { theme, setTheme } = useApp();

  return (
    <div className="max-w-xl space-y-6">
      <section className="rounded-lg border border-surface-border bg-surface-card p-5">
        <h2 className="text-sm font-semibold text-slate-200">Appearance</h2>
        <p className="mt-1 text-xs text-slate-500">
          Choose how the dashboard looks. “System” follows your operating system setting.
        </p>
        <div className="mt-4 grid grid-cols-3 gap-3">
          {OPTIONS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              onClick={() => setTheme(key)}
              className={clsx(
                "flex flex-col items-center gap-2 rounded-lg border p-4 text-xs font-medium transition-colors",
                theme === key
                  ? "border-accent-blue bg-accent-blue/10 text-accent-blue"
                  : "border-surface-border bg-surface-muted text-slate-400 hover:text-slate-200"
              )}
            >
              <Icon className="h-5 w-5" />
              {label}
            </button>
          ))}
        </div>
      </section>

      <BurstDetectionModelCard />

      <BurstBackfillCard />

      <NotificationSettingsCard />
    </div>
  );
}
