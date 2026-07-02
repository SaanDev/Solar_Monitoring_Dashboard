"use client";

import { useState } from "react";
import { clsx } from "clsx";
import { Upload, CalendarDays, FolderOpen, Film } from "lucide-react";
import { api } from "@/lib/api";
import { JobProgress } from "./JobProgress";
import type { AnalysisOptions, AnalysisSession } from "@/lib/types";

interface Props {
  options?: AnalysisOptions;
  onSession: (session: AnalysisSession) => void;
}

type Mode = "upload" | "fetch" | "archive" | "sequence";

function utcDateOffset(days: number): string {
  return new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
}

const inputCls =
  "w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue";
const btnCls =
  "w-full rounded bg-accent-blue/20 px-2 py-1.5 text-xs text-accent-blue transition-colors hover:bg-accent-blue/30 disabled:opacity-40";

export function DataSourcePicker({ options, onSession }: Props) {
  const [mode, setMode] = useState<Mode>("fetch");

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">Data Source</h2>
      <div className="flex gap-1">
        {(
          [
            ["fetch", "Fetch", CalendarDays],
            ["archive", "Archive", FolderOpen],
            ["sequence", "Sequence", Film],
            ["upload", "Upload", Upload],
          ] as const
        ).map(([m, label, Icon]) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={clsx(
              "flex flex-1 items-center justify-center gap-1 rounded px-2 py-1 text-xs transition-colors",
              mode === m
                ? "bg-accent-blue/20 text-accent-blue"
                : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
            )}
          >
            <Icon className="h-3.5 w-3.5" />
            {label}
          </button>
        ))}
      </div>

      {mode === "fetch" ? (
        <FetchForm options={options} onSession={onSession} />
      ) : mode === "archive" ? (
        <ArchiveForm options={options} onSession={onSession} />
      ) : mode === "sequence" ? (
        <SequenceForm options={options} onSession={onSession} />
      ) : (
        <UploadForm onSession={onSession} />
      )}
    </div>
  );
}

