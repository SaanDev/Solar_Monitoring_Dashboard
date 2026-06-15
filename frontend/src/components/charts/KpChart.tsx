"use client";

import dynamic from "next/dynamic";
import type { KpPoint } from "@/lib/types";
import { toPlotlyUtc } from "@/lib/formatting";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

const KP_COLORS = (kp: number) => {
  if (kp >= 8) return "#ef4444";
  if (kp >= 7) return "#f97316";
  if (kp >= 6) return "#eab308";
  if (kp >= 5) return "#f59e0b";
  return "#22c55e";
};

interface Props { data: KpPoint[]; loading?: boolean; }

export function KpChart({ data, loading }: Props) {
  if (loading) return <div className="h-full animate-pulse rounded bg-surface-muted" />;
  if (!data.length) {
    return <div className="flex h-full items-center justify-center text-xs text-slate-700">No data</div>;
  }

  return (
    <Plot
      data={[{
        x: data.map((d) => toPlotlyUtc(d.time)),
        y: data.map((d) => d.kp),
        type: "bar",
        marker: { color: data.map((d) => KP_COLORS(d.kp)) },
        name: "Kp",
      }]}
      layout={{
        paper_bgcolor: "transparent",
        plot_bgcolor: "#0a0d14",
        font: { color: "#94a3b8", size: 11 },
        xaxis: { color: "#475569", gridcolor: "#1e2535", title: { text: "Time (UTC)", font: { size: 10 } }, hoverformat: "%Y-%m-%d %H:%M UTC" },
        yaxis: { color: "#475569", gridcolor: "#1e2535", range: [0, 9], title: { text: "Kp", font: { size: 10 } } },
        margin: { t: 20, r: 20, b: 40, l: 50 },
        shapes: [
          { type: "line", xref: "paper", yref: "y", x0: 0, x1: 1, y0: 5, y1: 5, line: { color: "#eab308", dash: "dot", width: 1 } },
        ],
      } as Plotly.Layout}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}
