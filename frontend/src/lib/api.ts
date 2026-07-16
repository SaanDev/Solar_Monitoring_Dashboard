import type {
  StatusResponse,
  SourcesStatusResponse,
  SummaryLatest,
  GoesXrsResponse,
  GoesXrsLatest,
  GoesProtonResponse,
  GoesProtonLatest,
  GoesElectronResponse,
  GoesElectronLatest,
  GoesMagnetometerResponse,
  GoesMagnetometerLatest,
  SunspotSeriesResponse,
  F107Response,
  SolarWindLatest,
  SolarWindSeriesResponse,
  KpForecastResponse,
  CmeListResponse,
  CmeHistoryResponse,
  CmeHistogramResponse,
  NoaaScalesResponse,
  AuroraForecast,
  BurstScorecardResponse,
  OfficialBurstRangeResponse,
  NotificationSettings,
  NotificationTestResponse,
  SolarCycleResponse,
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
  ActivityHistogramResponse,
  SpaceWeatherEvent,
  EventChain,
  AnalyzerSession,
  AnalyzerStats,
  AnalyzerOptions,
  RenderParams,
  CombineMode,
  ProjectOpenResponse,
  BgMethod,
  IntensityUnit,
  RenderGeometry,
  ShockPoint,
  MaxIntensityResult,
  ShockFitResult,
  ExtraPlotKind,
  AnalysisSession,
  AnalysisOptions,
  AnalysisJobStatus,
  SearchResponse,
  PlotParams,
  FrameWcsMeta,
  CoordReadout,
  RulerResult,
  ProfileResult,
  RegionStatsResult,
  LightcurveResult,
  HeightTimeResult,
  CompareInfo,
} from "./types";

export interface SearchParams {
  observable: string;
  start: string;
  end: string;
  wavelength_angstrom?: number | null;
  product?: string | null;
  level?: string | null;
  satellite_number?: number | null;
  sample_seconds?: number | null;
  max_records?: number;
}

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Absolute URL for a backend path (for <img src> / <a href> to backend assets). */
export function apiUrl(path: string): string {
  return `${BASE}${path}`;
}

/** Build an Error carrying the backend's `detail` message (FastAPI convention),
 * so failures show their real cause instead of just a status code. */
async function apiError(res: Response, path: string): Promise<Error> {
  let detail = "";
  try {
    const body = await res.json();
    if (typeof body?.detail === "string") detail = body.detail;
    else if (body?.detail) detail = JSON.stringify(body.detail);
  } catch {
    try {
      detail = (await res.text()).slice(0, 300);
    } catch {
      /* unreadable body */
    }
  }
  return new Error(detail ? `${detail} (HTTP ${res.status})` : `API error ${res.status}: ${path}`);
}

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw await apiError(res, path);
  return res.json() as Promise<T>;
}

async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "POST", body: form });
  if (!res.ok) throw await apiError(res, path);
  return res.json() as Promise<T>;
}

async function postNoBody<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { method: "POST" });
  if (!res.ok) throw await apiError(res, path);
  return res.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await apiError(res, path);
  return res.json() as Promise<T>;
}

async function putJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw await apiError(res, path);
  return res.json() as Promise<T>;
}

/** Query string for the Data Analysis /render endpoint (vmin/vmax omitted when null). */
function analysisPlotQuery(session: string, frame: number, p: PlotParams): string {
  const q = new URLSearchParams({
    session,
    frame: String(frame),
    cmap: p.cmap,
    scale: p.scale,
    clip_low: String(p.clip_low),
    clip_high: String(p.clip_high),
    crop: String(p.crop),
    bl_x: String(p.bl_x),
    bl_y: String(p.bl_y),
    tr_x: String(p.tr_x),
    tr_y: String(p.tr_y),
    draw_limb: String(p.draw_limb),
    draw_grid: String(p.draw_grid),
    colorbar: String(p.colorbar),
    nrgf: String(p.nrgf ?? false),
    grid_frame: p.grid_frame ?? "",
  });
  if (p.vmin != null) q.set("vmin", String(p.vmin));
  if (p.vmax != null) q.set("vmax", String(p.vmax));
  return q.toString();
}

