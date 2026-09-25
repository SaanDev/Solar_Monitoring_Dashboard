"use client";

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { clsx } from "clsx";

import type { SpaceWeatherEvent } from "@/lib/types";

// ── Color taxonomy ───────────────────────────────────────────────────────────
// Blocks are colored by *what* the event is, not just its lane: flares by GOES
// class, radio bursts by their type. Both radio lanes share one type palette, so
// a burst the model and the catalog agree on is the same color in both rows and
// the comparison can be made at a glance. All classes are full literal strings
// (Tailwind's content scan needs them).

interface BlockColor {
  key: string;
  label: string;
  dot: string;
  block: string;
  selected: string;
}

export const FLARE_CLASS_LEGEND: BlockColor[] = [
  { key: "A", label: "A", dot: "bg-slate-400", block: "bg-slate-400/70 hover:bg-slate-300", selected: "bg-slate-300 ring-1 ring-white/80" },
  { key: "B", label: "B", dot: "bg-sky-400", block: "bg-sky-400/70 hover:bg-sky-300", selected: "bg-sky-300 ring-1 ring-white/80" },
  { key: "C", label: "C", dot: "bg-amber-400", block: "bg-amber-400/70 hover:bg-amber-300", selected: "bg-amber-300 ring-1 ring-white/80" },
  { key: "M", label: "M", dot: "bg-orange-500", block: "bg-orange-500/70 hover:bg-orange-400", selected: "bg-orange-400 ring-1 ring-white/80" },
  { key: "X", label: "X", dot: "bg-red-500", block: "bg-red-500/70 hover:bg-red-400", selected: "bg-red-400 ring-1 ring-white/80" },
];

export const BURST_TYPE_LEGEND: BlockColor[] = [
  { key: "I", label: "Type I", dot: "bg-stone-400", block: "bg-stone-400/70 hover:bg-stone-300", selected: "bg-stone-300 ring-1 ring-white/80" },
  { key: "II", label: "Type II", dot: "bg-rose-500", block: "bg-rose-500/70 hover:bg-rose-400", selected: "bg-rose-400 ring-1 ring-white/80" },
  { key: "III", label: "Type III", dot: "bg-lime-400", block: "bg-lime-400/70 hover:bg-lime-300", selected: "bg-lime-300 ring-1 ring-white/80" },
  { key: "IV", label: "Type IV", dot: "bg-violet-400", block: "bg-violet-400/70 hover:bg-violet-300", selected: "bg-violet-300 ring-1 ring-white/80" },
  { key: "V", label: "Type V", dot: "bg-sky-400", block: "bg-sky-400/70 hover:bg-sky-300", selected: "bg-sky-300 ring-1 ring-white/80" },
  { key: "CTM", label: "CTM", dot: "bg-cyan-400", block: "bg-cyan-400/70 hover:bg-cyan-300", selected: "bg-cyan-300 ring-1 ring-white/80" },
  { key: "RBR", label: "RBR", dot: "bg-amber-400", block: "bg-amber-400/70 hover:bg-amber-300", selected: "bg-amber-300 ring-1 ring-white/80" },
];

export const BURST_OTHER: BlockColor = {
  key: "other",
  label: "other",
  dot: "bg-yellow-600",
  block: "bg-yellow-600/70 hover:bg-yellow-500",
  selected: "bg-yellow-500 ring-1 ring-white/80",
};

const _FLARE_BY_KEY = new Map(FLARE_CLASS_LEGEND.map((c) => [c.key, c]));
const _BURST_BY_KEY = new Map(BURST_TYPE_LEGEND.map((c) => [c.key, c]));

/** Base burst type from a label like "Type III/2", "IIIGG/3", "CTM/1" or "Other".
 *
 * Handles both sources: the official list's catalog codes and the model's class
 * names, which is why both radio lanes can share one palette.
 *
 * e-CALLISTO codes put the Roman numeral first and append qualifiers — `IIIG`
 * and `IIIGG` are grouped Type III bursts, not separate types. So the Roman
 * numeral is matched on its own first; taking every leading letter instead would
 * bucket those (65 of ~360 Type III entries in a typical month) as "other" and
 * break the vertical comparison against the model lane. Non-numeral codes like
 * CTM and RBR still fall through to the whole-token match. */
