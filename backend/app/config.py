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

    # Subdirectories are derived from data_dir (see properties below) so a single
    # DATA_DIR controls all file storage.
    data_dir: str = _DEFAULT_DATA_DIR

    noaa_base_url: str = "https://services.swpc.noaa.gov"
    helioviewer_base_url: str = "https://api.helioviewer.org"

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
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    def ensure_dirs(self) -> None:
        for d in (self.fits_dir, self.spectra_dir, self.solar_images_dir, self.lasco_dir):
            Path(d).mkdir(parents=True, exist_ok=True)


settings = Settings()
