"use client";

import { useEffect, useRef, useState } from "react";
import { Lasso, Square, Eraser } from "lucide-react";
import { clsx } from "clsx";
import type { RenderGeometry, ShockPoint } from "@/lib/types";

type Tool = "lasso" | "box";

interface Props {
  spectrogramUrl: string;
  geometry: RenderGeometry | null;
  disabled?: boolean;
  onSelect: (polygon: ShockPoint[]) => void;
}

/**
 * Freehand-lasso / box selection drawn over the fixed-axes shock spectrogram. The
 * canvas works in the PNG's natural pixel space; on release each vertex is mapped to
 * data coordinates ([time_seconds, freq_mhz]) via `geometry.axes_px` + the data extents,
 * so the backend can isolate the burst exactly like the desktop lasso.
 */
export function BurstLassoOverlay({ spectrogramUrl, geometry, disabled, onSelect }: Props) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [tool, setTool] = useState<Tool>("lasso");
  const drawing = useRef(false);
  const pts = useRef<Array<[number, number]>>([]);
  const start = useRef<[number, number] | null>(null);
  const [hasSelection, setHasSelection] = useState(false);

  const imgW = geometry?.img_w ?? 1500;
  const imgH = geometry?.img_h ?? 975;

  // Size the canvas backing store to the natural PNG resolution.
  useEffect(() => {
    const c = canvasRef.current;
    if (!c) return;
    c.width = imgW;
    c.height = imgH;
    clear();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [imgW, imgH, spectrogramUrl]);

  function toCanvas(e: React.PointerEvent): [number, number] {
    const c = canvasRef.current!;
    const rect = c.getBoundingClientRect();
    const x = (e.clientX - rect.left) * (c.width / rect.width);
    const y = (e.clientY - rect.top) * (c.height / rect.height);
    return [x, y];
  }

  function draw() {
    const c = canvasRef.current;
    if (!c) return;
    const ctx = c.getContext("2d")!;
    ctx.clearRect(0, 0, c.width, c.height);
    const path = pts.current;
    if (path.length < 2) return;
    ctx.beginPath();
    ctx.moveTo(path[0][0], path[0][1]);
    for (let i = 1; i < path.length; i++) ctx.lineTo(path[i][0], path[i][1]);
    if (!drawing.current) ctx.closePath();
    ctx.lineWidth = 3;
    ctx.strokeStyle = "#38bdf8";
    ctx.setLineDash([10, 6]);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillStyle = "rgba(56,189,248,0.12)";
    ctx.fill();
  }

  function clear() {
    const c = canvasRef.current;
    if (c) c.getContext("2d")!.clearRect(0, 0, c.width, c.height);
    pts.current = [];
    start.current = null;
    setHasSelection(false);
  }

  function onDown(e: React.PointerEvent) {
    if (disabled || !geometry) return;
    e.preventDefault();
    try {
      canvasRef.current?.setPointerCapture(e.pointerId);
    } catch {
      /* pointer capture is best-effort */
    }
    drawing.current = true;
    const p = toCanvas(e);
    if (tool === "box") {
      start.current = p;
      pts.current = [p, p, p, p];
    } else {
      pts.current = [p];
    }
    draw();
  }

  function onMove(e: React.PointerEvent) {
    if (!drawing.current) return;
    const p = toCanvas(e);
    if (tool === "box" && start.current) {
      const [x0, y0] = start.current;
      pts.current = [[x0, y0], [p[0], y0], [p[0], p[1]], [x0, p[1]]];
    } else {
      pts.current.push(p);
    }
    draw();
  }

  function onUp() {
    if (!drawing.current) return;
    drawing.current = false;
    draw();
    setHasSelection(pts.current.length >= 3);
  }

  function apply() {
    if (!geometry || pts.current.length < 3) return;
    const [ax0, ay0, ax1, ay1] = geometry.axes_px;
    const { t0, t1, freq_top, freq_bottom } = geometry;
    const clamp = (v: number) => Math.max(0, Math.min(1, v));
    // Decimate long freehand paths to keep the request small.
    const src = pts.current;
    const stepN = Math.max(1, Math.floor(src.length / 200));
    const polygon: ShockPoint[] = [];
    for (let i = 0; i < src.length; i += stepN) {
      const [px, py] = src[i];
      const fx = clamp((px - ax0) / (ax1 - ax0));
      const fy = clamp((py - ay0) / (ay1 - ay0));
      polygon.push({
        time_s: t0 + fx * (t1 - t0),
        freq_mhz: freq_top + fy * (freq_bottom - freq_top),
      });
    }
    if (polygon.length >= 3) onSelect(polygon);
  }

  const toolBtn = (t: Tool, Icon: typeof Lasso, label: string) => (
    <button
      onClick={() => setTool(t)}
      className={clsx(
        "flex items-center gap-1 rounded px-2 py-1 text-xs transition-colors",
        tool === t ? "bg-accent-blue/20 text-accent-blue" : "text-slate-500 hover:bg-surface-muted"
      )}
      title={label}
    >
      <Icon className="h-3.5 w-3.5" /> {label}
    </button>
  );

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center gap-2">
        {toolBtn("lasso", Lasso, "Lasso")}
        {toolBtn("box", Square, "Box")}
        <button
          onClick={clear}
          className="flex items-center gap-1 rounded px-2 py-1 text-xs text-slate-500 transition-colors hover:bg-surface-muted"
        >
          <Eraser className="h-3.5 w-3.5" /> Clear
        </button>
        <button
          onClick={apply}
          disabled={!hasSelection || disabled}
          className="ml-auto rounded bg-accent-blue/20 px-3 py-1 text-xs font-medium text-accent-blue transition-colors hover:bg-accent-blue/30 disabled:cursor-not-allowed disabled:opacity-40"
        >
          Extract max intensity
        </button>
      </div>
      <div className="relative overflow-hidden rounded bg-black/30">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={spectrogramUrl} alt="Burst spectrogram" className="block h-auto w-full select-none" draggable={false} />
        <canvas
          ref={canvasRef}
          onPointerDown={onDown}
          onPointerMove={onMove}
          onPointerUp={onUp}
          className={clsx(
            "absolute inset-0 h-full w-full",
            disabled ? "cursor-not-allowed" : "cursor-crosshair"
          )}
        />
      </div>
      <p className="mt-1.5 text-[11px] text-slate-500">
        Draw around the Type II burst; everything outside is zeroed before the per-column peak-frequency extraction.
      </p>
    </div>
  );
}
