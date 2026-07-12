// ─── Status ──────────────────────────────────────────────────────────────────

export interface StatusResponse {
  service: string;
  status: string;
  timestamp: string;
  version: string;
}

export interface SourceStatus {
  name: string;
  status: "ok" | "degraded" | "error" | "unknown";
  last_updated: string | null;
  message: string | null;
}

export interface SourcesStatusResponse {
  sources: SourceStatus[];
}

// ─── Summary ─────────────────────────────────────────────────────────────────

export interface SummaryLatest {
  timestamp: string;
  goes_xray_class: string | null;
  goes_xray_flux: number | null;
  proton_flux_10mev: number | null;
  kp_index: number | null;
  dst_index: number | null;
  solar_wind_speed: number | null;
  sunspot_number: number | null;
  imf_bz: number | null;
  imf_bt: number | null;
  active_alerts: number;
}

// ─── GOES XRS ────────────────────────────────────────────────────────────────

export interface GoesXrsPoint {
  time: string;
  short_channel: number | null;
  long_channel: number | null;
}

export interface GoesXrsResponse {
  start: string;
  end: string;
  satellite: number | null;
  data: GoesXrsPoint[];
}

export interface GoesXrsLatest {
  time: string | null;
  satellite: number | null;
  short_channel: number | null;
  long_channel: number | null;
  flare_class: string | null;
}

// ─── GOES Proton ─────────────────────────────────────────────────────────────

export interface GoesProtonPoint {
  time: string;
  flux_gt10: number | null;
  flux_gt50: number | null;
  flux_gt100: number | null;
}

export interface GoesProtonResponse {
  start: string;
  end: string;
  satellite: number | null;
  data: GoesProtonPoint[];
}

export interface GoesProtonLatest {
  time: string | null;
  satellite: number | null;
  flux_gt10: number | null;
  flux_gt50: number | null;
  flux_gt100: number | null;
  storm_scale: string | null;
  event_in_progress: boolean;
}

// ─── GOES Electron ───────────────────────────────────────────────────────────

export interface GoesElectronPoint {
  time: string;
  flux_ge2mev: number | null;
}

export interface GoesElectronResponse {
  start: string;
  end: string;
  satellite: number | null;
  data: GoesElectronPoint[];
}

export interface GoesElectronLatest {
  time: string | null;
  satellite: number | null;
  flux_ge2mev: number | null;
}

// ─── GOES Magnetometer ───────────────────────────────────────────────────────

export interface GoesMagnetometerPoint {
  time: string;
  hp: number | null;
  he: number | null;
  hn: number | null;
  total: number | null;
}

export interface GoesMagnetometerResponse {
  start: string;
  end: string;
  satellite: number | null;
  data: GoesMagnetometerPoint[];
}

export interface GoesMagnetometerLatest {
  time: string | null;
  satellite: number | null;
  hp: number | null;
  he: number | null;
  hn: number | null;
  total: number | null;
}

// ─── Solar wind (real-time: speed + IMF Bt/Bz) ───────────────────────────────

export interface SolarWindPoint {
  time: string;
  speed: number | null;
  bt: number | null;
  bz: number | null;
}

export interface SolarWindSeriesResponse {
  range: string;
  source: string;
  data: SolarWindPoint[];
}

export interface SolarWindLatest {
  time: string | null;
  speed: number | null;
  bz: number | null;
  bt: number | null;
  source: string;
}

// ─── Forecast (predicted Kp, DONKI CMEs, NOAA 3-day outlook, aurora) ─────────

export interface KpForecastPoint {
  time: string;
  kp: number | null; // trailing-hour smoothed predicted Kp
}

export interface KpForecastLatest {
  time: string | null;
  kp: number | null; // smoothed predicted Kp (next ~1-3 h)
  coupling: number | null; // Newell dΦ/dt
  g_scale: string | null; // G level this Kp maps to (null = no storm)
}

