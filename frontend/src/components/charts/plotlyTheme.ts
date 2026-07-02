"use client";

import { useMemo } from "react";
import { useApp } from "@/components/providers";

/**
 * Theme-aware base tokens for the Plotly charts. Plotly colors are set as
 * literal values in each chart's `layout`, so they can't follow the CSS
 * variables in globals.css — every chart instead merges these over its own
 * layout and re-renders when the resolved theme flips.
 */
export interface PlotlyTheme {
  /** True in dark mode — for the rare trace color that must flip too. */
  dark: boolean;
  /** `paper_bgcolor` / `plot_bgcolor` / `font` for the layout root. */
  layout: {
    paper_bgcolor: string;
    plot_bgcolor: string;
    font: { color: string; size: number };
  };
  /** `color` + `gridcolor` to spread into each axis. */
  axis: { color: string; gridcolor: string };
}

const DARK = {
  plotBg: "#0a0d14",
  fontColor: "#94a3b8", // slate-400
  axisColor: "#475569", // slate-600
  gridColor: "#1e2535", // surface-border
};

const LIGHT = {
  plotBg: "#ffffff", // matches the light card surface
  fontColor: "#475569", // slate-600
  axisColor: "#64748b", // slate-500
  gridColor: "#e2e8f0", // slate-200
};

export function usePlotlyTheme(): PlotlyTheme {
  const { resolved } = useApp();
  return useMemo(() => {
    const t = resolved === "light" ? LIGHT : DARK;
    return {
      dark: resolved !== "light",
      layout: {
        paper_bgcolor: "transparent",
        plot_bgcolor: t.plotBg,
        font: { color: t.fontColor, size: 11 },
      },
      axis: { color: t.axisColor, gridcolor: t.gridColor },
    };
  }, [resolved]);
}
