"use client";

import { Slider } from "@/components/analyzer/Slider";
import type { AnalysisOptions, PlotParams } from "@/lib/types";

interface Props {
  params: PlotParams;
  options?: AnalysisOptions;
  onChange: (p: Partial<PlotParams>) => void;
}

const labelCls = "mb-1 block text-xs text-slate-500";
const selectCls =
  "w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue";
const numCls =
  "w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue";

export function PlotControls({ params, options, onChange }: Props) {
  const cmaps = options?.colormaps ?? ["auto"];
  const scales = options?.scales ?? ["linear", "sqrt", "log", "asinh"];
  const manual = params.vmin != null && params.vmax != null;

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">Plot Controls</h2>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={labelCls}>Colormap</label>
          <select
            value={params.cmap}
            onChange={(e) => onChange({ cmap: e.target.value })}
            className={selectCls}
          >
            {cmaps.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className={labelCls}>Scale</label>
          <select
            value={params.scale}
            onChange={(e) => onChange({ scale: e.target.value })}
            className={selectCls}
          >
            {scales.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Display range: percentile clip, or manual vmin/vmax. */}
      <div>
        <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-slate-400">
          <input
            type="checkbox"
            checked={manual}
            onChange={(e) =>
              onChange(
                e.target.checked
                  ? { vmin: 0, vmax: 0 }
                  : { vmin: null, vmax: null }
              )
            }
            className="h-3.5 w-3.5 accent-accent-blue"
          />
          Manual vmin / vmax
        </label>
        {manual ? (
          <div className="mt-2 grid grid-cols-2 gap-2">
            <div>
              <label className={labelCls}>vmin</label>
              <input
                type="number"
                value={params.vmin ?? 0}
                onChange={(e) => onChange({ vmin: parseFloat(e.target.value) })}
                className={numCls}
              />
            </div>
            <div>
              <label className={labelCls}>vmax</label>
              <input
                type="number"
                value={params.vmax ?? 0}
                onChange={(e) => onChange({ vmax: parseFloat(e.target.value) })}
                className={numCls}
              />
            </div>
          </div>
        ) : (
          <div className="mt-2 space-y-2">
            <Slider
              label="Clip low %"
              value={params.clip_low}
              min={0}
              max={50}
              step={0.1}
              onChange={(v) => onChange({ clip_low: v })}
            />
            <Slider
              label="Clip high %"
              value={params.clip_high}
              min={50}
              max={100}
              step={0.1}
              onChange={(v) => onChange({ clip_high: v })}
            />
          </div>
        )}
      </div>

      {/* Crop (submap) */}
      <div>
        <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-slate-400">
          <input
            type="checkbox"
            checked={params.crop}
            onChange={(e) => onChange({ crop: e.target.checked })}
            className="h-3.5 w-3.5 accent-accent-blue"
          />
          Crop (submap) — arcsec from disk centre
        </label>
        {params.crop && (
          <div className="mt-2 grid grid-cols-2 gap-2">
            {(["bl_x", "bl_y", "tr_x", "tr_y"] as const).map((k) => (
              <div key={k}>
                <label className={labelCls}>{k.replace("_", " ")}</label>
                <input
                  type="number"
                  value={params[k]}
                  onChange={(e) => onChange({ [k]: parseFloat(e.target.value) })}
                  className={numCls}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Annotation toggles */}
      <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-slate-400">
        {(
          [
            ["draw_limb", "Solar limb"],
            ["draw_grid", "Heliographic grid"],
            ["colorbar", "Colorbar"],
          ] as const
        ).map(([key, label]) => (
          <label key={key} className="flex cursor-pointer select-none items-center gap-2">
            <input
              type="checkbox"
              checked={params[key]}
              onChange={(e) => onChange({ [key]: e.target.checked })}
              className="h-3.5 w-3.5 accent-accent-blue"
            />
            {label}
          </label>
        ))}
      </div>
    </div>
  );
}
