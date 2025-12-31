"""Application configuration using Pydantic Settings.

Supports configuration from multiple sources with the following priority (highest first):
1. Environment variables
2. .env file
3. config.yml settings section
4. Default values

This allows portable configuration in config.yml while keeping secrets in .env.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic_settings.sources import PydanticBaseSettingsSource


# Load .env file at module import
load_dotenv()


class YamlSettingsSource(PydanticBaseSettingsSource):
    """
    Custom settings source that reads from config.yml settings section.

    Allows configuration to be defined in YAML while still supporting
    environment variable overrides.
    """

    def __init__(self, settings_cls: type[BaseSettings], yaml_file: Path):
        super().__init__(settings_cls)
        self.yaml_file = yaml_file
        self._yaml_data: dict[str, Any] = {}
        self._load_yaml()

    def _load_yaml(self) -> None:
        """Load and parse the YAML file."""
        if not self.yaml_file.exists():
            raise FileNotFoundError(
                f"Configuration file not found: {self.yaml_file}\n"
                f"Please create a config.yml file in your config directory.\n"
                f"See documentation: https://github.com/acucumel/jellyfin-collection#configuration"
            )

        try:
            with open(self.yaml_file, encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            settings_data = data.get("settings", {})
            self._yaml_data = self._flatten_settings(settings_data)
            print(f"[config] Loaded {len(self._yaml_data)} settings from: {self.yaml_file}")
        except FileNotFoundError:
            raise  # Re-raise FileNotFoundError as-is
        except Exception as e:
            raise RuntimeError(
                f"Failed to parse config.yml: {e}\n"
                f"Please check your YAML syntax."
            ) from e

    def _flatten_settings(self, data: dict, prefix: str = "") -> dict:
        """
        Flatten nested dict to match env var naming.

        Example: jellyfin.url -> jellyfin_url
        """
        result = {}
        for key, value in data.items():
            flat_key = f"{prefix}_{key}" if prefix else key
            if isinstance(value, dict):
                result.update(self._flatten_settings(value, flat_key))
            else:
                result[flat_key] = value
        return result

    def get_field_value(
        self, field: Any, field_name: str
    ) -> tuple[Any, str, bool]:
        """Get value for a specific field from YAML data."""
        value = self._yaml_data.get(field_name)
        return value, field_name, value is not None

    def __call__(self) -> dict[str, Any]:
        """Return all settings from YAML."""
        return self._yaml_data


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


class OpenAISettings(BaseModel):
    """OpenAI API configuration for poster generation."""

    api_key: Optional[str] = Field(default=None)
    enabled: bool = Field(default=False)
    explicit_refs: bool = Field(
        default=False,
        description="Include show titles in visual signatures for better context"
    )
    force_regenerate: bool = Field(
        default=False,
        description="Force poster regeneration on every run (useful for testing)"
    )
    missing_only: bool = Field(
        default=False,
        description="Only generate posters that don't exist yet (skip existing)"
    )
    poster_history_limit: int = Field(
        default=5,
        description="Number of old posters to keep (0=unlimited)"
    )
    prompt_history_limit: int = Field(
        default=10,
        description="Number of prompt JSON files to keep (0=unlimited)"
    )
    poster_logo_text: str = Field(
        default="NETFLEX",
        description="Logo text displayed at bottom of generated posters"
    )


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

    # Collections sync schedule (default: daily at 3am)
    collections_cron: str = Field(default="0 3 * * *")
    # Poster regeneration schedule (default: 1st of month at 4am, empty = disabled)
    posters_cron: str = Field(default="0 4 1 * *")
    # Run collections sync immediately on startup
    run_on_start: bool = Field(default=True)
    # Timezone for cron expressions
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

    # OpenAI (poster generation)
    openai_api_key: Optional[str] = Field(default=None)
    openai_enabled: bool = Field(default=False)
    openai_explicit_refs: bool = Field(default=False)
    openai_force_regenerate: bool = Field(default=False)
    openai_missing_only: bool = Field(default=False)
    openai_poster_history_limit: int = Field(default=5)
    openai_prompt_history_limit: int = Field(default=10)
    openai_poster_logo_text: str = Field(default="NETFLEX")

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
    scheduler_collections_cron: str = Field(default="0 3 * * *")
    scheduler_posters_cron: str = Field(default="0 4 1 * *")
    scheduler_run_on_start: bool = Field(default=True)
    scheduler_timezone: str = Field(default="Europe/Paris")

    # Application settings
    log_level: str = Field(default="INFO")
    config_path: Path = Field(default=Path("/config"))
    data_path: Path = Field(default=Path("/data"))
    log_path: Path = Field(default=Path("/logs"))
    dry_run: bool = Field(default=False)

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        """
        Customize settings sources to include config.yml.

        Priority (highest first):
        1. init_settings - direct arguments to Settings()
        2. env_settings - environment variables
        3. dotenv_settings - .env file
        4. yaml_settings - config.yml settings section
        5. file_secret_settings - secret files
        """
        # Determine config.yml path from env var (before other sources load)
        # Default to /config for Docker compatibility (workdir is /app)
        config_path = Path(os.getenv("CONFIG_PATH", "/config"))
        yaml_file = config_path / "config.yml"

        return (
            init_settings,
            env_settings,
            dotenv_settings,
            YamlSettingsSource(settings_cls, yaml_file),
            file_secret_settings,
        )

    @field_validator("config_path", mode="before")
    @classmethod
    def validate_config_path(cls, v: str | Path) -> Path:
        return Path(v) if isinstance(v, str) else v

    @field_validator("data_path", mode="before")
    @classmethod
    def validate_data_path(cls, v: str | Path) -> Path:
        return Path(v) if isinstance(v, str) else v

    @field_validator("log_path", mode="before")
    @classmethod
    def validate_log_path(cls, v: str | Path) -> Path:
        return Path(v) if isinstance(v, str) else v

    def get_data_path(self) -> Path:
        """Get data directory path."""
        return self.data_path

    def get_posters_path(self) -> Path:
        """Get posters directory (under data)."""
        return self.get_data_path() / "posters"

    def get_cache_path(self) -> Path:
        """Get cache directory (under data)."""
        return self.get_data_path() / "cache"

    def get_reports_path(self) -> Path:
        """Get reports directory (under data)."""
        return self.get_data_path() / "reports"

    def get_log_path(self) -> Path:
        """Get logs directory path."""
        return self.log_path

    def get_templates_path(self) -> Path:
        """Get templates directory (under config)."""
        return self.config_path / "templates"

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
    def openai(self) -> OpenAISettings:
        """Get OpenAI settings."""
        return OpenAISettings(
            api_key=self.openai_api_key,
            enabled=self.openai_enabled,
            explicit_refs=self.openai_explicit_refs,
            force_regenerate=self.openai_force_regenerate,
            missing_only=self.openai_missing_only,
            poster_history_limit=self.openai_poster_history_limit,
            prompt_history_limit=self.openai_prompt_history_limit,
            poster_logo_text=self.openai_poster_logo_text,
        )

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
            collections_cron=self.scheduler_collections_cron,
            posters_cron=self.scheduler_posters_cron,
            run_on_start=self.scheduler_run_on_start,
            timezone=self.scheduler_timezone,
        )


def _mask_secret(value: str | None, visible_chars: int = 4) -> str:
    """Mask a secret value, showing only first N characters."""
    if not value:
        return "(not set)"
    if len(value) <= visible_chars:
        return "*" * len(value)
    return value[:visible_chars] + "*" * (len(value) - visible_chars)


def log_settings(settings: "Settings") -> None:
    """Log all settings to the logger (secrets are masked)."""
    from loguru import logger

    logger.info("=" * 60)
    logger.info("JELLYFIN COLLECTION - CONFIGURATION")
    logger.info("=" * 60)

    # Paths
    logger.info("[Paths]")
    logger.info(f"  Config path: {settings.config_path}")
    logger.info(f"  Data path:   {settings.data_path}")
    logger.info(f"  Log path:    {settings.log_path}")

    # Jellyfin
    logger.info("[Jellyfin]")
    logger.info(f"  URL:     {settings.jellyfin_url}")
    logger.info(f"  API Key: {_mask_secret(settings.jellyfin_api_key)}")

    # TMDb
    logger.info("[TMDb]")
    logger.info(f"  API Key:  {_mask_secret(settings.tmdb_api_key)}")
    logger.info(f"  Language: {settings.tmdb_language}")
    logger.info(f"  Region:   {settings.tmdb_region}")

    # Trakt
    logger.info("[Trakt]")
    logger.info(f"  Client ID:     {_mask_secret(settings.trakt_client_id)}")
    logger.info(f"  Client Secret: {_mask_secret(settings.trakt_client_secret)}")

    # OpenAI
    logger.info("[OpenAI]")
    logger.info(f"  Enabled:        {settings.openai_enabled}")
    logger.info(f"  API Key:        {_mask_secret(settings.openai_api_key)}")
    logger.info(f"  Explicit Refs:  {settings.openai_explicit_refs}")
    logger.info(f"  Force Regen:    {settings.openai_force_regenerate}")
    logger.info(f"  Missing Only:   {settings.openai_missing_only}")
    logger.info(f"  Logo Text:      {settings.openai_poster_logo_text}")

    # Radarr
    logger.info("[Radarr]")
    logger.info(f"  URL:             {settings.radarr_url}")
    logger.info(f"  API Key:         {_mask_secret(settings.radarr_api_key)}")
    logger.info(f"  Root Folder:     {settings.radarr_root_folder}")
    logger.info(f"  Quality Profile: {settings.radarr_quality_profile}")
    logger.info(f"  Default Tag:     {settings.radarr_default_tag}")

    # Sonarr
    logger.info("[Sonarr]")
    logger.info(f"  URL:             {settings.sonarr_url}")
    logger.info(f"  API Key:         {_mask_secret(settings.sonarr_api_key)}")
    logger.info(f"  Root Folder:     {settings.sonarr_root_folder}")
    logger.info(f"  Quality Profile: {settings.sonarr_quality_profile}")
    logger.info(f"  Default Tag:     {settings.sonarr_default_tag}")

    # Discord
    logger.info("[Discord]")
    logger.info(f"  Webhook URL: {_mask_secret(settings.discord_webhook_url, 30) if settings.discord_webhook_url else '(not set)'}")

    # Scheduler
    logger.info("[Scheduler]")
    logger.info(f"  Collections Cron: {settings.scheduler_collections_cron}")
    logger.info(f"  Posters Cron:     {settings.scheduler_posters_cron or '(disabled)'}")
    logger.info(f"  Run on Start:     {settings.scheduler_run_on_start}")
    logger.info(f"  Timezone:         {settings.scheduler_timezone}")

    # Application
    logger.info("[Application]")
    logger.info(f"  Log Level: {settings.log_level}")
    logger.info(f"  Dry Run:   {settings.dry_run}")

    logger.info("=" * 60)


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings."""
    return Settings()
