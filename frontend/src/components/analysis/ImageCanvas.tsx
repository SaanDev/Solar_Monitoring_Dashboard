"use client";

import { useEffect, useRef, useState } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import { EmptyState } from "@/components/ui/EmptyState";
import type {
  AnalysisSession,
  CoordReadout,
  FrameWcsMeta,
  PlotParams,
} from "@/lib/types";

/** A point annotation in data-pixel coordinates (origin bottom-left). */
export interface CanvasMarker {
  px: number;
  py: number;
  label?: string;
  color?: string;
}
export interface CanvasSegment {
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  color?: string;
  dashed?: boolean;
}
export interface CanvasRect {
  x: number; // bottom-left corner, data pixels
  y: number;
  w: number;
  h: number;
  color?: string;
}

interface Props {
  session: AnalysisSession;
  frame: number;
  /** Debounce upstream — every change re-requests the bare render. */
  params: PlotParams;
  mode?: "plot" | "running" | "base";
  baseIndex?: number;
  /** Reference frame for the lon/lat click readout. */
  frameKey?: "HGS" | "HGC" | "HCI";
  markers?: CanvasMarker[];
  segments?: CanvasSegment[];
  rects?: CanvasRect[];
  /** Called with data-pixel coords (origin bottom-left) on click. */
  onPick?: (px: number, py: number) => void;
  hint?: string;
}

/**
 * Interactive solar image canvas.
 *
 * Background is the `/render-bare` PNG whose pixels map 1:1 to the FITS data
 * array (origin bottom-left), so screen positions convert linearly to data
 * pixels. Hover shows a live arcsec/R☉ readout computed client-side from
 * `/frame-meta`; a click asks `/coord` for the exact WCS numbers (lon/lat, PA,
 * data value) and reports the pick to the active tool via `onPick`.
 */
