"use client";

import dynamic from "next/dynamic";
import type { KpForecastPoint } from "@/lib/types";
import { toPlotlyUtc } from "@/lib/formatting";
import { usePlotlyTheme } from "./plotlyTheme";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface Props {
  data: KpForecastPoint[];
  loading?: boolean;
}

/** Smoothed predicted-Kp series with the G1 storm onset marked at Kp 5. */
export function KpForecastChart({ data, loading }: Props) {
  const theme = usePlotlyTheme();
  if (loading) return <div className="h-full animate-pulse rounded bg-surface-muted" />;
  if (!data.length) {
    return (
      <div className="flex h-full items-center justify-center text-xs text-slate-700">
        No data
      </div>
    );
  }

  return (
    <Plot
      data={[
        {
          x: data.map((d) => toPlotlyUtc(d.time)),
          y: data.map((d) => d.kp),
          type: "scatter",
          mode: "lines",
          name: "Predicted Kp",
          line: { color: "#a855f7", width: 1.5 },
        },
      ]}
      layout={
        {
          ...theme.layout,
          xaxis: {
            ...theme.axis,
            title: { text: "Time (UTC)", font: { size: 10 } },
            hoverformat: "%Y-%m-%d %H:%M UTC",
          },
          yaxis: {
            ...theme.axis,
            title: { text: "Predicted Kp", font: { size: 10 } },
            range: [0, 9],
            dtick: 1,
          },
          shapes: [
            {
              type: "line",
              xref: "paper",
              x0: 0,
              x1: 1,
              y0: 5,
              y1: 5,
              line: { color: "#ef4444", width: 1, dash: "dash" },
            },
          ],
          annotations: [
            {
              xref: "paper",
              x: 1,
              y: 5,
              xanchor: "right",
              yanchor: "bottom",
              text: "G1 storm onset",
              showarrow: false,
              font: { size: 9, color: "#ef4444" },
            },
          ],
          margin: { t: 20, r: 20, b: 40, l: 50 },
          showlegend: false,
        } as Plotly.Layout
      }
      config={{ displayModeBar: false, responsive: true }}
      style={{ width: "100%", height: "100%" }}
      useResizeHandler
    />
  );
}
