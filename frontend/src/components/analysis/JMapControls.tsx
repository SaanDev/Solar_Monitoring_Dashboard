"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { JobProgress } from "./JobProgress";
import { Slider } from "@/components/analyzer/Slider";

interface Props {
  sessionId: string;
  nFrames: number;
  onResult: (url: string | null) => void;
}

const inputCls =
  "w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue";
const btnCls =
  "w-full rounded bg-accent-blue/20 px-2 py-1.5 text-xs text-accent-blue transition-colors hover:bg-accent-blue/30 disabled:opacity-40";

/** Time–elongation J-map builder (ported hi_jmap): background-subtract the
 * stack, sample a radial slit per frame, stack profiles over time. */
export function JMapControls({ sessionId, nFrames, onResult }: Props) {
  const [pa, setPa] = useState(90);
  const [background, setBackground] = useState<"median" | "previous">("median");
  const [halfWidth, setHalfWidth] = useState(2);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function build() {
    setError(null);
    setJobId(null);
    onResult(null);
    try {
      const job = await api.analysisJMap(sessionId, pa, background, halfWidth);
      setJobId(job.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "J-map build failed");
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">J-map (Time–Elongation)</h2>

      <p className="text-[10px] leading-relaxed text-slate-600">
        Background-subtracts all {nFrames} frames, samples a radial slit at the
        chosen position angle and stacks the profiles over time — an outward CME
        appears as a slanted bright track.
      </p>

      <Slider label="Position angle (° N→E)" value={pa} min={0} max={359} step={1} onChange={setPa} />
      <div>
        <label className="mb-1 block text-xs text-slate-500">Background</label>
        <select
          value={background}
          onChange={(e) => setBackground(e.target.value as "median" | "previous")}
          className={inputCls}
        >
          <option value="median">Temporal median (static F-corona/starfield)</option>
          <option value="previous">Previous frame (running difference)</option>
        </select>
      </div>
      <Slider label="Slit half-width (px)" value={halfWidth} min={0} max={10} step={1} onChange={setHalfWidth} />

      <button disabled={!!jobId} onClick={build} className={btnCls}>
        {jobId ? "Building…" : "Build J-map"}
      </button>
      {jobId && (
        <JobProgress
          jobId={jobId}
          onDone={(job) => {
            setJobId(null);
            if (job.result_url) onResult(job.result_url);
          }}
          onError={(msg) => {
            setJobId(null);
            setError(msg);
          }}
        />
      )}
      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}
