import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

# Default data directory lives inside the backend project so local dev works
# without root (Docker overrides DATA_DIR=/data via a mounted volume).
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_DATA_DIR = str(_BACKEND_ROOT / "data")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    version: str = "1.0.0"
    log_level: str = "info"

    database_url: str = "postgresql+asyncpg://swdash:swdash@localhost:5432/swdash"
    redis_url: str = "redis://localhost:6379/0"

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
    # 0 (default) = use the active model's own tuned decision threshold, which is
    # per-model (CCM v1.0.0 = 0.595, CCM v1.1.0 = 0.51) and read from its
    # checkpoint. Set a positive value only to deliberately gate *above* that.
    radio_burst_alert_min_probability: float = 0.0
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
    # Which binary model the automatic scan uses, and the page's default choice.
    # Ids come from app/ml/registry.py: "ccm-1.0.0" | "ccm-1.1.0".
    radio_burst_binary_model: str = "ccm-1.1.0"
    # Second stage: classify the burst TYPE of every burst-positive file with
    # CCMT. Runs on region crops (see app/ml/regions.py), never whole files.
    radio_burst_classify_types: bool = True
    radio_burst_type_model: str = "ccmt-1.0.0"
    # Region proposals fed to the type model. Brightness in normalised [0,1]
    # units where 0 = -1 dB and 1 = +8 dB above background; the effective
    # threshold is capped adaptively per spectrum (see regions.resolve_threshold).
    radio_burst_region_threshold: float = 0.35
    radio_burst_region_min_area: int = 60
    radio_burst_region_max: int = 8
    # Smallest region worth typing, in pixels (frequency rows x time samples).
    # Matches the smallest box CCMT was trained on, and drops e-CALLISTO's
    # periodic narrow-band calibration marker, which otherwise fills every
    # candidate slot. See app/ml/regions.py.
    radio_burst_region_min_rows: int = 12
    radio_burst_region_min_cols: int = 9

    # Subdirectories are derived from data_dir (see properties below) so a single
    # DATA_DIR controls all file storage.
    data_dir: str = _DEFAULT_DATA_DIR

    noaa_base_url: str = "https://services.swpc.noaa.gov"
    # NASA DONKI (CME catalog + WSA-ENLIL arrival predictions). The CCMC web
    # service needs no API key, unlike the api.nasa.gov mirror.
    donki_base_url: str = "https://kauai.ccmc.gsfc.nasa.gov/DONKI"
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

    # ── Natural-language "State of the Sun" briefing (Anthropic) ──────────────
    # A scheduled, change-gated pass turns the current conditions/alerts/forecast/
    # storylines into a plain-English operator brief via Claude, cached in Redis
    # and served to all viewers. ``anthropic_api_key`` is the one secret (kept in
    # .env like the Telegram token); an empty key disables the feature — the
    # Overview card simply hides, exactly like a missing ML model or bot token.
    anthropic_api_key: str = ""
    briefing_enabled: bool = True
    briefing_model: str = "claude-sonnet-5"
    # How often the scheduler re-evaluates conditions; the LLM is only actually
    # called when the (bucketed) conditions changed since the last brief.
    briefing_interval_seconds: int = 1800
    briefing_max_tokens: int = 500

    # ── Native ML inference (burst classifiers) ───────────────────────────────
    # Paths to the ResNet-18 checkpoints. Relative paths are resolved from the
    # backend package root. They ship in the repo via Git LFS under
    # backend/ml_model/, so a normal `git clone` + `git lfs pull` brings them
    # down automatically — no manual download needed. See app/ml/registry.py for
    # which id maps to which path.
    ml_model_path: str = "ml_model/best.pt"            # CCM v1.0.0 (binary)
    ml_ccm_v110_path: str = "ml_model/ccm_v1_1_0.pt"   # CCM v1.1.0 (binary)
    ml_ccmt_v100_path: str = "ml_model/ccmt_v1_0_0.pt"  # CCMT v1.0.0 (burst type)
    # Optional direct download URLs — only a fallback for environments without
    # Git LFS (e.g. a GitHub "Download ZIP" that ships LFS pointer files).
    # Set via ML_MODEL_URL / ML_CCM_V110_URL / ML_CCMT_V100_URL in .env; leave
    # empty to rely on the LFS copies.
    ml_model_url: str = ""
    ml_ccm_v110_url: str = ""
    ml_ccmt_v100_url: str = ""
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
