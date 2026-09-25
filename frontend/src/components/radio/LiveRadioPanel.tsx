"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { Pin, X } from "lucide-react";
import { API_BASE, api } from "@/lib/api";
import { formatUtcShort } from "@/lib/formatting";
import { EmptyState } from "@/components/ui/EmptyState";

const apiBase = API_BASE;

const DEFAULT_STATION = "SRI-Lanka";
const LS_STATION = "live-radio-station";
const LS_FOCUS = "live-radio-focus";
const LS_PINNED = "overview-pinned-burst";

const selectCls =
  "rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue disabled:opacity-40";

/** A burst pinned into the panel, persisted so it survives a window refresh. */
interface PinnedBurst {
  date: string; // burst-list date the index refers to
  index: number; // index within that day's burst list
  start: string; // HH:MM UTC (label)
  end: string; // HH:MM UTC (label)
  burst_type: string;
  station_used: string | null;
}

/**
 * Homepage dynamic-spectrum panel. By default it shows a live e-CALLISTO spectrum
 * for a chosen station + focus code (remembered across visits). The user can also
 * PIN a burst from the latest burst list: while a burst is pinned the panel shows
 * that burst's archived spectrum instead of the live feed, and the pin is
 * remembered across window refreshes.
 */
export function LiveRadioPanel({
  heightClass = "min-h-[600px] flex-1",
}: {
  heightClass?: string;
}) {
  const { data: stationsResp } = useSWR("radio-live-stations", api.radioLiveStations, {
    refreshInterval: 300000, // 5 min
  });
  const stations = stationsResp?.stations ?? [];

  // Selection is restored from localStorage on mount (default: Sri Lanka).
  const [station, setStation] = usePersisted(LS_STATION, DEFAULT_STATION);
  const [focus, setFocus] = usePersisted(LS_FOCUS, "");
  // Pinned burst (persisted). When set, the panel shows it instead of live data.
  const [pinned, setPinned] = usePinnedBurst();

  const current = stations.find((s) => s.id === station);
  const focuses = current?.focuses ?? [];

  // Latest burst list — the source of pinnable bursts (only those with FITS).
  const { data: burstsResp } = useSWR("bursts-latest", api.burstsLatest, {
    refreshInterval: 600000, // 10 min
  });
  const burstEvents = useMemo(
    () => (burstsResp?.events ?? []).filter((e) => e.has_fits),
    [burstsResp]
  );

  // Reconcile the station/focus selection once stations load (or when the station
  // changes): fall back to a station that actually has data, and a valid focus.
  useEffect(() => {
    if (!stations.length) return;
    const ids = stations.map((s) => s.id);
    if (!station || !ids.includes(station)) {
      setStation(ids.includes(DEFAULT_STATION) ? DEFAULT_STATION : ids[0]);
      return; // focus reconciles on the next run after station updates
    }
    const fs = stations.find((s) => s.id === station)?.focuses ?? [];
    if (fs.length) {
      if (!focus || !fs.includes(focus)) setFocus(fs[0]);
    } else if (focus) {
      setFocus("");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stationsResp, station]);

  // Live spectrum — fetched only when no burst is pinned.
  const {
    data: live,
    isLoading: liveLoading,
    error: liveError,
  } = useSWR(
    !pinned && station ? ["radio-live-spectrum", station, focus] : null,
    () => api.radioLiveSpectrum(station, focus || undefined),
    { refreshInterval: 300000, keepPreviousData: true }
  );

  // Pinned burst's archived spectrum — fetched only while a burst is pinned.
  const {
    data: pinnedSpec,
    isLoading: pinnedLoading,
    error: pinnedError,
  } = useSWR(
    pinned ? ["pinned-burst-spectrum", pinned.date, pinned.index] : null,
    () => api.radioBurstSpectrumByDate(pinned!.date, pinned!.index),
    { revalidateOnFocus: false, keepPreviousData: true }
  );

  function onStationChange(id: string) {
    setStation(id);
    const fs = stations.find((s) => s.id === id)?.focuses ?? [];
    setFocus(fs[0] ?? "");
  }

  function onPickBurst(value: string) {
    if (value === "") return;
    const ev = burstEvents.find((e) => e.index === Number(value));
    if (!ev) return;
    setPinned({
      date: ev.date,
      index: ev.index,
      start: ev.start,
      end: ev.end,
      burst_type: ev.burst_type,
      station_used: ev.station_used,
    });
  }

  // Picker options — the latest day's FITS-backed bursts, plus the pinned burst
  // itself if it isn't in that list (e.g. it was pinned on an earlier day).
  const pickerOptions = useMemo(() => {
    const label = (start: string, type: string, st: string | null) =>
      `${start} · ${type}${st ? ` · ${st}` : ""}`;
    const opts = burstEvents.map((e) => ({
      index: e.index,
      label: label(e.start, e.burst_type, e.station_used),
    }));
    if (pinned && !opts.some((o) => o.index === pinned.index)) {
      opts.unshift({
        index: pinned.index,
        label: label(pinned.start, pinned.burst_type, pinned.station_used),
      });
    }
    return opts;
  }, [burstEvents, pinned]);

  // What to render (image + status) depends on the mode.
  const spec = pinned ? pinnedSpec : live;
  const loading = pinned ? pinnedLoading : liveLoading;
  const error = pinned ? pinnedError : liveError;

  return (
    <div
      className={clsx(
        "flex flex-1 flex-col rounded-lg border bg-surface-card p-4",
        pinned ? "border-accent-blue/40" : "border-accent-cyan/30"
      )}
    >
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2
          className={clsx(
            "flex items-center gap-2 text-sm font-semibold",
            pinned ? "text-accent-blue" : "text-accent-cyan"
          )}
        >
          {pinned ? (
            <>
              <Pin className="h-3.5 w-3.5 fill-current" />
              Pinned Burst
            </>
          ) : (
            <>
              <span className="h-2 w-2 animate-pulse rounded-full bg-accent-cyan" />
              Live Dynamic Spectrum
            </>
          )}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          {!pinned && (
            <>
              <select
                aria-label="Station"
                value={station}
                onChange={(e) => onStationChange(e.target.value)}
                disabled={!stations.length}
                className={selectCls}
              >
                {!stations.length && <option value="">— Loading… —</option>}
                {stations.map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.id}
                  </option>
                ))}
              </select>
              <select
                aria-label="Focus code"
                value={focus}
                onChange={(e) => setFocus(e.target.value)}
                disabled={focuses.length <= 1}
                className={selectCls}
              >
                {!focuses.length && <option value="">—</option>}
                {focuses.map((f) => (
                  <option key={f} value={f}>
                    Focus {f}
                  </option>
                ))}
              </select>
            </>
          )}

          {/* Pin-a-burst picker — choosing a burst pins it; selecting a different
              one re-pins. Available in both modes so the pin can be changed. */}
          <select
            aria-label="Pin a burst"
            value={pinned ? String(pinned.index) : ""}
            onChange={(e) => onPickBurst(e.target.value)}
            disabled={!pickerOptions.length && !pinned}
            className={selectCls}
            title="Pin a burst to keep it shown on the overview (persists across refresh)"
          >
            <option value="">
              📌 {pickerOptions.length ? "Pin a burst…" : "No bursts to pin"}
            </option>
            {pickerOptions.map((o) => (
              <option key={o.index} value={o.index}>
                {o.label}
              </option>
            ))}
          </select>

          {pinned && (
            <button
              onClick={() => setPinned(null)}
              className="flex items-center gap-1 rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-400 transition-colors hover:text-slate-200"
              title="Unpin — return to the live spectrum"
            >
              <X className="h-3.5 w-3.5" /> Unpin
            </button>
          )}
        </div>
      </div>

      {/* Metadata line */}
      {pinned ? (
        <div className="mb-2 text-xs text-slate-500">
          <span className="font-mono text-slate-300">
            {pinned.start}–{pinned.end} UTC
          </span>{" "}
          · {pinned.burst_type}
          {pinned.station_used ? ` · ${pinned.station_used}` : ""}
          {pinnedSpec && (
            <>
              {" "}
              · {pinnedSpec.freq_min_mhz.toFixed(0)}–{pinnedSpec.freq_max_mhz.toFixed(0)} MHz
            </>
          )}
        </div>
      ) : live ? (
        <div className="mb-2 text-xs text-slate-500">
          {live.start_time ? formatUtcShort(live.start_time) : "—"} ·{" "}
          {live.freq_min_mhz.toFixed(0)}–{live.freq_max_mhz.toFixed(0)} MHz
        </div>
      ) : null}

      <div className={heightClass}>
        {loading && !spec ? (
          <div className="h-full w-full animate-pulse rounded bg-surface-muted" />
        ) : error ? (
          // Split from the empty case below: a failed request and a station with
          // nothing to show are different facts and must not share a message.
          <EmptyState
            tone="error"
            message={
              pinned
                ? "Could not load the pinned burst spectrum."
                : `Could not reach the feed for ${station || "this station"}.`
            }
          />
        ) : !spec ? (
          <EmptyState
            message={
              pinned
                ? "No spectrum available for the pinned burst."
                : `No recent data for ${station || "this station"}.`
            }
          />
        ) : (
          <img
            src={`${apiBase}${spec.image_url}`}
            alt={
              pinned
                ? `Pinned burst ${pinned.start}–${pinned.end} dynamic spectrum`
                : `${station} dynamic spectrum`
            }
            className="h-full w-full rounded object-contain"
          />
        )}
      </div>
    </div>
  );
}

