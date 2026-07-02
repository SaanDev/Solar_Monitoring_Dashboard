"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { ChevronLeft, ChevronRight, Download } from "lucide-react";

import { api } from "@/lib/api";
import { DynamicSpectrumPanel } from "@/components/radio/DynamicSpectrumPanel";
import { SolarArchive } from "./SolarArchive";
import { XrayProtonArchive } from "./XrayProtonArchive";
import { GeomagneticArchive } from "./GeomagneticArchive";
import { formatUtcShort } from "@/lib/formatting";
import type { BurstEventSummary } from "@/lib/types";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function fitsUrl(date: string, station: string, filename: string | null): string | null {
  if (!filename) return null;
  return `${apiBase}/api/radio/archive/fits?date=${date}&station=${encodeURIComponent(
    station
  )}&filename=${encodeURIComponent(filename)}`;
}

function DownloadLinks({ pngUrl, fits }: { pngUrl: string; fits: string | null }) {
  const cls =
    "flex items-center gap-1 rounded bg-surface-muted px-2 py-1 text-xs text-slate-300 transition-colors hover:bg-accent-blue/30 hover:text-accent-blue";
  return (
    <div className="flex items-center gap-2">
      <a href={pngUrl} download className={cls} title="Download processed PNG">
        <Download className="h-3.5 w-3.5" /> PNG
      </a>
      {fits ? (
        <a href={fits} download className={cls} title="Download raw FITS (.fit.gz)">
          <Download className="h-3.5 w-3.5" /> FITS
        </a>
      ) : null}
    </div>
  );
}

const INSTRUMENTS = [
  { key: "radio", label: "Radio Bursts (e-CALLISTO)", enabled: true },
  { key: "solar", label: "Solar Images", enabled: true },
  { key: "xray", label: "X-ray / Proton", enabled: true },
  { key: "geomag", label: "Geomagnetic", enabled: true },
] as const;

function utcDateOffset(days: number): string {
  return new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
}

export function ArchiveClient() {
  const [instrument, setInstrument] = useState<string>("radio");
  // e-CALLISTO data for the current UTC day is often still incomplete, so default
  // to the previous day; the user can pick any date up to today.
  const [date, setDate] = useState<string>(utcDateOffset(-1));

  // Deep-link from an alert/event: ?instrument=xray|geomag|…&date=YYYY-MM-DD
  // pre-selects the tab and date so the click lands on that event's data.
  // Read once on mount (window.location, like the Burst Predictor) to avoid the
  // useSearchParams() Suspense requirement.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const ins = params.get("instrument");
    const d = params.get("date");
    if (ins && INSTRUMENTS.some((i) => i.key === ins && i.enabled)) setInstrument(ins);
    if (d && /^\d{4}-\d{2}-\d{2}$/.test(d)) setDate(d);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="flex flex-wrap gap-1">
          {INSTRUMENTS.map((ins) => (
            <button
              key={ins.key}
              disabled={!ins.enabled}
              onClick={() => ins.enabled && setInstrument(ins.key)}
              className={clsx(
                "rounded px-3 py-1 text-xs transition-colors",
                instrument === ins.key
                  ? "bg-accent-blue/20 text-accent-blue"
                  : ins.enabled
                    ? "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
                    : "cursor-not-allowed text-slate-700"
              )}
              title={ins.enabled ? ins.label : "Coming soon"}
            >
              {ins.label}
              {!ins.enabled && " · soon"}
            </button>
          ))}
        </div>

        {/* Single-date picker for instruments keyed to one day. The geomagnetic
            tab (From/To range) and the solar tab (defaults to the latest, with its
            own date control) manage their own dates instead. */}
        {instrument !== "geomag" && instrument !== "solar" && (
          <label className="flex items-center gap-2 text-xs text-slate-500">
            Date (UTC)
            <input
              type="date"
              value={date}
              max={utcDateOffset(0)}
              onChange={(e) => setDate(e.target.value)}
              className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue"
            />
          </label>
        )}
      </div>

      {instrument === "radio" ? (
        <RadioArchive date={date} />
      ) : instrument === "solar" ? (
        <SolarArchive />
      ) : instrument === "xray" ? (
        <XrayProtonArchive date={date} />
      ) : instrument === "geomag" ? (
        <GeomagneticArchive date={date} />
      ) : (
        <div className="flex h-64 items-center justify-center rounded-lg border border-surface-border bg-surface-card text-sm text-slate-600">
          This instrument archive is coming soon.
        </div>
      )}
    </div>
  );
}

