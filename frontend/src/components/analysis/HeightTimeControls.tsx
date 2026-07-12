"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { HeightTimeResult } from "@/lib/types";

export interface HtPick {
  frame: number;
  px: number;
  py: number;
}

interface Props {
  sessionId: string;
  picks: HtPick[];
  autoAdvance: boolean;
  onAutoAdvance: (v: boolean) => void;
  onUndo: () => void;
  onClear: () => void;
  onResult: (r: HeightTimeResult | null) => void;
}

function fmt(v: number | null | undefined, digits = 1): string {
  if (v == null || !isFinite(v)) return "—";
  return v.toFixed(digits);
}

/** CME height–time tracking: click the leading edge frame by frame; a linear
 * fit gives the plane-of-sky speed, a quadratic fit the acceleration
 * (ported coronagraph.fit_height_time). */
export function HeightTimeControls({
  sessionId,
  picks,
  autoAdvance,
  onAutoAdvance,
  onUndo,
  onClear,
  onResult,
}: Props) {
  const [result, setResult] = useState<HeightTimeResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (picks.length === 0) {
      setResult(null);
      setError(null);
      onResult(null);
      return;
    }
    let stale = false;
    api
      .analysisHeightTime(sessionId, picks)
      .then((r) => {
        if (!stale) {
          setResult(r);
          setError(null);
          onResult(r);
        }
      })
      .catch((e) => {
        if (!stale) setError(e instanceof Error ? e.message : "Fit failed");
      });
    return () => {
      stale = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sessionId, picks]);

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">CME Height–Time</h2>

      <p className="text-[10px] leading-relaxed text-slate-600">
        Click the CME leading edge on each frame (running difference makes the
        front easiest to see). Two picks give the mean plane-of-sky speed; three
        or more add the acceleration.
      </p>

      <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-slate-400">
        <input
          type="checkbox"
          checked={autoAdvance}
          onChange={(e) => onAutoAdvance(e.target.checked)}
          className="h-3.5 w-3.5 accent-accent-blue"
        />
        Auto-advance frame after each pick
      </label>

      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={onUndo}
          disabled={picks.length === 0}
          className="w-full rounded bg-surface-muted px-2 py-1 text-xs text-slate-300 transition-colors hover:bg-surface-border disabled:opacity-40"
        >
          Undo last
        </button>
        <button
          onClick={onClear}
          disabled={picks.length === 0}
          className="w-full rounded bg-surface-muted px-2 py-1 text-xs text-slate-300 transition-colors hover:bg-surface-border disabled:opacity-40"
        >
          Clear all
        </button>
      </div>

      {result && result.points.length > 0 && (
        <div className="max-h-36 overflow-y-auto rounded border border-surface-border">
          <table className="w-full font-mono text-[10px] text-slate-400">
            <thead>
              <tr className="border-b border-surface-border text-slate-500">
                <th className="px-2 py-1 text-left">#</th>
                <th className="px-2 py-1 text-left">frame</th>
                <th className="px-2 py-1 text-left">UTC</th>
                <th className="px-2 py-1 text-right">R☉</th>
              </tr>
            </thead>
            <tbody>
              {result.points.map((p, i) => (
                <tr key={i} className="border-b border-surface-border/50 last:border-0">
                  <td className="px-2 py-0.5">{i + 1}</td>
                  <td className="px-2 py-0.5">{p.frame + 1}</td>
                  <td className="px-2 py-0.5">{p.time ? p.time.slice(11, 19) : "—"}</td>
                  <td className="px-2 py-0.5 text-right">{p.r_rsun.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {result && result.speed_km_s != null && (
        <div className="space-y-1 rounded bg-surface-muted p-2 font-mono text-[11px] text-slate-200">
          <div>
            speed = <span className="text-accent-cyan">{fmt(result.speed_km_s, 0)} km/s</span>{" "}
            (linear fit)
          </div>
          {result.acceleration_km_s2 != null && (
            <div>
              acceleration = {result.acceleration_km_s2 >= 0 ? "+" : ""}
              {fmt(result.acceleration_km_s2 * 1000, 1)} m/s²
            </div>
          )}
          {result.segment_speeds_km_s && result.segment_speeds_km_s.length > 0 && (
            <div className="text-slate-400">
              segments: {result.segment_speeds_km_s.map((s) => fmt(s, 0)).join(", ")} km/s
            </div>
          )}
        </div>
      )}

      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}
