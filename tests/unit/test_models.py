"""Unit tests for data models."""

from datetime import date

import pytest

from jfc.models.collection import (
    Collection,
    CollectionConfig,
    CollectionFilter,
    CollectionItem,
    CollectionOrder,
    CollectionSchedule,
    ScheduleType,
    SyncMode,
)
from jfc.models.media import (
    LibraryItem,
    MediaItem,
    MediaType,
    Movie,
    ProviderMatch,
    Series,
)


class TestMediaType:
    """Tests for MediaType enum."""

    def test_media_type_values(self):
        """Test enum values."""
        assert MediaType.MOVIE.value == "movie"
        assert MediaType.SERIES.value == "series"
        assert MediaType.EPISODE.value == "episode"
        assert MediaType.SEASON.value == "season"


class TestMediaItem:
    """Tests for MediaItem model."""

    def test_create_minimal(self):
        """Test creating MediaItem with minimal fields."""
        item = MediaItem(title="Test Movie", media_type=MediaType.MOVIE)
        assert item.title == "Test Movie"
        assert item.media_type == MediaType.MOVIE
        assert item.year is None
        assert item.tmdb_id is None

    def test_create_full(self):
        """Test creating MediaItem with all fields."""
        item = MediaItem(
            title="Dune: Part Two",
            year=2024,
            media_type=MediaType.MOVIE,
            tmdb_id=693134,
            imdb_id="tt15239678",
            overview="Epic sci-fi movie",
            genres=[878, 12],
            vote_average=8.5,
        )
        assert item.title == "Dune: Part Two"
        assert item.year == 2024
        assert item.tmdb_id == 693134
        assert item.imdb_id == "tt15239678"
        assert 878 in item.genres

    def test_display_title_with_year(self):
        """Test display_title property with year."""
        item = MediaItem(title="Dune", year=2021, media_type=MediaType.MOVIE)
        assert item.display_title == "Dune (2021)"

    def test_display_title_without_year(self):
        """Test display_title property without year."""
        item = MediaItem(title="Dune", media_type=MediaType.MOVIE)
        assert item.display_title == "Dune"


class TestMovie:
    """Tests for Movie model."""

    def test_movie_has_correct_media_type(self):
        """Test that Movie defaults to MOVIE media type."""
        movie = Movie(title="Test")
        assert movie.media_type == MediaType.MOVIE

    def test_movie_specific_fields(self):
        """Test movie-specific fields."""
        movie = Movie(
            title="Oppenheimer",
            year=2023,
            runtime=180,
            budget=100000000,
            tagline="The world forever changes.",
        )
        assert movie.runtime == 180
        assert movie.budget == 100000000
        assert movie.tagline == "The world forever changes."


class TestSeries:
    """Tests for Series model."""

    def test_series_has_correct_media_type(self):
        """Test that Series defaults to SERIES media type."""
        series = Series(title="Test")
        assert series.media_type == MediaType.SERIES

    def test_series_specific_fields(self):
        """Test series-specific fields."""
        series = Series(
            title="Breaking Bad",
            year=2008,
            number_of_seasons=5,
            number_of_episodes=62,
            in_production=False,
            networks=["AMC"],
        )
        assert series.number_of_seasons == 5
        assert series.number_of_episodes == 62
        assert series.in_production is False
        assert "AMC" in series.networks


class TestProviderMatch:
    """Tests for ProviderMatch model."""

    def test_exact_match(self):
        """Test is_exact_match property."""
        item = MediaItem(title="Test", media_type=MediaType.MOVIE)
        match = ProviderMatch(item=item, confidence=0.95, source="tmdb")
        assert match.is_exact_match is True

    def test_not_exact_match(self):
        """Test is_exact_match returns False for low confidence."""
        item = MediaItem(title="Test", media_type=MediaType.MOVIE)
        match = ProviderMatch(item=item, confidence=0.8, source="tmdb")
        assert match.is_exact_match is False

    def test_confidence_bounds(self):
        """Test confidence must be between 0 and 1."""
        item = MediaItem(title="Test", media_type=MediaType.MOVIE)

        with pytest.raises(ValueError):
            ProviderMatch(item=item, confidence=1.5, source="tmdb")

        with pytest.raises(ValueError):
            ProviderMatch(item=item, confidence=-0.1, source="tmdb")


class TestLibraryItem:
    """Tests for LibraryItem model."""

    def test_create_library_item(self):
        """Test creating a LibraryItem."""
        item = LibraryItem(
            jellyfin_id="jf-123",
            title="Dune",
            year=2021,
            media_type=MediaType.MOVIE,
            tmdb_id=438631,
            library_id="lib-001",
            library_name="Films",
        )
        assert item.jellyfin_id == "jf-123"
        assert item.library_name == "Films"

    def test_to_media_item(self):
        """Test conversion to MediaItem."""
        lib_item = LibraryItem(
            jellyfin_id="jf-123",
            title="Dune",
            year=2021,
            media_type=MediaType.MOVIE,
            tmdb_id=438631,
            library_id="lib-001",
            library_name="Films",
        )
        media_item = lib_item.to_media_item()

        assert isinstance(media_item, MediaItem)
        assert media_item.title == "Dune"
        assert media_item.year == 2021
        assert media_item.tmdb_id == 438631
        assert media_item.jellyfin_id == "jf-123"


