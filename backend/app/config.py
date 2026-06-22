from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default data directory lives inside the backend project so local dev works
# without root (Docker overrides DATA_DIR=/data via a mounted volume).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_DIR = str(_BACKEND_ROOT / "data")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    version: str = "0.1.0"
    log_level: str = "info"

    database_url: str = "postgresql+asyncpg://swdash:swdash@localhost:5432/swdash"
    redis_url: str = "redis://localhost:6379/0"

    # Run the background ingestion scheduler on startup. Disable in tests/CI.
    enable_scheduler: bool = True

    # Apply Alembic migrations (upgrade to head) on startup so a fresh or
    # out-of-date database always has the current schema (e.g. after pulling new
    # migrations, or on a second machine). Disable in tests/CI.
    auto_migrate: bool = True

    # ── ML radio-burst detection ──────────────────────────────────────────────
    # The trained burst classifier runs in a separate microservice (the Burst
    # Identifier project). The backend polls e-CALLISTO for new files and scores
    # them via this service, raising `radio_burst` events from positive hits.
    ml_inference_url: str = "http://localhost:9000"
    radio_burst_enabled: bool = True
    # How often to scan the archive for new files (seconds). Files are ~15 min.
    radio_burst_scan_interval: int = 600
    # Only score files whose start time is within this many hours of now (bounds
    # the first-run backlog and keeps alerting focused on recent activity).
    radio_burst_max_age_hours: int = 3
    # Minimum burst probability for a detection to contribute to an alert/event.
    radio_burst_alert_min_probability: float = 0.595
    # Corroboration filter for raising a burst ALERT: a 15-min window only becomes
    # a radio_burst event when at least this many distinct stations detected the
    # burst, with at least this many of them above the high-confidence probability.
    radio_burst_min_stations: int = 4
    radio_burst_min_high_conf_stations: int = 2
    radio_burst_high_conf_probability: float = 0.9
    # Max concurrent scoring requests to the inference service per scan.
    radio_burst_concurrency: int = 4
    # Optional safety cap on files scored in one on-demand "Burst Predictor" run.
    # 0 (default) = no limit: process every available segment for the day across
    # all selected stations. Set a positive value only to bound a very large run.
    radio_burst_predict_max_files: int = 0

    # Subdirectories are derived from data_dir (see properties below) so a single
    # DATA_DIR controls all file storage.
    data_dir: str = _DEFAULT_DATA_DIR

    noaa_base_url: str = "https://services.swpc.noaa.gov"
    helioviewer_base_url: str = "https://api.helioviewer.org"
    # JSOC synoptic FITS archives (SDO/AIA + SDO/HMI) for raw downloads.
    jsoc_base_url: str = "http://jsoc.stanford.edu"
    # GFZ — historical Kp index (full record since 1932).
    gfz_base_url: str = "https://kp.gfz.de"
    # SILSO (SIDC, Royal Observatory of Belgium) — daily estimated sunspot number.
    silso_base_url: str = "https://www.sidc.be"

    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

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
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    def ensure_dirs(self) -> None:
        for d in (
            self.fits_dir,
            self.spectra_dir,
            self.solar_images_dir,
            self.lasco_dir,
            self.analyzer_dir,
        ):
            Path(d).mkdir(parents=True, exist_ok=True)


settings = Settings()
