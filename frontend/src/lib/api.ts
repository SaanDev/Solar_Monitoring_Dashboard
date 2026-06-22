import type {
  StatusResponse,
  SourcesStatusResponse,
  SummaryLatest,
  GoesXrsResponse,
  GoesXrsLatest,
  GoesProtonResponse,
  GoesProtonLatest,
  KpPoint,
  DstPoint,
  KpLatest,
  DstLatest,
  SolarImage,
  LascoMovie,
  SolarArchiveResponse,
  RadioStation,
  RadioSpectrum,
  RadioLiveStationsResponse,
  RadioArchiveStationsResponse,
  RadioArchiveFilesResponse,
  BurstEventsResponse,
  BurstSpectrum,
  BurstPredictionJob,
  BurstPredictionResult,
  Alert,
  SpaceWeatherEvent,
  AnalyzerSession,
  AnalyzerStats,
  AnalyzerOptions,
  RenderParams,
  CombineMode,
  ProjectOpenResponse,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Absolute URL for a backend path (for <img src> / <a href> to backend assets). */
export function apiUrl(path: string): string {
  return `${BASE}${path}`;
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${path}`);
  }
  return res.json() as Promise<T>;
}

async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "POST", body: form });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

async function postNoBody<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "POST" });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API error ${res.status}: ${path}`);
  return res.json() as Promise<T>;
}

/** Query string shared by /render and /export (vmin/vmax omitted when null). */
function analyzerQuery(id: string, p: RenderParams): string {
  const q = new URLSearchParams({
    id,
    method: p.method,
    intensity_unit: p.intensity_unit,
    time_unit: p.time_unit,
    cmap: p.cmap,
    rfi_enabled: String(p.rfi_enabled),
    rfi_low: String(p.rfi_low),
    rfi_high: String(p.rfi_high),
    station: p.station ?? "",
  });
  if (p.vmin != null) q.set("vmin", String(p.vmin));
  if (p.vmax != null) q.set("vmax", String(p.vmax));
  return q.toString();
}

