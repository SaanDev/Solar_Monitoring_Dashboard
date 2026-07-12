"use client";

import { useMemo, useRef, useState } from "react";
import { Trash2, RotateCcw } from "lucide-react";

interface Props {
  time: number[];
  freq: number[];
  fitLine?: { time_s: number[]; freq_mhz: number[] } | null;
  onRemove: (indices: number[]) => void;
  onReset?: () => void;
}

const W = 640;
const H = 380;
const PAD = { l: 58, r: 16, t: 16, b: 42 };

function pointInPolygon(x: number, y: number, poly: Array<[number, number]>): boolean {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const [xi, yi] = poly[i];
    const [xj, yj] = poly[j];
    const intersect = yi > y !== yj > y && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi;
    if (intersect) inside = !inside;
  }
  return inside;
}

/** Maximum-intensity scatter (time vs frequency) with a freehand lasso to flag and
 *  remove outliers before fitting. All selection is client-side in the plot's own space. */
export function MaxIntensityScatter({ time, freq, fitLine, onRemove, onReset }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const drawing = useRef(false);
  const [lasso, setLasso] = useState<Array<[number, number]>>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  const { sx, sy, plot } = useMemo(() => {
    const xs = time.length ? time : [0, 1];
    const ys = freq.length ? freq : [0, 1];
    let xmin = Math.min(...xs), xmax = Math.max(...xs);
    let ymin = Math.min(...ys), ymax = Math.max(...ys);
    if (xmin === xmax) { xmin -= 1; xmax += 1; }
    if (ymin === ymax) { ymin -= 1; ymax += 1; }
    const xpad = (xmax - xmin) * 0.05;
    const ypad = (ymax - ymin) * 0.05;
    xmin -= xpad; xmax += xpad; ymin -= ypad; ymax += ypad;
    const iw = W - PAD.l - PAD.r;
    const ih = H - PAD.t - PAD.b;
    const sx = (t: number) => PAD.l + ((t - xmin) / (xmax - xmin)) * iw;
    const sy = (f: number) => PAD.t + (1 - (f - ymin) / (ymax - ymin)) * ih;
    return { sx, sy, plot: { xmin, xmax, ymin, ymax, iw, ih } };
  }, [time, freq]);

  function toSvg(e: React.PointerEvent): [number, number] {
    const svg = svgRef.current!;
    const rect = svg.getBoundingClientRect();
    return [
      ((e.clientX - rect.left) / rect.width) * W,
      ((e.clientY - rect.top) / rect.height) * H,
    ];
  }

  function onDown(e: React.PointerEvent) {
    e.preventDefault();
    try {
      svgRef.current?.setPointerCapture(e.pointerId);
    } catch {
      /* pointer capture is best-effort */
    }
    drawing.current = true;
    setLasso([toSvg(e)]);
  }
  function onMove(e: React.PointerEvent) {
    if (!drawing.current) return;
    setLasso((p) => [...p, toSvg(e)]);
  }
  function onUp() {
    if (!drawing.current) return;
    drawing.current = false;
    setLasso((poly) => {
      if (poly.length >= 3) {
        const sel = new Set<number>();
        time.forEach((t, i) => {
          if (pointInPolygon(sx(t), sy(freq[i]), poly)) sel.add(i);
        });
        setSelected(sel);
      }
      return [];
    });
  }

  const ticks = (min: number, max: number, n = 5) =>
    Array.from({ length: n + 1 }, (_, i) => min + ((max - min) * i) / n);

  return (
    <div>
      <div className="mb-2 flex items-center gap-2">
        <span className="text-xs text-slate-500">
          {time.length} points{selected.size > 0 && ` · ${selected.size} selected`}
        </span>
        <button
          onClick={() => {
            if (selected.size) onRemove([...selected]);
            setSelected(new Set());
          }}
          disabled={selected.size === 0}
          className="ml-auto flex items-center gap-1 rounded bg-accent-red/15 px-2 py-1 text-xs text-accent-red transition-colors hover:bg-accent-red/25 disabled:cursor-not-allowed disabled:opacity-40"
        >
          <Trash2 className="h-3.5 w-3.5" /> Remove selected
        </button>
        {onReset && (
          <button
            onClick={() => { setSelected(new Set()); onReset(); }}
            className="flex items-center gap-1 rounded bg-surface-muted px-2 py-1 text-xs text-slate-400 transition-colors hover:text-slate-200"
          >
            <RotateCcw className="h-3.5 w-3.5" /> Reset
          </button>
        )}
      </div>
      <svg
        ref={svgRef}
        viewBox={`0 0 ${W} ${H}`}
        className="w-full touch-none rounded bg-black/30"
        onPointerDown={onDown}
        onPointerMove={onMove}
        onPointerUp={onUp}
        style={{ cursor: "crosshair" }}
      >
        {/* axes */}
        <line x1={PAD.l} y1={H - PAD.b} x2={W - PAD.r} y2={H - PAD.b} stroke="#334155" />
        <line x1={PAD.l} y1={PAD.t} x2={PAD.l} y2={H - PAD.b} stroke="#334155" />
        {ticks(plot.xmin, plot.xmax).map((t, i) => (
          <g key={`x${i}`}>
            <line x1={sx(t)} y1={H - PAD.b} x2={sx(t)} y2={H - PAD.b + 4} stroke="#334155" />
            <text x={sx(t)} y={H - PAD.b + 16} textAnchor="middle" fontSize="10" fill="#64748b">
              {t.toFixed(0)}
            </text>
          </g>
        ))}
        {ticks(plot.ymin, plot.ymax).map((f, i) => (
          <g key={`y${i}`}>
            <line x1={PAD.l - 4} y1={sy(f)} x2={PAD.l} y2={sy(f)} stroke="#334155" />
            <text x={PAD.l - 8} y={sy(f) + 3} textAnchor="end" fontSize="10" fill="#64748b">
              {f.toFixed(0)}
            </text>
          </g>
        ))}
        <text x={(PAD.l + W - PAD.r) / 2} y={H - 6} textAnchor="middle" fontSize="11" fill="#94a3b8">
          Time (s)
        </text>
        <text x={14} y={(PAD.t + H - PAD.b) / 2} textAnchor="middle" fontSize="11" fill="#94a3b8"
          transform={`rotate(-90 14 ${(PAD.t + H - PAD.b) / 2})`}>
          Frequency (MHz)
        </text>

        {/* fit line */}
        {fitLine && fitLine.time_s.length > 1 && (
          <polyline
            fill="none"
            stroke="#f87171"
            strokeWidth={2}
            points={fitLine.time_s.map((t, i) => `${sx(t)},${sy(fitLine.freq_mhz[i])}`).join(" ")}
          />
        )}

        {/* points */}
        {time.map((t, i) => (
          <circle
            key={i}
            cx={sx(t)}
            cy={sy(freq[i])}
            r={selected.has(i) ? 3.5 : 2.5}
            fill={selected.has(i) ? "#f87171" : "#38bdf8"}
            opacity={0.9}
          />
        ))}

        {/* active lasso */}
        {lasso.length > 1 && (
          <polyline
            fill="rgba(248,113,113,0.1)"
            stroke="#f87171"
            strokeWidth={1.5}
            strokeDasharray="6 4"
            points={lasso.map((p) => `${p[0]},${p[1]}`).join(" ")}
          />
        )}
      </svg>
    </div>
  );
}
