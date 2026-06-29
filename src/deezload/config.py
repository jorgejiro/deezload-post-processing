"""Configuration loaded from environment variables with documented defaults."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    spotify_client_id: str
    spotify_client_secret: str
    spotify_redirect_uri: str
    scan_interval_seconds: int
    stable_minutes: int
    part_size_threshold_mb: int
    min_total_size_mb: int
    album_artist: str
    puid: int | None
    pgid: int | None
    tz: str
    delete_zips_after: bool
    log_level: str
    input_dir: str
    output_dir: str
    config_dir: str


def load_config() -> Config:
    """Build a Config from the current environment."""

    def _int(key: str, default: int) -> int:
        return int(os.environ.get(key, default))

    def _bool(key: str, default: bool) -> bool:
        raw = os.environ.get(key, str(default)).lower()
        return raw not in ("0", "false", "no", "off")

    def _opt_int(key: str) -> int | None:
        val = os.environ.get(key)
        return int(val) if val else None

    return Config(
        spotify_client_id=os.environ.get("SPOTIFY_CLIENT_ID", ""),
        spotify_client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET", ""),
        spotify_redirect_uri=os.environ.get(
            "SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback"
        ),
        scan_interval_seconds=_int("SCAN_INTERVAL_SECONDS", 60),
        stable_minutes=_int("STABLE_MINUTES", 5),
        part_size_threshold_mb=_int("PART_SIZE_THRESHOLD_MB", 1000),
        min_total_size_mb=_int("MIN_TOTAL_SIZE_MB", 100),
        album_artist=os.environ.get("ALBUM_ARTIST", "Various Artists"),
        puid=_opt_int("PUID"),
        pgid=_opt_int("PGID"),
        tz=os.environ.get("TZ", "UTC"),
        delete_zips_after=_bool("DELETE_ZIPS_AFTER", True),
        log_level=os.environ.get("LOG_LEVEL", "INFO"),
        input_dir=os.environ.get("INPUT_DIR", "/input"),
        output_dir=os.environ.get("OUTPUT_DIR", "/output"),
        config_dir=os.environ.get("CONFIG_DIR", "/config"),
    )
