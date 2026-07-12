"use client";

import { useMemo, useState } from "react";
import { clsx } from "clsx";
import { Upload, CalendarDays, FolderOpen, Film, Telescope } from "lucide-react";
import { api } from "@/lib/api";
import type { SearchParams } from "@/lib/api";
import { JobProgress } from "./JobProgress";
import type {
  AnalysisOptions,
  AnalysisSession,
  Observable,
  SearchResponse,
} from "@/lib/types";

interface Props {
  options?: AnalysisOptions;
  onSession: (session: AnalysisSession) => void;
  /** Called instead of onSession when a .ecsolar bundle is restored (carries
   * the saved height–time picks + display state). */
  onRestore?: (
    session: AnalysisSession,
    picks: { frame: number; px: number; py: number }[],
    display: Record<string, unknown>
  ) => void;
}

type Mode = "search" | "fetch" | "archive" | "sequence" | "upload";

function utcDateOffset(days: number): string {
  return new Date(Date.now() + days * 86400000).toISOString().slice(0, 10);
}

const inputCls =
  "w-full rounded border border-surface-border bg-surface-muted px-2 py-1 text-xs text-slate-300 outline-none focus:border-accent-blue";
const btnCls =
  "w-full rounded bg-accent-blue/20 px-2 py-1.5 text-xs text-accent-blue transition-colors hover:bg-accent-blue/30 disabled:opacity-40";

