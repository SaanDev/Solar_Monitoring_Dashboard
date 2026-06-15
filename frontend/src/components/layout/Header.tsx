"use client";

import { useEffect, useState } from "react";
import { Search, Circle } from "lucide-react";

export function Header({ title }: { title: string }) {
  const [utc, setUtc] = useState("");

  useEffect(() => {
    const tick = () =>
      setUtc(new Date().toISOString().slice(0, 19).replace("T", " ") + " UTC");
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return (
    <header className="flex h-14 items-center justify-between border-b border-surface-border bg-surface-card px-6">
      <h1 className="text-sm font-semibold text-slate-200">{title}</h1>

      <div className="flex items-center gap-4">
        <div className="relative hidden md:block">
          <Search className="absolute left-2.5 top-2 h-3.5 w-3.5 text-slate-500" />
          <input
            type="text"
            placeholder="Search events…"
            className="h-7 rounded-md border border-surface-border bg-surface-muted pl-8 pr-3 text-xs text-slate-300 placeholder-slate-600 outline-none focus:border-accent-blue"
          />
        </div>

        <div className="flex items-center gap-1.5 text-xs text-slate-400 font-mono">
          <Circle className="h-2 w-2 fill-accent-green text-accent-green" />
          {utc}
        </div>
      </div>
    </header>
  );
}
