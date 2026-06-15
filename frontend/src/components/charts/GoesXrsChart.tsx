"use client";

import dynamic from "next/dynamic";
import type { GoesXrsPoint } from "@/lib/types";
import { toPlotlyUtc } from "@/lib/formatting";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const DARK_LAYOUT: Partial<Plotly.Layout> = {
  paper_bgcolor: "transparent",
  plot_bgcolor: "#0a0d14",
  font: { color: "#94a3b8", size: 11 },
  xaxis: {
    color: "#475569",
    gridcolor: "#1e2535",
    title: { text: "Time (UTC)", font: { size: 10 } },
    hoverformat: "%Y-%m-%d %H:%M UTC",
  },
  yaxis: {
    type: "log" as const,
    color: "#475569",
    gridcolor: "#1e2535",
    title: { text: "Flux (W/m²)", font: { size: 10 } },
    range: [-9, -3],
    dtick: 1,
  },
  margin: { t: 20, r: 80, b: 40, l: 70 },
  legend: { x: 0, y: 1, bgcolor: "transparent", font: { size: 10 } },
  shapes: _flareShapes(),
  annotations: _flareAnnotations(),
};

function _flareShapes(): Partial<Plotly.Shape>[] {
  const classes = [
    { y: 1e-8, color: "#334155" },
    { y: 1e-7, color: "#3b4a5e" },
    { y: 1e-6, color: "#374151" },
    { y: 1e-5, color: "#44394d" },
    { y: 1e-4, color: "#4c2626" },
  ];
  return classes.map(({ y, color }) => ({
    type: "rect",
    xref: "paper",
    yref: "y",
    x0: 0,
    x1: 1,
    y0: y,
    y1: y * 10,
    fillcolor: color,
    opacity: 0.3,
    line: { width: 0 },
  }));
}

function _flareAnnotations(): Partial<Plotly.Annotations>[] {
  // Center each label inside its decade band (A: 1e-8–1e-7, … X: 1e-4–1e-3)
  return (
    [
      { y: 3e-8, label: "A" },
      { y: 3e-7, label: "B" },
      { y: 3e-6, label: "C" },
      { y: 3e-5, label: "M" },
      { y: 3e-4, label: "X" },
    ] as const
  ).map(({ y, label }) => ({
    x: 1.01,
    y: Math.log10(y),
    xref: "paper",
    yref: "y",
    text: label,
    showarrow: false,
    font: { size: 11, color: "#64748b" },
    xanchor: "left",
  }));
}

interface Props {
  data: GoesXrsPoint[];
  loading?: boolean;
}

export function GoesXrsChart({ data, loading }: Props) {
  if (loading) {
    return <div className="h-full animate-pulse rounded bg-surface-muted" />;
  }
  if (!data.length) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-slate-700">
        No data
      </div>
    );
  }

  const times = data.map((d) => toPlotlyUtc(d.time));

  return (
    <Plot
      data={[
        {
          x: times,
          y: data.map((d) => d.long_channel),
          type: "scatter",
          mode: "lines",
          name: "0.1–0.8 nm (long)",
          line: { color: "#ef4444", width: 1.5 },
        },
        {
          x: times,
          y: data.map((d) => d.short_channel),
          type: "scatter",
          mode: "lines",
          name: "0.05–0.4 nm (short)",
          line: { color: "#3b82f6", width: 1.5 },
        },
      ]}
      layout={DARK_LAYOUT as Plotly.Layout}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}