export interface KpForecastResponse {
  range: string;
  source: string;
  latest: KpForecastLatest;
  data: KpForecastPoint[];
}

export interface CmeItem {
  activity_id: string;
  start_time: string;
  source_location: string | null;
  active_region: number | null;
  latitude: number | null;
  longitude: number | null;
  half_angle: number | null; // cone half-width, degrees
  speed: number | null; // radial speed at 21.5 Rs, km/s
  cme_type: string | null; // DONKI class: S/C/O/R/ER
  time21_5: string | null;
  is_earth_directed: boolean;
  predicted_arrival_time: string | null;
  predicted_kp: number | null;
  note: string;
  catalog_link: string | null;
}

export interface CmeListResponse {
  days: number;
  source: string;
  cmes: CmeItem[];
}

export interface CmeHistoryResponse {
  start: string;
  end: string;
  source: string;
  cmes: CmeItem[];
}

export interface CmeHistogramBin {
  bin_start: string;
  count: number;
  earth_directed: number;
}

export interface CmeHistogramResponse {
  start: string;
  end: string;
  interval_days: number;
  source: string;
  bins: CmeHistogramBin[];
}

export interface ActivityHistogramSeries {
  key: string;
  label: string;
  categories: string[];
  counts: number[][]; // [bin][category]
  total: number;
}

export interface ActivityHistogramResponse {
  start: string;
  end: string;
  interval_days: number;
  bin_starts: string[];
  series: ActivityHistogramSeries[];
}

export interface NoaaScaleDay {
  date: string | null;
  r_scale: string | null;
  r_text: string | null;
  r_minor_prob: number | null; // P(R1-R2) %
  r_major_prob: number | null; // P(R3+) %
  s_scale: string | null;
  s_text: string | null;
  s_prob: number | null; // P(S1+) %
  g_scale: string | null;
  g_text: string | null;
}

export interface NoaaScalesResponse {
  issued: string | null;
  source: string;
  observed: NoaaScaleDay | null; // yesterday's reached maxima
  current: NoaaScaleDay | null; // today so far
  forecast: NoaaScaleDay[]; // next 3 days
}

export interface AuroraForecast {
  observation_time: string | null;
  forecast_time: string | null;
  power_north_gw: number | null;
  power_south_gw: number | null;
  north_image_url: string;
  south_image_url: string;
  source: string;
}

// ─── Solar indices (sunspot progression + F10.7 radio flux) ──────────────────

export interface SunspotSeriesPoint {
  date: string;
  number: number;
  smoothed: number | null;
}

export interface SunspotSeriesResponse {
  scope: "cycle" | "recent";
  source: string;
  data: SunspotSeriesPoint[];
}

export interface F107Point {
  time: string;
  flux: number;
}

export interface F107Response {
  source: string;
  data: F107Point[];
}

// ─── Geomagnetic ─────────────────────────────────────────────────────────────

export interface KpPoint {
  time: string;
  kp: number;
}

export interface DstPoint {
  time: string;
  dst: number;
}

export interface KpLatest {
  time: string | null;
  kp: number | null;
  g_scale: string | null;
}

export interface DstLatest {
  time: string | null;
  dst: number | null;
  storm_level: string | null;
}

// ─── Solar Images ─────────────────────────────────────────────────────────────

export interface SolarImage {
  id: string;
  source: string;
  instrument: string;
  wavelength: string;
  timestamp: string;
  thumbnail_url: string;
  full_url: string;
}

export interface LascoMovie {
  camera: string;
  url: string;
  timestamp: string;
}

export interface SolarArchiveImage {
  id: string;
  source: string;
  instrument: string;
  measurement: string;
  label: string;
  source_id: number;
  supports_events: boolean;
  time: string | null;
  image_url: string;
  png_download_url: string;
  jp2_download_url: string;
  fits_available: boolean;
  fts_download_url: string | null;
}

export interface SolarArchiveResponse {
  date: string;
  time: string;
  with_events: boolean;
  latest: boolean;
  images: SolarArchiveImage[];
}

