"use client";

import { useEffect, useMemo, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { Play, Loader2, Check, X, Radar, ChevronRight } from "lucide-react";

import { API_BASE, api } from "@/lib/api";
import {
  alertsToReportEvents,
  predictedToReportEvents,
} from "@/lib/exportEvents";
import { ExportEventsButton } from "@/components/events/ExportEventsButton";
import type {
  ModelInfo,
  PredictedDetection,
  PredictedEvent,
  OfficialBurstCompare,
  BurstPredictionResult,
  TypedRegion,
} from "@/lib/types";

const apiBase = API_BASE;

function utcDateOffset(days: number): string {
  return new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
}

function alertColor(level: string): string {
  if (level === "High-confidence burst") return "border-accent-orange/40 bg-accent-orange/10 text-accent-orange";
  if (level === "Likely burst") return "border-accent-yellow/40 bg-accent-yellow/10 text-accent-yellow";
  if (level === "Possible burst") return "border-accent-blue/40 bg-accent-blue/10 text-accent-blue";
  return "border-slate-600/40 bg-slate-700/10 text-slate-400";
}

// Burst types get their own palette, distinct from the probability bands above so
// a type chip is never mistaken for a confidence chip.
function typeColor(type: string): string {
  if (type === "Type II") return "bg-accent-red/15 text-accent-red";
  if (type === "Type III") return "bg-accent-green/15 text-accent-green";
  return "bg-slate-600/20 text-slate-400"; // "Other"
}

/** Short form for dense rows: "Type III" -> "III". */
function shortType(type: string): string {
  return type.startsWith("Type ") ? type.slice(5) : type;
}

function TypeChip({
  type,
  confidence,
  short = false,
}: {
  type: string;
  confidence?: number | null;
  short?: boolean;
}) {
  return (
    <span
      className={clsx("rounded px-1.5 py-0.5 text-[10px]", typeColor(type))}
      title={
        confidence != null
          ? `${type} — CCMT confidence ${(confidence * 100).toFixed(0)}%`
          : type
      }
    >
      {short ? shortType(type) : type}
    </span>
  );
}

function formatRegionFreq(r: TypedRegion): string {
  if (r.freq_min_mhz == null || r.freq_max_mhz == null) return "—";
  return `${r.freq_min_mhz.toFixed(1)}–${r.freq_max_mhz.toFixed(1)} MHz`;
}

/** Confidence behind an event's dominant type: the best-typed matching detection. */
function typeConfidenceOf(ev: PredictedEvent): number | null {
  const matching = ev.detections.filter((d) => d.burst_type === ev.dominant_type);
  if (matching.length === 0) return null;
  return matching.reduce(
    (best, d) => Math.max(best, d.type_confidence ?? 0),
    0
  );
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
  // Burst-type stage output for this segment, when it ran. Carried on the
  // selection so the preview can list where in the spectrum each type was found.
  burstType?: string | null;
  regions?: TypedRegion[];
};

export function BurstPredictorClient() {
  // e-CALLISTO data for the current UTC day is often incomplete; default to the
  // previous day, the same convention the Archive page uses.
  const [date, setDate] = useState<string>(utcDateOffset(-1));
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [jobId, setJobId] = useState<string | null>(null);
  const [selectedDet, setSelectedDet] = useState<SelectedDet | null>(null);
  // Event-selection mode. false = corroboration criteria (the live-alert filter);
  // true = raw model output (every Burst-labelled segment). Toggling re-assembles
  // from the already-scored rows server-side, so it never re-scores.
  const [rawMode, setRawMode] = useState<boolean>(false);
  // Which classifier to score with, and whether to run the burst-type stage.
  // Both change the scores, so they only take effect on the next run — unlike
  // rawMode, which just re-assembles an existing result. null = server default,
  // until the model list arrives and pins an explicit choice.
  const [modelId, setModelId] = useState<string | null>(null);
  const [classifyTypes, setClassifyTypes] = useState<boolean | null>(null);
  // When set (deep-link from an alert: ?date=…), show that day's already-stored
  // real-time detections without re-scoring, until a fresh scan is run.
  const [deepLinkDate, setDeepLinkDate] = useState<string | null>(null);

  // Stations that recorded on the chosen day.
  const { data: stationsData, isLoading: stationsLoading } = useSWR(
    ["pred-stations", date],
    () => api.radioArchiveStations(date)
  );
  const stations = useMemo(() => stationsData?.stations ?? [], [stationsData]);

  // Available classifiers + the server's defaults. Static for the session, so it
  // never revalidates.
  const { data: modelsData } = useSWR("radio-models", api.radioModels, {
    revalidateOnFocus: false,
    revalidateIfStale: false,
  });
  const binaryModels = useMemo(
    () => (modelsData?.models ?? []).filter((m) => m.kind === "binary"),
    [modelsData]
  );
  const typeModel = useMemo(
    () => (modelsData?.models ?? []).find((m) => m.kind === "type") ?? null,
    [modelsData]
  );
  // Adopt the server defaults once, without clobbering a choice already made.
  useEffect(() => {
    if (!modelsData) return;
    setModelId((prev) => prev ?? modelsData.default_binary);
    setClassifyTypes((prev) => prev ?? modelsData.classify_types);
  }, [modelsData]);
  const activeModel = binaryModels.find((m) => m.id === modelId) ?? null;
  // Typing needs its checkpoint present; an unavailable CCMT disables the option.
  const typingPossible = !!typeModel?.available;
  const typingOn = typingPossible && classifyTypes === true;

  // Reset the run whenever the date changes.
  useEffect(() => {
    setJobId(null);
    setSelected(new Set());
    setSelectedDet(null);
  }, [date]);

  // Deep-link from an alert: ?date=YYYY-MM-DD pre-fills the date and flags the day
  // whose already-stored real-time detections should be shown (no re-scoring).
  // The actual fetch is driven by the SWR hook below so the mode toggle applies.
  useEffect(() => {
    const d = new URLSearchParams(window.location.search).get("date");
    if (!d) return;
    setDate(d);
    setDeepLinkDate(d);
  }, []);

  // Poll the prediction job while it runs. rawMode is part of the key so toggling
  // the mode re-fetches — the backend re-assembles from the cached scores in the
  // chosen mode, so switching never re-scores.
  const { data: job } = useSWR(
    jobId ? ["predict-job", jobId, rawMode] : null,
    () => api.burstPredictionJob(jobId as string, rawMode),
    {
      refreshInterval: (latest) => (latest?.status === "running" ? 1500 : 0),
      revalidateOnFocus: false,
      keepPreviousData: true,
    }
  );
  const running = job?.status === "running";

  // Alert deep-link view: the day's already-stored detections, re-assembled in the
  // chosen mode. Shown only before a fresh scan is started (jobId === null) and
  // while the date still matches the deep-link.
  const { data: storedResult } = useSWR(
    deepLinkDate && date === deepLinkDate && jobId === null
      ? ["pred-stored", deepLinkDate, rawMode]
      : null,
    () => api.burstPredictionStored(deepLinkDate as string, rawMode),
    { revalidateOnFocus: false }
  );

  // A finished job's result supersedes the stored deep-link view.
  const result =
    (job?.status === "done" ? job?.result ?? null : null) ?? storedResult ?? null;

  // Full alert/event history — the source of X-ray / SEP / geomagnetic rows for
  // the per-day .txt export (shares SWR cache with the Events page).
  const { data: alerts } = useSWR("alerts-latest", api.alertsLatest, {
    refreshInterval: 60000,
  });

  // Rows for the day export: X-ray / SEP / geomagnetic from the alert history,
  // and radio bursts from the current prediction result (so the export mirrors
  // what's on screen) — falling back to alert-history radio bursts when no
  // prediction for this date is loaded.
  const reportEvents = useMemo(() => {
    const fromAlerts = alertsToReportEvents(alerts ?? []);
    const predicted =
      result && result.date === date ? predictedToReportEvents(result) : [];
    return predicted.length
      ? [...fromAlerts.filter((e) => e.category !== "radio_burst"), ...predicted]
      : fromAlerts;
  }, [alerts, result, date]);

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
        burstType: first.burst_type,
        regions: first.regions,
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
    // Starting a job (jobId set) supersedes any alert-linked stored view.
    const res = await api.startBurstPrediction(
      date,
      [...selected],
      rawMode,
      modelId ?? undefined,
      typingPossible ? classifyTypes ?? undefined : false
    );
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

          <ModelPicker
            models={binaryModels}
            typeModel={typeModel}
            modelId={modelId}
            onModelChange={setModelId}
            classifyTypes={typingOn}
            onClassifyTypesChange={setClassifyTypes}
            disabled={running}
          />

          <label
            className="flex cursor-pointer select-none items-center gap-2 pb-1.5 text-xs text-slate-400"
            title="Raw model output shows every segment the model flags as a burst. Event-selection criteria keeps only multi-station corroborated events (the live-alert filter), which can hide bursts when few stations are selected."
          >
            <input
              type="checkbox"
              checked={rawMode}
              onChange={(e) => setRawMode(e.target.checked)}
              className="h-3.5 w-3.5 accent-accent-blue"
            />
            Raw model output
          </label>

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

          {/* Export this day's events (all types) as a .txt. Radio bursts come
              from the current prediction; other types from the alert history. */}
          <ExportEventsButton events={reportEvents} fixedDay={date} className="pb-0.5" />
        </div>

        {/* Mode hint — explains what the Raw model output checkbox changes. */}
        <p className="mt-2 text-[10px] text-slate-600">
          {rawMode
            ? "Raw mode: every segment the model labels a burst is shown — no multi-station corroboration filter, so nothing is dropped."
            : "Criteria mode: only multi-station corroborated events are shown (the live-alert filter). Tick “Raw model output” to see every burst the model flags."}
        </p>
        {activeModel && (
          <p className="mt-1 text-[10px] text-slate-600">
            {activeModel.name}: {activeModel.description}
            {activeModel.threshold != null
              ? ` Decision threshold ${activeModel.threshold}.`
              : ""}
            {typingOn && typeModel
              ? ` Burst types come from ${typeModel.name}, which classifies bright regions inside each burst — treat them as estimates, not the official list.`
              : ""}
          </p>
        )}

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
                <div
                  role="progressbar"
                  aria-valuenow={pct}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label="Burst scan progress"
                  className="h-1.5 w-full overflow-hidden rounded bg-surface-muted"
                >
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

/** Binary-model selector plus the burst-type toggle. */
function ModelPicker({
  models,
  typeModel,
  modelId,
  onModelChange,
  classifyTypes,
  onClassifyTypesChange,
  disabled,
}: {
  models: ModelInfo[];
  typeModel: ModelInfo | null;
  modelId: string | null;
  onModelChange: (id: string) => void;
  classifyTypes: boolean;
  onClassifyTypesChange: (on: boolean) => void;
  disabled?: boolean;
}) {
  const typeUnavailable = !!typeModel && !typeModel.available;
  return (
    <div className="flex flex-col gap-1">
      <label className="flex flex-col gap-1 text-xs text-slate-500">
        Model
        <select
          value={modelId ?? ""}
          disabled={disabled || models.length === 0}
          onChange={(e) => onModelChange(e.target.value)}
          className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-sm text-slate-300 outline-none focus:border-accent-blue disabled:opacity-50"
        >
          {models.length === 0 && <option value="">Loading…</option>}
          {models.map((m) => (
            <option
              key={m.id}
              value={m.id}
              disabled={!m.available}
              title={m.available ? m.description : "Checkpoint missing — run git lfs pull"}
            >
              {m.name}
              {m.threshold != null ? ` · t=${m.threshold}` : ""}
              {m.available ? "" : " (unavailable)"}
            </option>
          ))}
        </select>
      </label>
      <label
        className={clsx(
          "flex select-none items-center gap-2 text-[11px]",
          typeUnavailable ? "cursor-not-allowed text-slate-600" : "cursor-pointer text-slate-400"
        )}
        title={
          typeUnavailable
            ? `${typeModel?.name} checkpoint missing — run git lfs pull`
            : "Classify the burst type (Type II / Type III / Other) of every segment flagged as a burst. Adds a second pass, so a run takes longer."
        }
      >
        <input
          type="checkbox"
          checked={classifyTypes}
          disabled={disabled || typeUnavailable || !typeModel}
          onChange={(e) => onClassifyTypesChange(e.target.checked)}
          className="h-3.5 w-3.5 accent-accent-blue"
        />
        Classify burst types{typeModel ? ` (${typeModel.name})` : ""}
      </label>
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
  const typeEntries = Object.entries(result.type_counts ?? {}).sort(
    (a, b) => b[1] - a[1]
  );
  const stats: [string, string | number][] = [
    ["Segments scored", result.total_files],
    ["Burst files", result.burst_count],
    ["Predicted events", result.event_count],
    ["Official events", result.official_count],
    ["Matched", `${result.matched_count}/${result.event_count}`],
  ];
  return (
    <div className="space-y-2">
      {/* Which model produced these numbers — the whole point of the selector. */}
      <div className="flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        <span className="rounded bg-accent-blue/15 px-2 py-0.5 font-medium text-accent-blue">
          {result.model_name || result.model_id}
        </span>
        {result.classify_types ? (
          typeEntries.length > 0 ? (
            <span className="flex items-center gap-1">
              Burst types:
              {typeEntries.map(([type, count]) => (
                <span key={type} className="flex items-center gap-0.5">
                  <TypeChip type={type} short />
                  <span className="text-slate-400">×{count}</span>
                </span>
              ))}
            </span>
          ) : (
            <span>
              Burst typing on — no burst had a region clear enough to classify.
            </span>
          )
        ) : (
          <span>Burst typing off.</span>
        )}
      </div>
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
      <h2 className="mb-3 flex items-center gap-2 text-xs uppercase tracking-wider text-slate-500">
        Predicted Bursts (model)
        <span
          className={clsx(
            "rounded px-1.5 py-0.5 text-[10px] normal-case tracking-normal",
            result.raw
              ? "bg-accent-yellow/15 text-accent-yellow"
              : "bg-surface-muted text-slate-400"
          )}
        >
          {result.raw ? "raw" : "criteria"}
        </span>
      </h2>
      {result.events.length === 0 ? (
        <div className="flex h-32 items-center justify-center px-4 text-center text-xs text-slate-600">
          {result.raw
            ? "The model flagged no bursts for the selected stations."
            : "No corroborated bursts for the selected stations. Tick “Raw model output” above to see every burst the model flagged."}
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
        {ev.dominant_type && (
          <TypeChip type={ev.dominant_type} confidence={typeConfidenceOf(ev)} />
        )}
        <span className="text-slate-500">
          {ev.n_stations} st · {ev.n_detections} det
        </span>
        {/* Stations disagreeing on the type is worth surfacing, not hiding. */}
        {Object.keys(ev.type_counts ?? {}).length > 1 && (
          <span
            className="text-[10px] text-slate-600"
            title={Object.entries(ev.type_counts)
              .map(([t, n]) => `${t} ×${n}`)
              .join(", ")}
          >
            mixed
          </span>
        )}
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
                    burstType: d.burst_type,
                    regions: d.regions,
                  })
                }
                className={clsx(
                  "flex w-full items-center gap-2 rounded px-2 py-1 text-left text-[11px]",
                  selectedFile === d.filename ? "bg-accent-blue/15" : "hover:bg-surface-muted"
                )}
              >
                <span className="w-20 font-mono text-slate-300">{d.time}</span>
                <span className="flex-1 truncate text-slate-400">{d.station}</span>
                {d.burst_type && (
                  <TypeChip type={d.burst_type} confidence={d.type_confidence} short />
                )}
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
          <span className="flex items-center gap-2 font-mono text-xs text-slate-400">
            {det.station} · {det.time} UTC
            {det.probability != null ? ` · p=${det.probability.toFixed(3)}` : ""}
            {det.burstType && <TypeChip type={det.burstType} />}
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
      {det && <TypedRegionTable det={det} />}
    </section>
  );
}

/** Where inside the segment the burst-type stage found each classified region.
 *
 * A table rather than boxes drawn on the image: the preview is rendered
 * server-side with axis margins, so overlaying by pixel fraction would not line
 * up with the plotted data area. */
function TypedRegionTable({ det }: { det: SelectedDet }) {
  const regions = det.regions ?? [];
  if (regions.length === 0) {
    return (
      <p className="mt-3 text-[10px] text-slate-600">
        {det.burstType
          ? // Region geometry is not stored, so a detection loaded from the
            // background scan keeps its type but not where that type was found.
            "Region detail isn't kept for stored detections — re-run the scan for this day to see where the type was found."
          : "No burst-type regions for this segment — either typing was off, or no bright region was large enough to classify reliably."}
      </p>
    );
  }
  return (
    <div className="mt-3">
      <div className="mb-1 flex items-baseline justify-between">
        <h3 className="text-[10px] uppercase tracking-wider text-slate-500">
          Typed regions ({regions.length})
        </h3>
        <span className="text-[10px] text-slate-600">
          Bright regions classified by CCMT — locations are approximate
        </span>
      </div>
      <div className="overflow-x-auto rounded border border-surface-border">
        <table className="w-full min-w-[28rem] text-left text-[11px]">
          <thead className="bg-surface-muted/60 text-slate-500">
            <tr>
              <th className="px-2 py-1 font-medium">Frequency</th>
              <th className="px-2 py-1 font-medium">Time in segment</th>
              <th className="px-2 py-1 font-medium">Type</th>
              <th className="px-2 py-1 text-right font-medium">Confidence</th>
            </tr>
          </thead>
          <tbody className="text-slate-400">
            {regions.map((r, i) => (
              <tr key={i} className="border-t border-surface-border/60">
                <td className="px-2 py-1 font-mono">{formatRegionFreq(r)}</td>
                <td className="px-2 py-1 font-mono">
                  +{r.start_seconds}–{r.end_seconds}s
                </td>
                <td className="px-2 py-1">
                  {r.burst_type ? <TypeChip type={r.burst_type} /> : "—"}
                </td>
                <td className="px-2 py-1 text-right font-mono">
                  {r.confidence != null ? `${(r.confidence * 100).toFixed(0)}%` : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
