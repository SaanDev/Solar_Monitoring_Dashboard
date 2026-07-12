"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { api, apiUrl } from "@/lib/api";
import { DataSourcePicker } from "@/components/analysis/DataSourcePicker";
import { PlotControls } from "@/components/analysis/PlotControls";
import { CoronagraphControls } from "@/components/analysis/CoronagraphControls";
import { DifferenceControls } from "@/components/analysis/DifferenceControls";
import { CompositeControls } from "@/components/analysis/CompositeControls";
import { ActiveRegionControls } from "@/components/analysis/ActiveRegionControls";
import { MovieControls } from "@/components/analysis/MovieControls";
import { MovieResult } from "@/components/analysis/MovieResult";
import { PlotView } from "@/components/analysis/PlotView";
import { ImageCanvas } from "@/components/analysis/ImageCanvas";
import { MeasureControls, type MeasureMode } from "@/components/analysis/MeasureControls";
import { LightCurveControls } from "@/components/analysis/LightCurveControls";
import { HeightTimeControls, type HtPick } from "@/components/analysis/HeightTimeControls";
import { MiniChart } from "@/components/analysis/MiniChart";
import { JMapControls } from "@/components/analysis/JMapControls";
import { VectorFieldControls, type VectorOptions } from "@/components/analysis/VectorFieldControls";
import {
  CompareViewpointControls,
  type SessionRef,
} from "@/components/analysis/CompareViewpointControls";
import type {
  AnalysisSession,
  HeightTimeResult,
  LightcurveResult,
  PlotParams,
  ScienceClass,
} from "@/lib/types";

type Tool =
  | "plot"
  | "inspect"
  | "measure"
  | "lightcurve"
  | "heightTime"
  | "difference"
  | "composite"
  | "activeRegions"
  | "movie"
  | "jmap"
  | "vectorField"
  | "compare";

// Tools gated by science class mirror the desktop tool's instrument-adaptive
// sidebar: composites/active regions only make sense on disk imagers.
const TOOLS: {
  key: Tool;
  label: string;
  multiOnly?: boolean;
  classes?: ScienceClass[];
}[] = [
  { key: "plot", label: "Plot" },
  { key: "inspect", label: "Inspect" },
  { key: "measure", label: "Measure" },
  { key: "lightcurve", label: "Light Curve", multiOnly: true },
  { key: "heightTime", label: "Height–Time", multiOnly: true },
  { key: "difference", label: "Difference", multiOnly: true },
  { key: "composite", label: "Composite", classes: ["disk_euv", "magnetograph"] },
  { key: "activeRegions", label: "Active Regions", classes: ["disk_euv", "magnetograph"] },
  { key: "movie", label: "Movie", multiOnly: true },
  { key: "jmap", label: "J-map", multiOnly: true, classes: ["coronagraph", "heliospheric"] },
  { key: "vectorField", label: "Vector Field", classes: ["magnetograph"] },
  { key: "compare", label: "Compare View" },
];

const DEFAULT_PLOT_PARAMS: PlotParams = {
  cmap: "auto",
  scale: "linear",
  clip_low: 1,
  clip_high: 99.9,
  vmin: null,
  vmax: null,
  crop: false,
  bl_x: -600,
  bl_y: -600,
  tr_x: 600,
  tr_y: 600,
  draw_limb: false,
  draw_grid: false,
  colorbar: true,
  nrgf: false,
  grid_frame: "",
};

