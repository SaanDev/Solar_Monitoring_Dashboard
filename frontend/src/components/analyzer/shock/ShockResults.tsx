"use client";

import { useState } from "react";
import { Download } from "lucide-react";
import { clsx } from "clsx";
import { api } from "@/lib/api";
import type { ExtraPlotKind, PowerLawFit, ShockSummary } from "@/lib/types";

interface Props {
  id: string;
  summary: ShockSummary;
  fit: PowerLawFit;
  bust: string | number;
}

const ROWS: Array<{ label: string; key: keyof ShockSummary; errKey: keyof ShockSummary; unit: string; digits: number }> = [
  { label: "Average frequency", key: "avg_freq_mhz", errKey: "avg_freq_err_mhz", unit: "MHz", digits: 2 },
  { label: "Average drift rate", key: "avg_drift_mhz_s", errKey: "avg_drift_err_mhz_s", unit: "MHz/s", digits: 4 },
  { label: "Starting frequency", key: "start_freq_mhz", errKey: "start_freq_err_mhz", unit: "MHz", digits: 2 },
  { label: "Initial shock speed", key: "initial_shock_speed_km_s", errKey: "initial_shock_speed_err_km_s", unit: "km/s", digits: 2 },
  { label: "Initial shock height", key: "initial_shock_height_rs", errKey: "initial_shock_height_err_rs", unit: "R☉", digits: 3 },
  { label: "Average shock speed", key: "avg_shock_speed_km_s", errKey: "avg_shock_speed_err_km_s", unit: "km/s", digits: 2 },
  { label: "Average shock height", key: "avg_shock_height_rs", errKey: "avg_shock_height_err_rs", unit: "R☉", digits: 3 },
];

const EXTRA: Array<{ kind: ExtraPlotKind; label: string }> = [
  { kind: "speed_height", label: "Speed vs Height" },
  { kind: "speed_freq", label: "Speed vs Freq" },
  { kind: "height_freq", label: "Height vs Freq" },
];

function fmt(v: number | null | undefined, digits: number): string {
  return v == null || Number.isNaN(v) ? "—" : v.toFixed(digits);
}

export function ShockResults({ id, summary, fit, bust }: Props) {
  const [extra, setExtra] = useState<ExtraPlotKind>("speed_height");

  const dlCls =
    "flex items-center gap-1 rounded bg-surface-muted px-2 py-1 text-xs text-slate-300 transition-colors hover:bg-accent-blue/30 hover:text-accent-blue";

  return (
    <div className="space-y-4 rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">
          Shock parameters · Newkirk {summary.fold}× · {summary.harmonic ? "Harmonic" : "Fundamental"}
        </h3>
        <div className="flex items-center gap-2">
          <a href={api.analyzerShockExportUrl(id, "xlsx")} download className={dlCls}>
            <Download className="h-3.5 w-3.5" /> Excel
          </a>
          <a href={api.analyzerShockExportUrl(id, "csv")} download className={dlCls}>
            <Download className="h-3.5 w-3.5" /> CSV
          </a>
          <a href={api.analyzerShockFitPlotUrl(id, bust)} download={`shock_fit_${id.slice(0, 8)}.png`} className={dlCls}>
            <Download className="h-3.5 w-3.5" /> Plot PNG
          </a>
        </div>
      </div>

      {/* equation + goodness of fit */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 rounded bg-surface-muted/50 px-3 py-2 text-xs">
        <span className="font-mono text-slate-200">
          f(t) = {fit.a.toFixed(2)} · t<sup>−{Math.abs(fit.b).toFixed(2)}</sup>
        </span>
        <span className="text-slate-500">R² = {fmt(fit.r2, 4)}</span>
        <span className="text-slate-500">RMSE = {fmt(fit.rmse, 4)}</span>
        <span className="text-slate-500">n = {fit.point_count}</span>
      </div>

      {/* parameter table — needs its own scroll container so a narrow viewport
          scrolls the table rather than the whole page body */}
      <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <tbody>
          {ROWS.map((r) => (
            <tr key={r.label} className="border-b border-surface-border/60 last:border-0">
              <td className="py-1.5 text-slate-400">{r.label}</td>
              <td className="py-1.5 text-right font-medium text-slate-100">
                {fmt(summary[r.key] as number, r.digits)}
                <span className="text-slate-500">
                  {" ± "}
                  {fmt(summary[r.errKey] as number, r.digits)}
                </span>
              </td>
              <td className="w-14 py-1.5 pl-2 text-right text-slate-500">{r.unit}</td>
            </tr>
          ))}
        </tbody>
      </table>
      </div>

      {/* fit plot */}
      <div>
        <p className="mb-1 text-[10px] uppercase tracking-widest text-slate-500">Best-fit plot</p>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={api.analyzerShockFitPlotUrl(id, bust)}
          alt="Power-law fit"
          className="w-full rounded bg-black/30"
        />
      </div>

      {/* derived plots */}
      <div>
        <div className="mb-2 flex gap-1">
          {EXTRA.map((e) => (
            <button
              key={e.kind}
              onClick={() => setExtra(e.kind)}
              className={clsx(
                "flex-1 rounded px-2 py-1 text-xs transition-colors",
                extra === e.kind
                  ? "bg-accent-blue/20 text-accent-blue"
                  : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
              )}
            >
              {e.label}
            </button>
          ))}
        </div>
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={api.analyzerShockExtraPlotUrl(id, extra, bust)}
          alt="Derived shock plot"
          className="w-full rounded bg-black/30"
        />
      </div>
    </div>
  );
}
