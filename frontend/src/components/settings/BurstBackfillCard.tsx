"use client";

import { useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { Loader2, RefreshCw, X } from "lucide-react";

import { api } from "@/lib/api";
import type { BackfillDayCoverage, BackfillJob } from "@/lib/types";
import { EmptyState } from "@/components/ui/EmptyState";

/** Colour + wording per coverage state. "partial" is not an error: today is
 * always partial, because its most recent hours belong to the live scanner. */
const STATE_STYLE: Record<BackfillDayCoverage["state"], { cell: string; label: string }> = {
  done: { cell: "bg-accent-green/70", label: "fully scored" },
  partial: { cell: "bg-accent-yellow/70", label: "partly scored" },
  running: { cell: "bg-accent-blue/70 animate-pulse", label: "scoring now" },
  pending: { cell: "bg-accent-blue/30", label: "queued" },
  error: { cell: "bg-accent-red/70", label: "failed" },
  unknown: { cell: "bg-surface-muted", label: "never checked" },
};

function dayTooltip(d: BackfillDayCoverage): string {
  const state = STATE_STYLE[d.state]?.label ?? d.state;
  const files = d.archive_files
    ? ` — ${d.covered_files.toLocaleString()}/${d.archive_files.toLocaleString()} segments`
    : "";
  const events = d.events ? ` · ${d.events} burst event${d.events === 1 ? "" : "s"}` : "";
  return `${d.day}: ${state}${files}${events}${d.error ? `\n${d.error}` : ""}`;
}

function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded bg-surface-muted">
      <div
        className="h-full rounded bg-accent-blue transition-[width] duration-500"
        style={{ width: `${Math.round(Math.min(1, Math.max(0, value)) * 100)}%` }}
      />
    </div>
  );
}

function JobProgress({ job }: { job: BackfillJob }) {
  const running = job.status === "running";
  const dayShare = job.day_files_total
    ? job.day_files_done / job.day_files_total
    : running
      ? 0
      : 1;
  // Days already finished, plus how far into the day in flight we are.
  const overall = job.days_total
    ? (job.days_done + (running ? dayShare : 0)) / job.days_total
    : 1;

  return (
    <div className="mt-4 rounded border border-surface-border bg-surface-muted/30 p-3">
      <div className="flex flex-wrap items-center justify-between gap-2 text-xs">
        <span className="flex items-center gap-2 text-slate-300">
          {running && <Loader2 className="h-3.5 w-3.5 animate-spin text-accent-blue" />}
          {running
            ? job.current_day
              ? `Scoring ${job.current_day}`
              : job.message || "Working"
            : job.status === "error"
              ? "Last run failed"
              : job.status === "cancelled"
                ? "Last run cancelled"
                : "Last run finished"}
        </span>
        <span className="font-mono text-[10px] text-slate-500">
          {job.trigger === "auto" ? "automatic" : "manual"}
          {job.force ? " · re-score" : ""} · {job.start_day} → {job.end_day}
        </span>
      </div>

      {job.days_total > 0 && (
        <div className="mt-2">
          <ProgressBar value={overall} />
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-1 font-mono text-[10px] text-slate-500">
            <span>
              day {Math.min(job.days_done + (running ? 1 : 0), job.days_total)}/
              {job.days_total}
            </span>
            {running && job.day_files_total > 0 && (
              <span>
                segments {job.day_files_done.toLocaleString()}/
                {job.day_files_total.toLocaleString()}
              </span>
            )}
            <span>{job.files_scored.toLocaleString()} scored</span>
            {job.files_failed > 0 && (
              <span className="text-accent-yellow">
                {job.files_failed.toLocaleString()} unreadable
              </span>
            )}
            <span>{job.events_written} burst events rebuilt</span>
            <span>{job.model_name}</span>
          </div>
        </div>
      )}

      {job.days_total === 0 && !running && (
        <p className="mt-1 text-[11px] text-slate-500">
          No gaps were found in that range.
        </p>
      )}
      {job.error && (
        <p className="mt-2 text-[11px] text-accent-red">{job.error}</p>
      )}
    </div>
  );
}