/** Debounce a value so control drags don't spam the render endpoint. */
function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function DataAnalysisClient() {
  const [session, setSession] = useState<AnalysisSession | null>(null);
  const [frame, setFrame] = useState(0);
  const [params, setParams] = useState<PlotParams>(DEFAULT_PLOT_PARAMS);
  const [tool, setTool] = useState<Tool>("plot");
  const [diffType, setDiffType] = useState<"running" | "base">("running");
  const [baseIndex, setBaseIndex] = useState(0);
  const [contourLevel, setContourLevel] = useState(100);
  const [arMethod, setArMethod] = useState<"hek" | "threshold">("hek");
  const [thresholdPct, setThresholdPct] = useState(95);
  const [movieFmt, setMovieFmt] = useState<"mp4" | "gif">("mp4");
  const [movieFps, setMovieFps] = useState(8);
  const [movieMode, setMovieMode] = useState<"plot" | "difference">("plot");
  const [movieJobId, setMovieJobId] = useState<string | null>(null);
  const [movieResultUrl, setMovieResultUrl] = useState<string | null>(null);
  const [movieBuilding, setMovieBuilding] = useState(false);
  const [inspectMode, setInspectMode] = useState<"plot" | "running">("plot");
  // Interactive picks on the canvas (shared by measure / light-curve tools).
  const [picks, setPicks] = useState<{ px: number; py: number }[]>([]);
  const [measureMode, setMeasureMode] = useState<MeasureMode>("ruler");
  const [lcResult, setLcResult] = useState<LightcurveResult | null>(null);
  // CME height–time picks span frames (one leading-edge pick per frame).
  const [htPicks, setHtPicks] = useState<HtPick[]>([]);
  const [htAutoAdvance, setHtAutoAdvance] = useState(true);
  const [htResult, setHtResult] = useState<HeightTimeResult | null>(null);
  // Specialized science state.
  const [jmapUrl, setJmapUrl] = useState<string | null>(null);
  const [vecPrepared, setVecPrepared] = useState(false);
  const [vecOptions, setVecOptions] = useState<VectorOptions>({
    arrows: true,
    streamlines: false,
    magnitude: false,
    gridStep: 64,
    minGauss: 250,
  });
  const [sessionHistory, setSessionHistory] = useState<SessionRef[]>([]);
  const [compareOtherId, setCompareOtherId] = useState("");
  const [compareOtherFrame, setCompareOtherFrame] = useState(0);
  const [compareBlink, setCompareBlink] = useState(true);

  const { data: options } = useSWR("analysis-options", api.analysisOptions, {
    revalidateOnFocus: false,
  });

  // Restore a session from ?session=<id> so a refresh / shared link reopens it.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("session");
    if (!id) return;
    api
      .analysisSession(id)
      .then((s) => onSession(s))
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function onSession(s: AnalysisSession) {
    setSession(s);
    setFrame(0);
    setParams(DEFAULT_PLOT_PARAMS);
    setBaseIndex(0);
    setTool("plot");
    setMovieJobId(null);
    setMovieResultUrl(null);
    setMovieBuilding(false);
    setPicks([]);
    setLcResult(null);
    setHtPicks([]);
    setHtResult(null);
    setJmapUrl(null);
    setVecPrepared(false);
    setCompareOtherId("");
    setCompareOtherFrame(0);
    // Remember every session loaded this visit (compare-viewpoint candidates).
    const label = `${s.instrument || s.observatory || "?"} ${s.measurement} · ${
      s.reference_time ? s.reference_time.slice(0, 16).replace("T", " ") : s.id.slice(0, 8)
    }`;
    setSessionHistory((prev) =>
      prev.some((p) => p.id === s.id)
        ? prev
        : [...prev, { id: s.id, label, nFrames: s.n_frames }]
    );
  }

  // Switch tool, nudging the frame so a running difference has a previous frame.
  function selectTool(t: Tool) {
    setTool(t);
    setPicks([]);
    if (t === "difference" && diffType === "running" && frame === 0 && session && session.n_frames > 1) {
      setFrame(1);
    }
    if (t === "heightTime" && inspectMode === "running" && frame === 0 && session && session.n_frames > 1) {
      setFrame(1);
    }
  }

  // Two-point picks: a third click starts a fresh measurement.
  function onCanvasPick(px: number, py: number) {
    setPicks((prev) => (prev.length >= 2 ? [{ px, py }] : [...prev, { px, py }]));
  }

  // Height–time: record the leading-edge pick and step to the next frame.
  function onHtPick(px: number, py: number) {
    setHtPicks((prev) => [...prev, { frame, px, py }]);
    if (htAutoAdvance && session && frame < session.n_frames - 1) setFrame(frame + 1);
  }

  function patch(p: Partial<PlotParams>) {
    setParams((prev) => ({ ...prev, ...p }));
  }

  async function buildMovie() {
    if (!session) return;
    setMovieBuilding(true);
    setMovieResultUrl(null);
    setMovieJobId(null);
    try {
      const job = await api.analysisMovie(session.id, movieFmt, movieFps, movieMode, params);
      setMovieJobId(job.job_id);
    } catch {
      setMovieBuilding(false);
    }
  }

  // Short debounce keeps the preview live while dragging without flooding renders.
  const debounced = useDebounced(params, 150);
  let renderUrl: string | null = null;
  let downloadUrl: string | null = null;
  if (session) {
    const id = session.id;
    if (tool === "difference") {
      renderUrl = api.analysisDifferenceUrl(id, frame, diffType, baseIndex, debounced);
      downloadUrl = api.analysisDifferenceDownloadUrl(id, frame, diffType, baseIndex, debounced);
    } else if (tool === "composite") {
      renderUrl = api.analysisCompositeUrl(id, frame, contourLevel, debounced);
      downloadUrl = api.analysisCompositeDownloadUrl(id, frame, contourLevel, debounced);
    } else if (tool === "activeRegions") {
      renderUrl = api.analysisActiveRegionsUrl(id, frame, arMethod, thresholdPct, debounced);
      downloadUrl = api.analysisActiveRegionsDownloadUrl(id, frame, arMethod, thresholdPct, debounced);
    } else {
      renderUrl = api.analysisRenderUrl(id, frame, debounced);
      downloadUrl = api.analysisDownloadUrl(id, frame, debounced);
    }
  }

  const multiFrame = !!session && session.n_frames > 1;

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-1">
        <DataSourcePicker
          options={options}
          onSession={onSession}
          onRestore={(s, restoredPicks, display) => {
            onSession(s);
            setHtPicks(restoredPicks);
            // Restore saved display state on top of the defaults.
            setParams((prev) => ({ ...prev, ...(display as Partial<PlotParams>) }));
          }}
        />

        {session && (
          <div className="grid grid-cols-2 gap-1 rounded-lg border border-surface-border bg-surface-card p-1">
            {TOOLS.filter(
              ({ classes }) => !classes || classes.includes(session.science_class)
            ).map(({ key, label, multiOnly }) => {
              const disabled = !!multiOnly && !multiFrame;
              return (
                <button
                  key={key}
                  disabled={disabled}
                  title={disabled ? "Load a multi-frame sequence to enable this" : undefined}
                  onClick={() => selectTool(key)}
                  className={clsx(
                    "rounded px-2 py-1.5 text-xs transition-colors",
                    tool === key
                      ? "bg-accent-blue/20 text-accent-blue"
                      : "text-slate-500 hover:bg-surface-muted hover:text-slate-300",
                    disabled && "cursor-not-allowed opacity-40 hover:bg-transparent hover:text-slate-500"
                  )}
                >
                  {label}
                </button>
              );
            })}
          </div>
        )}

        {multiFrame && (
          <div className="rounded-lg border border-surface-border bg-surface-card p-4">
            <label className="mb-1 block text-xs text-slate-500">
              Frame {frame + 1} / {session!.n_frames}
            </label>
            <input
              type="range"
              min={0}
              max={session!.n_frames - 1}
              step={1}
              value={frame}
              onChange={(e) => setFrame(parseInt(e.target.value, 10))}
              className="w-full accent-accent-blue"
            />
          </div>
        )}

        {session && (tool === "plot" || tool === "inspect") && (
          <>
            {tool === "inspect" && multiFrame && (
              <div className="rounded-lg border border-surface-border bg-surface-card p-4">
                <label className="mb-1 block text-xs text-slate-500">Canvas content</label>
                <div className="flex gap-1">
                  {(
                    [
                      ["plot", "Frames"],
                      ["running", "Running diff"],
                    ] as const
                  ).map(([m, label]) => (
                    <button
                      key={m}
                      onClick={() => {
                        setInspectMode(m);
                        if (m === "running" && frame === 0 && session.n_frames > 1) setFrame(1);
                      }}
                      className={clsx(
                        "flex-1 rounded px-2 py-1 text-xs transition-colors",
                        inspectMode === m
                          ? "bg-accent-blue/20 text-accent-blue"
                          : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <PlotControls params={params} options={options} onChange={patch} />
            {session.science_class === "coronagraph" && (
              <CoronagraphControls params={params} onChange={patch} />
            )}
            <div className="space-y-2 rounded-lg border border-surface-border bg-surface-card p-4">
              <h2 className="text-xs uppercase tracking-wider text-slate-500">Export</h2>
              <a
                href={api.analysisExportFitsUrl(session.id, frame, params)}
                className="block w-full rounded bg-surface-muted px-2 py-1.5 text-center text-xs text-slate-300 transition-colors hover:bg-surface-border"
                download
              >
                Frame as FITS{params.crop ? " (cropped)" : ""}
              </a>
              <a
                href={api.analysisRegionsCsvUrl(session.id, frame)}
                className="block w-full rounded bg-surface-muted px-2 py-1.5 text-center text-xs text-slate-300 transition-colors hover:bg-surface-border"
                download
              >
                Bright regions as CSV
              </a>
              <button
                onClick={() =>
                  api
                    .analysisSessionExport(session.id, htPicks, params as unknown as Record<string, unknown>)
                    .catch(() => {})
                }
                className="w-full rounded bg-surface-muted px-2 py-1.5 text-xs text-slate-300 transition-colors hover:bg-surface-border"
                title="Bundle frames + display state + height–time picks; opens in the desktop e-CALLISTO FITS Analyzer too"
              >
                Save session (.ecsolar)
              </button>
            </div>
          </>
        )}
        {session && tool === "measure" && (
          <MeasureControls
            sessionId={session.id}
            frame={frame}
            mode={measureMode}
            onMode={setMeasureMode}
            picks={picks}
            onClear={() => setPicks([])}
          />
        )}
        {session && tool === "lightcurve" && (
          <LightCurveControls
            sessionId={session.id}
            picks={picks}
            onClear={() => setPicks([])}
            onResult={setLcResult}
          />
        )}
        {session && tool === "heightTime" && (
          <>
            <div className="rounded-lg border border-surface-border bg-surface-card p-4">
              <label className="mb-1 block text-xs text-slate-500">Canvas content</label>
              <div className="flex gap-1">
                {(
                  [
                    ["plot", "Frames"],
                    ["running", "Running diff"],
                  ] as const
                ).map(([m, label]) => (
                  <button
                    key={m}
                    onClick={() => {
                      setInspectMode(m);
                      if (m === "running" && frame === 0 && session.n_frames > 1) setFrame(1);
                    }}
                    className={clsx(
                      "flex-1 rounded px-2 py-1 text-xs transition-colors",
                      inspectMode === m
                        ? "bg-accent-blue/20 text-accent-blue"
                        : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
                    )}
                  >
                    {label}
                  </button>
                ))}
              </div>
            </div>
            <HeightTimeControls
              sessionId={session.id}
              picks={htPicks}
              autoAdvance={htAutoAdvance}
              onAutoAdvance={setHtAutoAdvance}
              onUndo={() => setHtPicks((prev) => prev.slice(0, -1))}
              onClear={() => setHtPicks([])}
              onResult={setHtResult}
            />
            {session.science_class === "coronagraph" && (
              <CoronagraphControls params={params} onChange={patch} />
            )}
          </>
        )}
        {session && tool === "jmap" && (
          <JMapControls sessionId={session.id} nFrames={session.n_frames} onResult={setJmapUrl} />
        )}
        {session && tool === "vectorField" && (
          <VectorFieldControls
            sessionId={session.id}
            frame={frame}
            prepared={vecPrepared}
            onPrepared={() => setVecPrepared(true)}
            options={vecOptions}
            onChange={(o) => setVecOptions((prev) => ({ ...prev, ...o }))}
            jsocEnabled={options?.jsoc_enabled ?? false}
          />
        )}
        {session && tool === "compare" && (
          <CompareViewpointControls
            sessionId={session.id}
            frame={frame}
            history={sessionHistory}
            otherId={compareOtherId}
            otherFrame={compareOtherFrame}
            onOther={setCompareOtherId}
            onOtherFrame={setCompareOtherFrame}
            blinking={compareBlink}
            onBlinking={setCompareBlink}
          />
        )}
        {session && tool === "difference" && (
          <DifferenceControls
            params={params}
            options={options}
            diffType={diffType}
            baseIndex={baseIndex}
            nFrames={session.n_frames}
            onChange={patch}
            onDiffType={setDiffType}
            onBaseIndex={setBaseIndex}
          />
        )}
        {session && tool === "composite" && (
          <CompositeControls
            params={params}
            options={options}
            contourLevel={contourLevel}
            onChange={patch}
            onContourLevel={setContourLevel}
          />
        )}
        {session && tool === "activeRegions" && (
          <ActiveRegionControls
            params={params}
            options={options}
            method={arMethod}
            thresholdPct={thresholdPct}
            onChange={patch}
            onMethod={setArMethod}
            onThreshold={setThresholdPct}
          />
        )}
        {session && tool === "movie" && (
          <MovieControls
            params={params}
            options={options}
            fmt={movieFmt}
            fps={movieFps}
            mode={movieMode}
            building={movieBuilding}
            onChange={patch}
            onFmt={setMovieFmt}
            onFps={setMovieFps}
            onMode={setMovieMode}
            onBuild={buildMovie}
          />
        )}
      </div>
      <div className="lg:col-span-2">
        {tool === "movie" ? (
          <MovieResult
            jobId={movieJobId}
            fmt={movieFmt}
            resultUrl={movieResultUrl}
            onResult={(url) => {
              setMovieResultUrl(url);
              setMovieBuilding(false);
            }}
            onError={() => setMovieBuilding(false)}
          />
        ) : tool === "inspect" && session ? (
          <ImageCanvas
            session={session}
            frame={frame}
            params={debounced}
            mode={inspectMode}
            hint="Hover for live coordinates · click anywhere for the exact WCS readout (R☉, position angle, lon/lat, pixel value)."
          />
        ) : tool === "jmap" && session ? (
          <div className="rounded-lg border border-surface-border bg-surface-card p-4">
            <h2 className="mb-2 text-xs uppercase tracking-wider text-slate-500">J-map</h2>
            {jmapUrl ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={apiUrl(jmapUrl)} alt="J-map" className="w-full rounded" />
            ) : (
              <p className="py-16 text-center text-xs text-slate-600">
                Configure the slit and build the J-map.
              </p>
            )}
          </div>
        ) : tool === "vectorField" && session ? (
          <div className="rounded-lg border border-surface-border bg-surface-card p-4">
            <h2 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
              HMI Vector Field
            </h2>
            {vecPrepared ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={api.analysisVectorFieldUrl(session.id, frame, vecOptions, debounced)}
                alt="vector field"
                className="w-full rounded"
              />
            ) : (
              <p className="py-16 text-center text-xs text-slate-600">
                Prepare the hmi.B_720s vector data first (left panel).
              </p>
            )}
          </div>
        ) : tool === "compare" && session ? (
          <BlinkView
            primaryUrl={
              compareOtherId
                ? api.analysisCompareUrl(session.id, frame, compareOtherId, compareOtherFrame, "primary", debounced)
                : null
            }
            reprojectedUrl={
              compareOtherId
                ? api.analysisCompareUrl(session.id, frame, compareOtherId, compareOtherFrame, "reprojected", debounced)
                : null
            }
            blinking={compareBlink}
          />
        ) : tool === "heightTime" && session ? (
          <div className="space-y-4">
            <ImageCanvas
              session={session}
              frame={frame}
              params={debounced}
              mode={inspectMode}
              onPick={onHtPick}
              markers={htPicks.map((p, i) => ({
                px: p.px,
                py: p.py,
                label: String(i + 1),
                color: p.frame === frame ? "#f59e0b" : "#64748b",
              }))}
              hint="Click the CME leading edge; the frame auto-advances after each pick."
            />
            {htResult && htResult.points.filter((p) => p.time).length >= 2 && (
              <div className="rounded-lg border border-surface-border bg-surface-card p-4">
                <h2 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
                  Height–time profile
                  {htResult.speed_km_s != null && ` · v = ${htResult.speed_km_s.toFixed(0)} km/s`}
                </h2>
                <MiniChart
                  x={htResult.points
                    .filter((p) => p.time)
                    .map((p) => new Date(p.time + "Z").getTime() / 1000)}
                  y={htResult.points.filter((p) => p.time).map((p) => p.r_rsun)}
                  height={200}
                  xLabel="time (UTC)"
                  yLabel="height (R☉)"
                  formatX={(v) => new Date(v * 1000).toISOString().slice(11, 16)}
                />
              </div>
            )}
          </div>
        ) : (tool === "measure" || tool === "lightcurve") && session ? (
          <div className="space-y-4">
            <ImageCanvas
              session={session}
              frame={frame}
              params={debounced}
              onPick={onCanvasPick}
              markers={picks.map((p, i) => ({
                px: p.px,
                py: p.py,
                label: String(i + 1),
                color: "#f59e0b",
              }))}
              segments={
                tool === "measure" &&
                measureMode !== "region" &&
                picks.length === 2
                  ? [{ x1: picks[0].px, y1: picks[0].py, x2: picks[1].px, y2: picks[1].py }]
                  : []
              }
              rects={
                (tool === "lightcurve" || measureMode === "region") && picks.length === 2
                  ? [
                      {
                        x: Math.min(picks[0].px, picks[1].px),
                        y: Math.min(picks[0].py, picks[1].py),
                        w: Math.abs(picks[1].px - picks[0].px),
                        h: Math.abs(picks[1].py - picks[0].py),
                      },
                    ]
                  : []
              }
              hint={
                tool === "measure"
                  ? "Click two points to measure."
                  : "Click two opposite corners of the region, then Extract."
              }
            />
            {tool === "lightcurve" && lcResult && (
              <div className="rounded-lg border border-surface-border bg-surface-card p-4">
                <h2 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
                  ROI light curve · {lcResult.statistic} [{lcResult.unit}]
                </h2>
                <MiniChart
                  x={lcResult.times.map((t) => (t ? new Date(t + "Z").getTime() / 1000 : NaN))}
                  y={lcResult.values}
                  height={220}
                  xLabel="time (UTC)"
                  yLabel={lcResult.unit}
                  formatX={(v) => new Date(v * 1000).toISOString().slice(11, 16)}
                  markers={
                    lcResult.peak_time
                      ? [
                          {
                            x: new Date(lcResult.peak_time + "Z").getTime() / 1000,
                            color: "#22d3ee",
                            label: "EUV peak",
                          },
                        ]
                      : []
                  }
                  bands={
                    lcResult.radio_start && lcResult.radio_end
                      ? [
                          {
                            x0: new Date(lcResult.radio_start + "Z").getTime() / 1000,
                            x1: new Date(lcResult.radio_end + "Z").getTime() / 1000,
                            color: "#f59e0b",
                            label: "radio burst",
                          },
                        ]
                      : []
                  }
                />
              </div>
            )}
          </div>
        ) : (
          <PlotView session={session} renderUrl={renderUrl} downloadUrl={downloadUrl} />
        )}
      </div>
    </div>
  );
}

/** Two-viewpoint blink: alternate the primary and reprojected renders. */
function BlinkView({
  primaryUrl,
  reprojectedUrl,
  blinking,
}: {
  primaryUrl: string | null;
  reprojectedUrl: string | null;
  blinking: boolean;
}) {
  const [showPrimary, setShowPrimary] = useState(true);

  useEffect(() => {
    if (!blinking || !primaryUrl || !reprojectedUrl) return;
    const t = setInterval(() => setShowPrimary((p) => !p), 900);
    return () => clearInterval(t);
  }, [blinking, primaryUrl, reprojectedUrl]);

  if (!primaryUrl || !reprojectedUrl) {
    return (
      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <h2 className="mb-2 text-xs uppercase tracking-wider text-slate-500">Compare Viewpoint</h2>
        <p className="py-16 text-center text-xs text-slate-600">
          Pick another loaded session in the left panel to compare viewpoints.
        </p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="mb-2 text-xs uppercase tracking-wider text-slate-500">
        Compare Viewpoint · showing {showPrimary || !blinking ? "primary" : "reprojected"}
      </h2>
      {/* Both images stay mounted so the blink never waits on a re-render. */}
      <div className="relative">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={primaryUrl} alt="primary view" className="w-full rounded" />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={reprojectedUrl}
          alt="reprojected view"
          className={clsx(
            "absolute inset-0 w-full rounded transition-opacity duration-150",
            showPrimary && blinking ? "opacity-0" : blinking ? "opacity-100" : "opacity-0"
          )}
        />
      </div>
      {!blinking && (
        <p className="mt-2 text-[10px] text-slate-500">
          Blink is off — showing the primary view. Enable blink in the left panel.
        </p>
      )}
    </div>
  );
}
