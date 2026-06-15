"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { clsx } from "clsx";
import { api } from "@/lib/api";
import { formatUtcShort } from "@/lib/formatting";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export function BurstEventSlider({
  heightClass = "min-h-[600px] flex-1",
}: {
  heightClass?: string;
}) {
  const { data: list, isLoading: listLoading } = useSWR("bursts-latest", api.burstsLatest, {
    refreshInterval: 600000, // 10 min
  });

  const events = list?.events ?? [];
  const [index, setIndex] = useState(0);

  // Default to the first burst that has FITS data once the list arrives.
  useEffect(() => {
    if (events.length) {
      const firstWithFits = events.find((e) => e.has_fits)?.index ?? 0;
      setIndex(firstWithFits);
    }
  }, [list?.date, events.length]);

  const current = events[index];
  const { data: spectrum, isLoading: specLoading } = useSWR(
    current?.has_fits ? ["burst-spectrum", index] : null,
    () => api.burstSpectrum(index),
    { revalidateOnFocus: false }
  );

  if (listLoading) {
    return <div className={`animate-pulse rounded-lg bg-surface-muted ${heightClass}`} />;
  }
  if (!events.length) {
    return (
      <div
        className={`flex items-center justify-center rounded-lg border border-surface-border bg-surface-card text-xs text-slate-600 ${heightClass}`}
      >
        No burst events found in the latest burst list.
      </div>
    );
  }

  const go = (delta: number) =>
    setIndex((i) => Math.min(events.length - 1, Math.max(0, i + delta)));

  return (
    <div className="flex flex-1 flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      {/* Header */}
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-slate-200">
          Burst Events — {list?.date ?? "—"}
          <span className="ml-2 text-xs font-normal text-slate-500">
            ({list?.sri_lanka_count ?? 0} involving Sri Lanka)
          </span>
        </h2>
        <span className="text-xs text-slate-500">
          Burst {index + 1} of {events.length}
        </span>
      </div>

      {/* Metadata bar */}
      {current && (
        <div className="mb-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          <span className="font-mono text-slate-200">
            {current.start}–{current.end} UTC
          </span>
          <span className="rounded bg-accent-purple/20 px-2 py-0.5 text-accent-purple">
            {current.burst_type}
          </span>
          <span className="text-slate-500">
            Station:{" "}
            <span
              className={clsx(
                "font-semibold",
                current.station_used === "SRI-Lanka" ? "text-accent-cyan" : "text-slate-300"
              )}
            >
              {current.station_used ?? "n/a"}
            </span>
          </span>
          {spectrum && (
            <span className="text-slate-600">
              {spectrum.freq_min_mhz.toFixed(0)}–{spectrum.freq_max_mhz.toFixed(0)} MHz
              {spectrum.start_time && ` · ${formatUtcShort(spectrum.start_time)}`}
            </span>
          )}
        </div>
      )}

      {/* Spectrum image with overlaid navigation arrows */}
      <div className={`relative overflow-hidden rounded bg-black/40 ${heightClass}`}>
        {!current?.has_fits ? (
          <div className="flex h-full flex-col items-center justify-center gap-1 text-xs text-slate-600">
            <p>No archived FITS available for this burst.</p>
            <p className="px-6 text-center text-slate-700">
              Stations: {current?.stations.join(", ")}
            </p>
          </div>
        ) : specLoading ? (
          <div className="h-full w-full animate-pulse bg-surface-muted" />
        ) : spectrum ? (
          <img
            src={`${apiBase}${spectrum.image_url}`}
            alt={`Burst ${index + 1} dynamic spectrum`}
            className="h-full w-full object-contain"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-slate-600">
            Failed to load spectrum
          </div>
        )}

        <button
          onClick={() => go(-1)}
          disabled={index === 0}
          className="absolute left-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/60 text-slate-200 backdrop-blur hover:bg-accent-blue/70 disabled:opacity-20"
          aria-label="Previous burst"
        >
          <ChevronLeft className="h-5 w-5" />
        </button>
        <button
          onClick={() => go(1)}
          disabled={index === events.length - 1}
          className="absolute right-2 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/60 text-slate-200 backdrop-blur hover:bg-accent-blue/70 disabled:opacity-20"
          aria-label="Next burst"
        >
          <ChevronRight className="h-5 w-5" />
        </button>
      </div>

      {/* Participating stations */}
      {current && (
        <p className="mt-2 truncate text-xs text-slate-600">
          Observed by: {current.stations.join(", ")}
        </p>
      )}

      {/* Dot indicators */}
      <div className="mt-3 flex flex-wrap justify-center gap-1">
        {events.map((e, i) => (
          <button
            key={i}
            onClick={() => setIndex(i)}
            title={`${e.start}–${e.end} ${e.burst_type}`}
            className={clsx(
              "h-1.5 rounded-full transition-all",
              i === index ? "w-5 bg-accent-blue" : "w-1.5",
              e.stations.includes("SRI-Lanka")
                ? "bg-accent-cyan/60"
                : i === index
                  ? ""
                  : "bg-slate-700"
            )}
          />
        ))}
      </div>
    </div>
  );
}
