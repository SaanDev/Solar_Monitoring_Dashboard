"use client";

import { useEffect, useRef, useState } from "react";
import { Download } from "lucide-react";
import { formatUtcShort } from "@/lib/formatting";
import type { AnalysisSession } from "@/lib/types";

interface Props {
  session: AnalysisSession | null;
  renderUrl: string | null;
  downloadUrl: string | null;
}

/**
 * Double-buffered solar-image viewer: preload the next render off-screen and only
 * swap the visible image once it's ready, so dragging a control updates live
 * without flicker (same approach as the e-CALLISTO analyzer's SpectrumView).
 */
export function PlotView({ session, renderUrl, downloadUrl }: Props) {
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

  useEffect(() => {
    if (!session) {
      setDisplayed(null);
      latest.current = null;
    }
  }, [session]);

  if (!session) {
    return (
      <div className="flex h-full min-h-[460px] items-center justify-center rounded-lg border border-surface-border bg-surface-card text-sm text-slate-600">
        Load an AIA/HMI FITS to begin.
      </div>
    );
  }

  const dlCls =
    "flex items-center gap-1 rounded bg-surface-muted px-2 py-1 text-xs text-slate-300 transition-colors hover:bg-accent-blue/30 hover:text-accent-blue";

  return (
    <div className="flex h-full flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <div className="text-xs text-slate-500">
          <span className="font-semibold text-slate-300">
            {session.instrument} {session.measurement}
          </span>
          {session.reference_time && (
            <span className="ml-2">{formatUtcShort(session.reference_time)}</span>
          )}
          <span className="ml-2 text-slate-600">
            {session.width}×{session.height}
            {session.n_frames > 1 ? ` · ${session.n_frames} frames` : ""}
          </span>
        </div>
        {downloadUrl && (
          <a href={downloadUrl} download className={dlCls}>
            <Download className="h-3.5 w-3.5" /> PNG
          </a>
        )}
      </div>

      <div className="relative flex min-h-[460px] flex-1 items-center justify-center overflow-hidden rounded bg-black/30">
        {pending && (
          <span className="absolute right-2 top-2 z-10 flex items-center gap-1 rounded bg-surface-card/80 px-2 py-0.5 text-[10px] text-slate-400">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-blue" />
            updating
          </span>
        )}
        {errored && !displayed && (
          <div className="absolute inset-0 flex items-center justify-center px-4 text-center text-xs text-accent-red">
            Failed to render this image. Check the controls and try again.
          </div>
        )}
        {displayed ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={displayed} alt="Solar image analysis" className="max-h-full max-w-full object-contain" />
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
