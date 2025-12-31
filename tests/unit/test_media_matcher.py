"""Unit tests for MediaMatcher service."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from jfc.models.media import LibraryItem, MediaItem, MediaType
from jfc.services.media_matcher import MediaMatcher


@pytest.fixture
def mock_jellyfin():
    """Create a mock Jellyfin client."""
    client = MagicMock()
    client.get_library_items = AsyncMock(return_value=[])
    client.search_items = AsyncMock(return_value=[])
    return client


@pytest.fixture
def matcher(mock_jellyfin):
    """Create a MediaMatcher with mock client."""
    return MediaMatcher(mock_jellyfin)


@pytest.fixture
def sample_library_items():
    """Create sample library items."""
    return [
        LibraryItem(
            jellyfin_id="jf-001",
            title="Dune: Part Two",
            year=2024,
            media_type=MediaType.MOVIE,
            tmdb_id=693134,
            library_id="lib-001",
            library_name="Films",
        ),
        LibraryItem(
            jellyfin_id="jf-002",
            title="Oppenheimer",
            year=2023,
            media_type=MediaType.MOVIE,
            tmdb_id=872585,
            library_id="lib-001",
            library_name="Films",
        ),
        LibraryItem(
            jellyfin_id="jf-003",
            title="The Batman",
            year=2022,
            media_type=MediaType.MOVIE,
            tmdb_id=414906,
            library_id="lib-001",
            library_name="Films",
        ),
    ]


class TestMediaMatcher:
    """Tests for MediaMatcher."""

    def test_init(self, mock_jellyfin):
        """Test matcher initialization."""
        matcher = MediaMatcher(mock_jellyfin)
        assert matcher.jellyfin == mock_jellyfin
        assert matcher._cache == {}
        assert matcher._library_loaded == {}

    @pytest.mark.asyncio
    async def test_find_in_library_by_tmdb_id(
        self, matcher, mock_jellyfin, sample_library_items
    ):
        """Test finding item by TMDb ID."""
        mock_jellyfin.get_library_items.return_value = sample_library_items

        item = MediaItem(
            title="Dune: Part Two",
            year=2024,
            media_type=MediaType.MOVIE,
            tmdb_id=693134,
        )

        result = await matcher.find_in_library(item, library_id="lib-001")

        assert result is not None
        assert result.jellyfin_id == "jf-001"
        assert result.tmdb_id == 693134

    @pytest.mark.asyncio
    async def test_find_in_library_not_found(
        self, matcher, mock_jellyfin, sample_library_items
    ):
        """Test item not found in library."""
        mock_jellyfin.get_library_items.return_value = sample_library_items

        item = MediaItem(
            title="Unknown Movie",
            year=2024,
            media_type=MediaType.MOVIE,
            tmdb_id=999999,
        )

        result = await matcher.find_in_library(item, library_id="lib-001")

        assert result is None

    @pytest.mark.asyncio
    async def test_find_in_library_cache_hit(
        self, matcher, mock_jellyfin, sample_library_items
    ):
        """Test cache hit on second lookup."""
        mock_jellyfin.get_library_items.return_value = sample_library_items

        item = MediaItem(
            title="Dune: Part Two",
            year=2024,
            media_type=MediaType.MOVIE,
            tmdb_id=693134,
        )

        # First lookup
        result1 = await matcher.find_in_library(item, library_id="lib-001")
        # Second lookup should use cache
        result2 = await matcher.find_in_library(item, library_id="lib-001")

        assert result1 == result2
        # Library should only be loaded once
        assert mock_jellyfin.get_library_items.call_count == 1

    @pytest.mark.asyncio
    async def test_find_in_library_by_title_fallback(self, matcher, mock_jellyfin):
        """Test fallback to title search when no TMDb ID."""
        search_result = LibraryItem(
            jellyfin_id="jf-100",
            title="Old Movie",
            year=2020,
            media_type=MediaType.MOVIE,
            library_id="lib-001",
            library_name="Films",
        )
        mock_jellyfin.search_items.return_value = [search_result]

        item = MediaItem(
            title="Old Movie",
            year=2020,
            media_type=MediaType.MOVIE,
            # No tmdb_id
        )

        result = await matcher.find_in_library(item, library_id="lib-001")

        assert result is not None
        assert result.jellyfin_id == "jf-100"
        mock_jellyfin.search_items.assert_called_once()

    @pytest.mark.asyncio
    async def test_batch_find(self, matcher, mock_jellyfin, sample_library_items):
        """Test batch finding multiple items."""
        mock_jellyfin.get_library_items.return_value = sample_library_items

        items = [
            MediaItem(
                title="Dune: Part Two",
                year=2024,
                media_type=MediaType.MOVIE,
                tmdb_id=693134,
            ),
            MediaItem(
                title="Oppenheimer",
                year=2023,
                media_type=MediaType.MOVIE,
                tmdb_id=872585,
            ),
            MediaItem(
                title="Unknown",
                year=2024,
                media_type=MediaType.MOVIE,
                tmdb_id=999999,
            ),
        ]

        results = await matcher.batch_find(items, library_id="lib-001")

        assert results[693134] is not None
        assert results[872585] is not None
        assert results[999999] is None

    def test_clear_cache(self, matcher):
        """Test cache clearing."""
        matcher._cache[123] = "test"
        matcher.clear_cache()
        assert matcher._cache == {}


class TestIsMatch:
    """Tests for _is_match method."""

    def test_match_by_tmdb_id(self, matcher):
        """Test matching by TMDb ID."""
        item = MediaItem(
            title="Movie",
            media_type=MediaType.MOVIE,
            tmdb_id=123,
        )
        lib_item = LibraryItem(
            jellyfin_id="jf-1",
            title="Different Title",
            media_type=MediaType.MOVIE,
            tmdb_id=123,
            library_id="lib-1",
            library_name="Films",
        )

        assert matcher._is_match(item, lib_item) is True

    def test_match_by_imdb_id(self, matcher):
        """Test matching by IMDb ID."""
        item = MediaItem(
            title="Movie",
            media_type=MediaType.MOVIE,
            imdb_id="tt1234567",
        )
        lib_item = LibraryItem(
            jellyfin_id="jf-1",
            title="Different Title",
            media_type=MediaType.MOVIE,
            imdb_id="tt1234567",
            library_id="lib-1",
            library_name="Films",
        )

        assert matcher._is_match(item, lib_item) is True

    def test_match_by_tvdb_id(self, matcher):
        """Test matching by TVDB ID for series."""
        item = MediaItem(
            title="Series",
            media_type=MediaType.SERIES,
            tvdb_id=12345,
        )
        lib_item = LibraryItem(
            jellyfin_id="jf-1",
            title="Different Title",
            media_type=MediaType.SERIES,
            tvdb_id=12345,
            library_id="lib-1",
            library_name="Series",
        )

        assert matcher._is_match(item, lib_item) is True

    def test_match_by_title_and_year(self, matcher):
        """Test matching by title and year."""
        item = MediaItem(
            title="The Movie",
            year=2023,
            media_type=MediaType.MOVIE,
        )
        lib_item = LibraryItem(
            jellyfin_id="jf-1",
            title="The Movie",
            year=2023,
            media_type=MediaType.MOVIE,
            library_id="lib-1",
            library_name="Films",
        )

        assert matcher._is_match(item, lib_item) is True

    def test_match_year_tolerance(self, matcher):
        """Test year matching with 1 year tolerance."""
        item = MediaItem(
            title="Movie",
            year=2023,
            media_type=MediaType.MOVIE,
        )
        lib_item = LibraryItem(
            jellyfin_id="jf-1",
            title="Movie",
            year=2024,  # 1 year difference
            media_type=MediaType.MOVIE,
            library_id="lib-1",
            library_name="Films",
        )

        assert matcher._is_match(item, lib_item) is True

    def test_no_match_year_too_different(self, matcher):
        """Test no match when year difference > 1."""
        item = MediaItem(
            title="Movie",
            year=2020,
            media_type=MediaType.MOVIE,
        )
        lib_item = LibraryItem(
            jellyfin_id="jf-1",
            title="Movie",
            year=2023,  # 3 year difference
            media_type=MediaType.MOVIE,
            library_id="lib-1",
            library_name="Films",
        )

        assert matcher._is_match(item, lib_item) is False

    def test_no_match_different_title(self, matcher):
        """Test no match when titles are different."""
        item = MediaItem(
            title="Movie A",
            year=2023,
            media_type=MediaType.MOVIE,
        )
        lib_item = LibraryItem(
            jellyfin_id="jf-1",
            title="Movie B",
            year=2023,
            media_type=MediaType.MOVIE,
            library_id="lib-1",
            library_name="Films",
        )

        assert matcher._is_match(item, lib_item) is False


class TestNormalizeTitle:
    """Tests for _normalize_title method."""

    def test_lowercase(self, matcher):
        """Test title is lowercased."""
        assert matcher._normalize_title("THE MOVIE") == "movie"

    def test_remove_articles_english(self, matcher):
        """Test removing English articles."""
        assert matcher._normalize_title("The Movie") == "movie"
        assert matcher._normalize_title("A Movie") == "movie"
        assert matcher._normalize_title("An Apple") == "apple"

    def test_remove_articles_french(self, matcher):
        """Test removing French articles."""
        assert matcher._normalize_title("Le Film") == "film"
        assert matcher._normalize_title("La Vie") == "vie"
        assert matcher._normalize_title("Les Misérables") == "misérables"
        assert matcher._normalize_title("Un Film") == "film"
        assert matcher._normalize_title("Une Histoire") == "histoire"

    def test_remove_special_characters(self, matcher):
        """Test removing special characters."""
        assert matcher._normalize_title("Movie: Part 2") == "movie part 2"
        # Note: "The" in the middle is NOT removed, only at the start
        assert matcher._normalize_title("Movie - The Sequel") == "movie the sequel"

    def test_normalize_whitespace(self, matcher):
        """Test normalizing whitespace."""
        assert matcher._normalize_title("Movie   Title") == "movie title"
        assert matcher._normalize_title("  Spaced  Out  ") == "spaced out"

    def test_keep_alphanumeric(self, matcher):
        """Test keeping alphanumeric characters."""
        assert matcher._normalize_title("Movie 2") == "movie 2"
        assert matcher._normalize_title("Movie123") == "movie123"
