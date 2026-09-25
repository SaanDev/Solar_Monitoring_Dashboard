"use client";

import type { RadioSpectrum } from "@/lib/types";
import { formatUtcShort } from "@/lib/formatting";
import { API_BASE } from "@/lib/api";

interface Props {
  spectrum: RadioSpectrum | null;
  loading?: boolean;
  error?: string | null;
}

export function DynamicSpectrumPanel({ spectrum, loading, error }: Props) {
  if (loading) {
    return <div className="h-full animate-pulse rounded bg-surface-muted" />;
  }
  if (error) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-accent-red">{error}</div>
    );
  }
  if (!spectrum) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-2 text-xs text-slate-700">
        <p>Upload a FITS file or select a station and date range to load a dynamic spectrum.</p>
      </div>
    );
  }

  const apiBase = API_BASE;

  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex items-center justify-between text-xs text-slate-500">
        <span>
          <span className="font-semibold text-slate-300">{spectrum.station}</span>
          {spectrum.start_time && (
            <span className="ml-2">{formatUtcShort(spectrum.start_time)}</span>
          )}
        </span>
        <span>
          {spectrum.freq_min_mhz.toFixed(0)}–{spectrum.freq_max_mhz.toFixed(0)} MHz
        </span>
        <span className="text-slate-700">{spectrum.processing_method}</span>
      </div>
      <div className="relative flex-1 overflow-hidden rounded">
        <img
          src={`${apiBase}${spectrum.image_url}`}
          alt="Dynamic spectrum"
          className="h-full w-full object-contain"
        />
      </div>
    </div>
  );
}
