"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { api } from "@/lib/api";
import { DataSourcePicker } from "@/components/analysis/DataSourcePicker";
import { PlotControls } from "@/components/analysis/PlotControls";
import { DifferenceControls } from "@/components/analysis/DifferenceControls";
import { CompositeControls } from "@/components/analysis/CompositeControls";
import { ActiveRegionControls } from "@/components/analysis/ActiveRegionControls";
import { MovieControls } from "@/components/analysis/MovieControls";
import { MovieResult } from "@/components/analysis/MovieResult";
import { PlotView } from "@/components/analysis/PlotView";
import type { AnalysisSession, PlotParams } from "@/lib/types";

type Tool = "plot" | "difference" | "composite" | "activeRegions" | "movie";

const TOOLS: { key: Tool; label: string; multiOnly?: boolean }[] = [
  { key: "plot", label: "Plot" },
  { key: "difference", label: "Difference", multiOnly: true },
  { key: "composite", label: "Composite" },
  { key: "activeRegions", label: "Active Regions" },
  { key: "movie", label: "Movie", multiOnly: true },
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

  const { data: options } = useSWR("analysis-options", api.analysisOptions, {
    revalidateOnFocus: false,
  });

  // Restore a session from ?session=<id> so a refresh / shared link reopens it.
  useEffect(() => {
    const id = new URLSearchParams(window.location.search).get("session");
    if (!id) return;
    api
      .analysisSession(id)
      .then((s) => {
        setSession(s);
        setFrame(0);
        setParams(DEFAULT_PLOT_PARAMS);
        setBaseIndex(0);
        setTool("plot");
      })
      .catch(() => {});
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
  }

  // Switch tool, nudging the frame so a running difference has a previous frame.
  function selectTool(t: Tool) {
    setTool(t);
    if (t === "difference" && diffType === "running" && frame === 0 && session && session.n_frames > 1) {
      setFrame(1);
    }
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
        <DataSourcePicker options={options} onSession={onSession} />

        {session && (
          <div className="grid grid-cols-2 gap-1 rounded-lg border border-surface-border bg-surface-card p-1">
            {TOOLS.map(({ key, label, multiOnly }) => {
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

        {session && tool === "plot" && (
          <PlotControls params={params} options={options} onChange={patch} />
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
        ) : (
          <PlotView session={session} renderUrl={renderUrl} downloadUrl={downloadUrl} />
        )}
      </div>
    </div>
  );
}
