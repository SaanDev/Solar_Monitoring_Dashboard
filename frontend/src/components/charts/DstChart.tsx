"use client";

import dynamic from "next/dynamic";
import type { DstPoint } from "@/lib/types";
import { toPlotlyUtc } from "@/lib/formatting";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface Props { data: DstPoint[]; loading?: boolean; }

export function DstChart({ data, loading }: Props) {
  if (loading) return <div className="h-full animate-pulse rounded bg-surface-muted" />;
  if (!data.length) {
    return <div className="flex h-full items-center justify-center text-xs text-slate-700">No data</div>;
  }

  return (
    <Plot
      data={[{
        x: data.map((d) => toPlotlyUtc(d.time)),
        y: data.map((d) => d.dst),
        type: "scatter",
        mode: "lines",
        name: "Dst",
        line: { color: "#06b6d4", width: 1.5 },
        fill: "tozeroy",
        fillcolor: "rgba(6,182,212,0.08)",
      }]}
      layout={{
        paper_bgcolor: "transparent",
        plot_bgcolor: "#0a0d14",
        font: { color: "#94a3b8", size: 11 },
        xaxis: { color: "#475569", gridcolor: "#1e2535", title: { text: "Time (UTC)", font: { size: 10 } }, hoverformat: "%Y-%m-%d %H:%M UTC" },
        yaxis: { color: "#475569", gridcolor: "#1e2535", title: { text: "Dst (nT)", font: { size: 10 } } },
        margin: { t: 20, r: 20, b: 40, l: 60 },
        shapes: [
          { type: "line", xref: "paper", yref: "y", x0: 0, x1: 1, y0: -50, y1: -50, line: { color: "#eab308", dash: "dot", width: 1 } },
          { type: "line", xref: "paper", yref: "y", x0: 0, x1: 1, y0: -100, y1: -100, line: { color: "#ef4444", dash: "dot", width: 1 } },
        ],
      } as Plotly.Layout}
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}
