"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { formatUtcShort } from "@/lib/formatting";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const DEFAULT_STATION = "SRI-Lanka";
const LS_STATION = "live-radio-station";
const LS_FOCUS = "live-radio-focus";

const selectCls =
  "rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue disabled:opacity-40";

/**
 * Homepage live dynamic-spectrum panel. The user picks an e-CALLISTO station and
 * focus code (from those with data on the most recent day); the panel shows that
 * station's latest available spectrum and remembers the choice across visits.
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

  const current = stations.find((s) => s.id === station);
  const focuses = current?.focuses ?? [];

  // Reconcile the selection once stations load (or when the station changes):
  // fall back to a station that actually has data, and a valid focus for it.
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

  const {
    data,
    isLoading,
    error,
  } = useSWR(
    station ? ["radio-live-spectrum", station, focus] : null,
    () => api.radioLiveSpectrum(station, focus || undefined),
    { refreshInterval: 300000, keepPreviousData: true }
  );

  function onStationChange(id: string) {
    setStation(id);
    const fs = stations.find((s) => s.id === id)?.focuses ?? [];
    setFocus(fs[0] ?? "");
  }

  return (
    <div className="flex flex-1 flex-col rounded-lg border border-accent-cyan/30 bg-surface-card p-4">
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-semibold text-accent-cyan">
          <span className="h-2 w-2 animate-pulse rounded-full bg-accent-cyan" />
          Live Dynamic Spectrum
        </h2>
        <div className="flex items-center gap-2">
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
        </div>
      </div>

      {data && (
        <div className="mb-2 text-xs text-slate-500">
          {data.start_time ? formatUtcShort(data.start_time) : "—"} ·{" "}
          {data.freq_min_mhz.toFixed(0)}–{data.freq_max_mhz.toFixed(0)} MHz
        </div>
      )}

      <div className={heightClass}>
        {isLoading && !data ? (
          <div className="h-full w-full animate-pulse rounded bg-surface-muted" />
        ) : error || !data ? (
          <div className="flex h-full items-center justify-center text-center text-xs text-slate-600">
            No recent data for {station || "this station"}
          </div>
        ) : (
          <img
            src={`${apiBase}${data.image_url}`}
            alt={`${station} dynamic spectrum`}
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
