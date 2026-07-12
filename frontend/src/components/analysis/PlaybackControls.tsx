"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronLeft, ChevronRight, Pause, Play, SkipBack, SkipForward } from "lucide-react";
import type { AnalysisFrameMeta } from "@/lib/types";

interface Props {
  sessionId: string;
  frame: number;
  nFrames: number;
  /** First playable frame (1 for running-difference views, else 0). */
  minFrame?: number;
  /** Frame metadata for the timestamp readout. */
  frames?: AnalysisFrameMeta[];
  onFrame: (f: number) => void;
  /** Current-view URL for an arbitrary frame — lets Play pre-warm the
   * browser/server caches so the first loop stutters less. */
  preloadUrl?: (frame: number) => string | null;
}

const btnCls =
  "flex flex-1 items-center justify-center rounded bg-surface-muted py-1.5 text-slate-300 transition-colors hover:bg-accent-blue/20 hover:text-accent-blue disabled:opacity-40 disabled:hover:bg-surface-muted disabled:hover:text-slate-300";

/** Video-style playback bar for multi-frame sessions: first/prev/play/next/last,
 * frame slider and an fps control (mirrors the desktop tool's playback bar). */
export function PlaybackControls({
  sessionId,
  frame,
  nFrames,
  minFrame = 0,
  frames = [],
  onFrame,
  preloadUrl,
}: Props) {
  const [playing, setPlaying] = useState(false);
  const [fps, setFps] = useState(8);

  // Refs keep the interval callback reading fresh values without re-arming.
  const frameRef = useRef(frame);
  frameRef.current = frame;
  const onFrameRef = useRef(onFrame);
  onFrameRef.current = onFrame;

  // A new session (or a view whose first playable frame moved) stops playback.
  useEffect(() => setPlaying(false), [sessionId, minFrame]);

  useEffect(() => {
    if (!playing || nFrames < 2) return;
    const t = setInterval(() => {
      const next = frameRef.current + 1;
      onFrameRef.current(next > nFrames - 1 ? minFrame : next);
    }, Math.max(40, 1000 / Math.max(1, fps)));
    return () => clearInterval(t);
  }, [playing, fps, nFrames, minFrame]);

  function togglePlay() {
    if (!playing && preloadUrl) {
      // Fire-and-forget warm-up of every frame of the current view.
      for (let i = minFrame; i < nFrames; i++) {
        const u = preloadUrl(i);
        if (u) new Image().src = u;
      }
    }
    setPlaying((p) => !p);
  }

  function jump(f: number) {
    setPlaying(false);
    onFrame(Math.min(nFrames - 1, Math.max(minFrame, f)));
  }

  const time = frames.find((f) => f.index === frame)?.time ?? null;

  return (
    <div className="space-y-2 rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="flex items-baseline justify-between">
        <label className="block text-xs text-slate-500">
          Frame {frame + 1} / {nFrames}
        </label>
        {time && (
          <span className="font-mono text-[10px] text-slate-500">
            {time.replace("T", " ").slice(0, 19)} UTC
          </span>
        )}
      </div>

      <input
        type="range"
        min={minFrame}
        max={nFrames - 1}
        step={1}
        value={frame}
        onChange={(e) => jump(parseInt(e.target.value, 10))}
        className="w-full accent-accent-blue"
      />

      <div className="flex items-center gap-1">
        <button onClick={() => jump(minFrame)} disabled={frame <= minFrame} className={btnCls} title="First frame">
          <SkipBack className="h-3.5 w-3.5" />
        </button>
        <button onClick={() => jump(frame - 1)} disabled={frame <= minFrame} className={btnCls} title="Previous frame">
          <ChevronLeft className="h-3.5 w-3.5" />
        </button>
        <button
          onClick={togglePlay}
          className="flex flex-[1.6] items-center justify-center rounded bg-accent-blue/20 py-1.5 text-accent-blue transition-colors hover:bg-accent-blue/30"
          title={playing ? "Stop" : "Play"}
        >
          {playing ? <Pause className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
        </button>
        <button onClick={() => jump(frame + 1)} disabled={frame >= nFrames - 1} className={btnCls} title="Next frame">
          <ChevronRight className="h-3.5 w-3.5" />
        </button>
        <button onClick={() => jump(nFrames - 1)} disabled={frame >= nFrames - 1} className={btnCls} title="Last frame">
          <SkipForward className="h-3.5 w-3.5" />
        </button>
        <div className="ml-2 flex items-center gap-1" title="Playback speed (frames per second)">
          <input
            type="number"
            min={1}
            max={30}
            value={fps}
            onChange={(e) => setFps(Math.min(30, Math.max(1, parseInt(e.target.value || "1", 10))))}
            className="w-12 rounded border border-surface-border bg-surface-muted px-1.5 py-1 text-center text-xs text-slate-300 outline-none focus:border-accent-blue"
          />
          <span className="text-[10px] text-slate-500">fps</span>
        </div>
      </div>
    </div>
  );
}
