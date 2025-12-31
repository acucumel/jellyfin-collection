"""Unit tests for Kometa YAML parser."""

from pathlib import Path

import pytest

from jfc.models.collection import (
    CollectionOrder,
    ScheduleType,
    SyncMode,
)
from jfc.parsers.kometa import KometaParser


class TestKometaParser:
    """Tests for KometaParser."""

    def test_init(self, temp_config_dir: Path):
        """Test parser initialization."""
        parser = KometaParser(temp_config_dir)
        assert parser.config_path == temp_config_dir

    def test_parse_config_missing_file(self, temp_config_dir: Path):
        """Test parsing missing config file returns empty dict."""
        parser = KometaParser(temp_config_dir)
        result = parser.parse_config()
        assert result == {}

    def test_parse_config(self, temp_config_dir: Path, sample_config_yml: Path):
        """Test parsing main config.yml."""
        parser = KometaParser(temp_config_dir)
        config = parser.parse_config()

        assert "libraries" in config
        assert "Films" in config["libraries"]
        assert "Séries" in config["libraries"]

    def test_parse_library_config(self, temp_config_dir: Path, sample_config_yml: Path):
        """Test parsing library configuration."""
        parser = KometaParser(temp_config_dir)
        config = parser.parse_config()

        lib_config = parser.parse_library_config(config["libraries"]["Films"])

        assert "collection_files" in lib_config
        assert "Films.yml" in lib_config["collection_files"]
        assert lib_config["radarr"]["root_folder_path"] == "/movies"
        assert lib_config["radarr"]["tag"] == "jfc-films"

    def test_parse_collection_file_missing(self, temp_config_dir: Path):
        """Test parsing missing collection file returns empty list."""
        parser = KometaParser(temp_config_dir)
        result = parser.parse_collection_file(temp_config_dir / "missing.yml")
        assert result == []

    def test_parse_collection_file(self, temp_config_dir: Path, sample_films_yml: Path):
        """Test parsing collection file."""
        parser = KometaParser(temp_config_dir)
        collections = parser.parse_collection_file(sample_films_yml)

        assert len(collections) == 3

        # Check Trending Movies collection
        trending = next(c for c in collections if c.name == "Trending Movies")
        assert trending.tmdb_trending_weekly == 20
        assert trending.summary == "Top trending movies this week"
        assert trending.schedule.schedule_type == ScheduleType.DAILY
        assert trending.filters.year_gte == 2015  # From template

    def test_parse_collection_with_tmdb_discover(
        self, temp_config_dir: Path, sample_films_yml: Path
    ):
        """Test parsing collection with tmdb_discover."""
        parser = KometaParser(temp_config_dir)
        collections = parser.parse_collection_file(sample_films_yml)

        action = next(c for c in collections if c.name == "Popular Action")
        assert action.tmdb_discover is not None
        assert action.tmdb_discover["sort_by"] == "popularity.desc"
        assert 28 in action.tmdb_discover["with_genres"]
        assert action.limit == 30

    def test_parse_collection_order(self, temp_config_dir: Path, sample_films_yml: Path):
        """Test parsing collection_order."""
        parser = KometaParser(temp_config_dir)
        collections = parser.parse_collection_file(sample_films_yml)

        action = next(c for c in collections if c.name == "Popular Action")
        assert action.collection_order == CollectionOrder.PREMIERE_DATE

    def test_parse_collection_with_schedule(
        self, temp_config_dir: Path, sample_films_yml: Path
    ):
        """Test parsing collection with weekly schedule."""
        parser = KometaParser(temp_config_dir)
        collections = parser.parse_collection_file(sample_films_yml)

        netflix = next(c for c in collections if c.name == "Netflix Originals")
        assert netflix.schedule.schedule_type == ScheduleType.WEEKLY
        assert netflix.schedule.day_of_week == "sunday"

    def test_parse_collection_with_filters(
        self, temp_config_dir: Path, sample_films_yml: Path
    ):
        """Test parsing collection with filters."""
        parser = KometaParser(temp_config_dir)
        collections = parser.parse_collection_file(sample_films_yml)

        netflix = next(c for c in collections if c.name == "Netflix Originals")
        assert netflix.filters.vote_average_gte == 6.0

    def test_parse_templates(self, temp_config_dir: Path, sample_films_yml: Path):
        """Test that templates are applied to collections."""
        parser = KometaParser(temp_config_dir)
        collections = parser.parse_collection_file(sample_films_yml)

        trending = next(c for c in collections if c.name == "Trending Movies")
        # Template sets sync_mode to sync and schedule to daily
        assert trending.sync_mode == SyncMode.SYNC
        assert trending.schedule.schedule_type == ScheduleType.DAILY

    def test_get_all_collections(
        self,
        temp_config_dir: Path,
        sample_config_yml: Path,
        sample_films_yml: Path,
        sample_series_yml: Path,
    ):
        """Test getting all collections from config."""
        parser = KometaParser(temp_config_dir)
        all_collections = parser.get_all_collections()

        assert "Films" in all_collections
        assert "Séries" in all_collections
        assert len(all_collections["Films"]) == 3
        assert len(all_collections["Séries"]) == 2

    def test_library_radarr_config_applied(
        self,
        temp_config_dir: Path,
        sample_config_yml: Path,
        sample_films_yml: Path,
    ):
        """Test that library-level Radarr config is applied to collections."""
        parser = KometaParser(temp_config_dir)
        all_collections = parser.get_all_collections()

        # All Films collections should have the radarr config from library
        for collection in all_collections["Films"]:
            assert collection.radarr_root_folder == "/movies"
            assert collection.radarr_tag == "jfc-films"

    def test_library_sonarr_config_applied(
        self,
        temp_config_dir: Path,
        sample_config_yml: Path,
        sample_series_yml: Path,
    ):
        """Test that library-level Sonarr config is applied to collections."""
        parser = KometaParser(temp_config_dir)
        all_collections = parser.get_all_collections()

        # All Séries collections should have the sonarr config from library
        for collection in all_collections["Séries"]:
            assert collection.sonarr_root_folder == "/tv"
            assert collection.sonarr_tag == "jfc-series"


