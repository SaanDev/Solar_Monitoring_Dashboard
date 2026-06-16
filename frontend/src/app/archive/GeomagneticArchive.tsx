"use client";

import { useState } from "react";
import useSWR from "swr";
import { Download } from "lucide-react";

import { api } from "@/lib/api";
import { KpChart } from "@/components/charts/KpChart";
import { DstChart } from "@/components/charts/DstChart";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function shiftDays(d: string, days: number): string {
  const t = new Date(d + "T00:00:00Z").getTime() + days * 86400000;
  return new Date(t).toISOString().slice(0, 10);
}

function utcToday(): string {
  return new Date().toISOString().slice(0, 10);
}

const linkCls =
  "flex items-center gap-1 rounded bg-surface-muted px-2 py-1 text-xs text-slate-300 transition-colors hover:bg-accent-blue/30 hover:text-accent-blue";

function Downloads({ base, query }: { base: string; query: string }) {
  return (
    <div className="flex items-center gap-2">
      <a href={`${apiBase}${base}/plot?${query}&download=1`} download className={linkCls} title="Download plot image (PNG)">
        <Download className="h-3.5 w-3.5" /> Image
      </a>
      <a href={`${apiBase}${base}/download?${query}&format=csv`} download className={linkCls} title="Download raw data (CSV)">
        <Download className="h-3.5 w-3.5" /> CSV
      </a>
      <a href={`${apiBase}${base}/download?${query}&format=json`} download className={linkCls} title="Download raw data (JSON)">
        <Download className="h-3.5 w-3.5" /> JSON
      </a>
    </div>
  );
}

export function GeomagneticArchive({ date }: { date: string }) {
  // Default to a 7-day window ending on the shared date; both ends are editable.
  const [fromDate, setFromDate] = useState(() => shiftDays(date, -6));
  const [toDate, setToDate] = useState(date);

  const valid = !!fromDate && !!toDate && fromDate <= toDate;
  const start = `${fromDate}T00:00:00Z`;
  const end = `${toDate}T23:59:59Z`;
  const query = `start=${start}&end=${end}`;

  const { data: kp, isLoading: kpLoading } = useSWR(
    valid ? ["arch-kp", start, end] : null,
    () => api.kp(start, end),
    { revalidateOnFocus: false }
  );
  const { data: dst, isLoading: dstLoading } = useSWR(
    valid ? ["arch-dst", start, end] : null,
    () => api.dst(start, end),
    { revalidateOnFocus: false }
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border bg-surface-card p-3">
        <p className="text-xs text-slate-500">
          Planetary Kp (GFZ, since 1932) &amp; Dst (Kyoto WDC) · times UTC
          <span className="ml-1 text-slate-700">— historical dates supported</span>
        </p>
        <div className="flex flex-wrap items-center gap-3 text-xs text-slate-500">
          <label className="flex items-center gap-1">
            From
            <input
              type="date"
              value={fromDate}
              max={toDate || utcToday()}
              onChange={(e) => setFromDate(e.target.value)}
              className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-slate-300 outline-none focus:border-accent-blue"
            />
          </label>
          <label className="flex items-center gap-1">
            To
            <input
              type="date"
              value={toDate}
              min={fromDate}
              max={utcToday()}
              onChange={(e) => setToDate(e.target.value)}
              className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-slate-300 outline-none focus:border-accent-blue"
            />
          </label>
        </div>
      </div>

      {!valid && (
        <div className="rounded-lg border border-surface-border bg-surface-card p-3 text-xs text-accent-red">
          Pick a valid date range (From must be on or before To).
        </div>
      )}

      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xs uppercase tracking-wider text-slate-500">Kp Index</h2>
          <Downloads base="/api/geomagnetic/kp" query={query} />
        </div>
        <div className="h-72">
          <KpChart data={kp ?? []} loading={kpLoading} />
        </div>
      </div>

      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xs uppercase tracking-wider text-slate-500">Dst Index</h2>
          <Downloads base="/api/geomagnetic/dst" query={query} />
        </div>
        <div className="h-72">
          <DstChart data={dst ?? []} loading={dstLoading} />
        </div>
      </div>
    </div>
  );
}
