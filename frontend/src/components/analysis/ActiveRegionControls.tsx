"use client";

import { clsx } from "clsx";
import { Slider } from "@/components/analyzer/Slider";
import { PlotControls } from "./PlotControls";
import type { AnalysisOptions, PlotParams } from "@/lib/types";

interface Props {
  params: PlotParams;
  options?: AnalysisOptions;
  method: "hek" | "threshold";
  thresholdPct: number;
  onChange: (p: Partial<PlotParams>) => void;
  onMethod: (m: "hek" | "threshold") => void;
  onThreshold: (p: number) => void;
}

export function ActiveRegionControls({
  params,
  options,
  method,
  thresholdPct,
  onChange,
  onMethod,
  onThreshold,
}: Props) {
  return (
    <div className="space-y-3">
      <div className="space-y-2 rounded-lg border border-surface-border bg-surface-card p-4">
        <h2 className="text-xs uppercase tracking-wider text-slate-500">Active Regions</h2>
        <div className="flex gap-1">
          {(
            [
              ["hek", "NOAA (HEK)"],
              ["threshold", "Threshold"],
            ] as const
          ).map(([m, label]) => (
            <button
              key={m}
              onClick={() => onMethod(m)}
              className={clsx(
                "flex-1 rounded px-2 py-1 text-xs transition-colors",
                method === m
                  ? "bg-accent-blue/20 text-accent-blue"
                  : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
              )}
            >
              {label}
            </button>
          ))}
        </div>
        {method === "threshold" ? (
          <>
            <Slider
              label="Brightness percentile"
              value={thresholdPct}
              min={80}
              max={99.9}
              step={0.1}
              onChange={onThreshold}
            />
            <p className="text-[10px] leading-relaxed text-slate-600">
              Boxes bright connected regions above this intensity percentile.
            </p>
          </>
        ) : (
          <p className="text-[10px] leading-relaxed text-slate-600">
            Marks NOAA SWPC active regions (from the HEK) nearest this frame&apos;s
            time, labelled with their AR numbers.
          </p>
        )}
      </div>
      <PlotControls params={params} options={options} onChange={onChange} />
    </div>
  );
}
