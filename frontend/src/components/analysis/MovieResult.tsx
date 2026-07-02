"use client";

import { Download } from "lucide-react";
import { apiUrl } from "@/lib/api";
import { JobProgress } from "./JobProgress";

interface Props {
  jobId: string | null;
  fmt: "mp4" | "gif";
  resultUrl: string | null;
  onResult: (url: string) => void;
  onError: (message: string) => void;
}

/** Right-column output for the Movie tool: progress while building, then the
 * playable MP4 / animated GIF with a download link. */
export function MovieResult({ jobId, fmt, resultUrl, onResult, onError }: Props) {
  return (
    <div className="flex h-full flex-col rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-wider text-slate-500">Time-lapse</h2>
        {resultUrl && (
          <a
            href={`${resultUrl}${resultUrl.includes("?") ? "&" : "?"}download=true`}
            download
            className="flex items-center gap-1 rounded bg-surface-muted px-2 py-1 text-xs text-slate-300 transition-colors hover:bg-accent-blue/30 hover:text-accent-blue"
          >
            <Download className="h-3.5 w-3.5" /> {fmt.toUpperCase()}
          </a>
        )}
      </div>

      <div className="relative flex min-h-[460px] flex-1 items-center justify-center overflow-hidden rounded bg-black/30">
        {!jobId && !resultUrl && (
          <p className="px-4 text-center text-sm text-slate-600">
            Choose options and click “Build movie”.
          </p>
        )}

        {jobId && !resultUrl && (
          <div className="w-full max-w-sm px-6">
            <JobProgress
              jobId={jobId}
              onDone={(job) =>
                job.result_url ? onResult(apiUrl(job.result_url)) : onError("No movie produced")
              }
              onError={onError}
            />
          </div>
        )}

        {resultUrl &&
          (fmt === "mp4" ? (
            <video
              key={resultUrl}
              src={resultUrl}
              controls
              autoPlay
              loop
              muted
              className="max-h-full max-w-full object-contain"
            />
          ) : (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={resultUrl} alt="Time-lapse movie" className="max-h-full max-w-full object-contain" />
          ))}
      </div>
    </div>
  );
}
