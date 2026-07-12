"use client";

/** Dependency-free SVG line chart for profiles and light curves. */
export interface ChartBand {
  x0: number;
  x1: number;
  color?: string;
  label?: string;
}
export interface ChartMarker {
  x: number;
  color?: string;
  label?: string;
}

interface Props {
  x: number[];
  y: (number | null)[];
  height?: number;
  xLabel?: string;
  yLabel?: string;
  /** Format an x value for the tick labels. */
  formatX?: (v: number) => string;
  bands?: ChartBand[];
  markers?: ChartMarker[];
}

export function MiniChart({
  x,
  y,
  height = 180,
  xLabel = "",
  yLabel = "",
  formatX,
  bands = [],
  markers = [],
}: Props) {
  const W = 640;
  const H = height;
  const padL = 46;
  const padR = 10;
  const padT = 8;
  const padB = 30;

  const pts = x
    .map((xv, i) => ({ x: xv, y: y[i] }))
    .filter((p): p is { x: number; y: number } => p.y != null && isFinite(p.y));
  if (pts.length < 2) {
    return <p className="text-[10px] text-slate-600">Not enough data to chart.</p>;
  }

  const xMin = Math.min(...pts.map((p) => p.x));
  const xMax = Math.max(...pts.map((p) => p.x));
  const yMin = Math.min(...pts.map((p) => p.y));
  const yMax = Math.max(...pts.map((p) => p.y));
  const xSpan = xMax - xMin || 1;
  const ySpan = yMax - yMin || 1;

  const X = (v: number) => padL + ((v - xMin) / xSpan) * (W - padL - padR);
  const Y = (v: number) => padT + (1 - (v - yMin) / ySpan) * (H - padT - padB);

  const path = pts.map((p, i) => `${i === 0 ? "M" : "L"}${X(p.x).toFixed(1)},${Y(p.y).toFixed(1)}`).join(" ");
  const fx = formatX ?? ((v: number) => v.toPrecision(3));

  const xTicks = [xMin, xMin + xSpan / 2, xMax];
  const yTicks = [yMin, yMin + ySpan / 2, yMax];

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="w-full" role="img">
      {/* radio-burst window bands */}
      {bands.map((b, i) => {
        const bx0 = Math.max(padL, Math.min(X(b.x0), W - padR));
        const bx1 = Math.max(padL, Math.min(X(b.x1), W - padR));
        if (bx1 <= bx0) return null;
        return (
          <g key={`b${i}`}>
            <rect x={bx0} y={padT} width={bx1 - bx0} height={H - padT - padB} fill={b.color ?? "#f59e0b"} opacity={0.12} />
            {b.label && (
              <text x={bx0 + 3} y={padT + 10} fill={b.color ?? "#f59e0b"} fontSize={9}>
                {b.label}
              </text>
            )}
          </g>
        );
      })}
      {/* frame */}
      <rect x={padL} y={padT} width={W - padL - padR} height={H - padT - padB} fill="none" stroke="#334155" strokeWidth={0.6} />
      {/* y ticks */}
      {yTicks.map((t, i) => (
        <g key={`yt${i}`}>
          <line x1={padL - 3} x2={padL} y1={Y(t)} y2={Y(t)} stroke="#64748b" strokeWidth={0.6} />
          <text x={padL - 6} y={Y(t) + 3} fill="#64748b" fontSize={9} textAnchor="end">
            {Math.abs(t) >= 1000 ? t.toExponential(1) : t.toPrecision(3)}
          </text>
        </g>
      ))}
      {/* x ticks */}
      {xTicks.map((t, i) => (
        <g key={`xt${i}`}>
          <line x1={X(t)} x2={X(t)} y1={H - padB} y2={H - padB + 3} stroke="#64748b" strokeWidth={0.6} />
          <text x={X(t)} y={H - padB + 13} fill="#64748b" fontSize={9} textAnchor="middle">
            {fx(t)}
          </text>
        </g>
      ))}
      {/* markers (e.g. peak) */}
      {markers.map((mk, i) => {
        const mx = X(mk.x);
        if (mx < padL || mx > W - padR) return null;
        return (
          <g key={`mk${i}`}>
            <line x1={mx} x2={mx} y1={padT} y2={H - padB} stroke={mk.color ?? "#22d3ee"} strokeWidth={0.8} strokeDasharray="3 3" />
            {mk.label && (
              <text x={mx + 3} y={padT + 10} fill={mk.color ?? "#22d3ee"} fontSize={9}>
                {mk.label}
              </text>
            )}
          </g>
        );
      })}
      {/* series */}
      <path d={path} fill="none" stroke="#3b82f6" strokeWidth={1.4} />
      {/* axis labels */}
      {xLabel && (
        <text x={(padL + W - padR) / 2} y={H - 4} fill="#94a3b8" fontSize={10} textAnchor="middle">
          {xLabel}
        </text>
      )}
      {yLabel && (
        <text x={12} y={(padT + H - padB) / 2} fill="#94a3b8" fontSize={10} textAnchor="middle" transform={`rotate(-90 12 ${(padT + H - padB) / 2})`}>
          {yLabel}
        </text>
      )}
    </svg>
  );
}
