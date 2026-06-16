"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { SolarImageCard } from "@/components/solar/SolarImageCard";

// Show a horizontal strip of the most useful channels on the overview.
const PREFERRED = ["aia171", "aia193", "aia211", "aia304", "hmib"];

export function OverviewSolarImages() {
  const { data, isLoading } = useSWR("overview-solar-images", api.solarImagesLatest, {
    refreshInterval: 300000,
  });

  const images = (data ?? [])
    .filter((img) => PREFERRED.includes(img.id))
    .sort((a, b) => PREFERRED.indexOf(a.id) - PREFERRED.indexOf(b.id));

  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4">
      <h3 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
        SDO/AIA &amp; HMI Latest Images
      </h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        {isLoading
          ? Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="aspect-square animate-pulse rounded bg-surface-muted" />
            ))
          : images.map((img) => <SolarImageCard key={img.id} image={img} />)}
      </div>
    </div>
  );
}
