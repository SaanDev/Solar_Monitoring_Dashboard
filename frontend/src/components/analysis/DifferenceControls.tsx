"use client";

import { clsx } from "clsx";
import { Slider } from "@/components/analyzer/Slider";
import type { AnalysisOptions, PlotParams } from "@/lib/types";

interface Props {
  params: PlotParams;
  options?: AnalysisOptions;
  diffType: "running" | "base";
  baseIndex: number;
  nFrames: number;
  onChange: (p: Partial<PlotParams>) => void;
  onDiffType: (t: "running" | "base") => void;
  onBaseIndex: (i: number) => void;
}

const labelCls = "mb-1 block text-xs text-slate-500";
const selectCls =
  "w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue";
const numCls = selectCls;

export function DifferenceControls({
  params,
  options,
  diffType,
  baseIndex,
  nFrames,
  onChange,
  onDiffType,
  onBaseIndex,
}: Props) {
  const cmaps = options?.colormaps ?? ["auto"];

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">Difference Controls</h2>

      <div>
        <label className={labelCls}>Type</label>
        <div className="flex gap-1">
          {(["running", "base"] as const).map((t) => (
            <button
              key={t}
              onClick={() => onDiffType(t)}
              className={clsx(
                "flex-1 rounded px-2 py-1 text-xs capitalize transition-colors",
                diffType === t
                  ? "bg-accent-blue/20 text-accent-blue"
                  : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
              )}
            >
              {t}
            </button>
          ))}
        </div>
        <p className="mt-1 text-[10px] text-slate-600">
          {diffType === "running"
            ? "Each frame minus the previous frame."
            : "Each frame minus a fixed base frame."}
        </p>
      </div>

      {diffType === "base" && (
        <div>
          <label className={labelCls}>
            Base frame: {baseIndex + 1} / {nFrames}
          </label>
          <input
            type="range"
            min={0}
            max={nFrames - 1}
            step={1}
            value={baseIndex}
            onChange={(e) => onBaseIndex(parseInt(e.target.value, 10))}
            className="w-full accent-accent-blue"
          />
        </div>
      )}

      <div>
        <label className={labelCls}>Colormap (diverging)</label>
        <select value={params.cmap} onChange={(e) => onChange({ cmap: e.target.value })} className={selectCls}>
          {cmaps.map((c) => (
            <option key={c} value={c}>
              {c === "auto" ? "auto (RdBu)" : c}
            </option>
          ))}
        </select>
      </div>

      <Slider
        label="Symmetric clip %"
        value={params.clip_high}
        min={90}
        max={100}
        step={0.1}
        onChange={(v) => onChange({ clip_high: v })}
      />

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
