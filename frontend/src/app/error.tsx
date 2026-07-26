"use client";

import { useEffect } from "react";
import Link from "next/link";
import { AlertTriangle, RotateCw } from "lucide-react";

/**
 * Route-level error boundary. Without this a single render throw anywhere in a
 * page tears down the whole shell to Next's default screen. The sidebar stays
 * mounted (it lives in the root layout), so the user can still navigate away
 * even if this particular route keeps failing.
 */
export default function RouteError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Route error:", error);
  }, [error]);

  return (
    <div className="flex flex-1 items-center justify-center overflow-y-auto p-6">
      <div className="w-full max-w-lg rounded-lg border border-surface-border bg-surface-card p-6">
        <div className="mb-3 flex items-center gap-2">
          <AlertTriangle className="h-5 w-5 shrink-0 text-accent-red" />
          <h2 className="text-sm font-semibold text-slate-200">
            This page failed to render
          </h2>
        </div>

        <p className="text-xs leading-relaxed text-slate-400">
          Something went wrong while building this view. Other pages are
          unaffected — you can retry, or navigate elsewhere from the sidebar.
        </p>

        {error.message ? (
          <pre className="mt-3 max-h-40 overflow-auto rounded border border-surface-border bg-surface-muted p-3 font-mono text-[11px] leading-relaxed text-slate-400">
            {error.message}
          </pre>
        ) : null}

        {error.digest ? (
          <p className="mt-2 font-mono text-[10px] text-slate-500">
            Digest: {error.digest}
          </p>
        ) : null}

        <div className="mt-4 flex items-center gap-2">
          <button
            onClick={reset}
            className="flex items-center gap-1.5 rounded bg-accent-blue/20 px-3 py-1.5 text-xs font-medium text-accent-blue transition-colors hover:bg-accent-blue/30"
          >
            <RotateCw className="h-3.5 w-3.5" />
            Try again
          </button>
          <Link
            href="/"
            className="rounded border border-surface-border px-3 py-1.5 text-xs text-slate-300 transition-colors hover:bg-surface-muted"
          >
            Back to Overview
          </Link>
        </div>
      </div>
    </div>
  );
}
