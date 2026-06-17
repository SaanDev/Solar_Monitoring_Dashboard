"use client";

import { useState } from "react";
import { clsx } from "clsx";
import { Layers, Check, Trash2 } from "lucide-react";
import { api } from "@/lib/api";
import type { AnalyzerSession, CombineMode } from "@/lib/types";

interface Props {
  sessions: AnalyzerSession[];
  activeId: string | null;
  onActivate: (id: string) => void;
  onCombined: (session: AnalyzerSession) => void;
  onClearAll: () => void;
}

export function SourcesPanel({ sessions, activeId, onActivate, onCombined, onClearAll }: Props) {
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [mode, setMode] = useState<CombineMode>("frequency");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle(id: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  async function combine() {
    const ids = [...selected];
    if (ids.length < 2) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.analyzerCombine(ids, mode);
      onCombined(result);
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Combine failed");
    } finally {
      setBusy(false);
    }
  }

  if (sessions.length === 0) return null;

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-wider text-slate-500">
          Sources ({sessions.length})
        </h2>
        <button
          onClick={onClearAll}
          className="flex items-center gap-1 rounded px-1.5 py-0.5 text-xs text-slate-500 transition-colors hover:bg-accent-red/15 hover:text-accent-red"
          title="Clear all loaded and combined files"
        >
          <Trash2 className="h-3.5 w-3.5" /> Clear
        </button>
      </div>

      <ul className="space-y-1">
        {sessions.map((s) => {
          const isActive = s.id === activeId;
          const isSel = selected.has(s.id);
          return (
            <li
              key={s.id}
              className={clsx(
                "flex items-center gap-2 rounded border px-2 py-1.5 text-xs transition-colors",
                isActive ? "border-accent-blue/50 bg-accent-blue/10" : "border-surface-border"
              )}
            >
              <button
                onClick={() => toggle(s.id)}
                aria-label="Select for combine"
                className={clsx(
                  "flex h-4 w-4 shrink-0 items-center justify-center rounded border",
                  isSel
                    ? "border-accent-blue bg-accent-blue text-white"
                    : "border-slate-600 text-transparent hover:border-accent-blue"
                )}
              >
                <Check className="h-3 w-3" />
              </button>
              <button onClick={() => onActivate(s.id)} className="min-w-0 flex-1 text-left">
                <div className="truncate font-medium text-slate-300">{s.station}</div>
                <div className="truncate text-slate-600">
                  {s.freq_min_mhz.toFixed(0)}–{s.freq_max_mhz.toFixed(0)} MHz · {s.n_freq}×{s.n_time}
                </div>
              </button>
              {isActive && (
                <span className="shrink-0 text-[10px] uppercase tracking-wide text-accent-blue">
                  active
                </span>
              )}
            </li>
          );
        })}
      </ul>

      <div className="space-y-2 border-t border-surface-border pt-3">
        <div className="flex gap-1">
          {(["frequency", "time"] as CombineMode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={clsx(
                "flex-1 rounded px-2 py-1 text-xs capitalize transition-colors",
                mode === m
                  ? "bg-accent-blue/20 text-accent-blue"
                  : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
              )}
            >
              {m}
            </button>
          ))}
        </div>
        <button
          disabled={selected.size < 2 || busy}
          onClick={combine}
          className="flex w-full items-center justify-center gap-1 rounded bg-accent-blue/20 px-2 py-1.5 text-xs text-accent-blue transition-colors hover:bg-accent-blue/30 disabled:opacity-40"
        >
          <Layers className="h-3.5 w-3.5" />
          {busy ? "Combining…" : `Combine ${selected.size || ""} (${mode})`}
        </button>
        <p className="text-[10px] leading-relaxed text-slate-600">
          {mode === "frequency"
            ? "Frequency combine needs files with the same time span (different bands)."
            : "Time combine needs files with the same frequency axis (consecutive in time)."}
        </p>
        {error && <p className="text-xs text-accent-red">{error}</p>}
      </div>
    </div>
  );
}