function WavelengthSelect({
  options,
  value,
  onChange,
}: {
  options?: AnalysisOptions;
  value: string;
  onChange: (v: string) => void;
}) {
  const list = options?.wavelengths ?? [{ code: "171", label: "AIA 171 Å" }];
  return (
    <div>
      <label className="mb-1 block text-xs text-slate-500">Wavelength</label>
      <select value={value} onChange={(e) => onChange(e.target.value)} className={inputCls}>
        {list.map((w) => (
          <option key={w.code} value={w.code}>
            {w.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function FetchForm({ options, onSession }: Props) {
  const [wavelength, setWavelength] = useState("171");
  const [date, setDate] = useState(utcDateOffset(-2));
  const [time, setTime] = useState("12:00");
  const [prep, setPrep] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function start() {
    setError(null);
    setJobId(null);
    try {
      const job = await api.analysisFetch(wavelength, `${date}T${time}:00Z`, prep);
      setJobId(job.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fetch failed");
    }
  }

  return (
    <div className="space-y-2">
      <WavelengthSelect options={options} value={wavelength} onChange={setWavelength} />
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1 block text-xs text-slate-500">Date (UTC)</label>
          <input type="date" value={date} max={utcDateOffset(0)} onChange={(e) => setDate(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">Time (UTC)</label>
          <input type="time" value={time} onChange={(e) => setTime(e.target.value)} className={inputCls} />
        </div>
      </div>
      <label className="flex cursor-pointer select-none items-center gap-2 text-xs text-slate-400">
        <input type="checkbox" checked={prep} onChange={(e) => setPrep(e.target.checked)} className="h-3.5 w-3.5 accent-accent-blue" />
        Calibrate to level 1.5 (aiapy — slower)
      </label>
      <button disabled={!!jobId} onClick={start} className={btnCls}>
        {jobId ? "Fetching…" : "Fetch full-resolution AIA"}
      </button>
      {jobId && (
        <JobProgress
          jobId={jobId}
          onDone={(job) => {
            setJobId(null);
            if (job.session) onSession(job.session);
          }}
          onError={(msg) => {
            setJobId(null);
            setError(msg);
          }}
        />
      )}
      <p className="text-[10px] leading-relaxed text-slate-600">
        Downloads the full-resolution (4096²) frame nearest the chosen time from
        VSO/JSOC. Large files — can take a minute or stall if the mirror is busy.
      </p>
      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}

function ArchiveForm({ options, onSession }: Props) {
  const [wavelength, setWavelength] = useState("171");
  const [date, setDate] = useState(utcDateOffset(-2));
  const [time, setTime] = useState("12:00");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    setBusy(true);
    setError(null);
    try {
      onSession(await api.analysisArchive(date, time, wavelength));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Archive load failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <WavelengthSelect options={options} value={wavelength} onChange={setWavelength} />
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1 block text-xs text-slate-500">Date (UTC)</label>
          <input type="date" value={date} max={utcDateOffset(0)} onChange={(e) => setDate(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">Time (UTC)</label>
          <input type="time" value={time} onChange={(e) => setTime(e.target.value)} className={inputCls} />
        </div>
      </div>
      <button disabled={busy} onClick={load} className={btnCls}>
        {busy ? "Loading…" : "Load 1024px synoptic frame"}
      </button>
      <p className="text-[10px] leading-relaxed text-slate-600">
        Fast path: the 1024px JSOC synoptic frame nearest the chosen time (same
        archive the dashboard already uses). Lower resolution than a full fetch.
      </p>
      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}

function SequenceForm({ options, onSession }: Props) {
  const [wavelength, setWavelength] = useState("171");
  const [date, setDate] = useState(utcDateOffset(-2));
  const [start, setStart] = useState("00:00");
  const [step, setStep] = useState(5);
  const [count, setCount] = useState(10);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const maxFrames = options?.max_frames ?? 40;

  async function startSeq() {
    setError(null);
    setJobId(null);
    try {
      const job = await api.analysisSequence(date, start, step, Math.min(count, maxFrames), wavelength);
      setJobId(job.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sequence build failed");
    }
  }

  return (
    <div className="space-y-2">
      <WavelengthSelect options={options} value={wavelength} onChange={setWavelength} />
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className="mb-1 block text-xs text-slate-500">Date (UTC)</label>
          <input type="date" value={date} max={utcDateOffset(0)} onChange={(e) => setDate(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">Start (UTC)</label>
          <input type="time" value={start} onChange={(e) => setStart(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">Step (min)</label>
          <input type="number" min={1} value={step} onChange={(e) => setStep(parseInt(e.target.value || "1", 10))} className={inputCls} />
        </div>
        <div>
          <label className="mb-1 block text-xs text-slate-500">Frames (≤ {maxFrames})</label>
          <input type="number" min={2} max={maxFrames} value={count} onChange={(e) => setCount(parseInt(e.target.value || "2", 10))} className={inputCls} />
        </div>
      </div>
      <button disabled={!!jobId} onClick={startSeq} className={btnCls}>
        {jobId ? "Building…" : "Build sequence"}
      </button>
      {jobId && (
        <JobProgress
          jobId={jobId}
          onDone={(job) => {
            setJobId(null);
            if (job.session) onSession(job.session);
          }}
          onError={(msg) => {
            setJobId(null);
            setError(msg);
          }}
        />
      )}
      <p className="text-[10px] leading-relaxed text-slate-600">
        Builds a multi-frame session (1024px synoptic frames) for running/base
        difference images and movies.
      </p>
      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}

function UploadForm({ onSession }: { onSession: (s: AnalysisSession) => void }) {
  const [files, setFiles] = useState<FileList | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!files || files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      onSession(await api.analysisUpload(Array.from(files)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <input
        type="file"
        accept=".fits,.fit,.fz,.gz"
        multiple
        onChange={(e) => setFiles(e.target.files)}
        className="block w-full text-xs text-slate-400 file:mr-2 file:rounded file:border-0 file:bg-surface-muted file:px-2 file:py-1 file:text-xs file:text-slate-300 hover:file:bg-accent-blue/30"
      />
      <button disabled={!files || files.length === 0 || busy} onClick={load} className={btnCls}>
        {busy ? "Loading…" : "Load FITS"}
      </button>
      <p className="text-[10px] leading-relaxed text-slate-600">
        Upload SDO/AIA or HMI FITS files. Select multiple frames to build a
        sequence (used for difference images and movies).
      </p>
      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}