/** useState mirrored to localStorage (restores the stored value on mount). */
function usePersisted(key: string, fallback: string): [string, (v: string) => void] {
  const [value, setValue] = useState(fallback);
  useEffect(() => {
    const stored = localStorage.getItem(key);
    if (stored !== null) setValue(stored);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const set = (v: string) => {
    setValue(v);
    try {
      localStorage.setItem(key, v);
    } catch {
      /* ignore quota / unavailable storage */
    }
  };
  return [value, set];
}

/** Pinned-burst state mirrored to localStorage as JSON (restored on mount). */
function usePinnedBurst(): [PinnedBurst | null, (v: PinnedBurst | null) => void] {
  const [value, setValue] = useState<PinnedBurst | null>(null);
  useEffect(() => {
    try {
      const raw = localStorage.getItem(LS_PINNED);
      if (raw) setValue(JSON.parse(raw) as PinnedBurst);
    } catch {
      /* ignore malformed / unavailable storage */
    }
  }, []);
  const set = (v: PinnedBurst | null) => {
    setValue(v);
    try {
      if (v) localStorage.setItem(LS_PINNED, JSON.stringify(v));
      else localStorage.removeItem(LS_PINNED);
    } catch {
      /* ignore quota / unavailable storage */
    }
  };
  return [value, set];
}
