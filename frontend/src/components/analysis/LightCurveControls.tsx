"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import type { LightcurveResult } from "@/lib/types";

interface Props {
  sessionId: string;
  /** ROI corners picked on the canvas (data pixels, max 2). */
  picks: { px: number; py: number }[];
  onClear: () => void;
  onResult: (r: LightcurveResult | null) => void;
}

const inputCls =
  "w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue";
const btnCls =
  "w-full rounded bg-accent-blue/20 px-2 py-1.5 text-xs text-accent-blue transition-colors hover:bg-accent-blue/30 disabled:opacity-40";

/** ROI light curve across all frames, with an optional radio-burst window
 * (ported extract_region_lightcurve + radio_euv_lag). */
export function LightCurveControls({ sessionId, picks, onClear, onResult }: Props) {
  const [statistic, setStatistic] = useState<"mean" | "sum">("mean");
  const [useRadio, setUseRadio] = useState(false);
  const [radioStart, setRadioStart] = useState("");
  const [radioEnd, setRadioEnd] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<LightcurveResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function extract() {
    if (picks.length !== 2) return;
    setBusy(true);
    setError(null);
    try {
      const [a, b] = picks;
      const r = await api.analysisLightcurve(
        sessionId,
        a.px, a.py, b.px, b.py,
        statistic,
        useRadio && radioStart ? radioStart : null,
        useRadio && radioEnd ? radioEnd : null
      );
      setResult(r);
      onResult(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Light-curve extraction failed");
      onResult(null);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">Region Light Curve</h2>

      <p className="text-[10px] leading-relaxed text-slate-600">
        Click two opposite corners of a region on the image; the ROI intensity
        (DN/s, exposure-normalised) is tracked across every frame. ({picks.length}/2 corners)
      </p>

      <div>
        <label className="mb-1 block text-xs text-slate-500">Statistic</label>
        <select value={statistic} onChange={(e) => setStatistic(e.target.value as "mean" | "sum")} className={inputCls}>
          <option value="mean">mean (DN/s per px)</option>
          <option value="sum">sum (total DN/s)</option>
        </select>
      </div>

      <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-slate-400">
        <input
          type="checkbox"
          checked={useRadio}
          onChange={(e) => setUseRadio(e.target.checked)}
          className="h-3.5 w-3.5 accent-accent-blue"
        />
        Overlay radio-burst window (e-CALLISTO)
      </label>
      {useRadio && (
        <div className="grid grid-cols-1 gap-2">
          <div>
            <label className="mb-1 block text-xs text-slate-500">Burst onset (UTC)</label>
            <input type="datetime-local" value={radioStart} onChange={(e) => setRadioStart(e.target.value)} className={inputCls} step={1} />
          </div>
          <div>
            <label className="mb-1 block text-xs text-slate-500">Burst end (UTC)</label>
            <input type="datetime-local" value={radioEnd} onChange={(e) => setRadioEnd(e.target.value)} className={inputCls} step={1} />
          </div>
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <button disabled={picks.length !== 2 || busy} onClick={extract} className={btnCls}>
          {busy ? "Extracting…" : "Extract light curve"}
        </button>
        <button
          onClick={() => {
            onClear();
            setResult(null);
            onResult(null);
          }}
          className="w-full rounded bg-surface-muted px-2 py-1.5 text-xs text-slate-300 transition-colors hover:bg-surface-border"
        >
          Clear
        </button>
      </div>

      {result && (
        <div className="space-y-1 font-mono text-[11px] text-slate-300">
          <div>peak: {result.peak_time ? result.peak_time.replace("T", " ").slice(0, 19) : "—"} UTC</div>
          {result.radio_euv_lag_s != null && (
            <div>
              EUV peak − radio onset = {result.radio_euv_lag_s >= 0 ? "+" : ""}
              {result.radio_euv_lag_s.toFixed(0)} s
            </div>
          )}
        </div>
      )}
      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}
