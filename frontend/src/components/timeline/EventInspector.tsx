"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { ExternalLink, Workflow } from "lucide-react";

import { api, apiUrl } from "@/lib/api";
import { alertLabel } from "@/lib/alerts";
import { formatUtcShort } from "@/lib/formatting";
import type { EventChain, SpaceWeatherEvent } from "@/lib/types";
import { ROLE_LABEL } from "@/components/timeline/StorylineList";
import { EmptyState } from "@/components/ui/EmptyState";
import { GoesXrsChart } from "@/components/charts/GoesXrsChart";
import { ProtonFluxChart } from "@/components/charts/ProtonFluxChart";
import { KpChart } from "@/components/charts/KpChart";
import { DstChart } from "@/components/charts/DstChart";

const iso = (ms: number) => new Date(ms).toISOString().slice(0, 19) + "Z";

function Panel({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-3">
      <h4 className="mb-2 text-[10px] uppercase tracking-wider text-slate-500">{title}</h4>
      {children}
    </div>
  );
}

/** e-CALLISTO dynamic spectrum covering the event time, with a station picker.
 *
 * For radio-burst events ``observers`` restricts the picker to the stations
 * that actually detected/observed the burst (in the event's own order — the
 * first-listed observer is usually the primary one), so only real burst
 * spectrograms are offered. Without ``observers`` (flares, storms, CMEs) any
 * archive station can be browsed for context. */
function RadioPanel({
  date,
  hhmm,
  observers,
}: {
  date: string;
  hhmm: string;
  observers?: string[];
}) {
  const { data: stations, isLoading: stationsLoading } = useSWR(
    ["timeline-radio-stations", date],
    () => api.radioArchiveStations(date)
  );
  const [station, setStation] = useState<string | null>(null);

  // Stations offered in the picker: the observers that have archive data (in
  // observer order), or every archive station when unrestricted.
  const options = useMemo(() => {
    if (!stations) return [];
    if (!observers?.length) return stations.stations.map((s) => s.id);
    const byId = new Map(stations.stations.map((s) => [s.id.trim().toUpperCase(), s.id]));
    return observers
      .map((o) => byId.get(o.trim().toUpperCase()))
      .filter((id): id is string => id != null);
  }, [observers, stations]);

  // A manually picked station only sticks while it's still offered (switching
  // from one burst to another resets to the new burst's primary observer).
  const active = (station && options.includes(station) ? station : null) ?? options[0] ?? null;

  const { data: spectrum, error, isLoading } = useSWR(
    active ? ["timeline-spectrum", date, active, hhmm] : null,
    () => api.radioArchiveSpectrumAt(date, active!, hhmm)
  );

  const title = observers?.length
    ? `Burst Spectrogram — ${hhmm} UTC · observing stations only`
    : `e-CALLISTO Spectrogram — ${hhmm} UTC`;

  return (
    <Panel title={title}>
      {options.length > 0 && (
        <select
          value={active ?? ""}
          onChange={(e) => setStation(e.target.value)}
          className="mb-2 w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300"
        >
          {options.map((id) => (
            <option key={id} value={id}>
              {id}
            </option>
          ))}
        </select>
      )}
      {stationsLoading || isLoading ? (
        <div className="h-40 animate-pulse rounded bg-surface-muted" />
      ) : options.length === 0 ? (
        <p className="py-8 text-center text-xs text-slate-600">
          {observers?.length
            ? "None of this burst's observing stations have archive data for this date"
            : "No stations with archive data for this date"}
        </p>
      ) : error ? (
        // Was folded into the "no spectrogram available" message, which made a
        // failed archive request look like a station that simply wasn't observing.
        <EmptyState
          tone="error"
          message="Could not load the spectrogram for this station/time."
          className="py-8"
        />
      ) : !spectrum ? (
        <EmptyState
          message="No spectrogram available for this station/time."
          className="py-8"
        />
      ) : (
        // eslint-disable-next-line @next/next/no-img-element -- backend-rendered PNG
        <img src={apiUrl(spectrum.image_url)} alt="dynamic spectrum" className="w-full rounded" />
      )}
    </Panel>
  );
}

