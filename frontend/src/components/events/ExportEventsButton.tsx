"use client";

import { useMemo, useState } from "react";
import { Download } from "lucide-react";
import { clsx } from "clsx";

import {
  countEventsForDay,
  exportEventReport,
  type ReportEvent,
} from "@/lib/exportEvents";

function todayUtc(): string {
  return new Date().toISOString().slice(0, 10);
}

/**
 * Download a day's space-weather events as a .txt, grouped by event type
 * (X-ray flares / radio bursts / SEP events / geomagnetic storms).
 *
 * Pass `events` spanning any number of days; the control exports just the
 * selected UTC day. With `fixedDay` the day is locked and no date picker is
 * shown — used where the page already has a date in context (e.g. the Burst
 * Predictor); otherwise a date input lets the user choose the day.
 */
export function ExportEventsButton({
  events,
  fixedDay,
  className,
}: {
  events: ReportEvent[];
  fixedDay?: string;
  className?: string;
}) {
  const [pickedDay, setPickedDay] = useState<string>(todayUtc());
  const day = fixedDay ?? pickedDay;
  const count = useMemo(() => countEventsForDay(day, events), [day, events]);

  return (
    <div className={clsx("flex items-center gap-2", className)}>
      {!fixedDay && (
        <input
          type="date"
          aria-label="Export day (UTC)"
          value={pickedDay}
          max={todayUtc()}
          onChange={(e) => setPickedDay(e.target.value)}
          className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue"
        />
      )}
      <button
        onClick={() => exportEventReport(day, events)}
        disabled={count === 0}
        title={
          count === 0
            ? `No events on ${day}`
            : `Export ${count} event(s) for ${day} as a .txt file`
        }
        className={clsx(
          "flex items-center gap-1.5 rounded-md px-3 py-1 text-xs font-medium transition-colors",
          count === 0
            ? "cursor-not-allowed bg-surface-muted text-slate-600"
            : "bg-accent-blue/20 text-accent-blue hover:bg-accent-blue/30"
        )}
      >
        <Download className="h-3.5 w-3.5" />
        Export .txt
        <span className="rounded bg-black/20 px-1 text-[10px] tabular-nums">{count}</span>
      </button>
    </div>
  );
}