function burstBaseType(label: string | null | undefined): string | null {
  if (!label) return null;
  const rest = label.replace(/^Type\s+/i, "");
  const roman = rest.match(/^[IVX]+/i);
  if (roman) return roman[0].toUpperCase();
  const alpha = rest.match(/^[A-Z]+/i);
  return alpha ? alpha[0].toUpperCase() : null;
}

/** Palette entry for a burst type; unrecognised named types fall to "other". */
function burstColor(label: string | null | undefined): BlockColor {
  const base = burstBaseType(label);
  return (base && _BURST_BY_KEY.get(base)) || BURST_OTHER;
}

// ── Lanes ────────────────────────────────────────────────────────────────────

export interface TimelineLane {
  key: string;
  label: string;
  dot: string;
  block: string;
  selected: string;
  match: (type: string) => boolean;
}

export const LANES: TimelineLane[] = [
  {
    key: "xray_flare",
    label: "Flares",
    dot: "bg-accent-orange",
    block: "bg-accent-orange/60 hover:bg-accent-orange",
    selected: "bg-accent-orange ring-1 ring-white/70",
    match: (t) => t === "xray_flare",
  },
  {
    key: "official_radio",
    label: "Radio · Official",
    dot: "bg-accent-yellow",
    block: "bg-accent-yellow/60 hover:bg-accent-yellow",
    selected: "bg-accent-yellow ring-1 ring-white/70",
    match: (t) => t === "official_radio_burst",
  },
  {
    key: "model_radio",
    label: "Radio · Model",
    dot: "bg-accent-green",
    block: "bg-accent-green/60 hover:bg-accent-green",
    selected: "bg-accent-green ring-1 ring-white/70",
    match: (t) => t === "radio_burst",
  },
  {
    key: "proton_event",
    label: "Protons",
    dot: "bg-accent-red",
    block: "bg-accent-red/60 hover:bg-accent-red",
    selected: "bg-accent-red ring-1 ring-white/70",
    match: (t) => t === "proton_event",
  },
  {
    key: "geomagnetic",
    label: "Geomag",
    dot: "bg-accent-purple",
    block: "bg-accent-purple/60 hover:bg-accent-purple",
    selected: "bg-accent-purple ring-1 ring-white/70",
    match: (t) => t.startsWith("geomagnetic_storm"),
  },
  {
    key: "cme",
    label: "CME",
    dot: "bg-accent-cyan",
    block: "bg-accent-cyan/60 hover:bg-accent-cyan",
    selected: "bg-accent-cyan ring-1 ring-white/70",
    match: (t) => t === "cme",
  },
];

/** Block colors for one event: flare class / burst type override the lane. */
function colorsFor(lane: TimelineLane, e: SpaceWeatherEvent): { block: string; selected: string } {
  if (e.type === "xray_flare" && e.severity) {
    const c = _FLARE_BY_KEY.get(e.severity[0].toUpperCase());
    if (c) return c;
  }
  // Official bursts carry their catalog code in `severity`.
  if (e.type === "official_radio_burst") return burstColor(e.severity);
  // Model bursts carry a structured `burst_type` — `severity` is the alert level
  // here, not a type. An untyped burst keeps the lane's neutral color: the model
  // detected it but found nothing it could classify, and inventing a color for
  // that would read as a confident type it never assigned.
  if (e.type === "radio_burst" && e.burst_type) return burstColor(e.burst_type);
  return lane;
}

// ── Layout ───────────────────────────────────────────────────────────────────
// Sub-row layout: blocks that would overlap (or merge visually) are stacked
// onto separate rows, so every event stays individually visible, hoverable
// and clickable — a dense run of flares never fuses into "one flare".

const MIN_WIDTH = 0.5; // % — keep short events (minutes) visible at long zooms
const GAP = 0.25;      // % — minimum horizontal gap between blocks in one row
const MAX_ROWS = 4;
const ROW_H = 14;      // px per sub-row
const BLOCK_H = 11;    // px block height inside a row

// Left offset of the strips inside the component: label w-24 (96px) + gap-2 (8px).
const LABEL_OFFSET_PX = 104;

interface Placed {
  e: SpaceWeatherEvent;
  left: number;
  width: number;
  row: number;
}

/** Greedy interval partitioning: first row whose last block ends far enough
 * left takes the event; otherwise open a new row (up to MAX_ROWS, then spill
 * into the least-filled row). Input is sorted by start. */