export function ImageCanvas({
  session,
  frame,
  params,
  mode = "plot",
  baseIndex = 0,
  frameKey = "HGS",
  markers = [],
  segments = [],
  rects = [],
  onPick,
  hint,
}: Props) {
  const { data: meta } = useSWR<FrameWcsMeta>(
    ["analysis-frame-meta", session.id, frame],
    () => api.analysisFrameMeta(session.id, frame),
    { revalidateOnFocus: false }
  );

  const targetUrl = api.analysisBareUrl(session.id, frame, mode, baseIndex, params);
  const [shownUrl, setShownUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Double-buffer: preload off-screen, swap when ready (no flicker on drags).
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const img = new Image();
    img.onload = () => {
      if (!cancelled) {
        setShownUrl(targetUrl);
        setLoading(false);
      }
    };
    img.onerror = () => {
      if (!cancelled) {
        setLoading(false);
        setError("Render failed (frame may need a previous frame for a difference).");
      }
    };
    img.src = targetUrl;
    return () => {
      cancelled = true;
    };
  }, [targetUrl]);

  const boxRef = useRef<HTMLDivElement>(null);
  const [hover, setHover] = useState<{ px: number; py: number; tx: number; ty: number; r: number } | null>(null);
  const [pick, setPick] = useState<CoordReadout | null>(null);

  function toDataPixel(e: React.MouseEvent): { px: number; py: number } | null {
    const box = boxRef.current;
    if (!box || !meta) return null;
    const rect = box.getBoundingClientRect();
    const u = (e.clientX - rect.left) / rect.width;
    const v = (e.clientY - rect.top) / rect.height;
    if (u < 0 || u > 1 || v < 0 || v > 1) return null;
    // PNG row 0 is the top = data row ny-1 (origin="lower" render).
    return { px: u * meta.nx - 0.5, py: (1 - v) * meta.ny - 0.5 };
  }

  function linearWorld(px: number, py: number) {
    const m = meta!;
    const dx = px - m.center_x;
    const dy = py - m.center_y;
    const tx = m.cdelt1 * (m.pc[0][0] * dx + m.pc[0][1] * dy);
    const ty = m.cdelt2 * (m.pc[1][0] * dx + m.pc[1][1] * dy);
    return { tx, ty, r: Math.hypot(tx, ty) / (m.rsun_arcsec || 960) };
  }

  function onMove(e: React.MouseEvent) {
    const p = toDataPixel(e);
    if (!p || !meta) {
      setHover(null);
      return;
    }
    setHover({ px: p.px, py: p.py, ...linearWorld(p.px, p.py) });
  }

  async function onClick(e: React.MouseEvent) {
    const p = toDataPixel(e);
    if (!p) return;
    onPick?.(p.px, p.py);
    try {
      setPick(await api.analysisCoord(session.id, frame, p.px, p.py, frameKey));
    } catch {
      setPick(null);
    }
  }

  const nx = meta?.nx ?? 1;
  const ny = meta?.ny ?? 1;
  // Data pixel (px, py) → SVG coords (origin top-left, y down).
  const sx = (px: number) => px + 0.5;
  const sy = (py: number) => ny - py - 0.5;

  return (
    <div className="space-y-2 rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-wider text-slate-500">
          {meta ? `${meta.instrument} ${meta.detector} ${meta.measurement}` : "Viewer"}
          {meta?.time ? ` · ${meta.time.replace("T", " ").slice(0, 19)} UTC` : ""}
        </h2>
        {loading && <span className="text-[10px] text-slate-500">rendering…</span>}
      </div>

      {hint && <p className="text-[10px] text-accent-cyan">{hint}</p>}

      <div
        ref={boxRef}
        // Pointer-only by design: a keyboard equivalent needs a cursor model and
        // key bindings for WCS pixel-picking, which is a feature rather than a
        // polish item. Naming it at least stops it being an anonymous region.
        role="img"
        aria-label={
          meta
            ? `${meta.instrument} ${meta.detector} ${meta.measurement} frame. Pointer-driven coordinate readout.`
            : "Solar frame viewer"
        }
        className="relative w-full cursor-crosshair select-none overflow-hidden rounded"
        onMouseMove={onMove}
        onMouseLeave={() => setHover(null)}
        onClick={onClick}
      >
        {shownUrl ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={shownUrl} alt="solar frame" className="block w-full" draggable={false} />
        ) : (
          // `{error ?? "Loading frame…"}` put a failure and a progress message
          // in the same slot with the same styling — indistinguishable at a glance.
          <div className="flex aspect-square w-full items-center justify-center">
            {error ? (
              <EmptyState tone="error" message={error} className="border-0 bg-transparent" />
            ) : (
              <span className="text-xs text-slate-500">Loading frame…</span>
            )}
          </div>
        )}
        {shownUrl && meta && (
          <svg
            viewBox={`0 0 ${nx} ${ny}`}
            preserveAspectRatio="none"
            className="pointer-events-none absolute inset-0 h-full w-full"
          >
            {rects.map((r, i) => (
              <rect
                key={`r${i}`}
                x={sx(r.x) - 0.5}
                y={sy(r.y + r.h) - 0.5}
                width={r.w}
                height={r.h}
                fill="none"
                stroke={r.color ?? "#22d3ee"}
                strokeWidth={Math.max(1, nx / 500)}
              />
            ))}
            {segments.map((s, i) => (
              <line
                key={`s${i}`}
                x1={sx(s.x1)}
                y1={sy(s.y1)}
                x2={sx(s.x2)}
                y2={sy(s.y2)}
                stroke={s.color ?? "#a3e635"}
                strokeWidth={Math.max(1, nx / 500)}
                strokeDasharray={s.dashed ? `${nx / 100} ${nx / 150}` : undefined}
              />
            ))}
            {markers.map((mk, i) => (
              <g key={`m${i}`}>
                <circle
                  cx={sx(mk.px)}
                  cy={sy(mk.py)}
                  r={Math.max(3, nx / 160)}
                  fill="none"
                  stroke={mk.color ?? "#f59e0b"}
                  strokeWidth={Math.max(1, nx / 500)}
                />
                {mk.label && (
                  <text
                    x={sx(mk.px) + nx / 90}
                    y={sy(mk.py) - ny / 120}
                    fill={mk.color ?? "#f59e0b"}
                    fontSize={Math.max(10, nx / 60)}
                  >
                    {mk.label}
                  </text>
                )}
              </g>
            ))}
          </svg>
        )}
      </div>

      {/* Live readout: linear hover values + exact click readout. */}
      <div className="grid grid-cols-2 gap-2 font-mono text-[10px] text-slate-400">
        <div className="rounded bg-surface-muted px-2 py-1">
          {hover && meta ? (
            <>
              px ({hover.px.toFixed(1)}, {hover.py.toFixed(1)}) · Tx {hover.tx.toFixed(0)}″ Ty{" "}
              {hover.ty.toFixed(0)}″ · r {hover.r.toFixed(2)} R☉
            </>
          ) : (
            "hover for coordinates"
          )}
        </div>
        <div className="rounded bg-surface-muted px-2 py-1">
          {pick ? (
            <>
              click: {pick.r_rsun != null ? `${pick.r_rsun.toFixed(2)} R☉` : "—"} · PA{" "}
              {pick.position_angle_deg.toFixed(0)}°
              {pick.lon_deg != null && pick.lat_deg != null
                ? ` · ${pick.frame_key} (${pick.lon_deg.toFixed(1)}°, ${pick.lat_deg.toFixed(1)}°)`
                : " · off-disk"}
              {pick.value != null ? ` · ${pick.value.toPrecision(4)}` : ""}
            </>
          ) : (
            "click for exact WCS readout"
          )}
        </div>
      </div>
    </div>
  );
}
