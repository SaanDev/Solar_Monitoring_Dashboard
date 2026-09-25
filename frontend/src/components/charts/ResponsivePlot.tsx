"use client";

import dynamic from "next/dynamic";
import { useEffect, useRef } from "react";
import type { PlotParams } from "react-plotly.js";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

/**
 * A Plotly chart that fills its parent and keeps following the parent's size.
 *
 * react-plotly's `useResizeHandler` (and Plotly's `responsive` config) only react
 * to *window* resizes. A plot whose box changes size on its own — e.g. an Overview
 * grid row that grows once the neighbouring e-CALLISTO spectrum image loads —
 * kept its stale pixel size. A ResizeObserver on the box closes that gap, and
 * covers window resizes too.
 *
 * The plot is absolutely positioned so its drawn pixel size never feeds back into
 * the parent's height; otherwise a grid row, once grown, could never shrink again.
 * The parent therefore needs a definite height (h-72, flex-1 in a sized column…).
 */
export function ResponsivePlot(props: PlotParams) {
  const boxRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const box = boxRef.current;
    if (!box || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => {
      const gd = box.querySelector<HTMLElement>(".js-plotly-plot");
      if (!gd) return; // not drawn yet — Plotly sizes itself on first draw
      // Same bundle react-plotly already loaded, so this resolves from cache.
      // Plots.resize debounces per plot, and rejects while the plot is hidden.
      void import("plotly.js/dist/plotly")
        .then(({ default: Plotly }) => Plotly.Plots.resize(gd))
        .catch(() => {});
    });
    observer.observe(box);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="relative h-full w-full">
      <div ref={boxRef} className="absolute inset-0">
        <Plot {...props} style={{ width: "100%", height: "100%", ...props.style }} />
      </div>
    </div>
  );
}