function layoutLane(
  events: SpaceWeatherEvent[],
  startMs: number,
  endMs: number
): { placed: Placed[]; rows: number } {
  const span = Math.max(1, endMs - startMs);
  const items: Placed[] = events
    .map((e) => {
      const s = new Date(e.start_time).getTime();
      const eMs = e.end_time ? new Date(e.end_time).getTime() : endMs; // ongoing → right edge
      return {
        e,
        left: ((s - startMs) / span) * 100,
        right: ((Math.max(eMs, s) - startMs) / span) * 100,
      };
    })
    .filter((it) => it.right >= 0 && it.left <= 100)
    .map((it) => {
      const left = Math.max(0, it.left);
      const width = Math.min(
        Math.max(MIN_WIDTH, Math.min(it.right, 100) - left),
        100 - left
      );
      return { e: it.e, left, width, row: 0 };
    })
    .sort((a, b) => a.left - b.left || b.width - a.width);

  const rowEnds: number[] = []; // rightmost occupied % per row
  for (const it of items) {
    let row = rowEnds.findIndex((end) => it.left >= end + GAP);
    if (row === -1) {
      if (rowEnds.length < MAX_ROWS) {
        row = rowEnds.length;
        rowEnds.push(-1);
      } else {
        row = rowEnds.indexOf(Math.min(...rowEnds)); // extreme density: least-filled row
      }
    }
    it.row = row;
    rowEnds[row] = Math.max(rowEnds[row], it.left + it.width);
  }
  return { placed: items, rows: Math.max(1, rowEnds.length) };
}

// ── Component ────────────────────────────────────────────────────────────────

interface Props {
  events: SpaceWeatherEvent[];
  startMs: number;
  endMs: number;
  selectedId: string | null;
  onSelect: (e: SpaceWeatherEvent) => void;
  /** Wheel-zoom callback: fraction = cursor position across the strip (0..1),
   * factor < 1 zooms in, > 1 zooms out. Omit to disable wheel zoom. */
  onZoomAt?: (fraction: number, factor: number) => void;
  /** Member ids of the active storyline: non-members dim, members keep full
   * opacity. Null/undefined = no chain highlight. */
  highlightIds?: Set<string> | null;
  /** Member ids in causal order, for drawing the connective line across lanes. */
  chainOrder?: string[] | null;
}

function ticks(startMs: number, endMs: number, n = 6): { pct: number; label: string }[] {
  const span = endMs - startMs;
  const out = [];
  for (let i = 0; i <= n; i++) {
    const t = startMs + (span * i) / n;
    const d = new Date(t).toISOString();
    // Label resolution follows the zoomed span: time-only when under a day.
    const label =
      span <= 86400_000
        ? d.slice(11, 16)
        : span <= 3 * 86400_000
          ? d.slice(5, 16).replace("T", " ")
          : d.slice(5, 10);
    out.push({ pct: (i / n) * 100, label });
  }
  return out;
}

/**
 * All event types on one chronological strip, one lane per source. Events that
 * are close together stack onto sub-rows instead of overlapping; an event
 * still in progress extends to the right edge. Flares are colored by GOES
 * class, official bursts by burst type (see the exported legends).
 */
