import Link from "next/link";
import { Compass } from "lucide-react";

import { DashboardShell } from "@/components/layout/DashboardShell";

/**
 * Rendered inside the root layout, so the sidebar stays available — a 404 here
 * is a wrong-turn, not a dead end.
 */
export default function NotFound() {
  return (
    <DashboardShell title="Not Found">
      <div className="flex min-h-[60vh] items-center justify-center">
        <div className="w-full max-w-md rounded-lg border border-dashed border-surface-border p-8 text-center">
          <Compass className="mx-auto mb-3 h-6 w-6 text-slate-500" />
          <p className="font-mono text-xs uppercase tracking-widest text-slate-500">
            404
          </p>
          <h2 className="mt-2 text-sm font-semibold text-slate-200">
            No such page
          </h2>
          <p className="mt-2 text-xs leading-relaxed text-slate-400">
            That route doesn&apos;t exist. Pick a view from the sidebar, or head
            back to the Overview.
          </p>
          <div className="mt-4 flex items-center justify-center gap-2">
            <Link
              href="/"
              className="rounded bg-accent-blue/20 px-3 py-1.5 text-xs font-medium text-accent-blue transition-colors hover:bg-accent-blue/30"
            >
              Overview
            </Link>
            <Link
              href="/user-guide"
              className="rounded border border-surface-border px-3 py-1.5 text-xs text-slate-300 transition-colors hover:bg-surface-muted"
            >
              User Guide
            </Link>
          </div>
        </div>
      </div>
    </DashboardShell>
  );
}
