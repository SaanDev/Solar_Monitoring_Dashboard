"use client";

import { Moon, Sun } from "lucide-react";
import { useApp } from "@/components/providers";

export function ThemeToggle() {
  const { resolved, setTheme } = useApp();
  const next = resolved === "dark" ? "light" : "dark";
  return (
    <button
      onClick={() => setTheme(next)}
      title={`Switch to ${next} mode`}
      aria-label="Toggle theme"
      className="flex h-7 w-7 items-center justify-center rounded-md border border-surface-border bg-surface-muted text-slate-400 transition-colors hover:border-accent-blue/50 hover:text-accent-blue"
    >
      {resolved === "dark" ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
    </button>
  );
}