// ─── Radio ───────────────────────────────────────────────────────────────────

export interface RadioStation {
  id: string;
  name: string;
  location: string;
  freq_min_mhz: number;
  freq_max_mhz: number;
  active: boolean;
}

export interface RadioSpectrum {
  station: string;
  start_time: string;
  end_time: string;
  freq_min_mhz: number;
  freq_max_mhz: number;
  image_url: string;
  processing_method: string;
  fits_filename: string | null;
}

export interface RadioLiveStation {
  id: string;
  has_metadata: boolean;
  focuses: string[];
}

export interface RadioLiveStationsResponse {
  date: string | null;
  stations: RadioLiveStation[];
}

export interface RadioArchiveStation {
  id: string;
  has_metadata: boolean;
}

export interface RadioArchiveStationsResponse {
  date: string;
  stations: RadioArchiveStation[];
}

export interface RadioArchiveFile {
  filename: string;
  start_time: string;
}

export interface RadioArchiveFilesResponse {
  date: string;
  station: string;
  files: RadioArchiveFile[];
}

export interface BurstEventSummary {
  index: number;
  date: string;
  start: string;
  end: string;
  burst_type: string;
  stations: string[];
  station_used: string | null;
  has_fits: boolean;
}

export interface BurstEventsResponse {
  date: string | null;
  count: number;
  sri_lanka_count: number;
  events: BurstEventSummary[];
}

export interface BurstSpectrum {
  index: number;
  date: string;
  start: string;
  end: string;
  burst_type: string;
  station_used: string;
  stations: string[];
  start_time: string | null;
  end_time: string | null;
  freq_min_mhz: number;
  freq_max_mhz: number;
  image_url: string;
  processing_method: string;
  fits_filename: string | null;
}

export interface BurstCandidate {
  id: string;
  start_time: string;
  end_time: string;
  freq_start_mhz: number;
  freq_end_mhz: number;
  classification: string;
  confidence: number;
  status: "pending" | "accepted" | "rejected";
}

// ─── Burst Predictor (ML daily prediction vs official burst list) ─────────────

export interface PredictedDetection {
  station: string;
  focus: string;
  filename: string;
  time: string; // HH:MM:SS UTC
  probability: number;
  alert_level: string;
}

export interface PredictedEvent {
  index: number;
  start: string; // HH:MM UTC
  end: string;
  start_seconds: number;
  end_seconds: number;
  n_stations: number;
  n_detections: number;
  stations: string[];
  max_probability: number;
  alert_level: string;
  matched_official: boolean;
  detections: PredictedDetection[];
}

export interface OfficialBurstCompare {
  start: string;
  end: string;
  burst_type: string;
  stations: string[];
  matched_prediction: boolean;
}

export interface BurstPredictionResult {
  date: string;
  raw: boolean; // true = raw model output (corroboration filter skipped)
  stations: string[];
  total_files: number;
  burst_count: number;
  event_count: number;
  events: PredictedEvent[];
  official_events: OfficialBurstCompare[];
  official_count: number;
  matched_count: number;
}

export interface BurstPredictionJob {
  job_id: string;
  status: "running" | "done" | "error";
  scanned: number;
  total: number;
  date: string;
  stations: string[];
  error: string | null;
  result: BurstPredictionResult | null;
}

// ─── Burst scorecard (model vs official list, trailing window) ───────────────

export interface ScorecardDay {
  date: string;
  has_data: boolean;
  pending: boolean; // official list likely not published yet
  scored_files: number;
  burst_files: number;
  official_count: number;
  predicted_count: number;
  matched_official: number;
  matched_predicted: number;
}

export interface BurstScorecardResponse {
  days: number;
  days_with_data: number;
  official_total: number;
  predicted_total: number;
  matched_official: number;
  matched_predicted: number;
  recall: number | null; // official bursts the model matched
  precision: number | null; // predicted events matching an official burst
  daily: ScorecardDay[];
}

