"use client";

import { clsx } from "clsx";
import { Zap } from "lucide-react";

interface Props {
  fold: number;
  harmonic: boolean;
  fitting: boolean;
  canFit: boolean;
  onFoldChange: (fold: number) => void;
  onHarmonicChange: (harmonic: boolean) => void;
  onFit: () => void;
}

/** Newkirk fold-number + fundamental/harmonic selectors and the "Best Fit" trigger. */
export function ShockControls({
  fold,
  harmonic,
  fitting,
  canFit,
  onFoldChange,
  onHarmonicChange,
  onFit,
}: Props) {
  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <h3 className="text-xs uppercase tracking-wider text-slate-500">Model</h3>

      <div>
        <p className="mb-1 text-[10px] uppercase tracking-widest text-slate-500">
          Newkirk fold number
        </p>
        <div className="flex gap-1">
          {[1, 2, 3, 4].map((n) => (
            <button
              key={n}
              onClick={() => onFoldChange(n)}
              className={clsx(
                "flex-1 rounded px-2 py-1 text-xs transition-colors",
                fold === n
                  ? "bg-accent-blue/20 text-accent-blue"
                  : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
              )}
            >
              {n}×
            </button>
          ))}
        </div>
      </div>

      <div>
        <p className="mb-1 text-[10px] uppercase tracking-widest text-slate-500">Emission</p>
        <div className="flex gap-1">
          {[
            { key: false, label: "Fundamental" },
            { key: true, label: "Harmonic" },
          ].map((o) => (
            <button
              key={o.label}
              onClick={() => onHarmonicChange(o.key)}
              className={clsx(
                "flex-1 rounded px-2 py-1 text-xs transition-colors",
                harmonic === o.key
                  ? "bg-accent-blue/20 text-accent-blue"
                  : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
              )}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <button
        onClick={onFit}
        disabled={!canFit || fitting}
        className="flex w-full items-center justify-center gap-1.5 rounded bg-accent-blue/20 px-3 py-2 text-sm font-medium text-accent-blue transition-colors hover:bg-accent-blue/30 disabled:cursor-not-allowed disabled:opacity-40"
      >
        <Zap className="h-4 w-4" />
        {fitting ? "Fitting…" : "Best fit & shock parameters"}
      </button>
    </div>
  );
}
