"use client";

import { useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";

import { api } from "@/lib/api";
import { Segmented } from "@/components/ui/Segmented";
import { EmptyState } from "@/components/ui/EmptyState";

type Hemisphere = "north" | "south";

/**
 * OVATION aurora forecast: NOAA's rendered oval (re-drawn every ~5 min) plus
 * the hemispheric power index. A time-bucketed cache-buster keeps the image
 * fresh without defeating the browser cache entirely.
 */
export function AuroraPanel() {
  const [hemi, setHemi] = useState<Hemisphere>("north");
  const { data, error } = useSWR("forecast-aurora", api.forecastAurora, {
    refreshInterval: 300000,
  });
  // The image slot keys off `url`, which stays falsy forever on a failed fetch —
  // so without this the panel pulsed indefinitely instead of reporting failure.
  const [imgFailed, setImgFailed] = useState(false);

  const bucket = Math.floor(Date.now() / 300000); // one URL per 5-min window
  const url =
    data && `${hemi === "north" ? data.north_image_url : data.south_image_url}?t=${bucket}`;
  const power = hemi === "north" ? data?.power_north_gw : data?.power_south_gw;

  return (
    <div className="flex h-full flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-xs uppercase tracking-wider text-slate-500">
          Aurora Forecast — OVATION
        </h3>
        <Segmented
          ariaLabel="Hemisphere"
          value={hemi}
          onChange={(h) => {
            setHemi(h);
            setImgFailed(false); // give the other hemisphere a clean attempt
          }}
          options={[
            { value: "north", label: "North" },
            { value: "south", label: "South" },
          ]}
        />
      </div>

      <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
        <span className="text-slate-500">
          Hemispheric power:{" "}
          <span
            className={clsx(
              "font-mono font-bold",
              power != null && power >= 50
                ? "text-accent-red"
                : power != null && power >= 20
                  ? "text-accent-orange"
                  : "text-accent-green"
            )}
          >
            {power != null ? `${power.toFixed(0)} GW` : "—"}
          </span>
        </span>
        {data?.forecast_time && (
          <span className="text-slate-600">
            forecast valid {data.forecast_time.slice(11, 16)} UTC
          </span>
        )}
      </div>

      <div className="flex min-h-[16rem] flex-1 items-center justify-center overflow-hidden rounded bg-black/40">
        {error || imgFailed ? (
          <EmptyState
            tone="error"
            message="Aurora forecast unavailable — could not load the OVATION render."
            className="border-0 bg-transparent"
          />
        ) : url ? (
          // eslint-disable-next-line @next/next/no-img-element -- external NOAA render
          <img
            src={url}
            alt={`OVATION aurora forecast, ${hemi}ern hemisphere`}
            className="max-h-full w-full max-w-xl object-contain"
            onError={() => setImgFailed(true)}
          />
        ) : (
          <div className="h-64 w-full animate-pulse bg-surface-muted" />
        )}
      </div>
      <p className="mt-2 text-[10px] text-slate-600">
        Probability of visible aurora, 30-min forecast · NOAA SWPC OVATION model
      </p>
    </div>
  );
}