/** Nearest solar imagery (SDO/SOHO browse archive) around the event time. */
function SolarImagesPanel({ date, hhmm }: { date: string; hhmm: string }) {
  const { data, isLoading } = useSWR(["timeline-solar-images", date, hhmm], () =>
    api.solarArchiveImages(date, false, hhmm)
  );
  const images = (data?.images ?? []).slice(0, 4);
  return (
    <Panel title={`Solar Imagery — nearest to ${hhmm} UTC`}>
      {isLoading ? (
        <div className="h-32 animate-pulse rounded bg-surface-muted" />
      ) : images.length === 0 ? (
        <p className="py-8 text-center text-xs text-slate-600">No imagery available</p>
      ) : (
        <div className="grid grid-cols-4 gap-2">
          {images.map((im) => (
            <figure key={im.id}>
              {/* eslint-disable-next-line @next/next/no-img-element -- archive browse image */}
              <img src={im.image_url} alt={im.label} className="w-full rounded" />
              <figcaption className="mt-1 truncate text-center text-[9px] text-slate-500">
                {im.label}
              </figcaption>
            </figure>
          ))}
        </div>
      )}
    </Panel>
  );
}

/** Station list from a model-burst description ("…: A, B, C (peak p=0.97)") —
 * fallback for events stored before the structured ``stations`` column. */
function stationsFromDescription(desc: string): string[] {
  const m = desc.match(/\):\s*(.+?)\s*\(peak p=/);
  return m ? m[1].split(",").map((s) => s.trim()).filter(Boolean) : [];
}

/**
 * Every instrument's view of one selected event: X-ray flux, radio
 * spectrogram, geomagnetic indices, and solar imagery around its time.
 * Radio-burst events restrict the spectrogram to their observing stations.
 */
/** The causal storyline the selected event belongs to: its ordered sequence as
 * clickable role pills, with the current event marked. */
function StorylineStrip({
  chain,
  currentId,
  onSelect,
}: {
  chain: EventChain;
  currentId: string;
  onSelect?: (e: SpaceWeatherEvent) => void;
}) {
  return (
    <div className="rounded-lg border border-accent-blue/40 bg-accent-blue/5 p-3">
      <div className="mb-2 flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-accent-blue">
        <Workflow className="h-3.5 w-3.5" /> Storyline
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {chain.events.map((e, i) => (
          <div key={e.id} className="flex items-center gap-1.5">
            {i > 0 && <span className="text-slate-600">→</span>}
            <button
              onClick={() => onSelect?.(e)}
              className={clsx(
                "rounded border px-2 py-1 text-[11px] transition-colors",
                e.id === currentId
                  ? "border-accent-blue bg-accent-blue/20 text-accent-blue"
                  : "border-surface-border text-slate-300 hover:bg-surface-muted"
              )}
            >
              {(ROLE_LABEL[chain.roles[e.id]] ?? chain.roles[e.id])}
              {e.severity ? ` · ${e.severity}` : ""}
            </button>
          </div>
        ))}
      </div>
      <p className="mt-2 text-[11px] leading-relaxed text-slate-500">{chain.summary}</p>
    </div>
  );
}

