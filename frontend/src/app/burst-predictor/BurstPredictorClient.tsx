"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { Play, Loader2, Check, X, Radar, ChevronRight } from "lucide-react";

import { api } from "@/lib/api";
import type {
  PredictedDetection,
  PredictedEvent,
  OfficialBurstCompare,
  BurstPredictionResult,
} from "@/lib/types";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function utcDateOffset(days: number): string {
  return new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
}

function alertColor(level: string): string {
  if (level === "High-confidence burst") return "border-accent-orange/40 bg-accent-orange/10 text-accent-orange";
  if (level === "Likely burst") return "border-accent-yellow/40 bg-accent-yellow/10 text-accent-yellow";
  if (level === "Possible burst") return "border-accent-blue/40 bg-accent-blue/10 text-accent-blue";
  return "border-slate-600/40 bg-slate-700/10 text-slate-400";
}

// A spectrum-preview selection. Predicted detections carry an exact `filename`;
// official burst-list stations carry only a `time` (HH:MM) — the segment covering
// that time is resolved server-side. `source` keeps the two highlightable apart.
type SelectedDet = {
  station: string;
  time: string;
  filename?: string;
  probability?: number;
  source: "predicted" | "official";
};

export function BurstPredictorClient() {
  // e-CALLISTO data for the current UTC day is often incomplete; default to the
  // previous day, the same convention the Archive page uses.
  const [date, setDate] = useState<string>(utcDateOffset(-1));
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [jobId, setJobId] = useState<string | null>(null);
  const [selectedDet, setSelectedDet] = useState<SelectedDet | null>(null);
  // Result loaded from already-stored detections (deep-link from an alert), shown
  // without re-scoring; cleared when the user changes date or runs a fresh scan.
  const [storedResult, setStoredResult] = useState<BurstPredictionResult | null>(null);

  // Stations that recorded on the chosen day.
  const { data: stationsData, isLoading: stationsLoading } = useSWR(
    ["pred-stations", date],
    () => api.radioArchiveStations(date)
  );
  const stations = useMemo(() => stationsData?.stations ?? [], [stationsData]);

  // Reset the run whenever the date changes.
  useEffect(() => {
    setJobId(null);
    setSelected(new Set());
    setSelectedDet(null);
    setStoredResult(null);
  }, [date]);

  // Deep-link from an alert: ?date=YYYY-MM-DD pre-fills the date and shows the
  // already-stored real-time detections for that day (no re-scoring). Runs once.
  useEffect(() => {
    const d = new URLSearchParams(window.location.search).get("date");
    if (!d) return;
    setDate(d);
    api.burstPredictionStored(d).then(setStoredResult).catch(() => setStoredResult(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Poll the prediction job while it runs.
  const { data: job } = useSWR(
    jobId ? ["predict-job", jobId] : null,
    () => api.burstPredictionJob(jobId as string),
    {
      refreshInterval: (latest) => (latest?.status === "running" ? 1500 : 0),
      revalidateOnFocus: false,
    }
  );
  const running = job?.status === "running";
  // Stored result (from an alert deep-link) takes precedence until the user runs
  // a fresh prediction, which clears it so the job result shows instead.
  const result = storedResult ?? (job?.status === "done" ? job?.result ?? null : null);

  // Auto-select the first detection for preview when a result arrives.
  useEffect(() => {
    const first = result?.events?.[0]?.detections?.[0];
    if (first) {
      setSelectedDet({
        station: first.station,
        filename: first.filename,
        time: first.time,
        probability: first.probability,
        source: "predicted",
      });
    }
  }, [result]);

  const toggleStation = (id: string) =>
    setSelected((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });

  const runPrediction = async () => {
    setSelectedDet(null);
    setStoredResult(null); // a fresh scan supersedes any alert-linked stored view
    const res = await api.startBurstPrediction(date, [...selected]);
    setJobId(res.job_id);
  };

  const pct = job && job.total > 0 ? Math.round((job.scanned / job.total) * 100) : 0;

  return (
    <div className="space-y-4">
      <RealtimeMonitor />

      {/* ── Controls ── */}
      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="flex flex-wrap items-end gap-4">
          <label className="flex flex-col gap-1 text-xs text-slate-500">
            Date (UTC)
            <input
              type="date"
              value={date}
              max={utcDateOffset(0)}
              onChange={(e) => setDate(e.target.value)}
              className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-sm text-slate-300 outline-none focus:border-accent-blue"
            />
          </label>

          <div className="flex-1">
            <div className="mb-1 flex items-center justify-between text-xs text-slate-500">
              <span>
                Stations ({selected.size > 0 ? `${selected.size} selected` : "all"})
              </span>
              <span className="flex gap-2">
                <button
                  onClick={() => setSelected(new Set(stations.map((s) => s.id)))}
                  disabled={!stations.length}
                  className="text-accent-blue hover:underline disabled:opacity-40"
                >
                  Select all
                </button>
                <button
                  onClick={() => setSelected(new Set())}
                  className="text-slate-500 hover:underline"
                >
                  Clear
                </button>
              </span>
            </div>
            <div className="max-h-24 overflow-y-auto rounded border border-surface-border bg-surface-muted/40 p-2">
              {stationsLoading ? (
                <span className="text-xs text-slate-600">Loading stations…</span>
              ) : !stations.length ? (
                <span className="text-xs text-slate-600">No e-CALLISTO data for {date}.</span>
              ) : (
                <div className="flex flex-wrap gap-1.5">
                  {stations.map((s) => (
                    <button
                      key={s.id}
                      onClick={() => toggleStation(s.id)}
                      className={clsx(
                        "rounded px-2 py-0.5 text-xs transition-colors",
                        selected.has(s.id)
                          ? "bg-accent-blue/25 text-accent-blue"
                          : "bg-surface-muted text-slate-400 hover:text-slate-200"
                      )}
                    >
                      {s.id}
                    </button>
                  ))}
                </div>
              )}
            </div>
            {selected.size === 0 && stations.length > 0 && (
              <p className="mt-1 text-[10px] text-slate-600">
                No selection = score every station for the day (can be slow).
              </p>
            )}
          </div>

          <button
            onClick={runPrediction}
            disabled={running || !stations.length}
            className={clsx(
              "flex items-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors",
              running || !stations.length
                ? "cursor-not-allowed bg-surface-muted text-slate-600"
                : "bg-accent-blue/20 text-accent-blue hover:bg-accent-blue/30"
            )}
          >
            {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <Radar className="h-4 w-4" />}
            {running ? "Predicting…" : "Predict bursts"}
          </button>
        </div>

        {/* Progress / status */}
        {job && (
          <div className="mt-3">
            {running ? (
              <>
                <div className="mb-1 flex justify-between text-xs text-slate-500">
                  <span>Scoring segments through the model…</span>
                  <span>
                    {job.scanned}/{job.total || "…"} ({pct}%)
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded bg-surface-muted">
                  <div
                    className="h-full bg-accent-blue transition-all"
                    style={{ width: `${pct}%` }}
                  />
                </div>
              </>
            ) : job.status === "error" ? (
              <p className="text-xs text-accent-red">Prediction failed: {job.error}</p>
            ) : null}
          </div>
        )}
      </div>

      {/* ── Result ── */}
      {result && <Summary result={result} />}

      {result && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
          <PredictedEvents
            result={result}
            selectedDet={selectedDet}
            onSelect={setSelectedDet}
          />
          <OfficialList result={result} selectedDet={selectedDet} onSelect={setSelectedDet} />
        </div>
      )}

      {result && <SpectrumPreview date={date} det={selectedDet} />}
    </div>
  );
}

function RealtimeMonitor() {
  // Health of the 10-min background scan, so a stalled real-time pipeline (most
  // often the model microservice being down) is visible here instead of just
  // silently producing no alerts.
  const { data } = useSWR("sources-status", api.sourcesStatus, { refreshInterval: 30000 });
  const src = data?.sources.find((s) => s.name === "Radio-Burst-Scan");
  const status = src?.status ?? "unknown";
  const dotCls =
    status === "ok"
      ? "bg-accent-green"
      : status === "error"
        ? "bg-accent-red"
        : status === "degraded"
          ? "bg-accent-yellow"
          : "bg-slate-600";
  const last = src?.last_updated
    ? new Date(src.last_updated).toISOString().slice(11, 16) + " UTC"
    : null;
  let text: string;
  if (status === "ok") {
    text = `Scanning every 10 min for new bursts${last ? ` · last run ${last}` : ""}`;
  } else if (status === "error") {
    text = src?.message || "Real-time scan reported an error.";
  } else {
    text = "Real-time scan hasn't reported yet — is the backend scheduler running?";
  }
  return (
    <div className="flex items-center gap-2 rounded-lg border border-surface-border bg-surface-card px-4 py-2 text-xs">
      <span className={clsx("h-2 w-2 shrink-0 rounded-full", dotCls)} />
      <span className="font-medium text-slate-300">Real-time monitor</span>
      <span className={clsx("truncate", status === "error" ? "text-accent-red/90" : "text-slate-500")}>
        {text}
      </span>
    </div>
  );
}

function Summary({ result }: { result: BurstPredictionResult }) {
  const stats: [string, string | number][] = [
    ["Segments scored", result.total_files],
    ["Burst files", result.burst_count],
    ["Predicted events", result.event_count],
    ["Official events", result.official_count],
    ["Matched", `${result.matched_count}/${result.event_count}`],
  ];
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
      {stats.map(([label, value]) => (
        <div
          key={label}
          className="rounded-lg border border-surface-border bg-surface-card p-3 text-center"
        >
          <div className="text-lg font-semibold text-slate-200">{value}</div>
          <div className="text-[10px] uppercase tracking-wider text-slate-500">{label}</div>
        </div>
      ))}
    </div>
  );
}

function PredictedEvents({
  result,
  selectedDet,
  onSelect,
}: {
  result: BurstPredictionResult;
  selectedDet: SelectedDet | null;
  onSelect: (d: SelectedDet) => void;
}) {
  return (
    <section className="flex flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="mb-3 text-xs uppercase tracking-wider text-slate-500">
        Predicted Bursts (model)
      </h2>
      {result.events.length === 0 ? (
        <div className="flex h-32 items-center justify-center text-xs text-slate-600">
          No bursts predicted for the selected stations.
        </div>
      ) : (
        <ul className="max-h-[28rem] space-y-2 overflow-y-auto pr-1">
          {result.events.map((ev) => (
            <EventRow
              key={ev.index}
              ev={ev}
              selectedFile={selectedDet?.filename ?? null}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function EventRow({
  ev,
  selectedFile,
  onSelect,
}: {
  ev: PredictedEvent;
  selectedFile: string | null;
  onSelect: (d: SelectedDet) => void;
}) {
  const [open, setOpen] = useState(false);
  const span = ev.start === ev.end ? `${ev.start}` : `${ev.start}–${ev.end}`;
  return (
    <li className="rounded border border-surface-border">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-surface-muted"
      >
        <ChevronRight className={clsx("h-3.5 w-3.5 shrink-0 text-slate-500 transition-transform", open && "rotate-90")} />
        <span className="w-24 font-mono text-slate-200">{span} UTC</span>
        <span className={clsx("rounded border px-1.5 py-0.5", alertColor(ev.alert_level))}>
          p={ev.max_probability.toFixed(2)}
        </span>
        <span className="text-slate-500">
          {ev.n_stations} st · {ev.n_detections} det
        </span>
        <span className="ml-auto flex items-center gap-1">
          {ev.matched_official ? (
            <span className="flex items-center gap-1 text-accent-green">
              <Check className="h-3.5 w-3.5" /> in list
            </span>
          ) : (
            <span className="flex items-center gap-1 text-slate-600">
              <X className="h-3.5 w-3.5" /> new
            </span>
          )}
        </span>
      </button>
      {open && (
        <div className="border-t border-surface-border/60 p-2">
          <div className="space-y-1">
            {ev.detections.map((d: PredictedDetection) => (
              <button
                key={d.filename}
                onClick={() =>
                  onSelect({
                    station: d.station,
                    filename: d.filename,
                    time: d.time,
                    probability: d.probability,
                    source: "predicted",
                  })
                }
                className={clsx(
                  "flex w-full items-center gap-2 rounded px-2 py-1 text-left text-[11px]",
                  selectedFile === d.filename ? "bg-accent-blue/15" : "hover:bg-surface-muted"
                )}
              >
                <span className="w-20 font-mono text-slate-300">{d.time}</span>
                <span className="flex-1 truncate text-slate-400">{d.station}</span>
                <span className="text-slate-500">{d.probability.toFixed(3)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
    </li>
  );
}

function OfficialList({
  result,
  selectedDet,
  onSelect,
}: {
  result: BurstPredictionResult;
  selectedDet: SelectedDet | null;
  onSelect: (d: SelectedDet) => void;
}) {
  return (
    <section className="flex flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="mb-3 text-xs uppercase tracking-wider text-slate-500">
        Official e-CALLISTO Burst List
      </h2>
      {result.official_events.length === 0 ? (
        <div className="flex h-32 items-center justify-center text-xs text-slate-600">
          No bursts in the official list for {result.date}.
        </div>
      ) : (
        <ul className="max-h-[28rem] space-y-2 overflow-y-auto pr-1">
          {result.official_events.map((o, i) => (
            <OfficialRow
              key={`${o.start}-${i}`}
              o={o}
              selectedDet={selectedDet}
              onSelect={onSelect}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function OfficialRow({
  o,
  selectedDet,
  onSelect,
}: {
  o: OfficialBurstCompare;
  selectedDet: SelectedDet | null;
  onSelect: (d: SelectedDet) => void;
}) {
  const [open, setOpen] = useState(false);
  const span = o.start === o.end ? o.start : `${o.start}–${o.end}`;
  const isSelected = (st: string) =>
    selectedDet?.source === "official" &&
    selectedDet.station === st &&
    selectedDet.time === o.start;
  return (
    <li className="rounded border border-surface-border">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center gap-2 px-3 py-2 text-left text-xs hover:bg-surface-muted"
      >
        <ChevronRight className={clsx("h-3.5 w-3.5 shrink-0 text-slate-500 transition-transform", open && "rotate-90")} />
        <span className="w-24 font-mono text-slate-200">{span} UTC</span>
        <span className="rounded bg-accent-purple/20 px-1.5 py-0.5 text-accent-purple">
          {o.burst_type}
        </span>
        <span className="text-slate-500">
          {o.stations.length} st
        </span>
        <span className="ml-auto flex items-center gap-1">
          {o.matched_prediction ? (
            <span className="flex items-center gap-1 text-accent-green">
              <Check className="h-3.5 w-3.5" /> predicted
            </span>
          ) : (
            <span className="flex items-center gap-1 text-accent-red/80">
              <X className="h-3.5 w-3.5" /> missed
            </span>
          )}
        </span>
      </button>
      {open && (
        <div className="border-t border-surface-border/60 p-2">
          {o.stations.length === 0 ? (
            <p className="px-2 py-1 text-[11px] text-slate-600">No stations listed.</p>
          ) : (
            <div className="flex flex-wrap gap-1.5">
              {o.stations.map((st) => (
                <button
                  key={st}
                  onClick={() => onSelect({ station: st, time: o.start, source: "official" })}
                  className={clsx(
                    "rounded px-2 py-0.5 text-[11px] transition-colors",
                    isSelected(st)
                      ? "bg-accent-blue/25 text-accent-blue"
                      : "bg-surface-muted text-slate-400 hover:text-slate-200"
                  )}
                >
                  {st}
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </li>
  );
}

function SpectrumPreview({
  date,
  det,
}: {
  date: string;
  det: SelectedDet | null;
}) {
  const { data: spectrum, isLoading } = useSWR(
    det ? ["pred-spec", date, det.station, det.filename ?? det.time] : null,
    () =>
      det!.filename
        ? api.radioArchiveSpectrum(date, det!.station, det!.filename)
        : api.radioArchiveSpectrumAt(date, det!.station, det!.time),
    { revalidateOnFocus: false }
  );

  return (
    <section className="rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-xs uppercase tracking-wider text-slate-500">
          Dynamic Spectrum Preview
        </h2>
        {det && (
          <span className="font-mono text-xs text-slate-400">
            {det.station} · {det.time} UTC
            {det.probability != null ? ` · p=${det.probability.toFixed(3)}` : ""}
          </span>
        )}
      </div>
      <div className="relative min-h-[260px] overflow-hidden rounded bg-black/40">
        {!det ? (
          <div className="flex h-[260px] items-center justify-center text-xs text-slate-600">
            Select a predicted burst to preview its dynamic spectrum.
          </div>
        ) : isLoading ? (
          <div className="h-[260px] w-full animate-pulse bg-surface-muted" />
        ) : spectrum ? (
          <img
            src={`${apiBase}${spectrum.image_url}`}
            alt={`Dynamic spectrum for ${det.station} at ${det.time}`}
            className="max-h-[420px] w-full object-contain"
          />
        ) : (
          <div className="flex h-[260px] items-center justify-center text-xs text-slate-600">
            Could not render this spectrum.
          </div>
        )}
      </div>
    </section>
  );
}
