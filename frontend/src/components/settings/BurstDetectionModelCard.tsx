"use client";

import { useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { Check, Loader2 } from "lucide-react";

import { api } from "@/lib/api";
import type { ModelInfo } from "@/lib/types";
import { EmptyState } from "@/components/ui/EmptyState";

/** Metrics worth showing per model, in the order they read best. */
const METRIC_LABELS: [key: string, label: string][] = [
  ["test_f1", "test F1"],
  ["val_f1", "val F1"],
  ["test_accuracy", "test acc"],
];

function metricSummary(model: ModelInfo): string {
  const parts = METRIC_LABELS.filter(([k]) => model.metrics?.[k] != null).map(
    ([k, label]) => `${label} ${model.metrics[k].toFixed(3)}`
  );
  if (model.threshold != null) parts.unshift(`threshold ${model.threshold}`);
  return parts.join(" · ");
}

/**
 * Which classifier the *automatic* burst detection + alert system runs.
 *
 * The choice is server-side state, not a browser preference: the background
 * scanner is what uses it, so it is stored in the backend and applies to every
 * viewer. The Burst Detector page keeps its own per-run picker — this only
 * decides what runs unattended (and what that page preselects).
 */
export function BurstDetectionModelCard() {
  const { data, mutate, error } = useSWR("radio-models", api.radioModels, {
    revalidateOnFocus: false,
  });
  // Pending choice; null = showing whatever the server currently has.
  const [choice, setChoice] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [status, setStatus] = useState<string | null>(null);
  const [statusTone, setStatusTone] = useState<"ok" | "error">("ok");

  if (error) {
    return (
      <section className="rounded-lg border border-surface-border bg-surface-card p-5">
        <h2 className="mb-4 text-sm font-semibold text-slate-200">
          Automatic Burst Detection
        </h2>
        <EmptyState
          tone="error"
          message="Couldn't load the burst classifiers. The detection model is unchanged."
        />
      </section>
    );
  }

  if (!data) {
    return (
      <section className="rounded-lg border border-surface-border bg-surface-card p-5">
        <h2 className="text-sm font-semibold text-slate-200">Automatic Burst Detection</h2>
        <div className="mt-4 h-24 animate-pulse rounded bg-surface-muted" />
      </section>
    );
  }

  const binaryModels = data.models.filter((m) => m.kind === "binary");
  const active = data.default_binary;
  const selected = choice ?? active;
  const dirty = selected !== active;

  const save = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const updated = await api.setBurstDetectionModel(selected);
      await mutate(updated, { revalidate: false });
      setChoice(null);
      const name = updated.models.find((m) => m.id === updated.default_binary)?.name;
      setStatus(`Saved — automatic detection now uses ${name ?? updated.default_binary}.`);
      setStatusTone("ok");
    } catch (e) {
      setStatus(`Save failed: ${e instanceof Error ? e.message : e}`);
      setStatusTone("error");
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="rounded-lg border border-surface-border bg-surface-card p-5">
      <h2 className="text-sm font-semibold text-slate-200">Automatic Burst Detection</h2>
      <p className="mt-1 text-xs text-slate-500">
        The classifier the background scan runs over new e-CALLISTO data to raise
        radio-burst alerts. Applies to every viewer, not just this browser.
      </p>

      <div className="mt-4 space-y-2">
        {binaryModels.map((m) => {
          const isSelected = selected === m.id;
          const summary = metricSummary(m);
          return (
            <label
              key={m.id}
              title={m.available ? m.full_name : "Checkpoint missing — run git lfs pull"}
              className={clsx(
                "flex gap-3 rounded border p-3 transition-colors",
                !m.available
                  ? "cursor-not-allowed border-surface-border bg-surface-muted/20 opacity-50"
                  : isSelected
                    ? "cursor-pointer border-accent-blue bg-accent-blue/10"
                    : "cursor-pointer border-surface-border bg-surface-muted/30 hover:border-slate-600"
              )}
            >
              <input
                type="radio"
                name="burst-detection-model"
                value={m.id}
                checked={isSelected}
                disabled={!m.available || saving}
                onChange={() => setChoice(m.id)}
                className="mt-0.5 h-4 w-4 accent-[var(--accent-blue,#3b82f6)]"
              />
              <span className="min-w-0">
                <span className="flex flex-wrap items-center gap-2">
                  <span className="text-sm font-medium text-slate-200">{m.name}</span>
                  {m.id === active && (
                    <span className="flex items-center gap-1 rounded bg-accent-green/10 px-1.5 py-0.5 text-[10px] font-medium text-accent-green">
                      <Check className="h-3 w-3" />
                      In use
                    </span>
                  )}
                  {!m.available && (
                    <span className="rounded bg-surface-muted px-1.5 py-0.5 text-[10px] text-slate-400">
                      checkpoint missing
                    </span>
                  )}
                </span>
                <span className="mt-1 block text-xs text-slate-500">{m.description}</span>
                {summary && (
                  <span className="mt-1 block font-mono text-[10px] text-slate-600">
                    {summary}
                  </span>
                )}
              </span>
            </label>
          );
        })}
      </div>

      <p className="mt-3 text-[11px] text-slate-600">
        A change takes effect on the next scan: the last few hours are re-scored
        with the new model and the burst alerts rebuilt from that, so recent
        events may shift. Each model alerts on its own tuned threshold. The Burst
        Detector page&rsquo;s per-run picker is unaffected.
        {data.default_binary_source === "config" &&
          " No model has been chosen here yet — the backend default is in force."}
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          onClick={save}
          disabled={saving || !dirty}
          className="flex items-center gap-2 rounded bg-accent-blue px-4 py-1.5 text-sm font-medium text-white hover:bg-accent-blue/80 disabled:opacity-50"
        >
          {saving && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
          Save
        </button>
        {status && (
          <span
            role="status"
            aria-live="polite"
            className={clsx(
              "text-xs",
              statusTone === "ok" ? "text-accent-green" : "text-accent-red"
            )}
          >
            {status}
          </span>
        )}
      </div>
    </section>
  );
}