export function EventInspector({
  event,
  chain,
  onSelectEvent,
}: {
  event: SpaceWeatherEvent;
  chain?: EventChain | null;
  onSelectEvent?: (e: SpaceWeatherEvent) => void;
}) {
  const isRadioBurst = event.type === "radio_burst" || event.type === "official_radio_burst";
  const stations = event.stations.length
    ? event.stations
    : stationsFromDescription(event.description);
  const observers = isRadioBurst && stations.length ? stations : undefined;
  const w = useMemo(() => {
    const startMs = new Date(event.start_time).getTime();
    const anchorMs = new Date(
      event.peak_time ?? event.end_time ?? event.start_time
    ).getTime();
    const endMs = Math.min(
      Date.now(),
      new Date(event.end_time ?? event.start_time).getTime() + 3 * 3600_000
    );
    const anchor = new Date(anchorMs);
    return {
      date: anchor.toISOString().slice(0, 10),
      hhmm: anchor.toISOString().slice(11, 16),
      xrs: { start: iso(startMs - 3 * 3600_000), end: iso(Math.max(endMs, startMs + 3600_000)) },
      // Kp is 3-hourly / Dst hourly - a day of context either side.
      geo: { start: iso(startMs - 24 * 3600_000), end: iso(Math.min(Date.now(), startMs + 24 * 3600_000)) },
    };
  }, [event]);

  const { data: xrs, isLoading: xrsLoading } = useSWR(["timeline-xrs", w.xrs.start, w.xrs.end], () =>
    api.goesXrs(w.xrs.start, w.xrs.end)
  );
  const { data: proton, isLoading: protonLoading } = useSWR(
    event.type === "proton_event" ? ["timeline-proton", w.xrs.start, w.xrs.end] : null,
    () => api.goesProton(w.xrs.start, w.xrs.end)
  );
  const { data: kp, isLoading: kpLoading } = useSWR(["timeline-kp", w.geo.start, w.geo.end], () =>
    api.kp(w.geo.start, w.geo.end)
  );
  const { data: dst, isLoading: dstLoading } = useSWR(["timeline-dst", w.geo.start, w.geo.end], () =>
    api.dst(w.geo.start, w.geo.end)
  );

  return (
    <div className="space-y-3">
      {/* header */}
      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="flex flex-wrap items-center gap-3">
          <span className="rounded border border-surface-border bg-surface-muted px-2 py-0.5 text-xs font-bold text-slate-200">
            {alertLabel(event.type)}
            {event.severity ? ` · ${event.severity}` : ""}
          </span>
          <span className="text-xs text-slate-500">
            {formatUtcShort(event.start_time)}
            {event.end_time ? ` → ${formatUtcShort(event.end_time)}` : " → ongoing"}
          </span>
          {event.source_url && (
            <a
              href={event.source_url}
              target="_blank"
              rel="noreferrer"
              className="flex items-center gap-1 text-xs text-accent-blue hover:underline"
            >
              source <ExternalLink className="h-3 w-3" />
            </a>
          )}
        </div>
        <p className="mt-2 text-sm text-slate-300">{event.description}</p>
      </div>

      {/* storyline this event belongs to (if any) */}
      {chain && chain.events.length > 1 && (
        <StorylineStrip chain={chain} currentId={event.id} onSelect={onSelectEvent} />
      )}

      {/* instrument panels */}
      <div className="grid grid-cols-1 gap-3 lg:grid-cols-2">
        <Panel title="GOES X-ray Flux">
          <div className="h-56">
            <GoesXrsChart data={xrs?.data ?? []} loading={xrsLoading} />
          </div>
        </Panel>
        <RadioPanel date={w.date} hhmm={w.hhmm} observers={observers} />
        {event.type === "proton_event" && (
          <Panel title="GOES Proton Flux">
            <div className="h-56">
              <ProtonFluxChart data={proton?.data ?? []} loading={protonLoading} />
            </div>
          </Panel>
        )}
        <Panel title="Kp Index (±24 h)">
          <div className="h-56">
            <KpChart data={kp ?? []} loading={kpLoading} />
          </div>
        </Panel>
        <Panel title="Dst Index (±24 h)">
          <div className="h-56">
            <DstChart data={dst ?? []} loading={dstLoading} />
          </div>
        </Panel>
        <div className="lg:col-span-2">
          <SolarImagesPanel date={w.date} hhmm={w.hhmm} />
        </div>
      </div>
    </div>
  );
}
