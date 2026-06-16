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
  RadioArchiveStationsResponse,
  RadioArchiveFilesResponse,
  BurstEventsResponse,
  BurstSpectrum,
  Alert,
  SpaceWeatherEvent,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${path}`);
  }
  return res.json() as Promise<T>;
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
  radioBurstsByDate: (date: string) =>
    get<BurstEventsResponse>(`/api/radio/bursts?date=${date}`),
  radioBurstSpectrumByDate: (date: string, index: number) =>
    get<BurstSpectrum>(`/api/radio/bursts/spectrum?date=${date}&index=${index}`),

  alertsLatest: () => get<Alert[]>("/api/alerts/latest"),
  events: (start: string, end: string) =>
    get<SpaceWeatherEvent[]>(`/api/events?start=${start}&end=${end}`),
};
