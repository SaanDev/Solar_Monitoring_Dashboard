"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { SolarImageCard } from "@/components/solar/SolarImageCard";

// Show a compact set of the most useful channels on the overview.
const PREFERRED = ["aia171", "aia193", "aia304", "hmib"];

export function OverviewSolarImages() {
  const { data, isLoading } = useSWR("overview-solar-images", api.solarImagesLatest, {
    refreshInterval: 300000,
  });

  const images = (data ?? [])
    .filter((img) => PREFERRED.includes(img.id))
    .sort((a, b) => PREFERRED.indexOf(a.id) - PREFERRED.indexOf(b.id));

  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4">
      <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">Solar Images</h3>
      {isLoading ? (
        <div className="grid grid-cols-2 gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="aspect-square animate-pulse rounded bg-surface-muted" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          {images.map((img) => (
            <SolarImageCard key={img.id} image={img} />
          ))}
        </div>
      )}
    </div>
  );
}
