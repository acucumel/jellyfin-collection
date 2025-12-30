"""Application configuration using Pydantic Settings."""

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


# Load .env file at module import
load_dotenv()


class JellyfinSettings(BaseModel):
    """Jellyfin server configuration."""

    url: str = Field(default="http://localhost:8096")
    api_key: str = Field(default="")


class TMDbSettings(BaseModel):
    """TMDb API configuration."""

    api_key: str = Field(default="")
    language: str = Field(default="fr")
    region: str = Field(default="FR")


class TraktSettings(BaseModel):
    """Trakt API configuration."""

    client_id: str = Field(default="")
    client_secret: str = Field(default="")
    access_token: Optional[str] = Field(default=None)
    refresh_token: Optional[str] = Field(default=None)


class MDBListSettings(BaseModel):
    """MDBList API configuration."""

    api_key: Optional[str] = Field(default=None)


class RadarrSettings(BaseModel):
    """Radarr configuration."""

    url: str = Field(default="http://localhost:7878")
    api_key: str = Field(default="")
    root_folder: str = Field(default="/movies")
    quality_profile: str = Field(default="HD-1080p")
    default_tag: str = Field(default="jfc")
    add_missing: bool = Field(default=True)


class SonarrSettings(BaseModel):
    """Sonarr configuration."""

    url: str = Field(default="http://localhost:8989")
    api_key: str = Field(default="")
    root_folder: str = Field(default="/tv")
    quality_profile: str = Field(default="HD-1080p")
    default_tag: str = Field(default="jfc")
    add_missing: bool = Field(default=True)


class DiscordSettings(BaseModel):
    """Discord webhook configuration."""

    webhook_url: Optional[str] = Field(default=None)
    webhook_error: Optional[str] = Field(default=None)
    webhook_run_start: Optional[str] = Field(default=None)
    webhook_run_end: Optional[str] = Field(default=None)
    webhook_changes: Optional[str] = Field(default=None)

    def get_webhook(self, event_type: str) -> Optional[str]:
        """Get webhook URL for a specific event type, falling back to default."""
        specific = getattr(self, f"webhook_{event_type}", None)
        return specific or self.webhook_url


class SchedulerSettings(BaseModel):
    """Scheduler configuration."""

    cron: str = Field(default="0 3 * * *")
    timezone: str = Field(default="Europe/Paris")


class Settings(BaseSettings):
    """Main application settings."""

    # Jellyfin
    jellyfin_url: str = Field(default="http://localhost:8096")
    jellyfin_api_key: str = Field(default="")

    # TMDb
    tmdb_api_key: str = Field(default="")
    tmdb_language: str = Field(default="fr")
    tmdb_region: str = Field(default="FR")

    # Trakt
    trakt_client_id: str = Field(default="")
    trakt_client_secret: str = Field(default="")
    trakt_access_token: Optional[str] = Field(default=None)
    trakt_refresh_token: Optional[str] = Field(default=None)

    # MDBList
    mdblist_api_key: Optional[str] = Field(default=None)

    # Radarr
    radarr_url: str = Field(default="http://localhost:7878")
    radarr_api_key: str = Field(default="")
    radarr_root_folder: str = Field(default="/movies")
    radarr_quality_profile: str = Field(default="HD-1080p")
    radarr_default_tag: str = Field(default="jfc")

    # Sonarr
    sonarr_url: str = Field(default="http://localhost:8989")
    sonarr_api_key: str = Field(default="")
    sonarr_root_folder: str = Field(default="/tv")
    sonarr_quality_profile: str = Field(default="HD-1080p")
    sonarr_default_tag: str = Field(default="jfc")

    # Discord
    discord_webhook_url: Optional[str] = Field(default=None)
    discord_webhook_error: Optional[str] = Field(default=None)
    discord_webhook_run_start: Optional[str] = Field(default=None)
    discord_webhook_run_end: Optional[str] = Field(default=None)
    discord_webhook_changes: Optional[str] = Field(default=None)

    # Scheduler
    scheduler_cron: str = Field(default="0 3 * * *")
    scheduler_timezone: str = Field(default="Europe/Paris")

    # Application settings
    log_level: str = Field(default="INFO")
    config_path: Path = Field(default=Path("/config"))
    posters_path: Optional[Path] = Field(default=None)  # Default: config_path/posters
    database_url: str = Field(default="sqlite+aiosqlite:///data/jfc.db")
    dry_run: bool = Field(default=False)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("config_path", mode="before")
    @classmethod
    def validate_config_path(cls, v: str | Path) -> Path:
        return Path(v) if isinstance(v, str) else v

    @field_validator("posters_path", mode="before")
    @classmethod
    def validate_posters_path(cls, v: str | Path | None) -> Path | None:
        if v is None:
            return None
        return Path(v) if isinstance(v, str) else v

    def get_posters_path(self) -> Path:
        """Get effective posters path (default: config_path/posters)."""
        if self.posters_path:
            return self.posters_path
        return self.config_path / "posters"

    @property
    def jellyfin(self) -> JellyfinSettings:
        """Get Jellyfin settings."""
        return JellyfinSettings(
            url=self.jellyfin_url,
            api_key=self.jellyfin_api_key,
        )

    @property
    def tmdb(self) -> TMDbSettings:
        """Get TMDb settings."""
        return TMDbSettings(
            api_key=self.tmdb_api_key,
            language=self.tmdb_language,
            region=self.tmdb_region,
        )

    @property
    def trakt(self) -> TraktSettings:
        """Get Trakt settings."""
        return TraktSettings(
            client_id=self.trakt_client_id,
            client_secret=self.trakt_client_secret,
            access_token=self.trakt_access_token,
            refresh_token=self.trakt_refresh_token,
        )

    @property
    def mdblist(self) -> MDBListSettings:
        """Get MDBList settings."""
        return MDBListSettings(api_key=self.mdblist_api_key)

    @property
    def radarr(self) -> RadarrSettings:
        """Get Radarr settings."""
        return RadarrSettings(
            url=self.radarr_url,
            api_key=self.radarr_api_key,
            root_folder=self.radarr_root_folder,
            quality_profile=self.radarr_quality_profile,
            default_tag=self.radarr_default_tag,
        )

    @property
    def sonarr(self) -> SonarrSettings:
        """Get Sonarr settings."""
        return SonarrSettings(
            url=self.sonarr_url,
            api_key=self.sonarr_api_key,
            root_folder=self.sonarr_root_folder,
            quality_profile=self.sonarr_quality_profile,
            default_tag=self.sonarr_default_tag,
        )

    @property
    def discord(self) -> DiscordSettings:
        """Get Discord settings."""
        return DiscordSettings(
            webhook_url=self.discord_webhook_url,
            webhook_error=self.discord_webhook_error,
            webhook_run_start=self.discord_webhook_run_start,
            webhook_run_end=self.discord_webhook_run_end,
            webhook_changes=self.discord_webhook_changes,
        )

    @property
    def scheduler(self) -> SchedulerSettings:
        """Get Scheduler settings."""
        return SchedulerSettings(
            cron=self.scheduler_cron,
            timezone=self.scheduler_timezone,
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
