"use client";

import dynamic from "next/dynamic";
import useSWR from "swr";
import { clsx } from "clsx";

import { api } from "@/lib/api";
import { usePlotlyTheme } from "@/components/charts/plotlyTheme";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

function Stat({
  label,
  value,
  hint,
  accent,
}: {
  label: string;
  value: string;
  hint?: string;
  accent?: string;
}) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-muted/40 p-3">
      <p className="text-[10px] uppercase tracking-wider text-slate-500">{label}</p>
      <p className={clsx("font-mono text-xl font-bold", accent ?? "text-slate-200")}>{value}</p>
      {hint && <p className="text-[10px] text-slate-600">{hint}</p>}
    </div>
  );
}

const pct = (v: number | null) => (v != null ? `${(v * 100).toFixed(0)}%` : "—");

/**
 * Model performance over the trailing 30 days: the live scanner's stored
 * detections (with the alert pipeline's corroboration criteria) matched
 * two-way against the official e-CALLISTO burst list.
 */
export function ScorecardSection() {
  const theme = usePlotlyTheme();
  const { data, isLoading } = useSWR("burst-scorecard", () => api.burstScorecard(30), {
    refreshInterval: 3600000,
  });

  const daily = (data?.daily ?? []).filter(() => true);
  const days = daily.map((d) => d.date.slice(5)); // MM-DD
  const falseAlarms = daily.map((d) => d.predicted_count - d.matched_predicted);

  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-3 flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-xs uppercase tracking-wider text-slate-500">
          Model Performance — last 30 days
        </h2>
        <span className="text-[10px] text-slate-600">
          real-time scanner detections vs. official e-CALLISTO burst list
          {data ? ` · ${data.days_with_data}/${data.days} days with scanner data` : ""}
        </span>
      </div>

      {isLoading || !data ? (
        <div className="h-48 animate-pulse rounded bg-surface-muted" />
      ) : (
        <>
          <div className="mb-3 grid grid-cols-2 gap-3 md:grid-cols-4">
            <Stat
              label="Recall"
              value={pct(data.recall)}
              hint={`${data.matched_official}/${data.official_total} official bursts matched`}
              accent={
                data.recall != null && data.recall >= 0.7
                  ? "text-accent-green"
                  : "text-accent-orange"
              }
            />
            <Stat
              label="Precision"
              value={pct(data.precision)}
              hint={`${data.matched_predicted}/${data.predicted_total} predicted events confirmed`}
              accent={
                data.precision != null && data.precision >= 0.7
                  ? "text-accent-green"
                  : "text-accent-orange"
              }
            />
            <Stat label="Official Bursts" value={String(data.official_total)} hint="on days with data" />
            <Stat label="Predicted Events" value={String(data.predicted_total)} hint="corroborated clusters" />
          </div>

          <div className="h-56">
            <Plot
              data={[
                {
                  x: days,
                  y: daily.map((d) => d.official_count),
                  type: "bar",
                  name: "Official",
                  marker: { color: "#64748b" },
                },
                {
                  x: days,
                  y: daily.map((d) => d.matched_official),
                  type: "bar",
                  name: "Matched by model",
                  marker: { color: "#22c55e" },
                },
                {
                  x: days,
                  y: falseAlarms,
                  type: "bar",
                  name: "Unconfirmed",
                  // Trailing days are grey: the official list lags, so a fresh
                  // day's unmatched events aren't necessarily false alarms yet.
                  marker: { color: daily.map((d) => (d.pending ? "#64748b" : "#ef4444")) },
                },
              ]}
              layout={
                {
                  ...theme.layout,
                  barmode: "group",
                  xaxis: { ...theme.axis, tickfont: { size: 8 } },
                  yaxis: {
                    ...theme.axis,
                    title: { text: "Events / day", font: { size: 10 } },
                    dtick: 1,
                  },
                  legend: { orientation: "h", y: 1.15, font: { size: 10 } },
                  margin: { t: 10, r: 10, b: 40, l: 50 },
                } as Plotly.Layout
              }
              config={{ displayModeBar: false, responsive: true }}
              style={{ width: "100%", height: "100%" }}
              useResizeHandler
            />
          </div>
          <p className="mt-2 text-[10px] text-slate-600">
            Recall = official bursts the model also flagged; precision = model events
            that correspond to an official burst. Days without scanner data — and the
            last two days, whose official list is usually not yet published (grey bars)
            — are excluded from the totals. The model sees only stations the live scan
            covers, so recall is bounded by station coverage, not just model quality.
          </p>
        </>
      )}
    </div>
  );
}