class TestParseCollectionOrder:
    """Tests for _parse_collection_order method."""

    def test_custom(self, temp_config_dir: Path):
        """Test parsing 'custom' order."""
        parser = KometaParser(temp_config_dir)
        assert parser._parse_collection_order("custom") == CollectionOrder.CUSTOM
        assert parser._parse_collection_order(None) == CollectionOrder.CUSTOM

    def test_alphabetical_variants(self, temp_config_dir: Path):
        """Test parsing alphabetical order variants."""
        parser = KometaParser(temp_config_dir)
        assert parser._parse_collection_order("alpha") == CollectionOrder.SORT_NAME
        assert parser._parse_collection_order("alphabetical") == CollectionOrder.SORT_NAME
        assert parser._parse_collection_order("name") == CollectionOrder.SORT_NAME

    def test_release_date_variants(self, temp_config_dir: Path):
        """Test parsing release date order variants."""
        parser = KometaParser(temp_config_dir)
        assert parser._parse_collection_order("release") == CollectionOrder.PREMIERE_DATE
        assert parser._parse_collection_order("date") == CollectionOrder.PREMIERE_DATE
        assert parser._parse_collection_order("premieredate") == CollectionOrder.PREMIERE_DATE

    def test_rating_variants(self, temp_config_dir: Path):
        """Test parsing rating order variants."""
        parser = KometaParser(temp_config_dir)
        assert parser._parse_collection_order("rating") == CollectionOrder.COMMUNITY_RATING
        assert parser._parse_collection_order("audience_rating") == CollectionOrder.COMMUNITY_RATING

    def test_random(self, temp_config_dir: Path):
        """Test parsing random order."""
        parser = KometaParser(temp_config_dir)
        assert parser._parse_collection_order("random") == CollectionOrder.RANDOM

    def test_unknown_defaults_to_custom(self, temp_config_dir: Path):
        """Test unknown order defaults to custom."""
        parser = KometaParser(temp_config_dir)
        assert parser._parse_collection_order("unknown") == CollectionOrder.CUSTOM

    def test_case_insensitive(self, temp_config_dir: Path):
        """Test parsing is case insensitive."""
        parser = KometaParser(temp_config_dir)
        assert parser._parse_collection_order("ALPHA") == CollectionOrder.SORT_NAME
        assert parser._parse_collection_order("Release") == CollectionOrder.PREMIERE_DATE