/** Query string for the interactive canvas /render-bare endpoint. */
function analysisBareQuery(
  session: string,
  frame: number,
  mode: string,
  baseIndex: number,
  p: PlotParams
): string {
  const q = new URLSearchParams({
    session,
    frame: String(frame),
    mode,
    base_index: String(baseIndex),
    cmap: p.cmap,
    scale: p.scale,
    clip_low: String(p.clip_low),
    clip_high: String(p.clip_high),
    nrgf: String(p.nrgf ?? false),
  });
  if (p.vmin != null) q.set("vmin", String(p.vmin));
  if (p.vmax != null) q.set("vmax", String(p.vmax));
  return q.toString();
}

/** Query string for the Data Analysis /difference endpoint. */
function analysisDiffQuery(
  session: string,
  frame: number,
  diffType: string,
  baseIndex: number,
  p: PlotParams
): string {
  const q = new URLSearchParams({
    session,
    frame: String(frame),
    diff_type: diffType,
    base_index: String(baseIndex),
    cmap: p.cmap,
    clip_high: String(p.clip_high),
    crop: String(p.crop),
    bl_x: String(p.bl_x),
    bl_y: String(p.bl_y),
    tr_x: String(p.tr_x),
    tr_y: String(p.tr_y),
    draw_limb: String(p.draw_limb),
    draw_grid: String(p.draw_grid),
    colorbar: String(p.colorbar),
  });
  if (p.vmin != null) q.set("vmin", String(p.vmin));
  if (p.vmax != null) q.set("vmax", String(p.vmax));
  return q.toString();
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
  goesElectrons: (start: string, end: string) =>
    get<GoesElectronResponse>(`/api/goes/electrons?start=${start}&end=${end}`),
  goesElectronsLatest: () => get<GoesElectronLatest>("/api/goes/electrons/latest"),
  goesMagnetometer: (start: string, end: string) =>
    get<GoesMagnetometerResponse>(`/api/goes/magnetometer?start=${start}&end=${end}`),
  goesMagnetometerLatest: () =>
    get<GoesMagnetometerLatest>("/api/goes/magnetometer/latest"),

  // Slow solar-activity indices (live-cached, no DB).
  sunspotSeries: (scope: "cycle" | "recent") =>
    get<SunspotSeriesResponse>(`/api/indices/sunspot?scope=${scope}`),
  f107: () => get<F107Response>("/api/indices/f107"),

  // Real-time solar wind: speed + IMF Bt/Bz (live-proxied NOAA windows, no DB).
  solarWindLatest: () => get<SolarWindLatest>("/api/solar-wind/latest"),
  solarWindSeries: (range: string) =>
    get<SolarWindSeriesResponse>(`/api/solar-wind/series?range=${range}`),

  // Forecasting: predicted Kp (Newell coupling), DONKI CMEs with ENLIL
  // arrivals, NOAA 3-day R/S/G outlook, OVATION aurora.
  forecastKp: (range: string) =>
    get<KpForecastResponse>(`/api/forecast/kp?range=${range}`),
  forecastCmes: (days = 7) => get<CmeListResponse>(`/api/forecast/cmes?days=${days}`),
  // Past CMEs over an arbitrary date window (YYYY-MM-DD, inclusive).
  forecastCmesHistory: (start: string, end: string) =>
    get<CmeHistoryResponse>(`/api/forecast/cmes/history?start=${start}&end=${end}`),
  // CME counts per `interval`-day bin over a period (histogram).
  forecastCmesHistogram: (start: string, end: string, interval: number) =>
    get<CmeHistogramResponse>(
      `/api/forecast/cmes/histogram?start=${start}&end=${end}&interval=${interval}`
    ),
  forecastNoaaScales: () => get<NoaaScalesResponse>("/api/forecast/noaa-scales"),
  forecastAurora: () => get<AuroraForecast>("/api/forecast/aurora"),

  kp: (start: string, end: string) =>
    get<KpPoint[]>(`/api/geomagnetic/kp?start=${start}&end=${end}`),
  dst: (start: string, end: string) =>
    get<DstPoint[]>(`/api/geomagnetic/dst?start=${start}&end=${end}`),
  kpLatest: () => get<KpLatest>("/api/geomagnetic/kp/latest"),
  dstLatest: () => get<DstLatest>("/api/geomagnetic/dst/latest"),

  solarImagesLatest: () => get<SolarImage[]>("/api/solar/images/latest"),
  solarArchiveImages: (date: string, events: boolean, time = "12:00", latest = false) =>
    get<SolarArchiveResponse>(
      `/api/solar/archive/images?date=${date}&time=${time}&events=${events}&latest=${latest}`
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

  // Burst Predictor — run the model over a day and compare with the official list.
  // `raw` selects the event mode: true = raw model output (no corroboration
  // filter), false = event-selection criteria.
  startBurstPrediction: (date: string, stations: string[], raw = false) =>
    postJson<BurstPredictionJob>("/api/radio/predict", { date, stations, raw }),
  // `raw` re-assembles a finished job from its cached scores in the chosen mode
  // (no re-scoring), so toggling the mode is instant.
  burstPredictionJob: (jobId: string, raw = false) =>
    get<BurstPredictionJob>(`/api/radio/predict/${jobId}?raw=${raw}`),
  // Result assembled from already-stored detections for a date (no re-scoring).
  burstPredictionStored: (date: string, raw = false) =>
    get<BurstPredictionResult>(`/api/radio/predict/stored?date=${date}&raw=${raw}`),
  // Model performance over the trailing window (stored detections vs official list).
  burstScorecard: (days = 30) =>
    get<BurstScorecardResponse>(`/api/radio/predict/scorecard?days=${days}`),
  // Official burst-list events over a date range (timeline overlay, max 31 days).
  officialBurstsRange: (start: string, end: string) =>
    get<OfficialBurstRangeResponse>(`/api/radio/bursts/range?start=${start}&end=${end}`),

  alertsLatest: () => get<Alert[]>("/api/alerts/latest"),
  events: (start: string, end: string) =>
    get<SpaceWeatherEvent[]>(`/api/events?start=${start}&end=${end}`),
  // Causal storylines (flare → CME → burst → proton → geomagnetic storm).
  eventChains: (start: string, end: string) =>
    get<EventChain[]>(`/api/event-chains?start=${start}&end=${end}`),
  // Per-parameter, time-aligned activity histograms for the alerts page.
  activityHistogram: (start: string, end: string, interval: number) =>
    get<ActivityHistogramResponse>(
      `/api/events/activity-histogram?start=${start}&end=${end}&interval=${interval}`
    ),

  // Alert delivery (Telegram / webhook push)
  notificationSettings: () => get<NotificationSettings>("/api/notifications/settings"),
  saveNotificationSettings: (s: Omit<NotificationSettings, "telegram_token_configured" | "updated_at">) =>
    putJson<NotificationSettings>("/api/notifications/settings", s),
  testNotifications: () => postNoBody<NotificationTestResponse>("/api/notifications/test"),

  // Solar-cycle progression (monthly SSN/F10.7 + Cycle 25 prediction)
  solarCycle: () => get<SolarCycleResponse>("/api/indices/solar-cycle"),

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

  // Type II shock analysis (Path A)
  analyzerShockGeometry: (id: string, p: RenderParams) =>
    get<RenderGeometry>(`/api/analyzer/shock/geometry?${analyzerQuery(id, p)}`),
  analyzerShockSpectrogramUrl: (id: string, p: RenderParams) =>
    apiUrl(`/api/analyzer/shock/spectrogram?${analyzerQuery(id, p)}`),
  analyzerShockMaxIntensity: (body: {
    id: string;
    method: BgMethod;
    intensity_unit: IntensityUnit;
    rfi_enabled: boolean;
    rfi_low: number;
    rfi_high: number;
    polygon: ShockPoint[];
    auto_clean: boolean;
  }) => postJson<MaxIntensityResult>("/api/analyzer/shock/max-intensity", body),
  analyzerShockFit: (body: {
    id: string;
    points: ShockPoint[];
    fold: number;
    harmonic: boolean;
    time_channels?: number[] | null;
  }) => postJson<ShockFitResult>("/api/analyzer/shock/fit", body),
  analyzerShockFitPlotUrl: (id: string, bust: string | number = "") =>
    apiUrl(`/api/analyzer/shock/fit-plot?id=${id}${bust ? `&v=${bust}` : ""}`),
  analyzerShockExtraPlotUrl: (id: string, kind: ExtraPlotKind, bust: string | number = "") =>
    apiUrl(`/api/analyzer/shock/extra-plot?id=${id}&kind=${kind}${bust ? `&v=${bust}` : ""}`),
  analyzerShockExportUrl: (id: string, format: "xlsx" | "csv") =>
    apiUrl(`/api/analyzer/shock/export?id=${id}&format=${format}`),

  // Data Analysis (SDO/AIA via SunPy)
  analysisOptions: () => get<AnalysisOptions>("/api/analysis/options"),
  analysisUpload: (files: File[]) => {
    const form = new FormData();
    files.forEach((f) => form.append("files", f));
    return postForm<AnalysisSession>("/api/analysis/source/upload", form);
  },
  analysisSession: (id: string) =>
    get<AnalysisSession>(`/api/analysis/session/${id}`),
  // Multi-mission archive search (Fido) + selected-row download.
  analysisSearch: (params: SearchParams) =>
    postJson<SearchResponse>("/api/analysis/source/search", params),
  analysisFindLatest: (params: SearchParams) =>
    postJson<SearchResponse>("/api/analysis/source/find-latest", params),
  analysisFetchSelected: (body: {
    search_id: string;
    indices: number[];
    source: string;
    frame_size: string;
    cutout_x?: number;
    cutout_y?: number;
    cutout_w?: number;
    cutout_h?: number;
  }) => postJson<AnalysisJobStatus>("/api/analysis/source/fetch-selected", body),
  analysisFetch: (wavelength: string, time: string, prep: boolean) =>
    postJson<AnalysisJobStatus>("/api/analysis/source/fetch", { wavelength, time, prep }),
  analysisArchive: (date: string, time: string, wavelength: string) =>
    postJson<AnalysisSession>("/api/analysis/source/archive", { date, time, wavelength }),
  analysisSequence: (
    date: string,
    start_time: string,
    step_min: number,
    n_frames: number,
    wavelength: string
  ) =>
    postJson<AnalysisJobStatus>("/api/analysis/source/sequence", {
      date,
      start_time,
      step_min,
      n_frames,
      wavelength,
    }),
  analysisDifferenceUrl: (
    session: string,
    frame: number,
    diffType: string,
    baseIndex: number,
    p: PlotParams
  ) => apiUrl(`/api/analysis/difference?${analysisDiffQuery(session, frame, diffType, baseIndex, p)}`),
  analysisDifferenceDownloadUrl: (
    session: string,
    frame: number,
    diffType: string,
    baseIndex: number,
    p: PlotParams
  ) =>
    apiUrl(
      `/api/analysis/difference?${analysisDiffQuery(session, frame, diffType, baseIndex, p)}&download=true`
    ),
  analysisRenderUrl: (session: string, frame: number, p: PlotParams) =>
    apiUrl(`/api/analysis/render?${analysisPlotQuery(session, frame, p)}`),
  analysisDownloadUrl: (session: string, frame: number, p: PlotParams) =>
    apiUrl(`/api/analysis/render?${analysisPlotQuery(session, frame, p)}&download=true`),
  analysisCompositeUrl: (session: string, frame: number, contourLevel: number, p: PlotParams) =>
    apiUrl(
      `/api/analysis/composite?${analysisPlotQuery(session, frame, p)}&contour_level=${contourLevel}`
    ),
  analysisCompositeDownloadUrl: (session: string, frame: number, contourLevel: number, p: PlotParams) =>
    apiUrl(
      `/api/analysis/composite?${analysisPlotQuery(session, frame, p)}&contour_level=${contourLevel}&download=true`
    ),
  analysisActiveRegionsUrl: (
    session: string,
    frame: number,
    method: string,
    thresholdPct: number,
    p: PlotParams
  ) =>
    apiUrl(
      `/api/analysis/active-regions?${analysisPlotQuery(session, frame, p)}&method=${method}&threshold_pct=${thresholdPct}`
    ),
  analysisActiveRegionsDownloadUrl: (
    session: string,
    frame: number,
    method: string,
    thresholdPct: number,
    p: PlotParams
  ) =>
    apiUrl(
      `/api/analysis/active-regions?${analysisPlotQuery(session, frame, p)}&method=${method}&threshold_pct=${thresholdPct}&download=true`
    ),
  analysisMovie: (
    session: string,
    fmt: "mp4" | "gif",
    fps: number,
    mode: "plot" | "difference",
    p: PlotParams
  ) =>
    postJson<AnalysisJobStatus>("/api/analysis/movie", {
      session,
      fmt,
      fps,
      mode,
      cmap: p.cmap,
      scale: p.scale,
      clip_low: p.clip_low,
      clip_high: p.clip_high,
      crop: p.crop,
      bl_x: p.bl_x,
      bl_y: p.bl_y,
      tr_x: p.tr_x,
      tr_y: p.tr_y,
    }),
  analysisJob: (jobId: string) =>
    get<AnalysisJobStatus>(`/api/analysis/jobs/${jobId}`),
  analysisResultUrl: (jobId: string, download = false) =>
    apiUrl(`/api/analysis/result/${jobId}${download ? "?download=true" : ""}`),
  // Interactive canvas (exact-pixel background + WCS metadata + readout).
  analysisBareUrl: (session: string, frame: number, mode: string, baseIndex: number, p: PlotParams) =>
    apiUrl(`/api/analysis/render-bare?${analysisBareQuery(session, frame, mode, baseIndex, p)}`),
  analysisFrameMeta: (session: string, frame: number) =>
    get<FrameWcsMeta>(`/api/analysis/frame-meta?session=${session}&frame=${frame}`),
  analysisCoord: (session: string, frame: number, px: number, py: number, frameKey = "HGS") =>
    get<CoordReadout>(
      `/api/analysis/coord?session=${session}&frame=${frame}&px=${px}&py=${py}&frame_key=${frameKey}`
    ),
  // CME height–time tracking.
  analysisHeightTime: (session: string, picks: { frame: number; px: number; py: number }[]) =>
    postJson<HeightTimeResult>("/api/analysis/height-time", { session, picks }),
  // Specialized science: J-map, HMI vector field, compare viewpoint.
  analysisJMap: (session: string, paDeg: number, background: string, halfWidth: number) =>
    postJson<AnalysisJobStatus>("/api/analysis/jmap", {
      session,
      pa_deg: paDeg,
      background,
      half_width: halfWidth,
    }),
  analysisVectorPrepare: (session: string, frame: number) =>
    postJson<AnalysisJobStatus>("/api/analysis/vector-field/prepare", { session, frame }),
  analysisVectorFieldUrl: (
    session: string,
    frame: number,
    o: {
      arrows: boolean;
      streamlines: boolean;
      magnitude: boolean;
      gridStep: number;
      minGauss: number;
    },
    p: PlotParams
  ) => {
    const q = new URLSearchParams({
      session,
      frame: String(frame),
      arrows: String(o.arrows),
      streamlines: String(o.streamlines),
      magnitude: String(o.magnitude),
      grid_step: String(o.gridStep),
      min_gauss: String(o.minGauss),
      cmap: p.cmap,
      scale: p.scale,
      clip_low: String(p.clip_low),
      clip_high: String(p.clip_high),
      draw_limb: String(p.draw_limb),
      colorbar: String(p.colorbar),
    });
    return apiUrl(`/api/analysis/vector-field?${q.toString()}`);
  },
  analysisCompareInfo: (session: string, frame: number, other: string, otherFrame: number) =>
    get<CompareInfo>(
      `/api/analysis/compare-viewpoint/info?session=${session}&frame=${frame}&other=${other}&other_frame=${otherFrame}`
    ),
  analysisCompareUrl: (
    session: string,
    frame: number,
    other: string,
    otherFrame: number,
    view: "primary" | "reprojected",
    p: PlotParams
  ) => {
    const q = new URLSearchParams({
      session,
      frame: String(frame),
      other,
      other_frame: String(otherFrame),
      view,
      cmap: p.cmap,
      scale: p.scale,
      clip_low: String(p.clip_low),
      clip_high: String(p.clip_high),
      draw_limb: String(p.draw_limb),
      colorbar: String(p.colorbar),
    });
    return apiUrl(`/api/analysis/compare-viewpoint?${q.toString()}`);
  },
  // Measurements + region light curve (interactive canvas tools).
  analysisMeasureRuler: (session: string, frame: number, x1: number, y1: number, x2: number, y2: number) =>
    get<RulerResult>(
      `/api/analysis/measure/ruler?session=${session}&frame=${frame}&x1=${x1}&y1=${y1}&x2=${x2}&y2=${y2}`
    ),
  analysisMeasureProfile: (session: string, frame: number, x1: number, y1: number, x2: number, y2: number) =>
    get<ProfileResult>(
      `/api/analysis/measure/profile?session=${session}&frame=${frame}&x1=${x1}&y1=${y1}&x2=${x2}&y2=${y2}`
    ),
  analysisMeasureRegion: (session: string, frame: number, x0: number, y0: number, x1: number, y1: number) =>
    get<RegionStatsResult>(
      `/api/analysis/measure/region?session=${session}&frame=${frame}&x0=${x0}&y0=${y0}&x1=${x1}&y1=${y1}`
    ),
  analysisLightcurve: (
    session: string,
    x0: number,
    y0: number,
    x1: number,
    y1: number,
    statistic: string,
    radioStart?: string | null,
    radioEnd?: string | null
  ) => {
    const q = new URLSearchParams({
      session,
      x0: String(x0),
      y0: String(y0),
      x1: String(x1),
      y1: String(y1),
      statistic,
    });
    if (radioStart) q.set("radio_start", radioStart);
    if (radioEnd) q.set("radio_end", radioEnd);
    return get<LightcurveResult>(`/api/analysis/lightcurve?${q.toString()}`);
  },
  // Session bundles (.ecsolar) + regions CSV.
  analysisSessionExport: async (
    session: string,
    picks: { frame: number; px: number; py: number }[],
    display: Record<string, unknown>
  ): Promise<void> => {
    const res = await fetch(apiUrl("/api/analysis/session/export"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session, picks, display }),
    });
    if (!res.ok) throw await apiError(res, "/api/analysis/session/export");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `session_${session.slice(0, 8)}.ecsolar`;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
  analysisSessionImport: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return postForm<{
      session: AnalysisSession;
      picks: { frame: number; px: number; py: number }[];
      display: Record<string, unknown>;
    }>("/api/analysis/session/import", form);
  },
  analysisRegionsCsvUrl: (session: string, frame: number, thresholdPct = 98) =>
    apiUrl(
      `/api/analysis/export/regions-csv?session=${session}&frame=${frame}&threshold_pct=${thresholdPct}`
    ),
  analysisExportFitsUrl: (session: string, frame: number, p: PlotParams) => {
    const q = new URLSearchParams({
      session,
      frame: String(frame),
      crop: String(p.crop),
      bl_x: String(p.bl_x),
      bl_y: String(p.bl_y),
      tr_x: String(p.tr_x),
      tr_y: String(p.tr_y),
    });
    return apiUrl(`/api/analysis/export/fits?${q.toString()}`);
  },
};
