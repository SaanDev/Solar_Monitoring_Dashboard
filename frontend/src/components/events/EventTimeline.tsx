"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { Link2 } from "lucide-react";
import type { SpaceWeatherEvent } from "@/lib/types";
import { formatUtcShort } from "@/lib/formatting";
import { alertHref } from "@/lib/alerts";
import { clsx } from "clsx";

// Full literal class strings per type so Tailwind's content scan keeps them
// (dynamic `accent-${x}` names would be purged from the build).
const TYPE_META: Record<
  string,
  { label: string; dot: string; badge: string }
> = {
  xray_flare: {
    label: "X-Ray Flare",
    dot: "bg-accent-orange",
    badge: "border-accent-orange/40 bg-accent-orange/10 text-accent-orange",
  },
  proton_event: {
    label: "Proton Event",
    dot: "bg-accent-red",
    badge: "border-accent-red/40 bg-accent-red/10 text-accent-red",
  },
  geomagnetic_storm_kp: {
    label: "Geomagnetic Storm · Kp",
    dot: "bg-accent-purple",
    badge: "border-accent-purple/40 bg-accent-purple/10 text-accent-purple",
  },
  geomagnetic_storm_dst: {
    label: "Geomagnetic Storm · Dst",
    dot: "bg-accent-cyan",
    badge: "border-accent-cyan/40 bg-accent-cyan/10 text-accent-cyan",
  },
  radio_burst: {
    label: "Radio Bursts",
    dot: "bg-accent-green",
    badge: "border-accent-green/40 bg-accent-green/10 text-accent-green",
  },
};

const FALLBACK = {
  label: "Event",
  dot: "bg-slate-500",
  badge: "border-slate-600/40 bg-slate-700/10 text-slate-300",
};

const domId = (id: string) => `event-${id}`;

/** Connected components over `related_event_ids`, keeping the timeline's
 * newest-first order between clusters; within a cluster members run
 * chronologically so a pair reads as flare → burst. */
function clusterRelated(events: SpaceWeatherEvent[]): SpaceWeatherEvent[][] {
  const byId = new Map(events.map((e) => [e.id, e]));
  const seen = new Set<string>();
  const clusters: SpaceWeatherEvent[][] = [];
  for (const e of events) {
    if (seen.has(e.id)) continue;
    seen.add(e.id);
    const members = [e];
    const stack = [e];
    while (stack.length) {
      for (const rid of stack.pop()!.related_event_ids ?? []) {
        const r = byId.get(rid);
        if (r && !seen.has(r.id)) {
          seen.add(r.id);
          members.push(r);
          stack.push(r);
        }
      }
    }
    members.sort((a, b) => a.start_time.localeCompare(b.start_time));
    clusters.push(members);
  }
  return clusters;
}

function clusterSummary(members: SpaceWeatherEvent[]): string {
  const labels: string[] = [];
  for (const m of members) {
    const label = (TYPE_META[m.type] ?? FALLBACK).label;
    if (!labels.includes(label)) labels.push(label);
  }
  return labels.join(" ↔ ");
}