// ─── Official burst list over a date range (timeline overlay) ────────────────

export interface OfficialBurstItem {
  start_time: string;
  end_time: string;
  burst_type: string; // e.g. "III", "II", "CTM"
  stations: string[];
}

export interface OfficialBurstRangeResponse {
  start: string;
  end: string;
  source: string;
  events: OfficialBurstItem[];
}

// ─── Notifications (alert delivery) ──────────────────────────────────────────

export type AlertSeverity = "info" | "watch" | "warning" | "critical";

export interface NotificationSettings {
  telegram_enabled: boolean;
  telegram_chat_id: string;
  webhook_enabled: boolean;
  webhook_url: string;
  min_severity: AlertSeverity;
  event_types: string[]; // empty = all
  telegram_token_configured: boolean;
  updated_at: string | null;
}

export interface ChannelResult {
  ok: boolean;
  error: string | null;
}

export interface NotificationTestResponse {
  telegram: ChannelResult | null;
  webhook: ChannelResult | null;
}

// ─── Solar cycle progression ─────────────────────────────────────────────────

export interface SolarCycleObservedPoint {
  month: string; // "YYYY-MM"
  ssn: number | null;
  smoothed_ssn: number | null;
  f107: number | null;
  smoothed_f107: number | null;
}

export interface SolarCyclePredictedPoint {
  month: string;
  ssn: number | null;
  ssn_high: number | null;
  ssn_low: number | null;
  f107: number | null;
  f107_high: number | null;
  f107_low: number | null;
}

export interface SolarCycleResponse {
  source: string;
  cycle25_start: string;
  observed: SolarCycleObservedPoint[];
  predicted: SolarCyclePredictedPoint[];
}

// ─── Alerts & Events ─────────────────────────────────────────────────────────

export interface Alert {
  id: string;
  type: string;
  severity: "info" | "watch" | "warning" | "critical";
  message: string;
  timestamp: string;
  source: string;
  /** Ids of physically associated events (e.g. the radio burst of a flare). */
  related_event_ids?: string[];
}

export interface SpaceWeatherEvent {
  id: string;
  type: string;
  severity: string | null;
  start_time: string;
  end_time: string | null;
  peak_time: string | null;
  peak_value: number | null;
  description: string;
  /** Observing stations for station-based events (radio bursts); empty otherwise. */
  stations: string[];
  related_event_ids: string[];
  source_url: string | null;
}

// ─── e-CALLISTO Analyzer ───────────────────────────────────────────────────────

export type BgMethod = "mean" | "median" | "robust";
export type IntensityUnit = "digits" | "db";
export type TimeUnit = "seconds" | "utc";
export type CombineMode = "time" | "frequency";

export interface AnalyzerSession {
  id: string;
  station: string;
  filename: string;
  n_freq: number;
  n_time: number;
  freq_min_mhz: number;
  freq_max_mhz: number;
  start_time: string | null;
  end_time: string | null;
  duration_s: number;
}

export interface AnalyzerStats {
  data_min: number;
  data_max: number;
  vmin: number;
  vmax: number;
}

export interface AnalyzerOptions {
  colormaps: string[];
  methods: BgMethod[];
  intensity_units: IntensityUnit[];
  time_units: TimeUnit[];
}

export interface RenderParams {
  method: BgMethod;
  intensity_unit: IntensityUnit;
  time_unit: TimeUnit;
  cmap: string;
  vmin: number | null;
  vmax: number | null;
  rfi_enabled: boolean;
  rfi_low: number;
  rfi_high: number;
  station: string;
}

export interface ProjectSettings {
  method: BgMethod;
  intensity_unit: IntensityUnit;
  time_unit: TimeUnit;
  cmap: string;
  vmin: number | null;
  vmax: number | null;
  rfi_enabled: boolean;
  rfi_low: number;
  rfi_high: number;
}

// ─── Type II shock analysis (Path A) ───────────────────────────────────────────

