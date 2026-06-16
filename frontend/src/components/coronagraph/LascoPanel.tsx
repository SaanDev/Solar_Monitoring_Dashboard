"use client";

import useSWR from "swr";
import { api } from "@/lib/api";
import { formatUtcShort } from "@/lib/formatting";

export function LascoMovie({ camera }: { camera: "C2" | "C3" }) {
  const { data, isLoading } = useSWR(
    `lasco-movie-${camera}`,
    () => api.lascoMovie(camera),
    { refreshInterval: 900000 } // refresh URL/timestamp every 15 min
  );

  return (
    <div className="flex flex-col">
      <div className="mb-1 flex items-center justify-between text-xs">
        <span className="font-semibold text-slate-200">LASCO {camera}</span>
        <span className="text-slate-600">
          {data ? `updated ${formatUtcShort(data.timestamp)}` : "—"}
        </span>
      </div>
      <div className="aspect-square overflow-hidden rounded bg-black">
        {isLoading ? (
          <div className="h-full w-full animate-pulse bg-surface-muted" />
        ) : data ? (
          <video
            key={data.url}
            src={data.url}
            className="h-full w-full object-contain"
            autoPlay
            loop
            muted
            playsInline
            controls
            preload="metadata"
          />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-slate-700">
            Movie unavailable
          </div>
        )}
      </div>
    </div>
  );
}

export function LascoPanel() {
  return (
    <div className="grid grid-cols-2 gap-3">
      <LascoMovie camera="C2" />
      <LascoMovie camera="C3" />
    </div>
  );
}