export const api = {
  status: () => get<StatusResponse>("/api/status"),
  sourcesStatus: () => get<SourcesStatusResponse>("/api/sources/status"),
  summaryLatest: () => get<SummaryLatest>("/api/summary/latest"),

  goesXrs: (start: string, end: string) =>
    get<GoesXrsResponse>(`/api/goes/xrs?start=${start}&end=${end}`),
  goesXrsLatest: () => get<GoesXrsLatest>("/api/goes/xrs/latest"),
  goesProton: (start: string, end: string) =>
    get<GoesProtonResponse>(`/api/goes/proton?start=${start}&end=${end}`),
  goesProtonLatest: () => get<GoesProtonLatest>("/api/goes/proton/latest"),

  kp: (start: string, end: string) =>
    get<KpPoint[]>(`/api/geomagnetic/kp?start=${start}&end=${end}`),
  dst: (start: string, end: string) =>
    get<DstPoint[]>(`/api/geomagnetic/dst?start=${start}&end=${end}`),
  kpLatest: () => get<KpLatest>("/api/geomagnetic/kp/latest"),
  dstLatest: () => get<DstLatest>("/api/geomagnetic/dst/latest"),

  solarImagesLatest: () => get<SolarImage[]>("/api/solar/images/latest"),
  solarArchiveImages: (date: string, events: boolean, time = "12:00") =>
    get<SolarArchiveResponse>(
      `/api/solar/archive/images?date=${date}&time=${time}&events=${events}`
    ),
  solarImages: (source: string, instrument: string, wavelength: string) =>
    get<SolarImage[]>(
      `/api/solar/images?source=${source}&instrument=${instrument}&wavelength=${wavelength}`
    ),

  lascoLatest: (camera: "C2" | "C3") =>
    get<SolarImage>(`/api/soho/lasco/latest?camera=${camera}`),
  lascoMovie: (camera: "C2" | "C3") =>
    get<LascoMovie>(`/api/soho/lasco/movie?camera=${camera}`),

  radioStations: () => get<RadioStation[]>("/api/radio/stations"),
  sriLankaLive: () => get<RadioSpectrum>("/api/radio/sri-lanka/live"),

  // Live dynamic spectrum — pick any station + focus code with current data.
  radioLiveStations: () =>
    get<RadioLiveStationsResponse>("/api/radio/live/stations"),
  radioLiveSpectrum: (station: string, focus?: string) =>
    get<RadioSpectrum>(
      `/api/radio/live/spectrum?station=${encodeURIComponent(station)}` +
        (focus ? `&focus=${encodeURIComponent(focus)}` : "")
    ),
  burstsLatest: () => get<BurstEventsResponse>("/api/radio/bursts/latest"),
  burstSpectrum: (index: number) =>
    get<BurstSpectrum>(`/api/radio/bursts/${index}/spectrum`),

  // Archive — browse e-CALLISTO by date + station
  radioArchiveStations: (date: string) =>
    get<RadioArchiveStationsResponse>(`/api/radio/archive/stations?date=${date}`),
  radioArchiveFiles: (date: string, station: string) =>
    get<RadioArchiveFilesResponse>(
      `/api/radio/archive/files?date=${date}&station=${encodeURIComponent(station)}`
    ),
  radioArchiveSpectrum: (date: string, station: string, filename?: string) =>
    get<RadioSpectrum>(
      `/api/radio/archive/spectrum?date=${date}&station=${encodeURIComponent(station)}` +
        (filename ? `&filename=${encodeURIComponent(filename)}` : "")
    ),
  // Spectrum for the segment covering a given HH:MM (preview an official event's station).
  radioArchiveSpectrumAt: (date: string, station: string, time: string) =>
    get<RadioSpectrum>(
      `/api/radio/archive/spectrum-at?date=${date}&station=${encodeURIComponent(
        station
      )}&time=${encodeURIComponent(time)}`
    ),
  radioBurstsByDate: (date: string) =>
    get<BurstEventsResponse>(`/api/radio/bursts?date=${date}`),
  radioBurstSpectrumByDate: (date: string, index: number) =>
    get<BurstSpectrum>(`/api/radio/bursts/spectrum?date=${date}&index=${index}`),

  // Burst Predictor — run the model over a day and compare with the official list
  startBurstPrediction: (date: string, stations: string[]) =>
    postJson<BurstPredictionJob>("/api/radio/predict", { date, stations }),
  burstPredictionJob: (jobId: string) =>
    get<BurstPredictionJob>(`/api/radio/predict/${jobId}`),
  // Result assembled from already-stored detections for a date (no re-scoring).
  burstPredictionStored: (date: string) =>
    get<BurstPredictionResult>(`/api/radio/predict/stored?date=${date}`),

  alertsLatest: () => get<Alert[]>("/api/alerts/latest"),
  events: (start: string, end: string) =>
    get<SpaceWeatherEvent[]>(`/api/events?start=${start}&end=${end}`),

  // e-CALLISTO Analyzer
  analyzerOptions: () => get<AnalyzerOptions>("/api/analyzer/colormaps"),
  analyzerUpload: (file: File, station: string) => {
    const form = new FormData();
    form.append("file", file);
    form.append("station", station);
    return postForm<AnalyzerSession>("/api/analyzer/upload", form);
  },
  analyzerFromArchive: (date: string, station: string, filename: string) =>
    postNoBody<AnalyzerSession>(
      `/api/analyzer/from-archive?date=${date}&station=${encodeURIComponent(
        station
      )}&filename=${encodeURIComponent(filename)}`
    ),
  analyzerCombine: (ids: string[], mode: CombineMode) => {
    const q = new URLSearchParams({ mode });
    ids.forEach((id) => q.append("ids", id));
    return postNoBody<AnalyzerSession>(`/api/analyzer/combine?${q.toString()}`);
  },
  analyzerStats: (id: string, p: RenderParams) =>
    get<AnalyzerStats>(
      `/api/analyzer/stats?id=${id}&method=${p.method}&intensity_unit=${p.intensity_unit}` +
        `&rfi_enabled=${p.rfi_enabled}&rfi_low=${p.rfi_low}&rfi_high=${p.rfi_high}`
    ),
  analyzerRenderUrl: (id: string, p: RenderParams) =>
    apiUrl(`/api/analyzer/render?${analyzerQuery(id, p)}`),
  analyzerExportUrl: (id: string, p: RenderParams, format: "png" | "fits") =>
    apiUrl(`/api/analyzer/export?${analyzerQuery(id, p)}&format=${format}`),
  analyzerProjectUrl: (id: string, p: RenderParams) =>
    apiUrl(`/api/analyzer/project?${analyzerQuery(id, p)}`),
  analyzerOpenProject: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return postForm<ProjectOpenResponse>("/api/analyzer/open-project", form);
  },
};
