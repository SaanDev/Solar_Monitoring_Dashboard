"use client";

import { clsx } from "clsx";

import { formatUtcShort } from "@/lib/formatting";
import type { EventChain, SpaceWeatherEvent } from "@/lib/types";

/** Alert-level accent for a chain's peak severity. */
const SEVERITY_ACCENT: Record<string, string> = {
  info: "bg-slate-500",
  watch: "bg-accent-yellow",
  warning: "bg-accent-orange",
  critical: "bg-accent-red",
};

/** Causal role → short label (roles come from the backend chain builder). */
export const ROLE_LABEL: Record<string, string> = {
  flare: "Flare",
  cme: "CME",
  radio_burst: "Radio",
  sep: "Proton",
  geomagnetic_storm: "Storm",
  predicted_storm: "Forecast",
  event: "Event",
};

function roleLabel(role: string | undefined): string {
  return (role && ROLE_LABEL[role]) || role || "Event";
}

interface Props {
  chains: EventChain[];
  activeId: string | null;
  onHover: (id: string | null) => void;
  onOpen: (e: SpaceWeatherEvent) => void;
}

/**
 * Causal storylines as a scannable list of cards: each renders the ordered
 * flare → CME → burst → proton → storm sequence as role chips, its one-line
 * summary, and its span. Hovering a card traces the chain on the timeline
 * above; clicking opens its first event in the inspector.
 */
export function StorylineList({ chains, activeId, onHover, onOpen }: Props) {
  if (!chains.length) return null;
  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">Storylines</h2>
      <p className="mb-3 mt-0.5 text-[11px] text-slate-600">
        Physically linked events chained across the Sun–Earth system (a flare and its
        CME, the shock&apos;s radio burst and proton storm, and the geomagnetic storm on
        arrival). Hover to trace one on the timeline; click to open it.
      </p>
      <div className="space-y-2">
        {chains.map((c) => {
          const active = c.chain_id === activeId;
          return (
            <button
              key={c.chain_id}
              onMouseEnter={() => onHover(c.chain_id)}
              onMouseLeave={() => onHover(null)}
              onClick={() => c.events[0] && onOpen(c.events[0])}
              className={clsx(
                "flex w-full items-stretch gap-3 rounded-md border p-2 text-left transition-colors",
                active
                  ? "border-accent-blue/60 bg-accent-blue/10"
                  : "border-surface-border hover:bg-surface-muted"
              )}
            >
              <span
                className={clsx(
                  "w-1 shrink-0 rounded-full",
                  SEVERITY_ACCENT[c.peak_severity] ?? "bg-slate-500"
                )}
              />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1">
                  {c.events.map((e, i) => (
                    <span key={e.id} className="flex items-center gap-1">
                      {i > 0 && <span className="text-slate-600">→</span>}
                      <span className="rounded bg-surface-muted px-1.5 py-0.5 text-[10px] text-slate-300">
                        {roleLabel(c.roles[e.id])}
                        {e.severity ? ` ${e.severity}` : ""}
                      </span>
                    </span>
                  ))}
                </div>
                <p className="mt-1 truncate text-[11px] text-slate-500" title={c.summary}>
                  {c.summary}
                </p>
                <p className="mt-0.5 text-[10px] text-slate-600">
                  {formatUtcShort(c.start_time)}
                  {c.end_time ? ` → ${formatUtcShort(c.end_time)}` : " → ongoing"} ·{" "}
                  {c.events.length} events
                </p>
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