/** Plotted-area geometry of the shock spectrogram (PNG pixels) for lasso mapping. */
export interface RenderGeometry {
  img_w: number;
  img_h: number;
  axes_px: [number, number, number, number]; // x0, y0, x1, y1 (top-left origin)
  t0: number;
  t1: number;
  freq_top: number;
  freq_bottom: number;
}

export interface ShockPoint {
  time_s: number;
  freq_mhz: number;
}

export interface MaxIntensityResult {
  time_channels: number[];
  time_seconds: number[];
  freqs: number[];
  auto_outlier_cleaned: boolean;
  auto_removed_count: number;
}

export interface PowerLawFit {
  a: number;
  b: number;
  std_errs: (number | null)[];
  r2: number | null;
  rmse: number | null;
  point_count: number;
}

export interface ShockSummary {
  avg_freq_mhz: number | null;
  avg_freq_err_mhz: number | null;
  avg_drift_mhz_s: number | null;
  avg_drift_err_mhz_s: number | null;
  start_freq_mhz: number | null;
  start_freq_err_mhz: number | null;
  initial_shock_speed_km_s: number | null;
  initial_shock_speed_err_km_s: number | null;
  initial_shock_height_rs: number | null;
  initial_shock_height_err_rs: number | null;
  avg_shock_speed_km_s: number | null;
  avg_shock_speed_err_km_s: number | null;
  avg_shock_height_rs: number | null;
  avg_shock_height_err_rs: number | null;
  fold: number;
  fundamental: boolean;
  harmonic: boolean;
  harmonic_number: number;
  observed_avg_freq_mhz: number | null;
  observed_avg_drift_mhz_s: number | null;
  observed_start_freq_mhz: number | null;
}

export interface ShockCurves {
  shock_freq_mhz: number[];
  shock_speed_km_s: number[];
  shock_height_rs: number[];
}

export interface FitLine {
  time_s: number[];
  freq_mhz: number[];
}

export interface ShockFitResult {
  fit: PowerLawFit;
  shock_summary: ShockSummary;
  curves: ShockCurves;
  fit_line: FitLine;
}

export interface ShockSession {
  time_seconds: number[];
  freqs: number[];
  fundamental: boolean;
  harmonic: boolean;
  fold: number;
  fit: PowerLawFit | null;
  shock_summary: ShockSummary | null;
}

export type ExtraPlotKind = "speed_height" | "speed_freq" | "height_freq";

export interface ProjectOpenResponse {
  session: AnalyzerSession;
  settings: ProjectSettings;
  shock: ShockSession | null;
}

// ─── Data Analysis (SDO/AIA via SunPy) ─────────────────────────────────────────

export interface AnalysisFrameMeta {
  index: number;
  time: string | null;
  filename: string;
  detector?: string;
  exptime?: number | null;
}

export type ScienceClass = "disk_euv" | "coronagraph" | "heliospheric" | "magnetograph";

export interface AnalysisSession {
  id: string;
  source: "upload" | "fetch" | "archive" | "search";
  observatory: string;
  instrument: string;
  detector: string;
  measurement: string;
  wavelength_angstrom: number | null;
  reference_time: string | null;
  width: number;
  height: number;
  n_frames: number;
  science_class: ScienceClass;
  frames: AnalysisFrameMeta[];
}

export interface WavelengthOption {
  code: string;
  label: string;
}

// A selectable multi-mission target (mirrors the backend instrument registry).
export interface Observable {
  key: string;
  label: string;
  spacecraft: string;
  instrument: string;
  detector: string | null;
  data_kind: string;
  science_class: ScienceClass | "unknown";
  supports_wavelength: boolean;
  supports_detector: boolean;
  supports_product: boolean;
  supports_satellite: boolean;
  supports_level: boolean;
  wavelengths: number[];
  products: string[];
  levels: string[];
  default_wavelength: number | null;
  default_product: string | null;
  default_level: string | null;
  default_satellite: number | null;
}

