"use client";

import { useState } from "react";
import useSWR from "swr";
import { Download } from "lucide-react";

import { api } from "@/lib/api";
import { GoesXrsChart } from "@/components/charts/GoesXrsChart";
import { ProtonFluxChart } from "@/components/charts/ProtonFluxChart";

const apiBase = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function iso(date: string, time: string): string {
  return `${date}T${time}:00Z`;
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

export function XrayProtonArchive({ date }: { date: string }) {
  const [startT, setStartT] = useState("00:00");
  const [endT, setEndT] = useState("23:59");
  const start = iso(date, startT);
  const end = iso(date, endT);
  const query = `start=${start}&end=${end}`;
  const valid = startT < endT;

  const { data: xrs, isLoading: xrsLoading } = useSWR(
    valid ? ["arch-xrs", start, end] : null,
    () => api.goesXrs(start, end),
    { revalidateOnFocus: false }
  );
  const { data: proton, isLoading: protonLoading } = useSWR(
    valid ? ["arch-proton", start, end] : null,
    () => api.goesProton(start, end),
    { revalidateOnFocus: false }
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-surface-border bg-surface-card p-3">
        <p className="text-xs text-slate-500">
          GOES X-ray &amp; proton flux · {date} · times UTC
          <span className="ml-1 text-slate-700">
            (history accumulates from ingestion; NOAA live covers ~7 days)
          </span>
        </p>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <label className="flex items-center gap-1">
            From
            <input
              type="time"
              value={startT}
              onChange={(e) => setStartT(e.target.value || "00:00")}
              className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-slate-300 outline-none focus:border-accent-blue"
            />
          </label>
          <label className="flex items-center gap-1">
            to
            <input
              type="time"
              value={endT}
              onChange={(e) => setEndT(e.target.value || "23:59")}
              className="rounded border border-surface-border bg-surface-muted px-2 py-1 text-slate-300 outline-none focus:border-accent-blue"
            />
          </label>
        </div>
      </div>

      {!valid && (
        <div className="rounded-lg border border-surface-border bg-surface-card p-3 text-xs text-accent-red">
          Start time must be before end time.
        </div>
      )}

      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xs uppercase tracking-wider text-slate-500">GOES X-ray Flux</h2>
          <Downloads base="/api/goes/xrs" query={query} />
        </div>
        <div className="h-72">
          <GoesXrsChart data={xrs?.data ?? []} loading={xrsLoading} />
        </div>
      </div>

      <div className="rounded-lg border border-surface-border bg-surface-card p-4">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="text-xs uppercase tracking-wider text-slate-500">GOES Proton Flux</h2>
          <Downloads base="/api/goes/proton" query={query} />
        </div>
        <div className="h-72">
          <ProtonFluxChart data={proton?.data ?? []} loading={protonLoading} />
        </div>
      </div>
    </div>
  );
}
