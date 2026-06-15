"use client";

import { useState } from "react";
import type { SolarImage } from "@/lib/types";
import { formatUtcShort } from "@/lib/formatting";

export function SolarImageCard({ image }: { image: SolarImage }) {
  const [open, setOpen] = useState(false);
  const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="group flex flex-col overflow-hidden rounded-lg border border-surface-border bg-surface-card hover:border-accent-blue/50 transition-colors"
      >
        <div className="aspect-square overflow-hidden bg-black">
          <img
            src={image.thumbnail_url}
            alt={`${image.instrument} ${image.wavelength}`}
            className="h-full w-full object-cover opacity-90 group-hover:opacity-100 transition-opacity"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        </div>
        <div className="p-2 text-left">
          <p className="text-xs font-semibold text-slate-200">{image.wavelength}</p>
          <p className="text-xs text-slate-600">{formatUtcShort(image.timestamp)}</p>
        </div>
      </button>

      {open && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80"
          onClick={() => setOpen(false)}
        >
          <div className="max-h-[90vh] max-w-[90vw]" onClick={(e) => e.stopPropagation()}>
            <img
              src={image.full_url}
              alt={`${image.instrument} ${image.wavelength} full`}
              className="max-h-[85vh] max-w-[85vw] rounded"
            />
            <p className="mt-2 text-center text-xs text-slate-400">
              {image.source} · {image.wavelength} — {formatUtcShort(image.timestamp)}
            </p>
          </div>
        </div>
      )}
    </>
  );
}
