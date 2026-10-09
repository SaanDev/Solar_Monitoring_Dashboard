import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default data directory lives inside the backend project so local dev works
# without root (Docker overrides DATA_DIR=/data via a mounted volume).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_DIR = str(_BACKEND_ROOT / "data")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    version: str = "1.1.0-beta"
    log_level: str = "info"

    database_url: str = "postgresql+asyncpg://swdash:swdash@localhost:5432/swdash"
    # Empty or "memory://" swaps Redis for an in-process TTL cache (app/cache.py)
    # — what the desktop app uses, since it ships without a Redis server.
    redis_url: str = "redis://localhost:6379/0"

    # ── Windows desktop app (see app/desktop.py, docs/desktop.md) ─────────────
    # Set by the desktop launcher, never by the website/Docker deployments.
    # desktop_mode turns on the cross-origin write guard in app/main.py.
    desktop_mode: bool = False
    # Directory holding the Next.js static export (`npm run build:desktop`).
    # When set, the backend serves the dashboard UI itself at "/", on the same
    # origin as /api. Empty (the default) leaves the frontend to Next.js.
    frontend_dist_dir: str = ""

    # Run the background ingestion scheduler on startup. Disable in tests/CI.
    enable_scheduler: bool = True

    # Apply Alembic migrations (upgrade to head) on startup so a fresh or
    # out-of-date database always has the current schema (e.g. after pulling new
    # migrations, or on a second machine). Disable in tests/CI.
    auto_migrate: bool = True

    # ── ML radio-burst detection (native, in-process) ─────────────────────────
    # The trained burst classifier runs inside this backend (see app/ml/). The
    # scheduler polls e-CALLISTO for new files, scores them in-process, and raises
    # `radio_burst` events from positive hits. Device/model settings are below.
    radio_burst_enabled: bool = True
    # How often to scan the archive for new files (seconds). Files are ~15 min.
    radio_burst_scan_interval: int = 600
    # Only score files whose start time is within this many hours of now (bounds
    # the first-run backlog and keeps alerting focused on recent activity).
    radio_burst_max_age_hours: int = 3
    # Minimum burst probability for a detection to contribute to an alert/event.
    # 0 (default) = use the model's own tuned decision threshold (BnB v1.1:
    # 0.787), read from its checkpoint. Set a positive value only to deliberately
    # gate *above* that.
    radio_burst_alert_min_probability: float = 0.0
    # Multi-station confirmation (app/processing/burst_confirmation.py, tuning in
    # docs/radio-burst-confirmation.md). A burst becomes a radio_burst event only
    # when the readings of every station observing it with the Sun up — each
    # weighted by that station's track record, stations within SITE_RADIUS_KM
    # counting once — add up to MIN_EVIDENCE (nats; 4.0 = ~55x likelier a burst
    # than chance), with at least MIN_SITES sites flagging it at
    # >= HIGH_CONF_PROBABILITY. 4.0 is "balanced" (~92% of events real, 80% of
    # important bursts found on the 2026 replay); 5.0 is stricter (~96% / 78%),
    # 3.5 more sensitive (~90% / 82%). SILENCE_WEIGHT scales how much a reliable
    # station staying silent counts against a burst.
    radio_burst_high_conf_probability: float = 0.9
    radio_burst_min_evidence: float = 4.0
    radio_burst_silence_weight: float = 0.8
    radio_burst_min_sites: int = 2
    radio_burst_min_observing_sites: int = 3
    radio_burst_site_radius_km: float = 30.0
    radio_burst_sun_min_elevation: float = 0.0
    # Each station's track record is re-measured daily from this many days of
    # stored detections. Stations scoring at least MIN_RELIABILITY (agreement with
    # other sites beyond chance) pick the sure bursts that record is learned on.
    # Settings can force a station's weight up or ignore it.
    radio_burst_min_reliability: float = 0.15
    radio_burst_reliability_days: int = 60
    # Max concurrent scoring requests to the inference service per scan.
    radio_burst_concurrency: int = 4
    # Optional safety cap on files scored in one on-demand "Burst Predictor" run.
    # 0 (default) = no limit: process every available segment for the day across
    # all selected stations. Set a positive value only to bound a very large run.
    radio_burst_predict_max_files: int = 0
    # ── Offline catch-up ──────────────────────────────────────────────────
    # Downtime leaves holes in the burst timeline: the live scan above only ever
    # looks at the last `radio_burst_max_age_hours`, so anything older is never
    # scored. The catch-up pass fills those days in the background
    # (app/services/radio_backfill_service.py).
    radio_burst_backfill_enabled: bool = True
    # How far back the AUTOMATIC catch-up reaches, in days. A day of archive is
    # ~5k segments (a few minutes of CPU scoring with BnB v1.1 at ~0.07 s each,
    # plus the downloads, which take longer), so a cold start
    # on a long gap — or a model change, which re-scores the window — is a long
    # job. It is resumable and cancellable, and runs newest day first. Wider gaps
    # can still be filled by hand from the Settings page.
    radio_burst_backfill_max_days: int = 30
    # How often to re-check for gaps (seconds). Cheap when there are none: days
    # already recorded as covered are skipped without touching the network.
    radio_burst_backfill_interval: int = 3600
    # Concurrent archive downloads while catching up. Deliberately gentler than
    # the live scan's: real-time alerting has priority over history.
    radio_burst_backfill_concurrency: int = 3

    # Default model for the automatic scan (and the Burst Detector page's initial
    # choice). Ids come from app/ml/registry.py; "bnb-1.1.0" is the only one. A
    # model chosen on the Settings page is stored in the database and takes
    # precedence (app/services/model_settings_service.py). Its threshold comes
    # from the checkpoint, where it was tuned, so it is deliberately not
    # configurable here.
    radio_burst_model: str = "bnb-1.1.0"

    # Subdirectories are derived from data_dir (see properties below) so a single
    # DATA_DIR controls all file storage.
    data_dir: str = _DEFAULT_DATA_DIR

    noaa_base_url: str = "https://services.swpc.noaa.gov"
    # NASA DONKI (CME catalog + WSA-ENLIL arrival predictions). CCMC's public
    # DONKI-API needs no API key; the collector appends /get/CME. It replaced
    # kauai.ccmc.gsfc.nasa.gov/DONKI/WS on 2026-09-30 (the old host and the
    # api.nasa.gov mirror now redirect to a CCMC news page).
    donki_base_url: str = "https://ccmc.gsfc.nasa.gov/DONKI-API"
    # How often to re-fetch the DONKI window (analyses are revised for days),
    # and how far back that window reaches.
    cme_poll_seconds: int = 7200
    cme_lookback_days: int = 30
    helioviewer_base_url: str = "https://api.helioviewer.org"
    # JSOC synoptic FITS archives (SDO/AIA + SDO/HMI) for raw downloads.
    jsoc_base_url: str = "http://jsoc.stanford.edu"
    # JSOC export requires a notify e-mail registered at
    # http://jsoc.stanford.edu/ajax/register_email.html — used by the drms
    # "fast path" (server-side cutout/binning) in the Data Analysis feature.
    # Empty disables the fast path; acquisition then falls back to VSO/Fido.
    jsoc_email: str = ""
    # GFZ — historical Kp index (full record since 1932).
    gfz_base_url: str = "https://kp.gfz.de"
    # SILSO (SIDC, Royal Observatory of Belgium) — daily estimated sunspot number.
    silso_base_url: str = "https://www.sidc.be"

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # ── Alert delivery (Telegram / webhook push) ───────────────────────────────
    # Bot token from @BotFather — the one channel secret, kept out of the DB.
    telegram_bot_token: str = ""
    telegram_api_base: str = "https://api.telegram.org"
    # Dispatch pass cadence + per-pass send cap (flood control) + how far back
    # an event can start and still be delivered.
    notify_dispatch_seconds: int = 120
    notify_max_per_pass: int = 8
    notify_lookback_hours: int = 48

    # ── Native ML inference (burst model) ─────────────────────────────────────
    # Path to the BnB v1.1 checkpoint. A relative path is resolved from the
    # backend package root. It ships in the repo via Git LFS under
    # backend/ml_model/, so a normal `git clone` + `git lfs pull` brings it down
    # automatically — no manual download needed.
    ml_model_path: str = "ml_model/bnb_v1_1.pt"
    # Optional direct download URL — only a fallback for environments without
    # Git LFS (e.g. a GitHub "Download ZIP" that ships LFS pointer files). Leave
    # empty to rely on the LFS copy.
    ml_model_url: str = ""
    # When True and a checkpoint is missing AND its URL is set, download on startup.
    ml_model_auto_download: bool = True
    # Device for torch inference: "auto" (CUDA > MPS > CPU), "cpu", "cuda", "mps".
    ml_inference_device: str = "auto"

    @property
    def fits_dir(self) -> str:
        return str(Path(self.data_dir) / "fits")

    @property
    def spectra_dir(self) -> str:
        return str(Path(self.data_dir) / "spectra")

    @property
    def solar_images_dir(self) -> str:
        return str(Path(self.data_dir) / "solar_images")

    @property
    def lasco_dir(self) -> str:
        return str(Path(self.data_dir) / "lasco")

    @property
    def analyzer_dir(self) -> str:
        # Uploaded / archive-imported FITS for the interactive e-CALLISTO Analyzer.
        return str(Path(self.data_dir) / "analyzer")

    @property
    def analysis_dir(self) -> str:
        # SDO/AIA Data Analysis sessions: source FITS + rendered artifacts, one
        # subfolder per session/job (see app/services/aia_data_service.py).
        return str(Path(self.data_dir) / "analysis")

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    @property
    def ml_model_dir(self) -> str:
        """Directory that holds the ML model checkpoint."""
        p = Path(self.ml_model_path)
        return str(p.parent if not p.is_absolute() else p.parent)

    def ensure_dirs(self) -> None:
        for d in (
            self.fits_dir,
            self.spectra_dir,
            self.solar_images_dir,
            self.lasco_dir,
            self.analyzer_dir,
            self.analysis_dir,
        ):
            Path(d).mkdir(parents=True, exist_ok=True)
        # Model checkpoint directory (relative paths live inside the backend root).
        ml_path = Path(self.ml_model_path)
        if not ml_path.is_absolute():
            ml_path = _BACKEND_ROOT / ml_path
        ml_path.parent.mkdir(parents=True, exist_ok=True)


settings = Settings()

# Point SunPy's config/cache directory at a writable location under DATA_DIR. This
# must be set *before* sunpy is first imported (done lazily inside the analysis
# services), so a read-only home directory (e.g. a hardened container) never makes
# `import sunpy` fail, and any downloads land with the rest of our data. Fido
# fetches always pass an explicit ``path=`` so downloaded FITS go to the session
# directory regardless of this setting.
os.environ.setdefault(
    "SUNPY_CONFIGDIR", str(Path(settings.data_dir) / "analysis" / "_sunpy")
)

# The VSO/JSOC export mirror often stalls on the first request while it stages
# the file, then serves it on a retry. Give each attempt a generous (but not
# endless) socket-read window and drop the total cap; fetch_via_fido retries once,
# so a stalled first attempt recovers without waiting the full default forever.
os.environ.setdefault("PARFIVE_SOCK_READ_TIMEOUT", "150")
os.environ.setdefault("PARFIVE_TOTAL_TIMEOUT", "0")