function EventCard({
  event: e,
  byId,
  onJump,
  highlighted,
}: {
  event: SpaceWeatherEvent;
  byId: Map<string, SpaceWeatherEvent>;
  onJump: (id: string) => void;
  highlighted: boolean;
}) {
  const meta = TYPE_META[e.type] ?? FALLBACK;
  const ongoing = e.end_time === null;
  // Only partners present in the fetched window can be labelled and jumped to.
  const related = (e.related_event_ids ?? [])
    .map((id) => byId.get(id))
    .filter((r): r is SpaceWeatherEvent => r !== undefined);
  return (
    <li
      id={domId(e.id)}
      className={clsx(
        "relative rounded-lg border bg-surface-card p-4 pl-5 transition-shadow",
        highlighted
          ? "border-accent-blue ring-1 ring-accent-blue/60"
          : "border-surface-border"
      )}
    >
      {/* Colored type rail */}
      <span
        className={clsx(
          "absolute left-0 top-0 h-full w-1 rounded-l-lg",
          meta.dot
        )}
      />
      {/* Card body deep-links to the event's visualization. The related-event
          chips and external "source" link live outside this anchor to avoid
          nested interactive elements. */}
      <Link
        href={alertHref(e.type, e.start_time)}
        className="block transition-opacity hover:opacity-80"
      >
        <div className="mb-1 flex flex-wrap items-center gap-2">
          <span
            className={clsx(
              "rounded border px-2 py-0.5 font-mono text-xs font-semibold",
              meta.badge
            )}
          >
            {e.severity ?? meta.label}
          </span>
          <span className="text-sm font-medium text-slate-300">{meta.label}</span>
          {ongoing && (
            <span className="flex items-center gap-1 rounded bg-accent-green/10 px-2 py-0.5 text-xs text-accent-green">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-green" />
              In progress
            </span>
          )}
        </div>

        <p className="text-sm text-slate-400">{e.description}</p>

        <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-600">
          <span>
            Start: <span className="font-mono text-slate-500">{formatUtcShort(e.start_time)}</span>
          </span>
          <span>
            {ongoing ? (
              <span className="text-accent-green">ongoing</span>
            ) : (
              <>
                End:{" "}
                <span className="font-mono text-slate-500">
                  {formatUtcShort(e.end_time as string)}
                </span>
              </>
            )}
          </span>
        </div>
      </Link>

      {(related.length > 0 || e.source_url) && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          {related.map((r) => {
            const rMeta = TYPE_META[r.type] ?? FALLBACK;
            return (
              <button
                key={r.id}
                type="button"
                onClick={() => onJump(r.id)}
                title={`Occurred together — jump to this ${rMeta.label.toLowerCase()}`}
                className={clsx(
                  "flex items-center gap-1 rounded border px-2 py-0.5 text-xs transition-opacity hover:opacity-80",
                  rMeta.badge
                )}
              >
                <Link2 className="h-3 w-3" />
                {rMeta.label}
                {r.severity ? ` · ${r.severity}` : ""}
              </button>
            );
          })}
          {e.source_url && (
            <a
              href={e.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs text-accent-blue hover:underline"
            >
              source ↗
            </a>
          )}
        </div>
      )}
    </li>
  );
}

export function EventTimeline({
  events,
  grouped = false,
}: {
  events: SpaceWeatherEvent[];
  /** Merge related events (flare ↔ radio burst) into one cluster card. */
  grouped?: boolean;
}) {
  const byId = useMemo(() => new Map(events.map((e) => [e.id, e])), [events]);
  const [highlightId, setHighlightId] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const jumpTo = useCallback((id: string) => {
    document
      .getElementById(domId(id))
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
    setHighlightId(id);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setHighlightId(null), 1800);
  }, []);

  if (!events.length) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-slate-600">
        No events detected in this window
      </div>
    );
  }

  if (grouped) {
    return (
      <ul className="space-y-3">
        {clusterRelated(events).map((members) =>
          members.length === 1 ? (
            <EventCard
              key={members[0].id}
              event={members[0]}
              byId={byId}
              onJump={jumpTo}
              highlighted={highlightId === members[0].id}
            />
          ) : (
            <li
              key={members[0].id}
              className="rounded-lg border border-accent-blue/40 bg-accent-blue/5 p-3"
            >
              <div className="mb-2 flex flex-wrap items-center gap-2 text-xs font-semibold uppercase tracking-wider text-accent-blue">
                <Link2 className="h-3.5 w-3.5" />
                Related events
                <span className="font-normal normal-case tracking-normal text-slate-500">
                  {clusterSummary(members)}
                </span>
              </div>
              <ul className="space-y-3">
                {members.map((m) => (
                  <EventCard
                    key={m.id}
                    event={m}
                    byId={byId}
                    onJump={jumpTo}
                    highlighted={highlightId === m.id}
                  />
                ))}
              </ul>
            </li>
          )
        )}
      </ul>
    );
  }

  return (
    <ul className="space-y-3">
      {events.map((e) => (
        <EventCard
          key={e.id}
          event={e}
          byId={byId}
          onJump={jumpTo}
          highlighted={highlightId === e.id}
        />
      ))}
    </ul>
  );
}
