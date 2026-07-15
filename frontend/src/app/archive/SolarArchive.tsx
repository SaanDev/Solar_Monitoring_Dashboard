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
  // PNG/JP2 exist for every source; FITS only for AIA/HMI (via JSOC). Show the
  // FITS control always, but disabled when this source has no raw science FITS.
  const fitsReady = img.fits_available && img.fts_download_url;
  return (
    <div className={clsx("flex items-center", compact ? "gap-1" : "gap-2")}>
      <a href={`${apiBase}${img.png_download_url}`} download className={cls} title="Download PNG image">
        <Download className="h-3.5 w-3.5" /> PNG
      </a>
      <a href={`${apiBase}${img.jp2_download_url}`} download className={cls} title="Download raw JPEG2000">
        <Download className="h-3.5 w-3.5" /> JP2
      </a>
      {fitsReady ? (
        <a
          href={`${apiBase}${img.fts_download_url}`}
          download
          className={cls}
          title="Download raw science FITS"
        >
          <Download className="h-3.5 w-3.5" /> FITS
        </a>
      ) : (
        <span
          className="flex cursor-not-allowed items-center gap-1 rounded bg-surface-muted/40 px-2 py-1 text-xs text-slate-600"
          title="No raw science FITS for this source"
          aria-disabled="true"
        >
          <Download className="h-3.5 w-3.5" /> FITS
        </span>
      )}
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

function utcToday(): string {
  return new Date().toISOString().slice(0, 10);
}

export function SolarArchive() {
  const today = utcToday();
  // Solar images are near-real-time, so this tab opens on *today* in "latest"
  // mode — the newest frames. Changing the Time (UTC) control (on any day,
  // including today) drops into by-time mode to browse an earlier frame.
  const [date, setDate] = useState(today);
  const [time, setTime] = useState("12:00");
  const [latest, setLatest] = useState(true);
  const [events, setEvents] = useState(false);
  const [active, setActive] = useState<SolarArchiveImage | null>(null);

  // "Latest" (newest near-real-time browse frames) only makes sense for the
  // current UTC day; any earlier day is always resolved by time. Picking a time
  // exits latest mode even on today, so the present day can be scrubbed too.
  const isToday = date >= today;
  const isLatest = isToday && latest;
  // Browse frames can't carry the HEK active-region overlay, so it only applies
  // to archived (by-time) renders.
  const reqEvents = isLatest ? false : events;

  const selectDate = (value: string) => {
    const next = value || today;
    setDate(next);
    setLatest(next >= today); // a past date is always by-time; today defaults to latest
  };
  const pickTime = (value: string) => {
    setTime(value || "12:00");
    setLatest(false); // scrub to a specific frame, even on the present day
  };
  const jumpToLatest = () => {
    setDate(today);
    setLatest(true);
  };

  const { data, isLoading, error } = useSWR(
    ["solar-archive", date, time, reqEvents, isLatest],
    () => api.solarArchiveImages(date, reqEvents, time, isLatest),
    { revalidateOnFocus: false }
  );
  const images = data?.images ?? [];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border bg-surface-card p-3">
        <p className="text-xs text-slate-500">
          Full-disk SDO (AIA/HMI) &amp; SOHO/LASCO ·{" "}
          {isLatest
            ? "latest near-real-time frames · downloads are the newest science data"
            : `${date} ~${time} UTC · closest archived frame (actual time shown per image)`}
        </p>
        <div className="flex flex-wrap items-center gap-4">
          <label className="flex items-center gap-2 text-xs text-slate-500">
            Date (UTC)
            <input
              type="date"
              value={date}
              max={today}
              onChange={(e) => selectDate(e.target.value)}
              className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue"
            />
          </label>
          <label className="flex items-center gap-2 text-xs text-slate-500">
            Time (UTC)
            <input
              type="time"
              value={isLatest ? data?.time ?? time : time}
              onChange={(e) => pickTime(e.target.value)}
              className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue"
            />
          </label>
          {isLatest ? (
            <span className="rounded bg-accent-blue/15 px-2 py-1 text-xs text-accent-blue">
              Live · latest
            </span>
          ) : (
            <>
              <button
                onClick={jumpToLatest}
                className="rounded bg-surface-muted px-2 py-1 text-xs text-accent-blue transition-colors hover:bg-accent-blue/20"
                title="Jump back to the latest images"
              >
                Latest
              </button>
              <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-300">
                <input
                  type="checkbox"
                  checked={events}
                  onChange={(e) => setEvents(e.target.checked)}
                  className="h-3.5 w-3.5 accent-accent-blue"
                />
                Show NOAA active regions
              </label>
            </>
          )}
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