export function HorizontalTimeline({
  events,
  startMs,
  endMs,
  selectedId,
  onSelect,
  onZoomAt,
  highlightIds,
  chainOrder,
}: Props) {
  const lanes = useMemo(() => {
    return LANES.map((lane) => {
      const laneEvents = events.filter((e) => lane.match(e.type));
      return { lane, ...layoutLane(laneEvents, startMs, endMs) };
    });
  }, [events, startMs, endMs]);

  // Native non-passive wheel listener (React's synthetic onWheel is passive,
  // so it can't preventDefault the page scroll while zooming).
  const wrapRef = useRef<HTMLDivElement>(null);
  const zoomRef = useRef(onZoomAt);
  zoomRef.current = onZoomAt;
  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    const onWheel = (ev: WheelEvent) => {
      if (!zoomRef.current) return;
      ev.preventDefault();
      const rect = el.getBoundingClientRect();
      const stripWidth = Math.max(1, rect.width - LABEL_OFFSET_PX);
      const fraction = Math.min(
        1,
        Math.max(0, (ev.clientX - rect.left - LABEL_OFFSET_PX) / stripWidth)
      );
      zoomRef.current(fraction, ev.deltaY < 0 ? 0.7 : 1 / 0.7);
    };
    el.addEventListener("wheel", onWheel, { passive: false });
    return () => el.removeEventListener("wheel", onWheel);
  }, []);

  // ── Storyline connectors ────────────────────────────────────────────────
  // Draw a line through the active chain's member blocks across lanes. Positions
  // are measured from the rendered DOM (robust to the responsive strip width and
  // the variable-height lanes) rather than re-derived from the layout math.
  const blockRefs = useRef<Map<string, HTMLButtonElement>>(new Map());
  const [link, setLink] = useState<{ pts: { x: number; y: number }[]; w: number; h: number }>({
    pts: [],
    w: 0,
    h: 0,
  });
  const chainKey = chainOrder?.join("|") ?? "";
  const dimming = !!highlightIds;

  const measure = useCallback(() => {
    const container = wrapRef.current;
    const order = chainKey ? chainKey.split("|") : [];
    if (!container || order.length < 2) {
      setLink((l) => (l.pts.length ? { pts: [], w: 0, h: 0 } : l));
      return;
    }
    const c = container.getBoundingClientRect();
    const pts: { x: number; y: number }[] = [];
    for (const id of order) {
      const el = blockRefs.current.get(id);
      if (!el) continue;
      const r = el.getBoundingClientRect();
      pts.push({ x: r.left + r.width / 2 - c.left, y: r.top + r.height / 2 - c.top });
    }
    setLink({ pts, w: c.width, h: c.height });
  }, [chainKey]);

  useLayoutEffect(() => {
    measure();
  }, [measure, events, startMs, endMs]);

  useEffect(() => {
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  const axis = ticks(startMs, endMs);

  return (
    <div ref={wrapRef} className="relative select-none">
      {lanes.map(({ lane, placed, rows }) => (
        <div
          key={lane.key}
          className="flex items-center gap-2 border-b border-surface-border/50 py-1"
        >
          <span className="w-24 shrink-0 text-right text-[10px] uppercase tracking-wider text-slate-500">
            {lane.label}
            {placed.length > 0 && (
              <span className="ml-1 font-mono text-slate-600">{placed.length}</span>
            )}
          </span>
          <div
            className="relative flex-1 rounded bg-surface-muted/40"
            style={{ height: rows * ROW_H + 4 }}
          >
            {placed.map(({ e, left, width, row }) => {
              const c = colorsFor(lane, e);
              const member = highlightIds?.has(e.id);
              return (
                <button
                  key={e.id}
                  ref={(el) => {
                    if (el) blockRefs.current.set(e.id, el);
                    else blockRefs.current.delete(e.id);
                  }}
                  onClick={() => onSelect(e)}
                  title={`${e.severity ?? ""} ${e.description}`.trim()}
                  // These blocks have no children, so without an explicit name a
                  // screen reader announced nothing at all for the page's main
                  // visualization — `title` alone is not a reliable name here.
                  aria-label={`${e.severity ? `${e.severity} ` : ""}${e.description}`.trim()}
                  className={clsx(
                    "absolute rounded-sm transition-[colors,opacity]",
                    selectedId === e.id ? c.selected : c.block,
                    dimming && !member && "opacity-25",
                    dimming && member && "ring-1 ring-accent-blue/90"
                  )}
                  style={{
                    left: `${left}%`,
                    width: `${width}%`,
                    top: row * ROW_H + 2,
                    height: BLOCK_H,
                  }}
                />
              );
            })}
          </div>
        </div>
      ))}

      {/* storyline connector: a dashed line threading the chain's member blocks */}
      {dimming && link.pts.length >= 2 && (
        <svg
          className="pointer-events-none absolute inset-0 z-10 text-accent-blue"
          width={link.w}
          height={link.h}
        >
          <polyline
            points={link.pts.map((p) => `${p.x},${p.y}`).join(" ")}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            strokeDasharray="3 3"
            strokeOpacity={0.85}
          />
          {link.pts.map((p, i) => (
            <circle key={i} cx={p.x} cy={p.y} r={2.5} fill="currentColor" />
          ))}
        </svg>
      )}

      {/* time axis */}
      <div className="ml-[6.5rem] mt-1 flex justify-between font-mono text-[9px] text-slate-600">
        {axis.map((t) => (
          <span key={t.pct}>{t.label}</span>
        ))}
      </div>
    </div>
  );
}
