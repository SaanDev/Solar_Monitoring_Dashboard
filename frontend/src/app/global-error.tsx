"use client";

import { useEffect } from "react";
import "@/styles/globals.css";

/**
 * Last-resort boundary for errors thrown by the root layout itself. It replaces
 * the entire document, so unlike error.tsx it must supply its own <html>/<body>
 * and re-import the stylesheet — the root layout is precisely what has failed.
 *
 * `dark` is hardcoded here because AppProvider (and the pre-paint theme script)
 * are part of the tree that just crashed; dark is the app's documented default.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Global error:", error);
  }, [error]);

  return (
    <html lang="en" className="dark">
      <body className="flex h-screen items-center justify-center bg-surface p-6 text-slate-200 antialiased">
        <div className="w-full max-w-lg rounded-lg border border-surface-border bg-surface-card p-6">
          <h2 className="mb-3 text-sm font-semibold text-accent-red">
            The dashboard failed to start
          </h2>
          <p className="text-xs leading-relaxed text-slate-400">
            An error occurred outside of any single page, so the application
            shell could not be rendered.
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

          <button
            onClick={reset}
            className="mt-4 rounded bg-accent-blue/20 px-3 py-1.5 text-xs font-medium text-accent-blue transition-colors hover:bg-accent-blue/30"
          >
            Reload the dashboard
          </button>
        </div>
      </body>
    </html>
  );
}
