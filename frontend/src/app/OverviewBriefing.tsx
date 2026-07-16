"use client";

import useSWR from "swr";
import { Sparkles } from "lucide-react";

import { api } from "@/lib/api";

/** Friendly model label, e.g. "claude-opus-4-8" → "Claude Opus 4.8". */
function modelLabel(model: string | null): string {
  if (!model) return "Claude";
  const m = model.match(/^claude-([a-z]+)-(\d)-(\d)$/);
  if (m) return `Claude ${m[1][0].toUpperCase()}${m[1].slice(1)} ${m[2]}.${m[3]}`;
  return model;
}

/**
 * Natural-language "State of the Sun" operator briefing — a plain-English
 * summary Claude generates from the dashboard's own current conditions, alerts,
 * forecast, and event-chain storylines. Server-side change-gated + cached; the
 * card hides entirely when no API key is configured (`available === false`).
 */
export function OverviewBriefing() {
  const { data, isLoading } = useSWR("summary-briefing", api.summaryBriefing, {
    refreshInterval: 300000,
  });

  // Feature not configured server-side → render nothing.
  if (data && !data.available) return null;

  return (
    <div className="rounded-lg border border-surface-border bg-surface-card p-4">
      <div className="mb-2 flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-1.5 text-xs uppercase tracking-wider text-slate-500">
          <Sparkles className="h-3.5 w-3.5 text-accent-cyan" />
          State of the Sun
        </h2>
        <span className="rounded border border-surface-border px-1.5 py-0.5 text-[9px] uppercase tracking-wider text-slate-500">
          AI-generated
        </span>
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <div className="h-3.5 w-full animate-pulse rounded bg-surface-muted" />
          <div className="h-3.5 w-11/12 animate-pulse rounded bg-surface-muted" />
          <div className="h-3.5 w-3/4 animate-pulse rounded bg-surface-muted" />
        </div>
      ) : data?.text ? (
        <p className="text-sm leading-relaxed text-slate-200">{data.text}</p>
      ) : (
        <p className="text-sm text-slate-500">
          Briefing is being generated from the latest conditions…
        </p>
      )}

      <p className="mt-2.5 text-[10px] text-slate-600">
        {data?.generated_at && (
          <>Generated {data.generated_at.slice(11, 16)} UTC · </>
        )}
        Summarized by {modelLabel(data?.model ?? null)} from this dashboard&apos;s data —
        verify against the panels below.
      </p>
    </div>
  );
}
