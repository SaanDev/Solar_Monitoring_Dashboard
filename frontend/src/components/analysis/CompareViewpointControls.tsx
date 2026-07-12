"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { CompareInfo } from "@/lib/types";

export interface SessionRef {
  id: string;
  label: string;
  nFrames: number;
}

interface Props {
  sessionId: string;
  frame: number;
  /** Sessions loaded earlier in this page visit (candidates for the other view). */
  history: SessionRef[];
  otherId: string;
  otherFrame: number;
  onOther: (id: string) => void;
  onOtherFrame: (n: number) => void;
  blinking: boolean;
  onBlinking: (v: boolean) => void;
}

const inputCls =
  "w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue";

/** Multi-viewpoint comparison (ported multiview): reproject another session's
 * map onto this frame's WCS/observer and blink the two views. */
export function CompareViewpointControls({
  sessionId,
  frame,
  history,
  otherId,
  otherFrame,
  onOther,
  onOtherFrame,
  blinking,
  onBlinking,
}: Props) {
  const [info, setInfo] = useState<CompareInfo | null>(null);
  const [error, setError] = useState<string | null>(null);
  const others = history.filter((s) => s.id !== sessionId);
  const selected = others.find((s) => s.id === otherId);

  useEffect(() => {
    setInfo(null);
    setError(null);
    if (!otherId) return;
    let stale = false;
    api
      .analysisCompareInfo(sessionId, frame, otherId, otherFrame)
      .then((r) => {
        if (!stale) setInfo(r);
      })
      .catch((e) => {
        if (!stale) setError(e instanceof Error ? e.message : "Comparison failed");
      });
    return () => {
      stale = true;
    };
  }, [sessionId, frame, otherId, otherFrame]);

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">Compare Viewpoint</h2>

      <p className="text-[10px] leading-relaxed text-slate-600">
        Reprojects another loaded session (e.g. STEREO/EUVI) onto this frame&apos;s
        WCS and observer, so the two viewpoints can be blinked pixel-for-pixel.
        Load the second observable via the Data Source first.
      </p>

      {others.length === 0 ? (
        <p className="text-xs text-accent-yellow">
          No other session loaded yet — fetch a second observable (it will appear
          here), then come back.
        </p>
      ) : (
        <>
          <div>
            <label className="mb-1 block text-xs text-slate-500">Other session</label>
            <select value={otherId} onChange={(e) => onOther(e.target.value)} className={inputCls}>
              <option value="">— choose —</option>
              {others.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          {selected && selected.nFrames > 1 && (
            <div>
              <label className="mb-1 block text-xs text-slate-500">
                Other frame (1–{selected.nFrames})
              </label>
              <input
                type="number"
                min={1}
                max={selected.nFrames}
                value={otherFrame + 1}
                onChange={(e) => onOtherFrame(Math.max(0, parseInt(e.target.value || "1", 10) - 1))}
                className={inputCls}
              />
            </div>
          )}
          {otherId && (
            <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-slate-400">
              <input
                type="checkbox"
                checked={blinking}
                onChange={(e) => onBlinking(e.target.checked)}
                className="h-3.5 w-3.5 accent-accent-blue"
              />
              Blink the two views
            </label>
          )}
        </>
      )}

      {info && (
        <div className="space-y-1 font-mono text-[11px] text-slate-300">
          <div>primary: {info.primary}</div>
          <div>other: {info.secondary}</div>
          {info.separation_deg != null && (
            <div>
              observer separation ={" "}
              <span className="text-accent-cyan">{info.separation_deg.toFixed(1)}°</span>
            </div>
          )}
        </div>
      )}
      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}
