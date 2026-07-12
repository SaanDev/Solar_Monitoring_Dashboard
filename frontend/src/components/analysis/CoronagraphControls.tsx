"use client";

import type { PlotParams } from "@/lib/types";

interface Props {
  params: PlotParams;
  onChange: (p: Partial<PlotParams>) => void;
}

/** Coronagraph-only display science (shown when science_class === "coronagraph"). */
export function CoronagraphControls({ params, onChange }: Props) {
  return (
    <div className="space-y-2 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">Coronagraph Tools</h2>
      <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-slate-400">
        <input
          type="checkbox"
          checked={params.nrgf}
          onChange={(e) => onChange({ nrgf: e.target.checked })}
          className="h-3.5 w-3.5 accent-accent-blue"
        />
        NRGF radial filter
      </label>
      <p className="text-[10px] leading-relaxed text-slate-600">
        Normalizing-Radial-Graded Filter (Morgan et&nbsp;al. 2006): subtracts the
        azimuthal mean and divides by the azimuthal spread in each annulus, so the
        corona&apos;s steep radial fall-off is flattened and faint CME fronts become
        visible at all heights.
      </p>
    </div>
  );
}
