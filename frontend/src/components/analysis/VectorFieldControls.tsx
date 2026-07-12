"use client";

import { useState } from "react";
import { api } from "@/lib/api";
import { JobProgress } from "./JobProgress";
import { Slider } from "@/components/analyzer/Slider";

export interface VectorOptions {
  arrows: boolean;
  streamlines: boolean;
  magnitude: boolean;
  gridStep: number;
  minGauss: number;
}

interface Props {
  sessionId: string;
  frame: number;
  prepared: boolean;
  onPrepared: () => void;
  options: VectorOptions;
  onChange: (o: Partial<VectorOptions>) => void;
  jsocEnabled: boolean;
}

const btnCls =
  "w-full rounded bg-accent-blue/20 px-2 py-1.5 text-xs text-accent-blue transition-colors hover:bg-accent-blue/30 disabled:opacity-40";

/** HMI magnetic vector field (ported hmi_vector_field): fetch hmi.B_720s
 * segments via JSOC, resolve the 180° disambiguation, overlay Bx/By/Bz. */
export function VectorFieldControls({
  sessionId,
  frame,
  prepared,
  onPrepared,
  options,
  onChange,
  jsocEnabled,
}: Props) {
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function prepare() {
    setError(null);
    setJobId(null);
    try {
      const job = await api.analysisVectorPrepare(sessionId, frame);
      setJobId(job.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Vector preparation failed");
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">Magnetic Vector Field</h2>

      <p className="text-[10px] leading-relaxed text-slate-600">
        Fetches the hmi.B_720s field/inclination/azimuth/disambig segments nearest
        this frame&apos;s time (JSOC), resolves the 180° azimuth ambiguity and overlays
        the transverse field — <span className="text-accent-red">red = +B</span>
        <sub>z</sub> toward the observer, <span className="text-accent-blue">blue = −B</span>
        <sub>z</sub>.
      </p>

      {!prepared ? (
        <>
          <button disabled={!!jobId || !jsocEnabled} onClick={prepare} className={btnCls}>
            {jobId ? "Preparing…" : "Prepare vector data (JSOC)"}
          </button>
          {!jsocEnabled && (
            <p className="text-[10px] text-accent-yellow">
              Requires a JSOC-registered notify e-mail (set JSOC_EMAIL in the backend).
            </p>
          )}
          {jobId && (
            <JobProgress
              jobId={jobId}
              onDone={() => {
                setJobId(null);
                onPrepared();
              }}
              onError={(msg) => {
                setJobId(null);
                setError(msg);
              }}
            />
          )}
        </>
      ) : (
        <>
          <div className="flex flex-wrap gap-x-4 gap-y-1.5 text-xs text-slate-400">
            {(
              [
                ["arrows", "Arrows"],
                ["streamlines", "Streamlines"],
                ["magnitude", "|B| tint"],
              ] as const
            ).map(([key, label]) => (
              <label key={key} className="flex cursor-pointer select-none items-center gap-2">
                <input
                  type="checkbox"
                  checked={options[key]}
                  onChange={(e) => onChange({ [key]: e.target.checked })}
                  className="h-3.5 w-3.5 accent-accent-blue"
                />
                {label}
              </label>
            ))}
          </div>
          <Slider
            label="Arrow spacing (px)"
            value={options.gridStep}
            min={16}
            max={256}
            step={8}
            onChange={(v) => onChange({ gridStep: v })}
          />
          <Slider
            label="Min B⊥ (Gauss)"
            value={options.minGauss}
            min={0}
            max={1000}
            step={25}
            onChange={(v) => onChange({ minGauss: v })}
          />
        </>
      )}
      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}
