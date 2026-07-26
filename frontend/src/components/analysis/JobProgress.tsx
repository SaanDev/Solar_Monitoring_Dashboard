"use client";

import { useEffect, useRef } from "react";
import useSWR from "swr";
import { api } from "@/lib/api";
import type { AnalysisJobStatus } from "@/lib/types";

interface Props {
  jobId: string;
  onDone: (job: AnalysisJobStatus) => void;
  onError?: (message: string) => void;
}

/**
 * Polls a background analysis job and renders its progress bar. Fires onDone /
 * onError exactly once when the job settles (the burst-predictor uses the same
 * SWR refreshInterval-while-running pattern).
 */
export function JobProgress({ jobId, onDone, onError }: Props) {
  const fired = useRef(false);
  const { data: job } = useSWR(["analysis-job", jobId], () => api.analysisJob(jobId), {
    refreshInterval: (latest) =>
      latest && (latest.state === "running" || latest.state === "pending") ? 1200 : 0,
    // Keep polling even when the tab is backgrounded — a job started here should
    // finish and show its result regardless of focus (and SWR otherwise pauses the
    // interval while the document is hidden).
    refreshWhenHidden: true,
    revalidateOnFocus: false,
  });

  useEffect(() => {
    if (!job || fired.current) return;
    if (job.state === "done") {
      fired.current = true;
      onDone(job);
    } else if (job.state === "error") {
      fired.current = true;
      onError?.(job.error ?? "Job failed");
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.state]);

  const pct = Math.round((job?.progress ?? 0) * 100);
  const active = !job || job.state === "running" || job.state === "pending";

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs text-slate-500">
        <span className="truncate">{job?.message || "Starting…"}</span>
        <span>{pct}%</span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={pct}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={job?.message || "Job progress"}
        className="h-1.5 w-full overflow-hidden rounded bg-surface-muted"
      >
        {/* `transition-all` is on both states: the completed variant used to drop
            it, so the final jump to 100% and the blue→green swap snapped. */}
        <div
          className={
            active
              ? "h-full bg-accent-blue transition-all"
              : "h-full bg-accent-green transition-all"
          }
          style={{ width: `${pct}%` }}
        />
      </div>
      {job?.state === "error" && (
        <p className="text-xs text-accent-red">{job.error}</p>
      )}
    </div>
  );
}
