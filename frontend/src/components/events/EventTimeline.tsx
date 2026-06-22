import Link from "next/link";
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

export function EventTimeline({ events }: { events: SpaceWeatherEvent[] }) {
  if (!events.length) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-slate-600">
        No events detected in this window
      </div>
    );
  }

  return (
    <ul className="space-y-3">
      {events.map((e) => {
        const meta = TYPE_META[e.type] ?? FALLBACK;
        const ongoing = e.end_time === null;
        return (
          <li
            key={e.id}
            className="relative rounded-lg border border-surface-border bg-surface-card p-4 pl-5"
          >
            {/* Colored type rail */}
            <span
              className={clsx(
                "absolute left-0 top-0 h-full w-1 rounded-l-lg",
                meta.dot
              )}
            />
            {/* Card body deep-links to the event's visualization. The external
                "source" link lives outside this anchor to avoid nested <a>. */}
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

            {e.source_url && (
              <a
                href={e.source_url}
                target="_blank"
                rel="noopener noreferrer"
                className="mt-2 inline-block text-xs text-accent-blue hover:underline"
              >
                source ↗
              </a>
            )}
          </li>
        );
      })}
    </ul>
  );
}
