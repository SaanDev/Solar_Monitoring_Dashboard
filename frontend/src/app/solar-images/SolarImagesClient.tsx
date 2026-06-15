"use client";

import { useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { SolarImageGrid } from "@/components/solar/SolarImageGrid";
import { clsx } from "clsx";

const FILTERS = [
  { key: "all", label: "All", match: () => true },
  { key: "aia", label: "SDO/AIA", match: (inst: string) => inst === "AIA" },
  { key: "hmi", label: "SDO/HMI", match: (inst: string) => inst === "HMI" },
  { key: "suvi", label: "GOES/SUVI", match: (inst: string) => inst === "SUVI" },
] as const;

type FilterKey = (typeof FILTERS)[number]["key"];

export function SolarImagesClient() {
  const [filter, setFilter] = useState<FilterKey>("all");
  const { data, isLoading } = useSWR("solar-images-latest", api.solarImagesLatest, {
    refreshInterval: 300000, // 5 min
  });

  const matcher = FILTERS.find((f) => f.key === filter)!.match;
  const images = (data ?? []).filter((img) => matcher(img.instrument));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="text-xs text-slate-500">
          Latest full-disk images · sources: SDO (AIA/HMI), GOES (SUVI) · times in UTC
        </div>
        <div className="flex gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setFilter(f.key)}
              className={clsx(
                "rounded px-3 py-1 text-xs transition-colors",
                filter === f.key
                  ? "bg-accent-blue/20 text-accent-blue"
                  : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <SolarImageGrid images={images} loading={isLoading} />
    </div>
  );
}
