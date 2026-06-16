"use client";

import { useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { Download, X } from "lucide-react";

import { api } from "@/lib/api";
import { formatUtcShort } from "@/lib/formatting";
import type { SolarArchiveImage } from "@/lib/types";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function DownloadRow({ img, compact = false }: { img: SolarArchiveImage; compact?: boolean }) {
  const cls =
    "flex items-center gap-1 rounded bg-surface-muted px-2 py-1 text-xs text-slate-300 transition-colors hover:bg-accent-blue/30 hover:text-accent-blue";
  return (
    <div className={clsx("flex items-center", compact ? "gap-1" : "gap-2")}>
      <a href={`${apiBase}${img.png_download_url}`} download className={cls} title="Download PNG image">
        <Download className="h-3.5 w-3.5" /> PNG
      </a>
      <a href={`${apiBase}${img.jp2_download_url}`} download className={cls} title="Download raw JPEG2000">
        <Download className="h-3.5 w-3.5" /> JP2
      </a>
      {img.fits_available && img.fts_download_url ? (
        <a
          href={`${apiBase}${img.fts_download_url}`}
          download
          className={cls}
          title="Download raw science FITS"
        >
          <Download className="h-3.5 w-3.5" /> FITS
        </a>
      ) : null}
    </div>
  );
}

function ImageCard({ img, onOpen }: { img: SolarArchiveImage; onOpen: () => void }) {
  return (
    <div className="group flex flex-col overflow-hidden rounded-lg border border-surface-border bg-surface-card transition-colors hover:border-accent-blue/50">
      <button onClick={onOpen} className="aspect-square overflow-hidden bg-black" title="Click to enlarge">
        <img
          src={img.image_url}
          alt={img.label}
          loading="lazy"
          className="h-full w-full object-contain opacity-90 transition-opacity group-hover:opacity-100"
          onError={(e) => ((e.target as HTMLImageElement).style.visibility = "hidden")}
        />
      </button>
      <div className="flex items-center justify-between gap-1 p-2">
        <div className="min-w-0">
          <p className="truncate text-xs font-semibold text-slate-200">{img.label}</p>
          <p className="truncate text-[10px] text-slate-600">
            {img.time ? formatUtcShort(img.time) : "—"}
          </p>
        </div>
        <DownloadRow img={img} compact />
      </div>
    </div>
  );
}

function Lightbox({ img, onClose }: { img: SolarArchiveImage; onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4"
      onClick={onClose}
    >
      <div
        className="flex max-h-[92vh] max-w-[92vw] flex-col items-center gap-3"
        onClick={(e) => e.stopPropagation()}
      >
        <img
          src={img.image_url}
          alt={img.label}
          className="max-h-[78vh] max-w-[92vw] rounded border border-surface-border object-contain"
        />
        <div className="flex flex-wrap items-center justify-center gap-3 text-xs text-slate-400">
          <span className="font-semibold text-slate-200">{img.label}</span>
          <span>{img.source}</span>
          <span>{img.time ? formatUtcShort(img.time) : "—"}</span>
          <DownloadRow img={img} />
        </div>
      </div>
      <button
        onClick={onClose}
        className="absolute right-4 top-4 flex h-9 w-9 items-center justify-center rounded-full bg-black/60 text-slate-200 hover:bg-accent-blue/70"
        aria-label="Close"
      >
        <X className="h-5 w-5" />
      </button>
    </div>
  );
}

export function SolarArchive({ date }: { date: string }) {
  const [events, setEvents] = useState(false);
  const [time, setTime] = useState("12:00");
  const [active, setActive] = useState<SolarArchiveImage | null>(null);

  const { data, isLoading, error } = useSWR(
    ["solar-archive", date, time, events],
    () => api.solarArchiveImages(date, events, time),
    { revalidateOnFocus: false }
  );
  const images = data?.images ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border bg-surface-card p-3">
        <p className="text-xs text-slate-500">
          Full-disk SDO (AIA/HMI) &amp; SOHO/LASCO via Helioviewer · {date} ~{time} UTC
        </p>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-xs text-slate-500">
            Time (UTC)
            <input
              type="time"
              value={time}
              onChange={(e) => setTime(e.target.value || "12:00")}
              className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue"
            />
          </label>
          <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
            <input
              type="checkbox"
              checked={events}
              onChange={(e) => setEvents(e.target.checked)}
              className="h-3.5 w-3.5 accent-accent-blue"
            />
            Show NOAA active regions
          </label>
        </div>
      </div>

      {error ? (
        <div className="flex h-40 items-center justify-center rounded-lg border border-surface-border bg-surface-card text-xs text-accent-red">
          Failed to load solar images for {date}.
        </div>
      ) : isLoading ? (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {Array.from({ length: 12 }).map((_, i) => (
            <div key={i} className="aspect-square animate-pulse rounded-lg bg-surface-muted" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
          {images.map((img) => (
            <ImageCard key={img.id} img={img} onOpen={() => setActive(img)} />
          ))}
        </div>
      )}

      {active && <Lightbox img={active} onClose={() => setActive(null)} />}
    </div>
  );
}
