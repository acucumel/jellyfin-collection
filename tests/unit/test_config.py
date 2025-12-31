"""Unit tests for configuration settings."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from jfc.core.config import (
    DiscordSettings,
    JellyfinSettings,
    OpenAISettings,
    RadarrSettings,
    SchedulerSettings,
    Settings,
    SonarrSettings,
    TMDbSettings,
    TraktSettings,
)


class TestJellyfinSettings:
    """Tests for JellyfinSettings."""

    def test_default_values(self):
        """Test default values."""
        settings = JellyfinSettings()
        assert settings.url == "http://localhost:8096"
        assert settings.api_key == ""

    def test_custom_values(self):
        """Test custom values."""
        settings = JellyfinSettings(
            url="http://jellyfin:8096",
            api_key="my-api-key",
        )
        assert settings.url == "http://jellyfin:8096"
        assert settings.api_key == "my-api-key"


class TestTMDbSettings:
    """Tests for TMDbSettings."""

    def test_default_values(self):
        """Test default values."""
        settings = TMDbSettings()
        assert settings.api_key == ""
        assert settings.language == "fr"
        assert settings.region == "FR"

    def test_custom_values(self):
        """Test custom values."""
        settings = TMDbSettings(
            api_key="tmdb-key",
            language="en",
            region="US",
        )
        assert settings.api_key == "tmdb-key"
        assert settings.language == "en"
        assert settings.region == "US"


class TestTraktSettings:
    """Tests for TraktSettings."""

    def test_default_values(self):
        """Test default values."""
        settings = TraktSettings()
        assert settings.client_id == ""
        assert settings.client_secret == ""
        assert settings.access_token is None

    def test_with_tokens(self):
        """Test with OAuth tokens."""
        settings = TraktSettings(
            client_id="client-id",
            client_secret="client-secret",
            access_token="access-token",
            refresh_token="refresh-token",
        )
        assert settings.access_token == "access-token"
        assert settings.refresh_token == "refresh-token"


class TestOpenAISettings:
    """Tests for OpenAISettings."""

    def test_default_values(self):
        """Test default values."""
        settings = OpenAISettings()
        assert settings.api_key is None
        assert settings.enabled is False
        assert settings.explicit_refs is False
        assert settings.poster_history_limit == 5
        assert settings.prompt_history_limit == 10
        assert settings.poster_logo_text == "NETFLEX"

    def test_custom_values(self):
        """Test custom values."""
        settings = OpenAISettings(
            api_key="sk-xxx",
            enabled=True,
            explicit_refs=True,
            poster_history_limit=10,
            poster_logo_text="MYLOGO",
        )
        assert settings.api_key == "sk-xxx"
        assert settings.enabled is True
        assert settings.poster_logo_text == "MYLOGO"


class TestRadarrSettings:
    """Tests for RadarrSettings."""

    def test_default_values(self):
        """Test default values."""
        settings = RadarrSettings()
        assert settings.url == "http://localhost:7878"
        assert settings.api_key == ""
        assert settings.root_folder == "/movies"
        assert settings.quality_profile == "HD-1080p"
        assert settings.default_tag == "jfc"
        assert settings.add_missing is True


class TestSonarrSettings:
    """Tests for SonarrSettings."""

    def test_default_values(self):
        """Test default values."""
        settings = SonarrSettings()
        assert settings.url == "http://localhost:8989"
        assert settings.api_key == ""
        assert settings.root_folder == "/tv"
        assert settings.quality_profile == "HD-1080p"
        assert settings.default_tag == "jfc"


class TestDiscordSettings:
    """Tests for DiscordSettings."""

    def test_default_values(self):
        """Test default values."""
        settings = DiscordSettings()
        assert settings.webhook_url is None
        assert settings.webhook_error is None
        assert settings.webhook_changes is None

    def test_get_webhook_specific(self):
        """Test get_webhook returns specific webhook if set."""
        settings = DiscordSettings(
            webhook_url="https://discord.com/default",
            webhook_error="https://discord.com/error",
        )
        assert settings.get_webhook("error") == "https://discord.com/error"

    def test_get_webhook_fallback(self):
        """Test get_webhook falls back to default."""
        settings = DiscordSettings(
            webhook_url="https://discord.com/default",
        )
        assert settings.get_webhook("error") == "https://discord.com/default"

    def test_get_webhook_none(self):
        """Test get_webhook returns None if nothing set."""
        settings = DiscordSettings()
        assert settings.get_webhook("error") is None


class TestSchedulerSettings:
    """Tests for SchedulerSettings."""

    def test_default_values(self):
        """Test default values."""
        settings = SchedulerSettings()
        assert settings.collections_cron == "0 3 * * *"
        assert settings.posters_cron == "0 4 1 * *"
        assert settings.run_on_start is True
        assert settings.timezone == "Europe/Paris"


class TestSettings:
    """Tests for main Settings class."""

    def test_default_paths(self):
        """Test default path values when env vars are not set."""
        # Clear path-related env vars to test defaults
        env_override = {
            "CONFIG_PATH": "/config",
            "DATA_PATH": "/data",
            "LOG_PATH": "/logs",
        }
        with patch.dict(os.environ, env_override, clear=False):
            settings = Settings()
            assert settings.config_path == Path("/config")
            assert settings.data_path == Path("/data")
            assert settings.log_path == Path("/logs")

    def test_path_helpers(self):
        """Test path helper methods."""
        with patch.dict(os.environ, {"DATA_PATH": "/custom/data"}, clear=False):
            settings = Settings()
            settings.data_path = Path("/custom/data")

            assert settings.get_data_path() == Path("/custom/data")
            assert settings.get_posters_path() == Path("/custom/data/posters")
            assert settings.get_cache_path() == Path("/custom/data/cache")
            assert settings.get_reports_path() == Path("/custom/data/reports")

    def test_get_templates_path(self):
        """Test get_templates_path method."""
        with patch.dict(os.environ, {"CONFIG_PATH": "/myconfig"}, clear=False):
            settings = Settings()
            settings.config_path = Path("/myconfig")
            assert settings.get_templates_path() == Path("/myconfig/templates")

    def test_jellyfin_property(self):
        """Test jellyfin property returns JellyfinSettings."""
        with patch.dict(
            os.environ,
            {
                "JELLYFIN_URL": "http://test:8096",
                "JELLYFIN_API_KEY": "test-key",
            },
            clear=False,
        ):
            settings = Settings()
            jellyfin = settings.jellyfin

            assert isinstance(jellyfin, JellyfinSettings)
            assert jellyfin.url == "http://test:8096"
            assert jellyfin.api_key == "test-key"

    def test_tmdb_property(self):
        """Test tmdb property returns TMDbSettings."""
        with patch.dict(
            os.environ,
            {
                "TMDB_API_KEY": "tmdb-test-key",
                "TMDB_LANGUAGE": "en",
                "TMDB_REGION": "US",
            },
            clear=False,
        ):
            settings = Settings()
            tmdb = settings.tmdb

            assert isinstance(tmdb, TMDbSettings)
            assert tmdb.api_key == "tmdb-test-key"
            assert tmdb.language == "en"
            assert tmdb.region == "US"

    def test_openai_property(self):
        """Test openai property returns OpenAISettings."""
        with patch.dict(
            os.environ,
            {
                "OPENAI_API_KEY": "sk-test",
                "OPENAI_ENABLED": "true",
                "OPENAI_POSTER_LOGO_TEXT": "CUSTOM",
            },
            clear=False,
        ):
            settings = Settings()
            openai = settings.openai

            assert isinstance(openai, OpenAISettings)
            assert openai.api_key == "sk-test"
            assert openai.enabled is True
            assert openai.poster_logo_text == "CUSTOM"

    def test_scheduler_property(self):
        """Test scheduler property returns SchedulerSettings."""
        with patch.dict(
            os.environ,
            {
                "SCHEDULER_COLLECTIONS_CRON": "0 5 * * *",
                "SCHEDULER_RUN_ON_START": "false",
            },
            clear=False,
        ):
            settings = Settings()
            scheduler = settings.scheduler

            assert isinstance(scheduler, SchedulerSettings)
            assert scheduler.collections_cron == "0 5 * * *"
            assert scheduler.run_on_start is False

    def test_dry_run_default(self):
        """Test dry_run defaults to False."""
        with patch.dict(os.environ, {}, clear=False):
            settings = Settings()
            assert settings.dry_run is False

    def test_dry_run_enabled(self):
        """Test dry_run can be enabled via env."""
        with patch.dict(os.environ, {"DRY_RUN": "true"}, clear=False):
            settings = Settings()
            assert settings.dry_run is True
