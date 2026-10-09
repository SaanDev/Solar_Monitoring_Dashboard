"use client";

import { useMemo, useState, type ReactNode } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { Loader2, RefreshCw } from "lucide-react";

import { api } from "@/lib/api";
import type { StationOverride, StationReliabilityItem } from "@/lib/types";
import { EmptyState } from "@/components/ui/EmptyState";

type Filter = "all" | "strong" | "weak" | "overridden";

const FILTERS: { key: Filter; label: string }[] = [
  { key: "all", label: "All" },
  { key: "strong", label: "Strong" },
  { key: "weak", label: "Weak / noisy" },
  { key: "overridden", label: "Overridden" },
];

// Evidence of a high-confidence flag, in nats. ~3 is the cleanest stations; the
// bar is drawn on 0..BAR_MAX.
const BAR_MAX = 3.5;
const STRONG = 1.5;
const WEAK = 0.5;

const flagWeight = (s: StationReliabilityItem) => s.evidence?.[3] ?? 0;

function pct(weight: number): number {
  return Math.max(0, Math.min(100, (weight / BAR_MAX) * 100));
}

function signed(x: number): string {
  return `${x >= 0 ? "+" : "−"}${Math.abs(x).toFixed(1)}`;
}

function statusOf(s: StationReliabilityItem): { label: string; tone: string } {
  if (s.excluded) return { label: "ignored", tone: "text-slate-500" };
  const w = flagWeight(s);
  if (s.override === "always") return { label: "boosted", tone: "text-accent-blue" };
  // Nothing in the measurement window: the weight is the built-in prior's.
  if (s.files === 0) return { label: "no recent data", tone: "text-slate-500" };
  if (w >= STRONG) return { label: "strong", tone: "text-accent-green" };
  if (w >= WEAK) return { label: "moderate", tone: "text-accent-yellow" };
  return { label: "mostly noise", tone: "text-slate-500" };
}

/**
 * How much each e-CALLISTO station's readings weigh in the burst confirmation.
 *
 * A burst becomes an event only when different stations flag it together and
 * the readings of every station observing — each weighted by its track record —
 * make a burst far likelier than chance. The record is re-measured daily on the
 * server; the override here boosts a station or ignores it, for every viewer.
 */
