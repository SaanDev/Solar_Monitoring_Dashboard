"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import {
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  HelpCircle,
  Maximize2,
  ZoomIn,
  ZoomOut,
} from "lucide-react";

import { api } from "@/lib/api";
import { windowFor } from "@/lib/formatting";
import type { SpaceWeatherEvent } from "@/lib/types";
import {
  BURST_OTHER,
  BURST_TYPE_LEGEND,
  FLARE_CLASS_LEGEND,
  HorizontalTimeline,
  LANES,
} from "@/components/timeline/HorizontalTimeline";
import { EventInspector } from "@/components/timeline/EventInspector";
import { StorylineList } from "@/components/timeline/StorylineList";
import { RangeSelector, type RangeOption } from "@/components/charts/RangeSelector";

const RANGES: readonly RangeOption[] = [
  { key: "1d", label: "1D", hours: 24 },
  { key: "3d", label: "3D", hours: 72 },
  { key: "7d", label: "7D", hours: 168 },
  { key: "30d", label: "30D", hours: 720 },
];

// Zoom limits: never wider than the fetched range, never narrower than this.
const MIN_VIEW_SPAN_MS = 30 * 60 * 1000;

/** "6 h" / "2.5 d" — human span for the zoom indicator. */
function formatSpan(ms: number): string {
  const h = ms / 3600_000;
  if (h < 48) return `${h < 10 ? h.toFixed(1).replace(/\.0$/, "") : Math.round(h)} h`;
  const d = h / 24;
  return `${d < 10 ? d.toFixed(1).replace(/\.0$/, "") : Math.round(d)} d`;
}

function HelpPanel() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-lg border border-surface-border bg-surface-card">
      <button
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-4 py-2.5 text-xs text-slate-400 hover:text-slate-200"
      >
        <HelpCircle className="h-3.5 w-3.5 shrink-0 text-accent-blue" />
        <span className="flex-1 text-left font-medium">How to use this page</span>
        <ChevronDown className={clsx("h-3.5 w-3.5 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-2 border-t border-surface-border px-4 py-3 text-xs leading-relaxed text-slate-400">
          <p>
            The timeline correlates every event the dashboard detects across its
            instruments. Each row is one source; time runs left to right over the
            selected window (<span className="text-slate-300">1D–30D</span>, top right).
            Each colored block is one event — events that are close together stack
            onto separate sub-rows, so every flare stays individually visible. Hover
            for a summary, click to open the full cross-instrument view below.
          </p>
          <p>
            <span className="text-slate-300">Zooming:</span> scroll the mouse wheel
            over the lanes to zoom around the cursor, or use the{" "}
            <span className="text-slate-300">+ / −</span> buttons; ‹ › pan the zoomed
            view and the fit button returns to the full window. The time axis
            re-labels itself as you zoom.
          </p>
          <ul className="list-disc space-y-1 pl-5">
            <li>
              <span className="text-slate-300">Flares</span> — GOES X-ray events,
              colored by class:{" "}
              <span className="text-slate-400">A</span>/<span className="text-sky-400">B</span>/
              <span className="text-amber-400">C</span>/<span className="text-orange-500">M</span>/
              <span className="text-red-500">X</span> (quiet → extreme), one block per flare.
            </li>
            <li>
              <span className="text-accent-yellow">Radio · Official</span> — bursts from
              the published e-CALLISTO burst list (human-catalogued;{" "}
              <em>usually 1–2 days behind real time</em>), colored by burst type — e.g.{" "}
              <span className="text-rose-500">Type II</span> (shock/CME-driven),{" "}
              <span className="text-lime-400">Type III</span> (electron beams; the most
              common), <span className="text-violet-400">Type IV</span> (post-flare
              continuum).
            </li>
            <li>
              <span className="text-accent-green">Radio · Model</span> — this
              dashboard&apos;s ML detections, only when corroborated by multiple
              stations (the same events that raise alerts). Blocks use the{" "}
              <em>same burst-type colors as the official lane</em>, so a burst both
              agree on is the same color in both rows — compare them vertically to
              see where the model and the catalog line up. Bursts the type
              classifier could not label keep the lane&apos;s plain{" "}
              <span className="text-accent-green">green</span>: detected, type
              undetermined. Types here are estimates, not catalogued fact.
            </li>
            <li>
              <span className="text-accent-red">Protons</span> — solar radiation storms
              (&ge;10 MeV flux, NOAA S-scale).
            </li>
            <li>
              <span className="text-accent-purple">Geomag</span> — Kp/Dst storms and
              solar-wind-coupling <em>predictions</em>.
            </li>
            <li>
              <span className="text-accent-cyan">CME</span> — Earth-directed CMEs from
              NASA DONKI, spanning launch → predicted arrival.
            </li>
          </ul>
          <p>
            A block touching the right edge is still in progress. Selecting an event
            loads: the GOES X-ray curve around it, an e-CALLISTO spectrogram at its
            time, Kp/Dst context (±24 h), and the nearest solar imagery. For radio
            bursts the spectrogram picker offers <em>only the stations that observed
            that burst</em>; for other event types you can browse any station. Use the{" "}
            <em>source</em> link for the upstream catalog entry.
          </p>
        </div>
      )}
    </div>
  );
}