export interface AnalysisOptions {
  wavelengths: WavelengthOption[];
  colormaps: string[];
  scales: string[];
  difference_types: string[];
  movie_formats: string[];
  max_frames: number;
  observables: Observable[];
  sources: string[];
  frame_sizes: string[];
  jsoc_enabled: boolean;
}

export interface SearchRow {
  index: number;
  start: string | null;
  end: string | null;
  source: string;
  provider: string;
  instrument: string;
  size: string;
  fileid: string;
}

export interface SearchResponse {
  search_id: string;
  observable: string;
  data_kind: string;
  rows: SearchRow[];
  notice: string | null;
}

export interface AnalysisJobStatus {
  job_id: string;
  state: "pending" | "running" | "done" | "error";
  progress: number;
  message: string;
  error: string | null;
  session: AnalysisSession | null;
  result_url: string | null;
  meta: Record<string, unknown> | null;
}

export interface PlotParams {
  cmap: string;
  scale: string;
  clip_low: number;
  clip_high: number;
  vmin: number | null;
  vmax: number | null;
  crop: boolean;
  bl_x: number;
  bl_y: number;
  tr_x: number;
  tr_y: number;
  draw_limb: boolean;
  draw_grid: boolean;
  colorbar: boolean;
  nrgf: boolean;               // coronagraph radial filter
  grid_frame: "" | "hgs" | "hgc" | "hci"; // coordinate graticule ("" = off)
}

// WCS/geometry for the interactive canvas (GET /frame-meta).
export interface FrameWcsMeta {
  nx: number;
  ny: number;
  center_x: number;            // Sun-centre pixel, 0-based
  center_y: number;
  cdelt1: number;              // arcsec / pixel
  cdelt2: number;
  pc: number[][];              // 2×2 rotation matrix
  rsun_arcsec: number;
  time: string | null;
  instrument: string;
  detector: string;
  measurement: string;
  exptime: number | null;
}

// Measurement results (GET /measure/*, /lightcurve).
export interface RulerResult {
  p0_arcsec: number[];
  p1_arcsec: number[];
  dx_arcsec: number;
  dy_arcsec: number;
  distance_arcsec: number;
  distance_rsun: number | null;
  distance_km: number | null;
  position_angle_deg: number;
}

export interface ProfileResult {
  distance_arcsec: number[];
  values: (number | null)[];
  n: number;
  length_arcsec: number;
  length_rsun: number | null;
}

export interface RegionStatsResult {
  n_pixels: number;
  min: number;
  max: number;
  mean: number;
  median: number;
  std: number;
  centroid_x_pix: number;
  centroid_y_pix: number;
  centroid_tx_arcsec: number;
  centroid_ty_arcsec: number;
}

export interface LightcurveResult {
  times: (string | null)[];
  values: (number | null)[];
  unit: string;
  statistic: string;
  bounds: number[];
  peak_index: number;
  peak_time: string | null;
  radio_start: string | null;
  radio_end: string | null;
  radio_euv_lag_s: number | null;
}

// CME height–time tracking (POST /height-time).
export interface HeightTimePoint {
  frame: number;
  time: string | null;
  px: number;
  py: number;
  r_rsun: number;
  height_km: number;
}

export interface HeightTimeResult {
  points: HeightTimePoint[];
  n: number;
  speed_km_s?: number;
  acceleration_km_s2?: number | null;
  segment_speeds_km_s?: (number | null)[];
}

// Two-viewpoint comparison (GET /compare-viewpoint/info).
export interface CompareInfo {
  separation_deg: number | null;
  primary: string;
  secondary: string;
  primary_time: string | null;
  secondary_time: string | null;
}

// Exact server-side coordinate readout (GET /coord).
export interface CoordReadout {
  px: number;
  py: number;
  tx_arcsec: number;
  ty_arcsec: number;
  r_rsun: number | null;
  position_angle_deg: number;
  lon_deg: number | null;
  lat_deg: number | null;
  frame_key: string;
  value: number | null;
}