export function DataSourcePicker({ options, onSession, onRestore }: Props) {
  const [mode, setMode] = useState<Mode>("search");

  return (
    <div className="space-y-3 rounded-lg border border-surface-border bg-surface-card p-4">
      <h2 className="text-xs uppercase tracking-wider text-slate-500">Data Source</h2>
      <div className="flex flex-wrap gap-1">
        {(
          [
            ["search", "Search", Telescope],
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

      {mode === "search" ? (
        <SearchForm options={options} onSession={onSession} />
      ) : mode === "fetch" ? (
        <FetchForm options={options} onSession={onSession} />
      ) : mode === "archive" ? (
        <ArchiveForm options={options} onSession={onSession} />
      ) : mode === "sequence" ? (
        <SequenceForm options={options} onSession={onSession} />
      ) : (
        <UploadForm onSession={onSession} onRestore={onRestore} />
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

function labelCls() {
  return "mb-1 block text-xs text-slate-500";
}

function SearchForm({ options, onSession }: Props) {
  const observables = options?.observables ?? [];
  const sources = options?.sources ?? ["auto", "vso"];
  const frameSizes = options?.frame_sizes ?? ["full", "bin2", "bin4", "cutout"];

  const [obsKey, setObsKey] = useState("sdo_aia");
  const obs: Observable | undefined = useMemo(
    () => observables.find((o) => o.key === obsKey) ?? observables[0],
    [observables, obsKey]
  );

  const [wavelength, setWavelength] = useState<number | null>(null);
  const [product, setProduct] = useState<string | null>(null);
  const [level, setLevel] = useState<string | null>(null);
  const [satellite, setSatellite] = useState<number | null>(null);
  const [date, setDate] = useState(utcDateOffset(-3));
  const [startTime, setStartTime] = useState("00:00");
  const [endTime, setEndTime] = useState("01:00");
  const [cadence, setCadence] = useState(120);
  const [maxRecords, setMaxRecords] = useState(20);
  const [source, setSource] = useState("auto");
  const [frameSize, setFrameSize] = useState("full");
  const [cutout, setCutout] = useState({ x: 0, y: 0, w: 500, h: 500 });

  const [result, setResult] = useState<SearchResponse | null>(null);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [searching, setSearching] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const isSdo = obs?.spacecraft?.toUpperCase() === "SDO";
  const wlValue = wavelength ?? obs?.default_wavelength ?? obs?.wavelengths?.[0] ?? null;
  const prodValue = product ?? obs?.default_product ?? obs?.products?.[0] ?? null;
  const lvlValue = level ?? obs?.default_level ?? obs?.levels?.[0] ?? null;
  const satValue = satellite ?? obs?.default_satellite ?? 18;

  function pickObservable(key: string) {
    setObsKey(key);
    const o = observables.find((x) => x.key === key);
    setWavelength(o?.default_wavelength ?? null);
    setProduct(o?.default_product ?? null);
    setLevel(o?.default_level ?? null);
    setSatellite(o?.default_satellite ?? null);
    setResult(null);
    setSelected(new Set());
    if (!(o?.spacecraft?.toUpperCase() === "SDO")) setFrameSize("full");
  }

  function buildParams(): SearchParams {
    return {
      observable: obsKey,
      start: `${date}T${startTime}:00Z`,
      end: `${date}T${endTime}:00Z`,
      wavelength_angstrom: obs?.supports_wavelength ? wlValue : null,
      product: obs?.supports_product ? prodValue : null,
      level: obs?.supports_level ? lvlValue : null,
      satellite_number: obs?.supports_satellite ? satValue : null,
      sample_seconds: cadence > 0 ? cadence : null,
      max_records: maxRecords,
    };
  }

  async function runSearch(findLatest: boolean) {
    setSearching(true);
    setError(null);
    setResult(null);
    setJobId(null);
    try {
      const params = buildParams();
      const res = findLatest ? await api.analysisFindLatest(params) : await api.analysisSearch(params);
      setResult(res);
      setSelected(new Set(res.rows.map((r) => r.index)));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Search failed");
    } finally {
      setSearching(false);
    }
  }

  async function loadSelected() {
    if (!result || result.search_id === "" || selected.size === 0) return;
    setError(null);
    setJobId(null);
    try {
      const job = await api.analysisFetchSelected({
        search_id: result.search_id,
        indices: [...selected].sort((a, b) => a - b),
        source,
        frame_size: frameSize,
        cutout_x: cutout.x,
        cutout_y: cutout.y,
        cutout_w: cutout.w,
        cutout_h: cutout.h,
      });
      setJobId(job.job_id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Download failed");
    }
  }

  return (
    <div className="space-y-2">
      <div>
        <label className={labelCls()}>Observable</label>
        <select value={obsKey} onChange={(e) => pickObservable(e.target.value)} className={inputCls}>
          {observables.map((o) => (
            <option key={o.key} value={o.key}>
              {o.label}
            </option>
          ))}
        </select>
      </div>

      {obs?.supports_wavelength && (
        <div>
          <label className={labelCls()}>Wavelength (Å)</label>
          <select
            value={String(wlValue ?? "")}
            onChange={(e) => setWavelength(parseFloat(e.target.value))}
            className={inputCls}
          >
            {obs.wavelengths.map((w) => (
              <option key={w} value={w}>
                {w} Å
              </option>
            ))}
          </select>
        </div>
      )}
      {obs?.supports_product && (
        <div>
          <label className={labelCls()}>Product</label>
          <select value={prodValue ?? ""} onChange={(e) => setProduct(e.target.value)} className={inputCls}>
            {obs.products.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
        </div>
      )}
      {obs?.supports_level && (
        <div>
          <label className={labelCls()}>Level</label>
          <select value={lvlValue ?? ""} onChange={(e) => setLevel(e.target.value)} className={inputCls}>
            {obs.levels.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
      )}
      {obs?.supports_satellite && (
        <div>
          <label className={labelCls()}>GOES satellite #</label>
          <input
            type="number"
            value={satValue}
            onChange={(e) => setSatellite(parseInt(e.target.value || "18", 10))}
            className={inputCls}
          />
        </div>
      )}

      <div>
        <label className={labelCls()}>Date (UTC)</label>
        <input type="date" value={date} max={utcDateOffset(0)} onChange={(e) => setDate(e.target.value)} className={inputCls} />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={labelCls()}>Start (UTC)</label>
          <input type="time" value={startTime} onChange={(e) => setStartTime(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className={labelCls()}>End (UTC)</label>
          <input type="time" value={endTime} onChange={(e) => setEndTime(e.target.value)} className={inputCls} />
        </div>
        <div>
          <label className={labelCls()}>Cadence (s)</label>
          <input type="number" min={0} value={cadence} onChange={(e) => setCadence(parseInt(e.target.value || "0", 10))} className={inputCls} />
        </div>
        <div>
          <label className={labelCls()}>Max records</label>
          <input type="number" min={1} value={maxRecords} onChange={(e) => setMaxRecords(parseInt(e.target.value || "1", 10))} className={inputCls} />
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label className={labelCls()}>Source</label>
          <select value={source} onChange={(e) => setSource(e.target.value)} className={inputCls}>
            {sources.map((s) => (
              <option key={s} value={s}>
                {s.toUpperCase()}
              </option>
            ))}
          </select>
        </div>
        {isSdo && (
          <div>
            <label className={labelCls()}>Frame size</label>
            <select value={frameSize} onChange={(e) => setFrameSize(e.target.value)} className={inputCls}>
              {frameSizes.map((f) => (
                <option key={f} value={f}>
                  {f}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>
      {isSdo && frameSize === "cutout" && (
        <div className="grid grid-cols-4 gap-2">
          {(["x", "y", "w", "h"] as const).map((k) => (
            <div key={k}>
              <label className={labelCls()}>{k === "w" ? "W″" : k === "h" ? "H″" : `${k}″`}</label>
              <input
                type="number"
                value={cutout[k]}
                onChange={(e) => setCutout({ ...cutout, [k]: parseFloat(e.target.value || "0") })}
                className={inputCls}
              />
            </div>
          ))}
        </div>
      )}

      <div className="grid grid-cols-2 gap-2">
        <button disabled={searching} onClick={() => runSearch(false)} className={btnCls}>
          {searching ? "Searching…" : "Search"}
        </button>
        <button
          disabled={searching}
          onClick={() => runSearch(true)}
          className="w-full rounded bg-surface-muted px-2 py-1.5 text-xs text-slate-300 transition-colors hover:bg-surface-border disabled:opacity-40"
          title="Walk back to the newest available frames (for lagging archives like LASCO)"
        >
          Find Latest
        </button>
      </div>

      {result?.notice && (
        <p className="rounded bg-accent-yellow/10 px-2 py-1 text-[10px] leading-relaxed text-accent-yellow">
          {result.notice}
        </p>
      )}

      {result && result.rows.length > 0 && (
        <>
          <ResultsTable
            rows={result.rows}
            selected={selected}
            onToggle={(i) => {
              const next = new Set(selected);
              next.has(i) ? next.delete(i) : next.add(i);
              setSelected(next);
            }}
            onAll={() => setSelected(new Set(result.rows.map((r) => r.index)))}
            onNone={() => setSelected(new Set())}
          />
          <button disabled={!!jobId || selected.size === 0} onClick={loadSelected} className={btnCls}>
            {jobId ? "Downloading…" : `Load ${selected.size} selected`}
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
        </>
      )}
      {result && result.rows.length === 0 && !result.notice && (
        <p className="text-[10px] text-slate-500">No records found for that window.</p>
      )}

      <p className="text-[10px] leading-relaxed text-slate-600">
        Multi-mission archive search (SunPy Fido): SDO/AIA·HMI, SOHO/LASCO,
        STEREO/SECCHI, GOES/SUVI, PROBA2/SWAP. SDO downloads can use the JSOC fast
        path with server-side cutouts/binning.
      </p>
      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}

function ResultsTable({
  rows,
  selected,
  onToggle,
  onAll,
  onNone,
}: {
  rows: SearchResponse["rows"];
  selected: Set<number>;
  onToggle: (i: number) => void;
  onAll: () => void;
  onNone: () => void;
}) {
  return (
    <div className="rounded border border-surface-border">
      <div className="flex items-center justify-between border-b border-surface-border px-2 py-1 text-[10px] text-slate-500">
        <span>{rows.length} records</span>
        <span className="flex gap-2">
          <button onClick={onAll} className="hover:text-accent-blue">
            All
          </button>
          <button onClick={onNone} className="hover:text-accent-blue">
            None
          </button>
        </span>
      </div>
      <div className="max-h-48 overflow-y-auto">
        <table className="w-full text-[10px] text-slate-400">
          <tbody>
            {rows.map((r) => (
              <tr key={r.index} className="border-b border-surface-border/50 last:border-0">
                <td className="w-6 px-2 py-1">
                  <input
                    type="checkbox"
                    checked={selected.has(r.index)}
                    onChange={() => onToggle(r.index)}
                    className="h-3 w-3 accent-accent-blue"
                  />
                </td>
                <td className="px-1 py-1 font-mono">
                  {r.start ? r.start.replace("T", " ").slice(0, 19) : "—"}
                </td>
                <td className="px-1 py-1">{r.source || r.provider}</td>
                <td className="px-1 py-1 text-right">{r.size}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function UploadForm({
  onSession,
  onRestore,
}: {
  onSession: (s: AnalysisSession) => void;
  onRestore?: Props["onRestore"];
}) {
  const [files, setFiles] = useState<FileList | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    if (!files || files.length === 0) return;
    setBusy(true);
    setError(null);
    try {
      const list = Array.from(files);
      const bundle = list.find((f) => f.name.toLowerCase().endsWith(".ecsolar"));
      if (bundle) {
        // Restore a saved session bundle (from this dashboard or the desktop app).
        const r = await api.analysisSessionImport(bundle);
        if (onRestore) onRestore(r.session, r.picks, r.display);
        else onSession(r.session);
      } else {
        onSession(await api.analysisUpload(list));
      }
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
        accept=".fits,.fit,.fz,.gz,.ecsolar"
        multiple
        onChange={(e) => setFiles(e.target.files)}
        className="block w-full text-xs text-slate-400 file:mr-2 file:rounded file:border-0 file:bg-surface-muted file:px-2 file:py-1 file:text-xs file:text-slate-300 hover:file:bg-accent-blue/30"
      />
      <button disabled={!files || files.length === 0 || busy} onClick={load} className={btnCls}>
        {busy ? "Loading…" : "Load FITS / .ecsolar"}
      </button>
      <p className="text-[10px] leading-relaxed text-slate-600">
        Upload solar FITS files (multiple frames build a sequence), or restore a
        saved <span className="font-mono">.ecsolar</span> session bundle — including
        ones made in the desktop e-CALLISTO FITS Analyzer.
      </p>
      {error && <p className="text-xs text-accent-red">{error}</p>}
    </div>
  );
}
