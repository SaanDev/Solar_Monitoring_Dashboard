"use client";

import { clsx } from "clsx";
import { Slider } from "./Slider";
import type {
  AnalyzerOptions,
  AnalyzerStats,
  BgMethod,
  IntensityUnit,
  RenderParams,
  TimeUnit,
} from "@/lib/types";

interface Props {
  params: RenderParams;
  stats?: AnalyzerStats;
  options?: AnalyzerOptions;
  onChange: (patch: Partial<RenderParams>) => void;
}

const UNIT_LABELS: Record<IntensityUnit, string> = { db: "dB", digits: "Digits" };
const TIME_LABELS: Record<TimeUnit, string> = { seconds: "Seconds", utc: "UTC" };
const METHOD_LABELS: Record<BgMethod, string> = {
  mean: "Mean",
  median: "Median",
  robust: "Robust (p25)",
};

function Pills<T extends string>({
  value,
  options,
  labels,
  onSelect,
}: {
  value: T;
  options: T[];
  labels: Record<T, string>;
  onSelect: (v: T) => void;
}) {
  return (
    <div className="flex gap-1">
      {options.map((o) => (
        <button
          key={o}
          onClick={() => onSelect(o)}
          className={clsx(
            "flex-1 rounded px-2 py-1 text-xs transition-colors",
            value === o
              ? "bg-accent-blue/20 text-accent-blue"
              : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
          )}
        >
          {labels[o]}
        </button>
      ))}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="mb-1 text-[10px] uppercase tracking-widest text-slate-500">{label}</p>
      {children}
    </div>
  );
}

export function AnalyzerControls({ params, stats, options, onChange }: Props) {
  const cmaps = options?.colormaps ?? ["magma"];
  const methods = options?.methods ?? ["mean", "median", "robust"];
  const intensityUnits = options?.intensity_units ?? ["db", "digits"];
  const timeUnits = options?.time_units ?? ["seconds", "utc"];

  // Slider bounds from the processed-data range; pad slightly so the thumbs aren't pinned.
  const lo = stats?.data_min ?? -1;
  const hi = stats?.data_max ?? 8;
  const pad = (hi - lo) * 0.1 || 1;
  const sliderMin = lo - pad;
  const sliderMax = hi + pad;
  const step = Math.max((sliderMax - sliderMin) / 200, 0.01);
  const vmin = params.vmin ?? stats?.vmin ?? lo;
  const vmax = params.vmax ?? stats?.vmax ?? hi;

  return (
    <div className="space-y-4 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">Controls</h2>

      <Field label="Intensity unit">
        <Pills
          value={params.intensity_unit}
          options={intensityUnits}
          labels={UNIT_LABELS}
          onSelect={(intensity_unit) => onChange({ intensity_unit, vmin: null, vmax: null })}
        />
      </Field>

      <Field label="Time axis">
        <Pills
          value={params.time_unit}
          options={timeUnits}
          labels={TIME_LABELS}
          onSelect={(time_unit) => onChange({ time_unit })}
        />
      </Field>

      <Field label="Background subtraction">
        <Pills
          value={params.method}
          options={methods}
          labels={METHOD_LABELS}
          onSelect={(method) => onChange({ method, vmin: null, vmax: null })}
        />
      </Field>

      <Field label="Display range">
        <div className="space-y-3">
          <Slider
            label="Min (vmin)"
            value={vmin}
            min={sliderMin}
            max={sliderMax}
            step={step}
            onChange={(v) => onChange({ vmin: Math.min(v, vmax) })}
          />
          <Slider
            label="Max (vmax)"
            value={vmax}
            min={sliderMin}
            max={sliderMax}
            step={step}
            onChange={(v) => onChange({ vmax: Math.max(v, vmin) })}
          />
        </div>
      </Field>

      <Field label="Colormap">
        <select
          value={params.cmap}
          onChange={(e) => onChange({ cmap: e.target.value })}
          className="w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue"
        >
          {cmaps.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </select>
      </Field>

      <Field label="RFI cleaning">
        <label className="mb-2 flex items-center gap-2 text-xs text-slate-400">
          <input
            type="checkbox"
            checked={params.rfi_enabled}
            onChange={(e) => onChange({ rfi_enabled: e.target.checked, vmin: null, vmax: null })}
            className="accent-accent-blue"
          />
          Enable percentile clipping
        </label>
        <div className={clsx("space-y-3", !params.rfi_enabled && "opacity-40")}>
          <Slider
            label="Low percentile"
            value={params.rfi_low}
            min={0}
            max={50}
            step={0.5}
            suffix="%"
            disabled={!params.rfi_enabled}
            onChange={(v) => onChange({ rfi_low: Math.min(v, params.rfi_high), vmin: null, vmax: null })}
          />
          <Slider
            label="High percentile"
            value={params.rfi_high}
            min={50}
            max={100}
            step={0.5}
            suffix="%"
            disabled={!params.rfi_enabled}
            onChange={(v) => onChange({ rfi_high: Math.max(v, params.rfi_low), vmin: null, vmax: null })}
          />
        </div>
      </Field>
    </div>
  );
}
