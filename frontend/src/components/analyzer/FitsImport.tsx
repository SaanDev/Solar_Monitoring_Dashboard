"use client";

import { useEffect, useState } from "react";
import useSWR from "swr";
import { clsx } from "clsx";
import { Upload, FolderOpen, FileText } from "lucide-react";
import { api } from "@/lib/api";
import type { AnalyzerSession, ProjectOpenResponse } from "@/lib/types";

interface Props {
  onImport: (session: AnalyzerSession) => void;
  onOpenProject: (resp: ProjectOpenResponse) => void;
}

function utcDateOffset(days: number): string {
  return new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
}

type Mode = "upload" | "archive" | "project";

export function FitsImport({ onImport, onOpenProject }: Props) {
  const [mode, setMode] = useState<Mode>("upload");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(fn: () => Promise<AnalyzerSession>) {
    setBusy(true);
    setError(null);
    try {
      onImport(await fn());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Import failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">Import FITS</h2>
      <div className="flex gap-1">
        {(["upload", "archive", "project"] as Mode[]).map((m) => (
          <button
            key={m}
            onClick={() => setMode(m)}
            className={clsx(
              "flex flex-1 items-center justify-center gap-1 rounded px-2 py-1 text-xs capitalize transition-colors",
              mode === m
                ? "bg-accent-blue/20 text-accent-blue"
                : "text-slate-500 hover:bg-surface-muted hover:text-slate-300"
            )}
          >
            {m === "upload" ? (
              <Upload className="h-3.5 w-3.5" />
            ) : m === "archive" ? (
              <FolderOpen className="h-3.5 w-3.5" />
            ) : (
              <FileText className="h-3.5 w-3.5" />
            )}
            {m}
          </button>
        ))}
      </div>

      {mode === "upload" ? (
        <UploadForm busy={busy} run={run} />
      ) : mode === "archive" ? (
        <ArchiveForm busy={busy} run={run} />
      ) : (
        <ProjectForm onOpenProject={onOpenProject} />
      )}

      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}

function ProjectForm({
  onOpenProject,
}: {
  onOpenProject: (resp: ProjectOpenResponse) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function open() {
    if (!file) return;
    setBusy(true);
    setError(null);
    try {
      onOpenProject(await api.analyzerOpenProject(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not open project");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <input
        type="file"
        accept=".efaproj"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="block w-full text-xs text-slate-400 file:mr-2 file:rounded file:border-0 file:bg-surface-muted file:px-2 file:py-1 file:text-xs file:text-slate-300 hover:file:bg-accent-blue/30"
      />
      <button
        disabled={!file || busy}
        onClick={open}
        className="w-full rounded bg-accent-blue/20 px-2 py-1.5 text-xs text-accent-blue transition-colors hover:bg-accent-blue/30 disabled:opacity-40"
      >
        {busy ? "Opening…" : "Open project (.efaproj)"}
      </button>
      <p className="text-[10px] leading-relaxed text-slate-600">
        Opens projects saved here or in the desktop e-CALLISTO Analyzer.
      </p>
      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}

function UploadForm({
  busy,
  run,
}: {
  busy: boolean;
  run: (fn: () => Promise<AnalyzerSession>) => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [station, setStation] = useState("");

  return (
    <div className="space-y-2">
      <input
        type="file"
        accept=".fit,.fits,.gz"
        onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        className="block w-full text-xs text-slate-400 file:mr-2 file:rounded file:border-0 file:bg-surface-muted file:px-2 file:py-1 file:text-xs file:text-slate-300 hover:file:bg-accent-blue/30"
      />
      <input
        type="text"
        placeholder="Station label (optional)"
        value={station}
        onChange={(e) => setStation(e.target.value)}
        className="w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue"
      />
      <button
        disabled={!file || busy}
        onClick={() => file && run(() => api.analyzerUpload(file, station))}
        className="w-full rounded bg-accent-blue/20 px-2 py-1.5 text-xs text-accent-blue transition-colors hover:bg-accent-blue/30 disabled:opacity-40"
      >
        {busy ? "Loading…" : "Load file"}
      </button>
    </div>
  );
}

function ArchiveForm({
  busy,
  run,
}: {
  busy: boolean;
  run: (fn: () => Promise<AnalyzerSession>) => void;
}) {
  const [date, setDate] = useState(utcDateOffset(-1));

  const { data: stationsData } = useSWR(["an-arch-stations", date], () =>
    api.radioArchiveStations(date)
  );
  const stations = stationsData?.stations ?? [];
  const stationIds = stations.map((s) => s.id).join(",");

  const [station, setStation] = useState("");
  useEffect(() => {
    const ids = stationIds ? stationIds.split(",") : [];
    if (!ids.length) setStation("");
    else if (!ids.includes(station)) setStation(ids.includes("SRI-Lanka") ? "SRI-Lanka" : ids[0]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, stationIds]);

  const { data: filesData } = useSWR(station ? ["an-arch-files", date, station] : null, () =>
    api.radioArchiveFiles(date, station)
  );
  const files = filesData?.files ?? [];
  const fileNames = files.map((f) => f.filename).join(",");

  const [filename, setFilename] = useState("");
  useEffect(() => {
    const names = fileNames ? fileNames.split(",") : [];
    if (!names.length) setFilename("");
    else if (!names.includes(filename)) setFilename(names[names.length - 1]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [date, station, fileNames]);

  return (
    <div className="space-y-2">
      <input
        type="date"
        value={date}
        max={utcDateOffset(0)}
        onChange={(e) => setDate(e.target.value)}
        className="w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue"
      />
      <select
        value={station}
        onChange={(e) => setStation(e.target.value)}
        disabled={!stations.length}
        className="w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue disabled:opacity-40"
      >
        {!stations.length && <option value="">— No stations for this date —</option>}
        {stations.map((s) => (
          <option key={s.id} value={s.id}>
            {s.id}
          </option>
        ))}
      </select>
      <select
        value={filename}
        onChange={(e) => setFilename(e.target.value)}
        disabled={!files.length}
        className="w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue disabled:opacity-40"
      >
        {!files.length && <option value="">— No segments —</option>}
        {files.map((f) => (
          <option key={f.filename} value={f.filename}>
            {f.start_time.slice(11, 16)} UTC
          </option>
        ))}
      </select>
      <button
        disabled={!station || !filename || busy}
        onClick={() => run(() => api.analyzerFromArchive(date, station, filename))}
        className="w-full rounded bg-accent-blue/20 px-2 py-1.5 text-xs text-accent-blue transition-colors hover:bg-accent-blue/30 disabled:opacity-40"
      >
        {busy ? "Loading…" : "Load from archive"}
      </button>
    </div>
  );
}