class TestParseFilters:
    """Tests for _parse_filters method."""

    def test_empty_filters(self, temp_config_dir: Path):
        """Test parsing empty filters."""
        parser = KometaParser(temp_config_dir)
        filters = parser._parse_filters({})
        assert filters.year_gte is None
        assert filters.with_genres == []

    def test_year_filters(self, temp_config_dir: Path):
        """Test parsing year filters."""
        parser = KometaParser(temp_config_dir)
        filters = parser._parse_filters({
            "year.gte": 2020,
            "year.lte": 2024,
        })
        assert filters.year_gte == 2020
        assert filters.year_lte == 2024

    def test_vote_filters(self, temp_config_dir: Path):
        """Test parsing vote filters."""
        parser = KometaParser(temp_config_dir)
        filters = parser._parse_filters({
            "vote_average.gte": 7.0,
            "tmdb_vote_count.gte": 1000,
        })
        assert filters.vote_average_gte == 7.0
        assert filters.tmdb_vote_count_gte == 1000

    def test_language_filter_string(self, temp_config_dir: Path):
        """Test parsing language filter as string."""
        parser = KometaParser(temp_config_dir)
        filters = parser._parse_filters({
            "original_language.not": "ja",
        })
        assert filters.original_language_not == ["ja"]

    def test_language_filter_list(self, temp_config_dir: Path):
        """Test parsing language filter as list."""
        parser = KometaParser(temp_config_dir)
        filters = parser._parse_filters({
            "original_language.not": ["ja", "ko"],
        })
        assert filters.original_language_not == ["ja", "ko"]

    def test_genre_filters(self, temp_config_dir: Path):
        """Test parsing genre filters."""
        parser = KometaParser(temp_config_dir)
        filters = parser._parse_filters({
            "with_genres": [28, 12],
            "without_genres": 16,
        })
        assert filters.with_genres == [28, 12]
        assert filters.without_genres == [16]

    def test_genre_filters_string(self, temp_config_dir: Path):
        """Test parsing genre filters as comma-separated string."""
        parser = KometaParser(temp_config_dir)
        filters = parser._parse_filters({
            "with_genres": "28,12",
        })
        assert filters.with_genres == [28, 12]

    def test_base_filter_inheritance(self, temp_config_dir: Path):
        """Test that base filter values are inherited."""
        from jfc.models.collection import CollectionFilter

        parser = KometaParser(temp_config_dir)
        base = CollectionFilter(year_gte=2015, vote_average_gte=6.0)

        filters = parser._parse_filters({"year.lte": 2024}, base=base)

        # Should inherit from base
        assert filters.year_gte == 2015
        assert filters.vote_average_gte == 6.0
        # Should add new filter
        assert filters.year_lte == 2024


class TestNormalizeTmdbDiscover:
    """Tests for _normalize_tmdb_discover method."""

    def test_direct_fields(self, temp_config_dir: Path):
        """Test direct field mappings."""
        parser = KometaParser(temp_config_dir)
        result = parser._normalize_tmdb_discover({
            "sort_by": "popularity.desc",
            "vote_average.gte": 7.0,
            "limit": 50,
        })
        assert result["sort_by"] == "popularity.desc"
        assert result["vote_average.gte"] == 7.0
        assert result["limit"] == 50

    def test_genres_list(self, temp_config_dir: Path):
        """Test genres as list."""
        parser = KometaParser(temp_config_dir)
        result = parser._normalize_tmdb_discover({
            "with_genres": [28, 12],
        })
        assert result["with_genres"] == [28, 12]

    def test_genres_string(self, temp_config_dir: Path):
        """Test genres as comma-separated string."""
        parser = KometaParser(temp_config_dir)
        result = parser._normalize_tmdb_discover({
            "with_genres": "28,12",
        })
        assert result["with_genres"] == [28, 12]

    def test_genres_single_int(self, temp_config_dir: Path):
        """Test single genre as int."""
        parser = KometaParser(temp_config_dir)
        result = parser._normalize_tmdb_discover({
            "with_genres": 28,
        })
        assert result["with_genres"] == [28]

    def test_watch_providers_pipe_separated(self, temp_config_dir: Path):
        """Test watch providers as pipe-separated string."""
        parser = KometaParser(temp_config_dir)
        result = parser._normalize_tmdb_discover({
            "with_watch_providers": "8|337|350",
        })
        assert result["with_watch_providers"] == [8, 337, 350]

    def test_date_fields(self, temp_config_dir: Path):
        """Test date field parsing."""
        from datetime import date

        parser = KometaParser(temp_config_dir)
        result = parser._normalize_tmdb_discover({
            "primary_release_date.gte": "2024-01-01",
            "primary_release_date.lte": date(2024, 12, 31),
        })
        assert result["primary_release_date.gte"] == date(2024, 1, 1)
        assert result["primary_release_date.lte"] == date(2024, 12, 31)