class TestCollectionSchedule:
    """Tests for CollectionSchedule model."""

    def test_from_kometa_daily(self):
        """Test parsing daily schedule."""
        schedule = CollectionSchedule.from_kometa("daily")
        assert schedule.schedule_type == ScheduleType.DAILY

    def test_from_kometa_weekly(self):
        """Test parsing weekly schedule."""
        schedule = CollectionSchedule.from_kometa("weekly(sunday)")
        assert schedule.schedule_type == ScheduleType.WEEKLY
        assert schedule.day_of_week == "sunday"

    def test_from_kometa_weekly_default(self):
        """Test parsing weekly schedule without day defaults to sunday."""
        schedule = CollectionSchedule.from_kometa("weekly")
        assert schedule.schedule_type == ScheduleType.WEEKLY
        assert schedule.day_of_week == "sunday"

    def test_from_kometa_monthly(self):
        """Test parsing monthly schedule."""
        schedule = CollectionSchedule.from_kometa("monthly(15)")
        assert schedule.schedule_type == ScheduleType.MONTHLY
        assert schedule.day_of_month == 15

    def test_from_kometa_monthly_default(self):
        """Test parsing monthly schedule without day defaults to 1."""
        schedule = CollectionSchedule.from_kometa("monthly")
        assert schedule.schedule_type == ScheduleType.MONTHLY
        assert schedule.day_of_month == 1

    def test_from_kometa_none(self):
        """Test parsing None returns NEVER."""
        schedule = CollectionSchedule.from_kometa(None)
        assert schedule.schedule_type == ScheduleType.NEVER

    def test_from_kometa_invalid(self):
        """Test parsing invalid string returns NEVER."""
        schedule = CollectionSchedule.from_kometa("invalid")
        assert schedule.schedule_type == ScheduleType.NEVER


class TestCollectionFilter:
    """Tests for CollectionFilter model."""

    def test_default_filter(self):
        """Test default filter has no constraints."""
        filter = CollectionFilter()
        assert filter.year_gte is None
        assert filter.year_lte is None
        assert filter.with_genres == []
        assert filter.without_genres == []

    def test_filter_with_values(self):
        """Test filter with values."""
        filter = CollectionFilter(
            year_gte=2020,
            year_lte=2024,
            vote_average_gte=7.0,
            with_genres=[28, 12],
            original_language_not=["ja"],
        )
        assert filter.year_gte == 2020
        assert filter.year_lte == 2024
        assert filter.vote_average_gte == 7.0
        assert 28 in filter.with_genres
        assert "ja" in filter.original_language_not


class TestCollectionOrder:
    """Tests for CollectionOrder enum."""

    def test_collection_order_values(self):
        """Test enum values."""
        assert CollectionOrder.CUSTOM.value == "custom"
        assert CollectionOrder.SORT_NAME.value == "SortName"
        assert CollectionOrder.PREMIERE_DATE.value == "PremiereDate"
        assert CollectionOrder.COMMUNITY_RATING.value == "CommunityRating"


class TestCollectionConfig:
    """Tests for CollectionConfig model."""

    def test_minimal_config(self):
        """Test creating minimal config."""
        config = CollectionConfig(name="Test Collection")
        assert config.name == "Test Collection"
        assert config.sync_mode == SyncMode.SYNC
        assert config.collection_order == CollectionOrder.CUSTOM

    def test_full_config(self):
        """Test creating full config."""
        config = CollectionConfig(
            name="Trending Movies",
            summary="Top trending movies",
            sync_mode=SyncMode.SYNC,
            visible_library=True,
            visible_home=True,
            tmdb_trending_weekly=20,
            collection_order=CollectionOrder.PREMIERE_DATE,
            filters=CollectionFilter(year_gte=2020),
        )
        assert config.name == "Trending Movies"
        assert config.tmdb_trending_weekly == 20
        assert config.visible_home is True
        assert config.filters.year_gte == 2020


class TestCollectionItem:
    """Tests for CollectionItem model."""

    def test_create_collection_item(self):
        """Test creating a collection item."""
        item = CollectionItem(
            title="Dune: Part Two",
            year=2024,
            tmdb_id=693134,
            matched=True,
            in_library=True,
        )
        assert item.title == "Dune: Part Two"
        assert item.matched is True
        assert item.in_library is True


class TestCollection:
    """Tests for Collection model."""

    def test_create_collection(self):
        """Test creating a collection."""
        config = CollectionConfig(name="Test")
        collection = Collection(
            config=config,
            library_name="Films",
            items=[
                CollectionItem(title="Movie 1", matched=True),
                CollectionItem(title="Movie 2", matched=True),
                CollectionItem(title="Movie 3", matched=False),
            ],
        )
        assert collection.library_name == "Films"
        assert len(collection.items) == 3

    def test_update_stats(self):
        """Test update_stats method."""
        config = CollectionConfig(name="Test")
        collection = Collection(
            config=config,
            library_name="Films",
            items=[
                CollectionItem(title="Movie 1", matched=True),
                CollectionItem(title="Movie 2", matched=True),
                CollectionItem(title="Movie 3", matched=False),
            ],
        )
        collection.update_stats()

        assert collection.total_items == 3
        assert collection.matched_items == 2
        assert collection.missing_items == 1
