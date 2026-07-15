"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import useSWR from "swr";
import { Download } from "lucide-react";
import { api } from "@/lib/api";
import { loadWorkflow, saveWorkflow } from "@/lib/workflowStorage";
import type {
  AnalyzerSession,
  RenderParams,
  ShockFitResult,
  ShockSession,
} from "@/lib/types";
import { BurstLassoOverlay } from "./BurstLassoOverlay";
import { MaxIntensityScatter } from "./MaxIntensityScatter";
import { ShockControls } from "./ShockControls";
import { ShockResults } from "./ShockResults";

interface Props {
  session: AnalyzerSession;
  params: RenderParams;
  restored?: ShockSession | null;
  onRestoredConsumed?: () => void;
}

interface Points {
  time: number[];
  freq: number[];
  channels: number[];
}

// Per-session, per-tab persistence of the shock-analysis work so a refresh or a
// Spectrum/Shock mode toggle (which unmounts this panel) reopens the same
// extracted points and fit. Keyed by session id; the backend keeps the fit
// artifacts for that id across a client reload.
const shockKey = (id: string) => `e-callisto-shock-${id}`;

interface ShockSnapshot {
  extracted: Points | null;
  kept: Points | null;
  fold: number;
  harmonic: boolean;
  fit: ShockFitResult | null;
  note: string;
  bust: number;
}

function Step({ n, title, children }: { n: number; title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4">
      <h3 className="mb-3 flex items-center gap-2 text-sm font-medium text-slate-200">
        <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent-blue/20 text-[11px] text-accent-blue">
          {n}
        </span>
        {title}
      </h3>
      {children}
    </div>
  );
}

