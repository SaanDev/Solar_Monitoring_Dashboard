"use client";

import { useEffect, useRef, useState } from "react";
import { Download } from "lucide-react";
import { api } from "@/lib/api";
import { formatUtcShort } from "@/lib/formatting";
import type { AnalyzerSession, RenderParams } from "@/lib/types";

interface Props {
  session: AnalyzerSession | null;
  params: RenderParams;
  renderUrl: string | null;
}

export function SpectrumView({ session, params, renderUrl }: Props) {
  // Double-buffer: preload the next render off-screen and only swap the visible
  // image once it's ready, so dragging a slider updates live without flicker.
  const [displayed, setDisplayed] = useState<string | null>(null);
  const [pending, setPending] = useState(false);
  const [errored, setErrored] = useState(false);
  const latest = useRef<string | null>(null);

  useEffect(() => {
    if (!renderUrl) return;
    latest.current = renderUrl;
    setPending(true);
    const img = new window.Image();
    img.onload = () => {
      if (latest.current === renderUrl) {
        setDisplayed(renderUrl);
        setPending(false);
        setErrored(false);
      }
    };
    img.onerror = () => {
      if (latest.current === renderUrl) {
        setPending(false);
        setErrored(true);
      }
    };
    img.src = renderUrl;
  }, [renderUrl]);

  // Reset when a new session is loaded.
  useEffect(() => {
    if (!session) {
      setDisplayed(null);
      latest.current = null;
    }
  }, [session]);

  if (!session) {
    return (
      <div className="flex h-full min-h-[420px] items-center justify-center rounded-lg border border-surface-border bg-surface-card text-sm text-slate-600">
        Import a FITS file to begin.
      </div>
    );
  }

  const dlCls =
    "flex items-center gap-1 rounded bg-surface-muted px-2 py-1 text-xs text-slate-300 transition-colors hover:bg-accent-blue/30 hover:text-accent-blue";

  return (
    <div className="flex h-full flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-slate-500">
          <span className="font-semibold text-slate-300">{session.station}</span>
          <span className="ml-2">{session.filename}</span>
          {session.start_time && (
            <span className="ml-2">{formatUtcShort(session.start_time)}</span>
          )}
          <span className="ml-2 text-slate-600">
            {session.freq_min_mhz.toFixed(0)}–{session.freq_max_mhz.toFixed(0)} MHz ·{" "}
            {session.n_freq}×{session.n_time}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <a href={api.analyzerExportUrl(session.id, params, "png")} download className={dlCls}>
            <Download className="h-3.5 w-3.5" /> PNG
          </a>
          <a href={api.analyzerExportUrl(session.id, params, "fits")} download className={dlCls}>
            <Download className="h-3.5 w-3.5" /> FITS
          </a>
          <a
            href={api.analyzerProjectUrl(session.id, params)}
            download
            className={dlCls}
            title="Save project (.efaproj) — opens in the desktop app too"
          >
            <Download className="h-3.5 w-3.5" /> Project
          </a>
        </div>
      </div>

      <div className="relative min-h-[420px] flex-1 overflow-hidden rounded bg-black/30">
        {/* Live-update indicator (non-blocking; previous frame stays visible). */}
        {pending && (
          <span className="absolute right-2 top-2 z-10 flex items-center gap-1 rounded bg-surface-card/80 px-2 py-0.5 text-[10px] text-slate-400">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-blue" />
            updating
          </span>
        )}
        {errored && !displayed && (
          <div className="absolute inset-0 flex items-center justify-center text-xs text-accent-red">
            Failed to render this spectrum.
          </div>
        )}
        {displayed ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={displayed} alt="Dynamic spectrum" className="h-full w-full object-contain" />
        ) : (
          !errored && (
            <div className="absolute inset-0 flex items-center justify-center text-xs text-slate-600">
              Rendering…
            </div>
          )
        )}
      </div>
    </div>
  );
}