function RadioArchive({ date }: { date: string }) {
  // ── Stations available on the selected date ──
  const { data: stationsData, isLoading: stationsLoading } = useSWR(
    ["arch-stations", date],
    () => api.radioArchiveStations(date)
  );
  const stations = stationsData?.stations ?? [];
  const stationIds = stations.map((s) => s.id).join(",");

  const [station, setStation] = useState<string>("");
  useEffect(() => {
    const ids = stationIds ? stationIds.split(",") : [];
    if (!ids.length) {
      setStation("");
    } else if (!ids.includes(station)) {
      setStation(ids.includes("SRI-Lanka") ? "SRI-Lanka" : ids[0]);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, stationIds]);

  // ── 15-min segments for the chosen station ──
  const { data: filesData, isLoading: filesLoading } = useSWR(
    station ? ["arch-files", date, station] : null,
    () => api.radioArchiveFiles(date, station)
  );
  const files = filesData?.files ?? [];
  const fileNames = files.map((f) => f.filename).join(",");

  const [filename, setFilename] = useState<string>("");
  useEffect(() => {
    const names = fileNames ? fileNames.split(",") : [];
    if (!names.length) {
      setFilename("");
    } else if (!names.includes(filename)) {
      setFilename(names[names.length - 1]); // default to the latest segment
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, station, fileNames]);

  const segIndex = files.findIndex((f) => f.filename === filename);
  const stepSegment = (delta: number) => {
    const next = segIndex + delta;
    if (next >= 0 && next < files.length) setFilename(files[next].filename);
  };

  const {
    data: spectrum,
    isLoading: specLoading,
    error: specError,
  } = useSWR(
    station && filename ? ["arch-spectrum", date, station, filename] : null,
    () => api.radioArchiveSpectrum(date, station, filename),
    { revalidateOnFocus: false }
  );

  const noData = !stationsLoading && stations.length === 0;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      {/* ── Left: dynamic spectrum by station ── */}
      <section className="flex flex-col rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="mb-3 flex items-center justify-between gap-2">
          <h2 className="text-xs uppercase tracking-wider text-slate-500">Dynamic Spectrum</h2>
          {spectrum && (
            <DownloadLinks
              pngUrl={`${apiBase}${spectrum.image_url}?download=1`}
              fits={fitsUrl(date, station, spectrum.fits_filename)}
            />
          )}
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-2">
          <select
            value={station}
            onChange={(e) => setStation(e.target.value)}
            disabled={!stations.length}
            className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue disabled:opacity-40"
          >
            {!stations.length && <option value="">— No stations —</option>}
            {stations.map((s) => (
              <option key={s.id} value={s.id}>
                {s.id}
                {s.has_metadata ? " ★" : ""}
              </option>
            ))}
          </select>

          {files.length > 0 && (
            <div className="flex items-center gap-1 text-xs text-slate-500">
              <button
                onClick={() => stepSegment(-1)}
                disabled={segIndex <= 0}
                className="flex h-6 w-6 items-center justify-center rounded bg-surface-muted text-slate-300 hover:bg-accent-blue/40 disabled:opacity-20"
                aria-label="Previous segment"
              >
                <ChevronLeft className="h-4 w-4" />
              </button>
              <select
                value={filename}
                onChange={(e) => setFilename(e.target.value)}
                className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue"
              >
                {files.map((f) => (
                  <option key={f.filename} value={f.filename}>
                    {f.start_time.slice(11, 16)} UTC
                  </option>
                ))}
              </select>
              <button
                onClick={() => stepSegment(1)}
                disabled={segIndex >= files.length - 1}
                className="flex h-6 w-6 items-center justify-center rounded bg-surface-muted text-slate-300 hover:bg-accent-blue/40 disabled:opacity-20"
                aria-label="Next segment"
              >
                <ChevronRight className="h-4 w-4" />
              </button>
              <span className="text-slate-600">
                {segIndex + 1}/{files.length}
              </span>
            </div>
          )}
        </div>

        <div className="min-h-[320px] flex-1">
          {noData ? (
            <div className="flex h-full items-center justify-center text-xs text-slate-600">
              No e-CALLISTO data found for {date}.
            </div>
          ) : (
            <DynamicSpectrumPanel
              spectrum={spectrum ?? null}
              loading={stationsLoading || filesLoading || specLoading}
              error={specError ? "Failed to render this spectrum." : null}
            />
          )}
        </div>
      </section>

      {/* ── Right: burst list for the date ── */}
      <BurstList date={date} />
    </div>
  );
}

function BurstList({ date }: { date: string }) {
  const { data, isLoading } = useSWR(["arch-bursts", date], () => api.radioBurstsByDate(date));
  const events: BurstEventSummary[] = data?.events ?? [];

  const [index, setIndex] = useState<number | null>(null);
  useEffect(() => {
    const firstWithFits = events.find((e) => e.has_fits)?.index ?? null;
    setIndex(firstWithFits);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, events.length]);

  const { data: spectrum, isLoading: specLoading } = useSWR(
    index !== null ? ["arch-burst-spec", date, index] : null,
    () => api.radioBurstSpectrumByDate(date, index as number),
    { revalidateOnFocus: false }
  );
  const current = index !== null ? events.find((e) => e.index === index) ?? null : null;

  return (
    <section className="flex flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-wider text-slate-500">Burst List</h2>
        {data && (
          <span className="text-xs text-slate-600">
            {data.count} bursts · {data.sri_lanka_count} with Sri Lanka
          </span>
        )}
      </div>

      {isLoading ? (
        <div className="h-64 animate-pulse rounded bg-surface-muted" />
      ) : events.length === 0 ? (
        <div className="flex h-64 items-center justify-center text-xs text-slate-600">
          No bursts listed for {date}.
        </div>
      ) : (
        <>
          {/* selected burst spectrum */}
          <div className="relative mb-3 min-h-[240px] flex-1 overflow-hidden rounded bg-black/40">
            {current && !current.has_fits ? (
              <div className="flex h-full flex-col items-center justify-center gap-1 px-6 text-center text-xs text-slate-600">
                <p>No archived FITS available for this burst.</p>
                <p className="text-slate-700">Stations: {current.stations.join(", ")}</p>
              </div>
            ) : specLoading ? (
              <div className="h-full w-full animate-pulse bg-surface-muted" />
            ) : spectrum ? (
              <img
                src={`${apiBase}${spectrum.image_url}`}
                alt="Burst dynamic spectrum"
                className="h-full w-full object-contain"
              />
            ) : (
              <div className="flex h-full items-center justify-center text-xs text-slate-600">
                Select a burst to visualize its spectrum.
              </div>
            )}
          </div>

          {current && (
            <div className="mb-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs">
              <span className="font-mono text-slate-200">
                {current.start}–{current.end} UTC
              </span>
              <span className="rounded bg-accent-purple/20 px-2 py-0.5 text-accent-purple">
                {current.burst_type}
              </span>
              {spectrum && (
                <span className="text-slate-600">
                  {spectrum.station_used} · {spectrum.freq_min_mhz.toFixed(0)}–
                  {spectrum.freq_max_mhz.toFixed(0)} MHz
                  {spectrum.start_time ? ` · ${formatUtcShort(spectrum.start_time)}` : ""}
                </span>
              )}
              {spectrum && current.has_fits && (
                <DownloadLinks
                  pngUrl={`${apiBase}${spectrum.image_url}?download=1`}
                  fits={fitsUrl(date, spectrum.station_used, spectrum.fits_filename)}
                />
              )}
            </div>
          )}

          {/* scrollable list */}
          <div className="max-h-48 overflow-y-auto rounded border border-surface-border">
            {events.map((e) => (
              <button
                key={e.index}
                onClick={() => setIndex(e.index)}
                className={clsx(
                  "flex w-full items-center gap-2 border-b border-surface-border/50 px-2 py-1.5 text-left text-xs last:border-0",
                  e.index === index ? "bg-accent-blue/15" : "hover:bg-surface-muted"
                )}
              >
                <span className="w-24 font-mono text-slate-300">
                  {e.start}–{e.end}
                </span>
                <span className="w-16 text-accent-purple">{e.burst_type}</span>
                <span
                  className={clsx(
                    "flex-1 truncate",
                    e.station_used === "SRI-Lanka" ? "text-accent-cyan" : "text-slate-500"
                  )}
                >
                  {e.station_used ?? "—"}
                </span>
                {!e.has_fits && <span className="text-slate-700">no FITS</span>}
              </button>
            ))}
          </div>
        </>
      )}
    </section>
  );
}
