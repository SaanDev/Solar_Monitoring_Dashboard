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

// ─── Alerts & Events ─────────────────────────────────────────────────────────

export interface Alert {
  id: string;
  type: string;
  severity: "info" | "watch" | "warning" | "critical";
  message: string;
  timestamp: string;
  source: string;
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

export interface ProjectOpenResponse {
  session: AnalyzerSession;
  settings: ProjectSettings;
}
