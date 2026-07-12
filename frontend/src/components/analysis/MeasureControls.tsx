"use client";

import { useEffect, useState } from "react";
import { clsx } from "clsx";
import { api } from "@/lib/api";
import { MiniChart } from "./MiniChart";
import type { ProfileResult, RegionStatsResult, RulerResult } from "@/lib/types";

export type MeasureMode = "ruler" | "profile" | "region";

interface Props {
  sessionId: string;
  frame: number;
  mode: MeasureMode;
  onMode: (m: MeasureMode) => void;
  /** Data-pixel picks collected on the canvas (max 2). */
  picks: { px: number; py: number }[];
  onClear: () => void;
}

const MODES: { key: MeasureMode; label: string }[] = [
  { key: "ruler", label: "Ruler" },
  { key: "profile", label: "Profile" },
  { key: "region", label: "Region" },
];

function fmt(v: number | null | undefined, digits = 1): string {
  if (v == null || !isFinite(v)) return "—";
  return Math.abs(v) >= 1e5 ? v.toExponential(2) : v.toFixed(digits);
}

/** Ruler / line-profile / region-statistics tool (ported image_measure). */
export function MeasureControls({ sessionId, frame, mode, onMode, picks, onClear }: Props) {
  const [ruler, setRuler] = useState<RulerResult | null>(null);
  const [profile, setProfile] = useState<ProfileResult | null>(null);
  const [region, setRegion] = useState<RegionStatsResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setRuler(null);
    setProfile(null);
    setRegion(null);
    setError(null);
    if (picks.length !== 2) return;
    const [a, b] = picks;
    const run = async () => {
      try {
        if (mode === "ruler") {
          setRuler(await api.analysisMeasureRuler(sessionId, frame, a.px, a.py, b.px, b.py));
        } else if (mode === "profile") {
          setProfile(await api.analysisMeasureProfile(sessionId, frame, a.px, a.py, b.px, b.py));
        } else {
          setRegion(await api.analysisMeasureRegion(sessionId, frame, a.px, a.py, b.px, b.py));
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : "Measurement failed");
      }
    };
    run();
  }, [sessionId, frame, mode, picks]);

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">Measurements</h2>

      <div className="flex gap-1">
        {MODES.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => {
              onMode(key);
              onClear();
            }}
            className={clsx(
              "flex-1 rounded px-2 py-1 text-xs transition-colors",
              mode === key
                ? "bg-accent-blue/20 text-accent-blue"
                : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
            )}
          >
            {label}
          </button>
        ))}
      </div>

      <p className="text-[10px] leading-relaxed text-slate-600">
        {mode === "ruler" && "Click two points on the image: plane-of-sky separation in arcsec, R☉ and km, plus the N→E position angle."}
        {mode === "profile" && "Click two points: intensity sampled along the segment (e.g. across a loop, filament or CME front)."}
        {mode === "region" && "Click two opposite corners: statistics + intensity-weighted centroid of the rectangle."}
        {" "}({picks.length}/2 points)
      </p>

      {picks.length > 0 && (
        <button
          onClick={onClear}
          className="w-full rounded bg-surface-muted px-2 py-1 text-xs text-slate-300 transition-colors hover:bg-surface-border"
        >
          Clear points
        </button>
      )}

      {ruler && (
        <div className="space-y-1 font-mono text-[11px] text-slate-300">
          <div>Δ = ({fmt(ruler.dx_arcsec)}″, {fmt(ruler.dy_arcsec)}″)</div>
          <div>distance = {fmt(ruler.distance_arcsec)}″ = {fmt(ruler.distance_rsun, 3)} R☉</div>
          <div>= {ruler.distance_km != null ? `${(ruler.distance_km / 1e3).toFixed(0)}×10³ km` : "—"}</div>
          <div>position angle = {fmt(ruler.position_angle_deg)}° (N→E)</div>
        </div>
      )}

      {profile && (
        <div className="space-y-1">
          <MiniChart
            x={profile.distance_arcsec}
            y={profile.values}
            height={160}
            xLabel="distance along segment (arcsec)"
            yLabel="intensity"
          />
          <p className="font-mono text-[10px] text-slate-500">
            {profile.n} samples · {fmt(profile.length_arcsec)}″ ({fmt(profile.length_rsun, 2)} R☉)
          </p>
        </div>
      )}

      {region && (
        <div className="space-y-1 font-mono text-[11px] text-slate-300">
          <div>n = {region.n_pixels} px</div>
          <div>min {fmt(region.min)} · max {fmt(region.max)}</div>
          <div>mean {fmt(region.mean, 2)} · median {fmt(region.median, 2)} · σ {fmt(region.std, 2)}</div>
          <div>
            centroid ({fmt(region.centroid_tx_arcsec)}″, {fmt(region.centroid_ty_arcsec)}″)
          </div>
        </div>
      )}

      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}
