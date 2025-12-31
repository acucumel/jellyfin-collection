"""Shared pytest fixtures and configuration."""

import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# Set test environment
os.environ.setdefault("JELLYFIN_URL", "http://localhost:8096")
os.environ.setdefault("JELLYFIN_API_KEY", "test-api-key")
os.environ.setdefault("TMDB_API_KEY", "test-tmdb-key")


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    """Create a temporary config directory."""
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    return config_dir


@pytest.fixture
def sample_config_yml(temp_config_dir: Path) -> Path:
    """Create a sample config.yml file."""
    config_content = """
libraries:
  Films:
    collection_files:
      - file: Films.yml
    radarr:
      root_folder_path: /movies
      tag: jfc-films
  Séries:
    collection_files:
      - file: Series.yml
    sonarr:
      root_folder_path: /tv
      tag: jfc-series
"""
    config_file = temp_config_dir / "config.yml"
    config_file.write_text(config_content, encoding="utf-8")
    return config_file


@pytest.fixture
def sample_films_yml(temp_config_dir: Path) -> Path:
    """Create a sample Films.yml collection file."""
    content = """
templates:
  film_template:
    sync_mode: sync
    schedule: daily
    filters:
      year.gte: 2015

collections:
  "Trending Movies":
    template: {name: film_template}
    tmdb_trending_weekly: 20
    summary: "Top trending movies this week"

  "Popular Action":
    template: {name: film_template}
    tmdb_discover:
      sort_by: popularity.desc
      with_genres: 28
      limit: 30
    collection_order: release

  "Netflix Originals":
    sync_mode: sync
    schedule: weekly(sunday)
    tmdb_discover:
      with_watch_providers: 8
      watch_region: FR
      limit: 50
    filters:
      vote_average.gte: 6.0
"""
    films_file = temp_config_dir / "Films.yml"
    films_file.write_text(content, encoding="utf-8")
    return films_file


@pytest.fixture
def sample_series_yml(temp_config_dir: Path) -> Path:
    """Create a sample Series.yml collection file."""
    content = """
templates:
  series_template:
    sync_mode: sync
    schedule: daily

collections:
  "Trending Series":
    template: {name: series_template}
    tmdb_trending_weekly: 20

  "Anime Exclus":
    sync_mode: sync
    schedule: daily
    tmdb_discover:
      with_genres: 16
      limit: 30
    filters:
      original_language.not: ja
"""
    series_file = temp_config_dir / "Series.yml"
    series_file.write_text(content, encoding="utf-8")
    return series_file


@pytest.fixture
def mock_jellyfin_client() -> MagicMock:
    """Create a mock Jellyfin client."""
    client = MagicMock()
    client.get_libraries = AsyncMock(return_value=[
        {"Name": "Films", "ItemId": "lib-films-123"},
        {"Name": "Séries", "ItemId": "lib-series-456"},
    ])
    client.get_library_items = AsyncMock(return_value=[])
    client.search_items = AsyncMock(return_value=[])
    client.close = AsyncMock()
    return client


@pytest.fixture
def mock_tmdb_client() -> MagicMock:
    """Create a mock TMDb client."""
    client = MagicMock()
    client.get_trending_movies = AsyncMock(return_value=[])
    client.get_trending_series = AsyncMock(return_value=[])
    client.discover_movies = AsyncMock(return_value=[])
    client.discover_series = AsyncMock(return_value=[])
    client.close = AsyncMock()
    return client


@pytest.fixture
def sample_media_items() -> list[dict[str, Any]]:
    """Sample media items for testing."""
    return [
        {
            "title": "Dune: Part Two",
            "year": 2024,
            "tmdb_id": 693134,
            "imdb_id": "tt15239678",
            "overview": "Follow the mythic journey of Paul Atreides...",
            "genres": [878, 12],
        },
        {
            "title": "Oppenheimer",
            "year": 2023,
            "tmdb_id": 872585,
            "imdb_id": "tt15398776",
            "overview": "The story of American scientist J. Robert Oppenheimer...",
            "genres": [18, 36],
        },
        {
            "title": "The Batman",
            "year": 2022,
            "tmdb_id": 414906,
            "imdb_id": "tt1877830",
            "overview": "When a sadistic serial killer begins murdering...",
            "genres": [80, 9648, 53],
        },
    ]


@pytest.fixture
def sample_library_items() -> list[dict[str, Any]]:
    """Sample library items for testing."""
    return [
        {
            "jellyfin_id": "jf-001",
            "title": "Dune: Part Two",
            "year": 2024,
            "tmdb_id": 693134,
            "library_id": "lib-films-123",
            "library_name": "Films",
        },
        {
            "jellyfin_id": "jf-002",
            "title": "Oppenheimer",
            "year": 2023,
            "tmdb_id": 872585,
            "library_id": "lib-films-123",
            "library_name": "Films",
        },
    ]
