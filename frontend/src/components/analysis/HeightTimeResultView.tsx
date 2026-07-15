"use client";

import { MiniChart } from "@/components/analysis/MiniChart";
import { formatClockUtc, parseUtcSeconds } from "@/lib/formatting";
import type { HeightTimeResult } from "@/lib/types";

/** Real-time CME height–time readout: a live graph (height vs UTC with a
 * least-squares fit overlay) plus the per-pick data table. Both update as new
 * leading-edge picks stream in from the canvas. */
export function HeightTimeResultView({ result }: { result: HeightTimeResult | null }) {
  if (!result || result.points.length === 0) {
    return (
      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <h2 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
          CME height–time tracking
        </h2>
        <p className="py-16 text-center text-xs text-slate-600">
          Click the CME leading edge frame by frame to build the height–time
          profile. The graph and table update live after each pick.
        </p>
      </div>
    );
  }

  // Timed points, in chronological order, with seconds relative to the first.
  const timed = result.points
    .map((p) => ({ ...p, sec: parseUtcSeconds(p.time) }))
    .filter((p) => isFinite(p.sec))
    .sort((a, b) => a.sec - b.sec);

  const x = timed.map((p) => p.sec);
  const y = timed.map((p) => p.r_rsun);

  // Least-squares line for the overlay (endpoints only — MiniChart draws it
  // straight). Mirrors the backend linear fit but keeps the graph self-contained.
  let overlay: { x: number; y: number }[] = [];
  if (timed.length >= 2) {
    const n = x.length;
    const t0 = x[0];
    const tx = x.map((v) => v - t0);
    const sumT = tx.reduce((a, b) => a + b, 0);
    const sumY = y.reduce((a, b) => a + b, 0);
    const sumTT = tx.reduce((a, b) => a + b * b, 0);
    const sumTY = tx.reduce((a, b, i) => a + b * y[i], 0);
    const denom = n * sumTT - sumT * sumT;
    if (denom !== 0) {
      const slope = (n * sumTY - sumT * sumY) / denom;
      const intercept = (sumY - slope * sumT) / n;
      overlay = [
        { x: x[0], y: intercept },
        { x: x[n - 1], y: intercept + slope * (x[n - 1] - t0) },
      ];
    }
  }

  const fmt = (v: number | null | undefined, d = 1) =>
    v == null || !isFinite(v) ? "—" : v.toFixed(d);

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
          <h2 className="text-xs uppercase tracking-wider text-slate-500">
            Height–time profile
          </h2>
          <div className="flex flex-wrap gap-3 font-mono text-[11px]">
            {result.speed_km_s != null && (
              <span className="text-accent-cyan">v = {fmt(result.speed_km_s, 0)} km/s</span>
            )}
            {result.acceleration_km_s2 != null && (
              <span className="text-slate-300">
                a = {result.acceleration_km_s2 >= 0 ? "+" : ""}
                {fmt(result.acceleration_km_s2 * 1000, 1)} m/s²
              </span>
            )}
            <span className="text-slate-500">{timed.length} pts</span>
          </div>
        </div>
        {timed.length >= 2 ? (
          <MiniChart
            x={x}
            y={y}
            height={220}
            xLabel="time (UTC)"
            yLabel="height (R☉)"
            formatX={formatClockUtc}
            overlay={overlay}
            showDots
          />
        ) : (
          <p className="py-12 text-center text-xs text-slate-600">
            Pick at least two timed frames to draw the height–time graph.
          </p>
        )}
      </div>

      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <h2 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
          Track points
        </h2>
        <div className="max-h-64 overflow-y-auto rounded border border-surface-border">
          <table className="w-full font-mono text-[11px] text-slate-300">
            <thead className="sticky top-0 bg-surface-card">
              <tr className="border-b border-surface-border text-slate-500">
                <th className="px-2 py-1.5 text-left">#</th>
                <th className="px-2 py-1.5 text-left">frame</th>
                <th className="px-2 py-1.5 text-left">UTC</th>
                <th className="px-2 py-1.5 text-right">R☉</th>
                <th className="px-2 py-1.5 text-right">height (Mm)</th>
                <th className="px-2 py-1.5 text-right">Δt (s)</th>
                <th className="px-2 py-1.5 text-right">v (km/s)</th>
              </tr>
            </thead>
            <tbody>
              {result.points.map((p, i) => {
                const sec = parseUtcSeconds(p.time);
                // Instantaneous speed vs the previous timed point.
                let prevSec = NaN;
                let prevH = NaN;
                for (let j = i - 1; j >= 0; j--) {
                  const s = parseUtcSeconds(result.points[j].time);
                  if (isFinite(s)) {
                    prevSec = s;
                    prevH = result.points[j].height_km;
                    break;
                  }
                }
                const dt = isFinite(sec) && isFinite(prevSec) ? sec - prevSec : NaN;
                const segV = isFinite(dt) && dt !== 0 ? (p.height_km - prevH) / dt : NaN;
                return (
                  <tr key={i} className="border-b border-surface-border/50 last:border-0">
                    <td className="px-2 py-1">{i + 1}</td>
                    <td className="px-2 py-1">{p.frame + 1}</td>
                    <td className="px-2 py-1">{p.time ? p.time.slice(11, 19) : "—"}</td>
                    <td className="px-2 py-1 text-right">{p.r_rsun.toFixed(2)}</td>
                    <td className="px-2 py-1 text-right">{(p.height_km / 1000).toFixed(1)}</td>
                    <td className="px-2 py-1 text-right text-slate-500">{isFinite(dt) ? dt.toFixed(0) : "—"}</td>
                    <td className="px-2 py-1 text-right text-accent-cyan/90">
                      {isFinite(segV) ? segV.toFixed(0) : "—"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