export function StationReliabilityCard() {
  const { data, mutate, error } = useSWR("station-reliability", api.stationReliability, {
    revalidateOnFocus: false,
  });
  const [filter, setFilter] = useState<Filter>("all");
  const [busy, setBusy] = useState<string | null>(null); // station being saved, or "recompute"
  const [status, setStatus] = useState<{ text: string; tone: "ok" | "error" } | null>(null);

  const sites = useMemo(() => {
    // Members per site, so merged (co-located) stations can be labelled.
    const m = new Map<string, string[]>();
    for (const s of data?.stations ?? []) m.set(s.site, [...(m.get(s.site) ?? []), s.station]);
    return m;
  }, [data]);

  const rows = useMemo(() => {
    const all = [...(data?.stations ?? [])].sort(
      (a, b) =>
        Number(a.excluded) - Number(b.excluded) ||
        flagWeight(b) - flagWeight(a) ||
        a.station.localeCompare(b.station)
    );
    switch (filter) {
      case "strong":
        return all.filter((s) => !s.excluded && s.files > 0 && flagWeight(s) >= STRONG);
      case "weak":
        return all.filter((s) => s.excluded || flagWeight(s) < WEAK);
      case "overridden":
        return all.filter((s) => s.override !== "auto");
      default:
        return all;
    }
  }, [data, filter]);

  const run = async (key: string, action: () => Promise<unknown>, done: string) => {
    setBusy(key);
    setStatus(null);
    try {
      const updated = await action();
      await mutate(updated as typeof data, { revalidate: false });
      setStatus({ text: done, tone: "ok" });
    } catch (e) {
      setStatus({ text: `Failed: ${e instanceof Error ? e.message : e}`, tone: "error" });
    } finally {
      setBusy(null);
    }
  };

  const shell = (body: ReactNode) => (
    <section className="rounded-lg border border-surface-border bg-surface-card p-5">
      <h2 className="text-sm font-semibold text-slate-200">Burst Confirmation Stations</h2>
      {body}
    </section>
  );

  if (error) {
    return shell(
      <div className="mt-4">
        <EmptyState tone="error" message="Couldn't load the station records." />
      </div>
    );
  }
  if (!data) return shell(<div className="mt-4 h-40 animate-pulse rounded bg-surface-muted" />);

  const strong = data.stations.filter(
    (s) => !s.excluded && s.files > 0 && flagWeight(s) >= STRONG
  ).length;
  const odds = Math.round(Math.exp(data.min_evidence));

  return shell(
    <>
      <p className="mt-1 text-xs text-slate-500">
        A radio burst becomes an event when at least {data.min_sites} different sites flag
        it at p ≥ {data.high_conf_probability} with the Sun up, at the same time, and the
        readings of every station observing make a burst at least ~{odds}× likelier than
        chance. Each reading is weighed by the station’s track record: a flag from a
        station that rarely flags and is usually right counts a lot, one from a station
        that flags all day hardly at all, and a good station staying silent counts
        against. Stations within {data.site_radius_km} km count as one site.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-slate-400">
        <span>
          <span className="font-semibold text-slate-200">{strong}</span> of{" "}
          {data.stations.length} stations carry strong evidence
        </span>
        <span className="text-slate-600">
          last {data.window_days} days
          {data.computed_at &&
            ` · measured ${new Date(data.computed_at).toISOString().slice(0, 16).replace("T", " ")} UTC`}
        </span>
      </div>

      <div className="mt-3 flex flex-wrap gap-1.5" role="group" aria-label="Filter stations">
        {FILTERS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFilter(f.key)}
            aria-pressed={filter === f.key}
            className={clsx(
              "rounded border px-2 py-0.5 text-[11px] transition-colors",
              filter === f.key
                ? "border-accent-blue bg-accent-blue/10 text-accent-blue"
                : "border-surface-border text-slate-400 hover:text-slate-200"
            )}
          >
            {f.label}
          </button>
        ))}
      </div>

      <ul className="mt-3 max-h-96 divide-y divide-surface-border overflow-y-auto rounded border border-surface-border">
        {rows.length === 0 && (
          <li className="p-3 text-xs text-slate-500">No stations in this view.</li>
        )}
        {rows.map((s) => {
          const st = statusOf(s);
          const w = flagWeight(s);
          const silence = (s.evidence?.[0] ?? 0) * data.silence_weight;
          const mates = (sites.get(s.site) ?? []).filter((x) => x !== s.station);
          return (
            <li key={s.station} className={clsx("flex items-center gap-3 px-3 py-2", s.excluded && "opacity-60")}>
              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-xs font-medium text-slate-200" title={s.station}>
                    {s.station}
                  </span>
                  <span className={clsx("shrink-0 text-[10px]", st.tone)}>{st.label}</span>
                </div>
                <div
                  className="relative mt-1 h-1.5 rounded bg-surface-muted"
                  title={`A high-confidence flag counts ${signed(w)}; silence counts ${signed(silence)} (nats)`}
                >
                  <div
                    className={clsx(
                      "h-full rounded",
                      s.excluded
                        ? "bg-slate-600/50"
                        : w >= STRONG
                          ? "bg-accent-green/70"
                          : w >= WEAK
                            ? "bg-accent-yellow/60"
                            : "bg-slate-500/60"
                    )}
                    style={{ width: `${pct(w)}%` }}
                  />
                </div>
                <div className="mt-0.5 truncate text-[10px] text-slate-600">
                  flag {signed(w)} · silent {signed(silence)}
                  {s.duty != null && ` · flags ${(s.duty * 100).toFixed(1)}% of the time`}
                  {s.score != null && ` · agrees ${s.score.toFixed(2)}`}
                  {mates.length > 0 && ` · same site as ${mates.join(", ")}`}
                </div>
              </div>
              <label className="sr-only" htmlFor={`ovr-${s.station}`}>
                Override for {s.station}
              </label>
              <select
                id={`ovr-${s.station}`}
                value={s.override}
                disabled={busy !== null}
                onChange={(e) => {
                  const value = e.target.value as StationOverride;
                  run(
                    s.station,
                    () => api.setStationOverride(s.station, value),
                    `${s.station}: ${
                      value === "auto" ? "back to its record" : value === "always" ? "boosted" : "ignored"
                    }.`
                  );
                }}
                className="shrink-0 rounded border border-surface-border bg-surface-muted px-1.5 py-1 text-[11px] text-slate-300"
              >
                <option value="auto">Auto</option>
                <option value="always">Boost</option>
                <option value="never">Ignore</option>
              </select>
              {busy === s.station && <Loader2 className="h-3.5 w-3.5 shrink-0 animate-spin text-slate-400" />}
            </li>
          );
        })}
      </ul>

      <p className="mt-3 text-[11px] text-slate-600">
        Records are re-measured daily from the stored detections: how a station reads
        during sure bursts (ones other reliable stations confirm on their own) against
        how it reads the rest of the time. “Agrees” is how often its own bursts are
        also flagged by two or more other sites, beyond chance. Boost gives a station’s
        flags at least a typical reliable station’s weight; Ignore leaves it out. A
        change applies from the next rebuild of the last day’s events; older history
        keeps the events it was confirmed with.
      </p>

      <div className="mt-3 flex flex-wrap items-center gap-3">
        <button
          onClick={() =>
            run("recompute", api.recomputeStationReliability, "Re-measured every station.")
          }
          disabled={busy !== null}
          className="flex items-center gap-2 rounded border border-surface-border px-3 py-1.5 text-xs text-slate-300 hover:text-slate-100 disabled:opacity-50"
        >
          {busy === "recompute" ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          Re-measure now
        </button>
        {status && (
          <span
            role="status"
            aria-live="polite"
            className={clsx("text-xs", status.tone === "ok" ? "text-accent-green" : "text-accent-red")}
          >
            {status.text}
          </span>
        )}
      </div>
    </>
  );
}
