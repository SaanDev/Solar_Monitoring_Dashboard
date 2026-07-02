"use client";

import dynamic from "next/dynamic";
import type { GoesXrsPoint } from "@/lib/types";
import { toPlotlyUtc } from "@/lib/formatting";
import { usePlotlyTheme, type PlotlyTheme } from "./plotlyTheme";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

function _layout(theme: PlotlyTheme): Partial<Plotly.Layout> {
  return {
    ...theme.layout,
    xaxis: {
      ...theme.axis,
      title: { text: "Time (UTC)", font: { size: 10 } },
      hoverformat: "%Y-%m-%d %H:%M UTC",
    },
    yaxis: {
      type: "log" as const,
      ...theme.axis,
      title: { text: "Flux (W/m²)", font: { size: 10 } },
      range: [-9, -3],
      dtick: 1,
    },
    margin: { t: 20, r: 80, b: 40, l: 70 },
    legend: { x: 0, y: 1, bgcolor: "transparent", font: { size: 10 } },
    shapes: _flareShapes(theme.dark),
    annotations: _flareAnnotations(),
  };
}

// Flare-class decade bands, tinted increasingly "hot" toward X; each theme
// needs its own shades for the tint to stay subtle against the plot bg.
const _BAND_COLORS = {
  dark: ["#334155", "#3b4a5e", "#374151", "#44394d", "#4c2626"],
  light: ["#e2e8f0", "#dbeafe", "#e5e7eb", "#e9d5ff", "#fecaca"],
};

function _flareShapes(dark: boolean): Partial<Plotly.Shape>[] {
  const colors = dark ? _BAND_COLORS.dark : _BAND_COLORS.light;
  const classes = [
    { y: 1e-8, color: colors[0] },
    { y: 1e-7, color: colors[1] },
    { y: 1e-6, color: colors[2] },
    { y: 1e-5, color: colors[3] },
    { y: 1e-4, color: colors[4] },
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
  const theme = usePlotlyTheme();
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
      layout={_layout(theme) as Plotly.Layout}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}
