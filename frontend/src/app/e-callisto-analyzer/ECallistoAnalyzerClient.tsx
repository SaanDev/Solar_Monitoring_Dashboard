"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { FitsImport } from "@/components/analyzer/FitsImport";
import { SourcesPanel } from "@/components/analyzer/SourcesPanel";
import { AnalyzerControls } from "@/components/analyzer/AnalyzerControls";
import { SpectrumView } from "@/components/analyzer/SpectrumView";
import type { AnalyzerSession, ProjectOpenResponse, RenderParams } from "@/lib/types";

const DEFAULT_PARAMS: RenderParams = {
  method: "median",
  intensity_unit: "db",
  time_unit: "utc",
  cmap: "magma",
  vmin: null,
  vmax: null,
  rfi_enabled: false,
  rfi_low: 1,
  rfi_high: 99,
  station: "",
};

/** Debounce a value so slider drags don't spam the render endpoint. */
function useDebounced<T>(value: T, ms: number): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setV(value), ms);
    return () => clearTimeout(t);
  }, [value, ms]);
  return v;
}

export function ECallistoAnalyzerClient() {
  const [sessions, setSessions] = useState<AnalyzerSession[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [params, setParams] = useState<RenderParams>(DEFAULT_PARAMS);

  const session = sessions.find((s) => s.id === activeId) ?? null;

  const { data: options } = useSWR("analyzer-options", api.analyzerOptions, {
    revalidateOnFocus: false,
  });

  // Stats refetch only when the inputs that change the data distribution change.
  const { data: stats } = useSWR(
    session
      ? [
          "analyzer-stats",
          session.id,
          params.method,
          params.intensity_unit,
          params.rfi_enabled,
          params.rfi_low,
          params.rfi_high,
        ]
      : null,
    () => api.analyzerStats(session!.id, params),
    {
      revalidateOnFocus: false,
      onSuccess: (s) =>
        setParams((p) => (p.vmin == null || p.vmax == null ? { ...p, vmin: s.vmin, vmax: s.vmax } : p)),
    }
  );

  function addSession(s: AnalyzerSession) {
    setSessions((prev) => [...prev.filter((x) => x.id !== s.id), s]);
    setActiveId(s.id);
    setParams({ ...DEFAULT_PARAMS, station: s.station });
  }

  function activate(id: string) {
    const s = sessions.find((x) => x.id === id);
    if (!s) return;
    setActiveId(id);
    setParams({ ...DEFAULT_PARAMS, station: s.station });
  }

  function loadProject(resp: ProjectOpenResponse) {
    setSessions((prev) => [...prev.filter((x) => x.id !== resp.session.id), resp.session]);
    setActiveId(resp.session.id);
    setParams({ ...DEFAULT_PARAMS, station: resp.session.station, ...resp.settings });
  }

  function clearAll() {
    setSessions([]);
    setActiveId(null);
    setParams(DEFAULT_PARAMS);
  }

  function patch(p: Partial<RenderParams>) {
    setParams((prev) => ({ ...prev, ...p }));
  }

  // Short debounce keeps the preview live while dragging without flooding renders;
  // the off-screen preload in SpectrumView swaps frames without flicker.
  const debounced = useDebounced(params, 120);
  const renderUrl = session ? api.analyzerRenderUrl(session.id, debounced) : null;

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      <div className="space-y-4 lg:col-span-1">
        <FitsImport onImport={addSession} onOpenProject={loadProject} />
        <SourcesPanel
          sessions={sessions}
          activeId={activeId}
          onActivate={activate}
          onCombined={addSession}
          onClearAll={clearAll}
        />
        {session && (
          <AnalyzerControls params={params} stats={stats} options={options} onChange={patch} />
        )}
      </div>
      <div className="lg:col-span-2">
        <SpectrumView session={session} params={debounced} renderUrl={renderUrl} />
      </div>
    </div>
  );
}