export function ShockAnalysisPanel({ session, params, restored, onRestoredConsumed }: Props) {
  const [extracted, setExtracted] = useState<Points | null>(null);
  const [kept, setKept] = useState<Points | null>(null);
  const [fold, setFold] = useState(1);
  const [harmonic, setHarmonic] = useState(false);
  const [fit, setFit] = useState<ShockFitResult | null>(null);
  const [bust, setBust] = useState<number>(0);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string>("");
  const [error, setError] = useState<string>("");

  const spectrogramUrl = api.analyzerShockSpectrogramUrl(session.id, params);

  // Geometry is constant per session (data extents + fixed axes rectangle).
  const { data: geometry } = useSWR(
    ["shock-geo", session.id],
    () => api.analyzerShockGeometry(session.id, params),
    { revalidateOnFocus: false }
  );

  // On (re)mount or an active-session change, restore this session's saved work
  // if any, otherwise reset to a blank analysis.
  const loadedFor = useRef<string | null>(null);
  useEffect(() => {
    setError("");
    const saved = loadWorkflow<ShockSnapshot>(shockKey(session.id));
    if (saved) {
      setExtracted(saved.extracted);
      setKept(saved.kept);
      setFit(saved.fit);
      setNote(saved.note);
      setFold(saved.fold);
      setHarmonic(saved.harmonic);
      setBust(saved.bust);
    } else {
      setExtracted(null);
      setKept(null);
      setFit(null);
      setNote("");
      setFold(1);
      setHarmonic(false);
    }
    loadedFor.current = session.id;
  }, [session.id]);

  // Persist the working state for the active session. Guarded so a state carried
  // over from the previous session isn't written under the new session's key
  // before the restore/reset above has applied.
  useEffect(() => {
    if (loadedFor.current !== session.id) return;
    saveWorkflow(shockKey(session.id), {
      extracted,
      kept,
      fold,
      harmonic,
      fit,
      note,
      bust,
    } satisfies ShockSnapshot);
  }, [session.id, extracted, kept, fold, harmonic, fit, note, bust]);

  // Restore a shock session carried in an opened .efaproj.
  const restoredRef = useRef<ShockSession | null>(null);
  useEffect(() => {
    if (!restored || restoredRef.current === restored) return;
    restoredRef.current = restored;
    if (restored.freqs.length) {
      const pts: Points = {
        time: restored.time_seconds.slice(),
        freq: restored.freqs.slice(),
        channels: restored.time_seconds.map((_, i) => i),
      };
      setExtracted(pts);
      setKept(pts);
      setFold(restored.fold || 1);
      setHarmonic(restored.harmonic);
      if (restored.fit && restored.shock_summary) {
        setFit({
          fit: restored.fit,
          shock_summary: restored.shock_summary,
          curves: { shock_freq_mhz: [], shock_speed_km_s: [], shock_height_rs: [] },
          fit_line: { time_s: [], freq_mhz: [] },
        });
        setBust(Date.now());
      }
      setNote("Restored analysis from project.");
    }
    onRestoredConsumed?.();
  }, [restored, onRestoredConsumed]);

  async function onExtract(polygon: { time_s: number; freq_mhz: number }[]) {
    setBusy(true);
    setError("");
    setNote("");
    try {
      const res = await api.analyzerShockMaxIntensity({
        id: session.id,
        method: params.method,
        intensity_unit: params.intensity_unit,
        rfi_enabled: params.rfi_enabled,
        rfi_low: params.rfi_low,
        rfi_high: params.rfi_high,
        polygon,
        auto_clean: true,
      });
      const pts: Points = { time: res.time_seconds, freq: res.freqs, channels: res.time_channels };
      setExtracted(pts);
      setKept(pts);
      setFit(null);
      setNote(
        `${res.freqs.length} maximum-intensity points` +
          (res.auto_removed_count > 0 ? ` · auto-cleaned ${res.auto_removed_count} weak columns` : "")
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Extraction failed.");
    } finally {
      setBusy(false);
    }
  }

  function removePoints(indices: number[]) {
    if (!kept) return;
    const drop = new Set(indices);
    setKept({
      time: kept.time.filter((_, i) => !drop.has(i)),
      freq: kept.freq.filter((_, i) => !drop.has(i)),
      channels: kept.channels.filter((_, i) => !drop.has(i)),
    });
    setFit(null);
  }

  async function onFit() {
    if (!kept || kept.time.length < 2) return;
    setBusy(true);
    setError("");
    try {
      const res = await api.analyzerShockFit({
        id: session.id,
        points: kept.time.map((t, i) => ({ time_s: t, freq_mhz: kept.freq[i] })),
        fold,
        harmonic,
        time_channels: kept.channels,
      });
      setFit(res);
      setBust(Date.now());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fit failed.");
    } finally {
      setBusy(false);
    }
  }

  const dlCls =
    "flex items-center gap-1 rounded bg-surface-muted px-2 py-1 text-xs text-slate-300 transition-colors hover:bg-accent-blue/30 hover:text-accent-blue";

  const fitLine = useMemo(
    () => (fit && fit.fit_line.time_s.length ? fit.fit_line : null),
    [fit]
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-surface-border bg-surface-card px-4 py-2">
        <div className="text-xs text-slate-500">
          <span className="font-semibold text-slate-300">{session.station}</span>
          <span className="ml-2">{session.filename}</span>
        </div>
        <a
          href={api.analyzerProjectUrl(session.id, params)}
          download
          className={dlCls}
          title="Save project (.efaproj) with the shock analysis — opens in the desktop app too"
        >
          <Download className="h-3.5 w-3.5" /> Save project (.efaproj)
        </a>
      </div>

      {error && (
        <div className="rounded border border-accent-red/40 bg-accent-red/10 px-3 py-2 text-xs text-accent-red">
          {error}
        </div>
      )}

      <Step n={1} title="Isolate the burst">
        <BurstLassoOverlay
          spectrogramUrl={spectrogramUrl}
          geometry={geometry ?? null}
          disabled={busy}
          onSelect={onExtract}
        />
      </Step>

      {kept && (
        <Step n={2} title="Review maximum-intensity points & remove outliers">
          {note && <p className="mb-2 text-[11px] text-accent-blue">{note}</p>}
          <MaxIntensityScatter
            time={kept.time}
            freq={kept.freq}
            fitLine={fitLine}
            onRemove={removePoints}
            onReset={extracted ? () => setKept(extracted) : undefined}
          />
        </Step>
      )}

      {kept && (
        <Step n={3} title="Fit & shock parameters">
          <ShockControls
            fold={fold}
            harmonic={harmonic}
            fitting={busy}
            canFit={kept.time.length >= 2}
            onFoldChange={(f) => setFold(f)}
            onHarmonicChange={(h) => setHarmonic(h)}
            onFit={onFit}
          />
        </Step>
      )}

      {fit && fit.shock_summary && (
        <ShockResults id={session.id} summary={fit.shock_summary} fit={fit.fit} bust={bust} />
      )}
    </div>
  );
}