function LegendSwatch({ dot, label }: { dot: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={clsx("h-2 w-2 rounded-sm", dot)} />
      {label}
    </span>
  );
}

export function TimelineClient() {
  const [range, setRange] = useState("3d");
  const hours = RANGES.find((r) => r.key === range)!.hours;
  // Freeze the window per range selection so blocks don't drift between polls.
  const { start, end } = useMemo(() => windowFor(hours), [hours]);
  const [selected, setSelected] = useState<SpaceWeatherEvent | null>(null);
  // Chain currently traced on the timeline: a hovered storyline card wins,
  // otherwise the selected event's own chain.
  const [hoverChainId, setHoverChainId] = useState<string | null>(null);

  const startMs = new Date(start).getTime();
  const endMs = new Date(end).getTime();

  // Zoomed view window inside [startMs, endMs]; null = fit the whole range.
  const [view, setView] = useState<{ s: number; e: number } | null>(null);
  useEffect(() => setView(null), [range]);
  const viewStart = view?.s ?? startMs;
  const viewEnd = view?.e ?? endMs;
  const viewSpan = viewEnd - viewStart;

  /** Zoom keeping the time under `fraction` (0..1 across the strip) fixed. */
  const zoomAt = (fraction: number, factor: number) => {
    const newSpan = Math.min(endMs - startMs, Math.max(MIN_VIEW_SPAN_MS, viewSpan * factor));
    if (newSpan >= endMs - startMs) {
      setView(null);
      return;
    }
    const focus = viewStart + viewSpan * fraction;
    let s = focus - newSpan * fraction;
    let e = s + newSpan;
    if (s < startMs) {
      e += startMs - s;
      s = startMs;
    }
    if (e > endMs) {
      s -= e - endMs;
      e = endMs;
    }
    setView({ s: Math.max(startMs, s), e: Math.min(endMs, e) });
  };

  const pan = (dir: -1 | 1) => {
    if (!view) return;
    const shift = dir * viewSpan * 0.5;
    let s = view.s + shift;
    let e = view.e + shift;
    if (s < startMs) {
      e += startMs - s;
      s = startMs;
    }
    if (e > endMs) {
      s -= e - endMs;
      e = endMs;
    }
    setView({ s, e });
  };

  const { data: events, isLoading } = useSWR(
    ["timeline-events", range],
    () => api.events(start, end),
    { refreshInterval: 120000, keepPreviousData: true }
  );

  // Official e-CALLISTO list over the same window (dates are inclusive).
  const { data: official } = useSWR(
    ["timeline-official-bursts", range],
    () => api.officialBurstsRange(start.slice(0, 10), end.slice(0, 10)),
    { refreshInterval: 600000, keepPreviousData: true }
  );

  // Official entries become timeline pseudo-events; their observing stations
  // ride on the event so the inspector restricts spectrograms to them.
  //
  // Ids have to be unique — they are React keys, the block-ref map key, and what
  // selection/chain highlighting compare on, so a collision makes one block
  // highlight another. Start time alone is not enough: the catalog lists several
  // bursts per minute, and it even contains exact duplicates (same time, type,
  // end and stations), so *no* combination of fields is unique either. Hence a
  // per-group occurrence counter. It is scoped to the (time, type) group rather
  // than being a plain array index so that a burst published later elsewhere in
  // the window doesn't renumber everything after it and move the selection.
  const officialEvents = useMemo<SpaceWeatherEvent[]>(() => {
    const seen = new Map<string, number>();
    return (official?.events ?? []).map((b) => {
      const base = `official_radio_burst:${b.start_time}:${b.burst_type || "?"}`;
      const n = seen.get(base) ?? 0;
      seen.set(base, n + 1);
      return {
        id: n === 0 ? base : `${base}#${n}`,
        type: "official_radio_burst",
        severity: b.burst_type ? `Type ${b.burst_type}` : null,
        start_time: b.start_time,
        end_time: b.end_time,
        peak_time: null,
        peak_value: null,
        description:
          `Official e-CALLISTO burst list: Type ${b.burst_type || "?"} radio burst` +
          (b.stations.length ? ` — observed by ${b.stations.join(", ")}` : ""),
        stations: b.stations,
        related_event_ids: [],
        source_url: "https://www.e-callisto.org/",
      };
    });
  }, [official]);

  const all = useMemo(() => [...(events ?? []), ...officialEvents], [events, officialEvents]);

  // Causal storylines over the same window (flare → CME → burst → proton → storm).
  const { data: chains } = useSWR(
    ["timeline-chains", range],
    () => api.eventChains(start, end),
    { refreshInterval: 120000, keepPreviousData: true }
  );

  const activeChainId = hoverChainId ?? selected?.chain_id ?? null;
  const activeChain = useMemo(
    () => chains?.find((c) => c.chain_id === activeChainId) ?? null,
    [chains, activeChainId]
  );
  const highlightIds = useMemo(
    () => (activeChain ? new Set(activeChain.event_ids) : null),
    [activeChain]
  );
  const selectedChain = useMemo(
    () => chains?.find((c) => c.chain_id === selected?.chain_id) ?? null,
    [chains, selected]
  );

  const toolBtn =
    "rounded border border-surface-border p-1 text-slate-400 transition-colors " +
    "hover:bg-surface-muted hover:text-slate-200 disabled:cursor-not-allowed disabled:opacity-40";

  return (
    <div className="space-y-4">
      <HelpPanel />

      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <div>
            <h2 className="text-xs uppercase tracking-wider text-slate-500">
              All Instruments — Event Timeline
            </h2>
            <p className="mt-0.5 text-[11px] text-slate-600">
              {isLoading ? "Loading…" : `${all.length} events (${officialEvents.length} from the official burst list)`}{" "}
              · click any block to open every instrument&apos;s view of that moment
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {/* zoom / pan toolbar */}
            <div className="flex items-center gap-1">
              <button
                onClick={() => pan(-1)}
                disabled={!view || viewStart <= startMs}
                title="Pan left"
                className={toolBtn}
              >
                <ChevronLeft className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => zoomAt(0.5, 0.5)}
                disabled={viewSpan <= MIN_VIEW_SPAN_MS}
                title="Zoom in (or scroll on the lanes)"
                className={toolBtn}
              >
                <ZoomIn className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => zoomAt(0.5, 2)}
                disabled={!view}
                title="Zoom out"
                className={toolBtn}
              >
                <ZoomOut className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => setView(null)}
                disabled={!view}
                title="Fit the whole window"
                className={toolBtn}
              >
                <Maximize2 className="h-3.5 w-3.5" />
              </button>
              <button
                onClick={() => pan(1)}
                disabled={!view || viewEnd >= endMs}
                title="Pan right"
                className={toolBtn}
              >
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
              <span className="ml-1 font-mono text-[10px] text-slate-500">
                {formatSpan(viewSpan)}
                {view && <span className="text-slate-600"> / {formatSpan(endMs - startMs)}</span>}
              </span>
            </div>
            <RangeSelector options={RANGES} value={range} onChange={setRange} />
          </div>
        </div>

        {isLoading ? (
          <div className="h-40 animate-pulse rounded bg-surface-muted" />
        ) : (
          <HorizontalTimeline
            events={all}
            startMs={viewStart}
            endMs={viewEnd}
            selectedId={selected?.id ?? null}
            onSelect={setSelected}
            onZoomAt={zoomAt}
            highlightIds={highlightIds}
            chainOrder={activeChain?.event_ids ?? null}
          />
        )}

        {/* color references */}
        <div className="mt-2 space-y-1 text-[10px] text-slate-500">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="w-24 shrink-0 text-right uppercase tracking-wider text-slate-600">
              Flare class
            </span>
            {FLARE_CLASS_LEGEND.map((c) => (
              <LegendSwatch key={c.key} dot={c.dot} label={c.label} />
            ))}
            <span className="text-slate-600">(quiet → extreme)</span>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="w-24 shrink-0 text-right uppercase tracking-wider text-slate-600">
              Burst type
            </span>
            {BURST_TYPE_LEGEND.map((c) => (
              <LegendSwatch key={c.key} dot={c.dot} label={c.label} />
            ))}
            <LegendSwatch dot={BURST_OTHER.dot} label="other" />
            <span className="text-slate-600">
              (both radio lanes · an untyped model burst stays lane-green)
            </span>
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="w-24 shrink-0 text-right uppercase tracking-wider text-slate-600">
              Lanes
            </span>
            {LANES.filter((l) => !["xray_flare", "official_radio"].includes(l.key)).map((l) => (
              <LegendSwatch key={l.key} dot={l.dot} label={l.label} />
            ))}
            <span className="text-slate-600">
              · nearby events stack into rows · a block touching the right edge is ongoing ·
              scroll to zoom
            </span>
          </div>
        </div>
      </div>

      {chains && chains.length > 0 && (
        <StorylineList
          chains={chains}
          activeId={activeChainId}
          onHover={setHoverChainId}
          onOpen={setSelected}
        />
      )}

      {selected ? (
        <EventInspector event={selected} chain={selectedChain} onSelectEvent={setSelected} />
      ) : (
        <div className="rounded-lg border border-dashed border-surface-border p-8 text-center text-xs text-slate-600">
          Select an event above to see the GOES X-ray curve, radio spectrogram,
          geomagnetic indices, and solar imagery at that moment.
        </div>
      )}
    </div>
  );
}
