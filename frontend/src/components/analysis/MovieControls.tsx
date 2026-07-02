"use client";

import { clsx } from "clsx";
import { Film } from "lucide-react";
import { Slider } from "@/components/analyzer/Slider";
import { PlotControls } from "./PlotControls";
import type { AnalysisOptions, PlotParams } from "@/lib/types";

interface Props {
  params: PlotParams;
  options?: AnalysisOptions;
  fmt: "mp4" | "gif";
  fps: number;
  mode: "plot" | "difference";
  building: boolean;
  onChange: (p: Partial<PlotParams>) => void;
  onFmt: (f: "mp4" | "gif") => void;
  onFps: (n: number) => void;
  onMode: (m: "plot" | "difference") => void;
  onBuild: () => void;
}

function Segmented<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T;
  options: readonly (readonly [T, string])[];
  onChange: (v: T) => void;
}) {
  return (
    <div className="flex gap-1">
      {options.map(([v, label]) => (
        <button
          key={v}
          onClick={() => onChange(v)}
          className={clsx(
            "flex-1 rounded px-2 py-1 text-xs transition-colors",
            value === v
              ? "bg-accent-blue/20 text-accent-blue"
              : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
          )}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

export function MovieControls({
  params,
  options,
  fmt,
  fps,
  mode,
  building,
  onChange,
  onFmt,
  onFps,
  onMode,
  onBuild,
}: Props) {
  return (
    <div className="space-y-3">
      <div className="space-y-2 rounded-lg border border-surface-border bg-surface-card p-4">
        <h2 className="text-xs uppercase tracking-wider text-slate-500">Movie</h2>
        <div>
          <label className="mb-1 block text-xs text-slate-500">Content</label>
          <Segmented
            value={mode}
            options={[["plot", "Frames"], ["difference", "Running diff"]] as const}
            onChange={onMode}
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">Format</label>
          <Segmented value={fmt} options={[["mp4", "MP4"], ["gif", "GIF"]] as const} onChange={onFmt} />
        </div>
        <Slider label="Frames per second" value={fps} min={1} max={24} step={1} onChange={(v) => onFps(Math.round(v))} />
        <button
          disabled={building}
          onClick={onBuild}
          className="flex w-full items-center justify-center gap-2 rounded bg-accent-blue/20 px-2 py-1.5 text-xs text-accent-blue transition-colors hover:bg-accent-blue/30 disabled:opacity-40"
        >
          <Film className="h-3.5 w-3.5" />
          {building ? "Building…" : "Build movie"}
        </button>
      </div>
      <PlotControls params={params} options={options} onChange={onChange} />
    </div>
  );
}
