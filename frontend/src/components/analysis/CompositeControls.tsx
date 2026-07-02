"use client";

import { PlotControls } from "./PlotControls";
import type { AnalysisOptions, PlotParams } from "@/lib/types";

interface Props {
  params: PlotParams;
  options?: AnalysisOptions;
  contourLevel: number;
  onChange: (p: Partial<PlotParams>) => void;
  onContourLevel: (g: number) => void;
}

export function CompositeControls({ params, options, contourLevel, onChange, onContourLevel }: Props) {
  return (
    <div className="space-y-3">
      <div className="space-y-2 rounded-lg border border-surface-border bg-surface-card p-4">
        <h2 className="text-xs uppercase tracking-wider text-slate-500">Composite (AIA + HMI)</h2>
        <label className="mb-1 block text-xs text-slate-500">
          HMI |B| contour level: {contourLevel} G
        </label>
        <input
          type="range"
          min={50}
          max={2000}
          step={50}
          value={contourLevel}
          onChange={(e) => onContourLevel(parseInt(e.target.value, 10))}
          className="w-full accent-accent-blue"
        />
        <p className="text-[10px] leading-relaxed text-slate-600">
          Overlays line-of-sight magnetic-field contours from the HMI magnetogram
          nearest this frame&apos;s time — positive field red, negative cyan.
        </p>
      </div>
      <PlotControls params={params} options={options} onChange={onChange} />
    </div>
  );
}