/**
 * Detection coverage — and the catch-up that repairs it.
 *
 * The live scanner only scores the last few hours of e-CALLISTO data, so every
 * hour the backend is down is an hour that never gets scored: a hole in the
 * Timeline's burst lane and in the correlation histograms. The backend fills
 * those days automatically; this card is where that becomes visible (which days
 * are covered, what the current run is doing) and where a run can be aimed at a
 * range by hand, further back than the automatic window reaches.
 */
export function BurstBackfillCard() {
  const [range, setRange] = useState<{ start: string; end: string }>({ start: "", end: "" });
  const [force, setForce] = useState(false);
  const [custom, setCustom] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [statusTone, setStatusTone] = useState<"ok" | "error">("ok");

  const { data, mutate, error } = useSWR(
    "burst-backfill",
    () => api.burstBackfillStatus(30),
    {
      revalidateOnFocus: false,
      // Poll while a run is in flight; idle otherwise.
      refreshInterval: (latest) => (latest?.running ? 3000 : 60000),
    }
  );

  if (error) {
    return (
      <section className="rounded-lg border border-surface-border bg-surface-card p-5">
        <h2 className="mb-4 text-sm font-semibold text-slate-200">Detection Coverage</h2>
        <EmptyState
          tone="error"
          message="Couldn't load burst-detection coverage. Automatic catch-up is unaffected."
        />
      </section>
    );
  }

  if (!data) {
    return (
      <section className="rounded-lg border border-surface-border bg-surface-card p-5">
        <h2 className="text-sm font-semibold text-slate-200">Detection Coverage</h2>
        <div className="mt-4 h-24 animate-pulse rounded bg-surface-muted" />
      </section>
    );
  }

  const past = data.coverage.slice(0, -1); // today is partial by design
  const covered = past.filter((d) => d.state === "done").length;
  const gaps = past.filter((d) => d.state !== "done");

  const run = async (start?: string, end?: string, forceRun = false) => {
    setBusy(true);
    setStatus(null);
    try {
      const job = await api.startBurstBackfill(start, end, forceRun);
      await mutate();
      setStatus(
        job.force
          ? "Re-scoring started — this re-downloads every segment in the range."
          : "Catch-up started."
      );
      setStatusTone("ok");
    } catch (e) {
      setStatus(`Couldn't start: ${e instanceof Error ? e.message : e}`);
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  };

  const stop = async () => {
    setBusy(true);
    try {
      await api.cancelBurstBackfill();
      await mutate();
      setStatus("Stopping after the segments in flight. Scored days are kept.");
      setStatusTone("ok");
    } catch (e) {
      setStatus(`Couldn't stop: ${e instanceof Error ? e.message : e}`);
      setStatusTone("error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-lg border border-surface-border bg-surface-card p-5">
      <h2 className="text-sm font-semibold text-slate-200">Detection Coverage</h2>
      <p className="mt-1 text-xs text-slate-500">
        Burst detection only runs on live data, so time the dashboard spends offline
        leaves gaps in the timeline and the correlation histograms. Missed days are
        scored automatically in the background — the last{" "}
        {data.auto_window_days} days are checked hourly.
      </p>

      {!data.enabled && (
        <p className="mt-3 rounded border border-accent-yellow/40 bg-accent-yellow/5 px-3 py-2 text-[11px] text-accent-yellow">
          Automatic catch-up is switched off in this deployment
          (RADIO_BURST_BACKFILL_ENABLED). Runs started here still work.
        </p>
      )}

      {/* Coverage strip: one cell per UTC day, oldest on the left. */}
      <div className="mt-4">
        <div className="flex gap-[3px]">
          {data.coverage.map((d) => (
            <div
              key={d.day}
              title={dayTooltip(d)}
              className={clsx(
                "h-7 flex-1 rounded-sm",
                STATE_STYLE[d.state]?.cell ?? "bg-surface-muted"
              )}
            />
          ))}
        </div>
        <div className="mt-1.5 flex justify-between font-mono text-[10px] text-slate-600">
          <span>{data.coverage[0]?.day}</span>
          <span>today</span>
        </div>
      </div>

      <p className="mt-2 text-xs text-slate-400">
        {covered}/{past.length} past days fully scored
        {gaps.length > 0 && (
          <>
            {" · "}
            <span className="text-accent-yellow">
              {gaps.length} day{gaps.length === 1 ? "" : "s"} incomplete
            </span>
          </>
        )}
        . Today stays partial: its last {data.live_window_hours} h are the live
        scanner&rsquo;s.
      </p>

      {data.job && <JobProgress job={data.job} />}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          onClick={() => run()}
          disabled={busy || data.running}
          className="flex items-center gap-2 rounded bg-accent-blue px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-blue/80 disabled:opacity-50"
        >
          {busy && !data.running ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <RefreshCw className="h-3.5 w-3.5" />
          )}
          Fill gaps now
        </button>
        {data.running && (
          <button
            onClick={stop}
            disabled={busy}
            className="flex items-center gap-2 rounded border border-surface-border px-3 py-1.5 text-sm text-slate-300 hover:border-accent-red hover:text-accent-red disabled:opacity-50"
          >
            <X className="h-3.5 w-3.5" />
            Stop
          </button>
        )}
        <button
          onClick={() => setCustom((v) => !v)}
          className="text-xs text-slate-500 underline-offset-2 hover:text-slate-300 hover:underline"
        >
          {custom ? "Hide date range" : "Choose a date range…"}
        </button>
      </div>

      {custom && (
        <div className="mt-3 rounded border border-surface-border bg-surface-muted/30 p-3">
          <p className="text-[11px] text-slate-500">
            Reach further back than the automatic window, e.g. after a long outage.
            A day of archive is roughly 5,000 segments (~30 min of scoring), and the
            run works newest day first so the most recent gap closes first.
          </p>
          <div className="mt-3 flex flex-wrap items-end gap-3">
            <label className="text-[11px] text-slate-400">
              From
              <input
                type="date"
                value={range.start}
                max={range.end || undefined}
                onChange={(e) => setRange((r) => ({ ...r, start: e.target.value }))}
                className="mt-1 block rounded border border-surface-border bg-surface-card px-2 py-1 text-xs text-slate-200"
              />
            </label>
            <label className="text-[11px] text-slate-400">
              To
              <input
                type="date"
                value={range.end}
                min={range.start || undefined}
                onChange={(e) => setRange((r) => ({ ...r, end: e.target.value }))}
                className="mt-1 block rounded border border-surface-border bg-surface-card px-2 py-1 text-xs text-slate-200"
              />
            </label>
            <label className="flex items-center gap-2 pb-1 text-[11px] text-slate-400">
              <input
                type="checkbox"
                checked={force}
                onChange={(e) => setForce(e.target.checked)}
                className="h-3.5 w-3.5 accent-[var(--accent-blue,#3b82f6)]"
              />
              Re-score days that are already covered
            </label>
            <button
              onClick={() => run(range.start || undefined, range.end || undefined, force)}
              disabled={busy || data.running || (!range.start && !range.end)}
              className="rounded border border-accent-blue px-3 py-1.5 text-xs font-medium text-accent-blue hover:bg-accent-blue/10 disabled:opacity-50"
            >
              Run range
            </button>
          </div>
          {force && (
            <p className="mt-2 text-[11px] text-accent-yellow">
              Re-scoring downloads and scores every segment in the range again with
              the current model, replacing the stored verdicts. Days already covered
              are otherwise skipped, whichever model scored them.
            </p>
          )}
        </div>
      )}

      {status && (
        <p
          role="status"
          aria-live="polite"
          className={clsx(
            "mt-3 text-xs",
            statusTone === "ok" ? "text-accent-green" : "text-accent-red"
          )}
        >
          {status}
        </p>
      )}

      <p className="mt-3 text-[11px] text-slate-600">
        Filled-in bursts appear on the Timeline, the Events page and the activity
        histograms, but never send notifications — a gap closed days later would
        otherwise replay as a wave of stale alerts.
      </p>
    </section>
  );
}
