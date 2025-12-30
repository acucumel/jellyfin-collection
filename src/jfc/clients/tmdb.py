"""TMDb (The Movie Database) API client."""

from datetime import date
from typing import Any, Optional

from loguru import logger

from jfc.clients.base import BaseClient
from jfc.models.media import MediaItem, MediaType, Movie, Series


class TMDbClient(BaseClient):
    """Client for TMDb API v3."""

    BASE_URL = "https://api.themoviedb.org/3"

    def __init__(self, api_key: str, language: str = "fr", region: str = "FR"):
        """
        Initialize TMDb client.

        Args:
            api_key: TMDb API key
            language: Language for results
            region: Region for watch providers
        """
        super().__init__(base_url=self.BASE_URL)
        self.api_key = api_key
        self.language = language
        self.region = region

    def _params(self, **kwargs) -> dict[str, Any]:
        """Build request params with API key and language."""
        params = {
            "api_key": self.api_key,
            "language": self.language,
        }
        params.update(kwargs)
        return params

    def _log_items(
        self,
        source: str,
        items: list[MediaItem],
        params: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log fetched items with their IDs and titles."""
        # Log the API call parameters (excluding api_key for security)
        if params:
            filtered_params = {k: v for k, v in params.items() if k != "api_key"}
            logger.info(f"[TMDb] {source}: params={filtered_params}")

        logger.info(f"[TMDb] {source}: fetched {len(items)} items")
        for item in items:
            year_str = f" ({item.year})" if item.year else ""
            logger.debug(f"  - [tmdb:{item.tmdb_id}] {item.title}{year_str}")

    # =========================================================================
    # Trending
    # =========================================================================

    async def get_trending_movies(
        self,
        time_window: str = "week",
        limit: int = 20,
    ) -> list[Movie]:
        """
        Get trending movies.

        Args:
            time_window: 'day' or 'week'
            limit: Maximum results

        Returns:
            List of trending movies
        """
        params = self._params()
        response = await self.get(
            f"/trending/movie/{time_window}",
            params=params,
        )
        response.raise_for_status()

        movies = []
        for item in response.json().get("results", [])[:limit]:
            movies.append(self._parse_movie(item))

        self._log_items(f"Trending Movies ({time_window})", movies, params)
        return movies

    async def get_trending_series(
        self,
        time_window: str = "week",
        limit: int = 20,
    ) -> list[Series]:
        """
        Get trending TV series.

        Args:
            time_window: 'day' or 'week'
            limit: Maximum results

        Returns:
            List of trending series
        """
        params = self._params()
        response = await self.get(
            f"/trending/tv/{time_window}",
            params=params,
        )
        response.raise_for_status()

        series = []
        for item in response.json().get("results", [])[:limit]:
            series.append(self._parse_series(item))

        self._log_items(f"Trending Series ({time_window})", series, params)
        return series

    # =========================================================================
    # Popular
    # =========================================================================

    async def get_popular_movies(self, limit: int = 20) -> list[Movie]:
        """Get popular movies."""
        params = self._params()
        response = await self.get("/movie/popular", params=params)
        response.raise_for_status()

        movies = [
            self._parse_movie(item)
            for item in response.json().get("results", [])[:limit]
        ]
        self._log_items("Popular Movies", movies, params)
        return movies

    async def get_popular_series(self, limit: int = 20) -> list[Series]:
        """Get popular TV series."""
        params = self._params()
        response = await self.get("/tv/popular", params=params)
        response.raise_for_status()

        series = [
            self._parse_series(item)
            for item in response.json().get("results", [])[:limit]
        ]
        self._log_items("Popular Series", series, params)
        return series

    # =========================================================================
    # Discover
    # =========================================================================

    async def discover_movies(
        self,
        sort_by: str = "popularity.desc",
        with_genres: Optional[list[int]] = None,
        without_genres: Optional[list[int]] = None,
        vote_average_gte: Optional[float] = None,
        vote_average_lte: Optional[float] = None,
        vote_count_gte: Optional[int] = None,
        vote_count_lte: Optional[int] = None,
        primary_release_date_gte: Optional[date] = None,
        primary_release_date_lte: Optional[date] = None,
        with_watch_providers: Optional[list[int]] = None,
        watch_region: Optional[str] = None,
        with_watch_monetization_types: str = "flatrate",
        with_original_language: Optional[str] = None,
        with_release_type: Optional[str] = None,
        region: Optional[str] = None,
        limit: int = 20,
    ) -> list[Movie]:
        """
        Discover movies with filters.

        Args:
            sort_by: Sort order
            with_genres: Include genres (comma-separated IDs)
            without_genres: Exclude genres
            vote_average_gte: Minimum vote average
            vote_average_lte: Maximum vote average
            vote_count_gte: Minimum vote count
            vote_count_lte: Maximum vote count
            primary_release_date_gte: Released after date
            primary_release_date_lte: Released before date
            with_watch_providers: Watch provider IDs (OR with |)
            watch_region: Region for watch providers
            with_watch_monetization_types: flatrate, rent, buy, free
            with_original_language: Original language code
            with_release_type: Release type filter
            region: Region for release dates
            limit: Maximum results

        Returns:
            List of discovered movies
        """
        params = self._params(sort_by=sort_by)

        if with_genres:
            params["with_genres"] = ",".join(map(str, with_genres))
        if without_genres:
            params["without_genres"] = ",".join(map(str, without_genres))
        if vote_average_gte is not None:
            params["vote_average.gte"] = vote_average_gte
        if vote_average_lte is not None:
            params["vote_average.lte"] = vote_average_lte
        if vote_count_gte is not None:
            params["vote_count.gte"] = vote_count_gte
        if vote_count_lte is not None:
            params["vote_count.lte"] = vote_count_lte
        if primary_release_date_gte:
            params["primary_release_date.gte"] = primary_release_date_gte.isoformat()
        if primary_release_date_lte:
            params["primary_release_date.lte"] = primary_release_date_lte.isoformat()
        if with_watch_providers:
            params["with_watch_providers"] = "|".join(map(str, with_watch_providers))
            params["watch_region"] = watch_region or self.region
            params["with_watch_monetization_types"] = with_watch_monetization_types
        if with_original_language:
            params["with_original_language"] = with_original_language
        if with_release_type:
            params["with_release_type"] = with_release_type
        if region:
            params["region"] = region

        response = await self.get("/discover/movie", params=params)
        response.raise_for_status()

        movies = [
            self._parse_movie(item)
            for item in response.json().get("results", [])[:limit]
        ]
        self._log_items("Discover Movies", movies, params)
        return movies

    async def discover_series(
        self,
        sort_by: str = "popularity.desc",
        with_genres: Optional[list[int]] = None,
        without_genres: Optional[list[int]] = None,
        vote_average_gte: Optional[float] = None,
        vote_count_gte: Optional[int] = None,
        vote_count_lte: Optional[int] = None,
        first_air_date_gte: Optional[date] = None,
        first_air_date_lte: Optional[date] = None,
        with_watch_providers: Optional[list[int]] = None,
        watch_region: Optional[str] = None,
        with_status: Optional[int] = None,
        limit: int = 20,
    ) -> list[Series]:
        """
        Discover TV series with filters.

        Args:
            sort_by: Sort order
            with_genres: Include genres
            without_genres: Exclude genres
            vote_average_gte: Minimum vote average
            vote_count_gte: Minimum vote count
            vote_count_lte: Maximum vote count
            first_air_date_gte: Aired after date
            first_air_date_lte: Aired before date
            with_watch_providers: Watch provider IDs
            watch_region: Region for watch providers
            with_status: Status filter (0=Returning, 3=Ended, etc.)
            limit: Maximum results

        Returns:
            List of discovered series
        """
        params = self._params(sort_by=sort_by)

        if with_genres:
            params["with_genres"] = ",".join(map(str, with_genres))
        if without_genres:
            params["without_genres"] = ",".join(map(str, without_genres))
        if vote_average_gte is not None:
            params["vote_average.gte"] = vote_average_gte
        if vote_count_gte is not None:
            params["vote_count.gte"] = vote_count_gte
        if vote_count_lte is not None:
            params["vote_count.lte"] = vote_count_lte
        if first_air_date_gte:
            params["first_air_date.gte"] = first_air_date_gte.isoformat()
        if first_air_date_lte:
            params["first_air_date.lte"] = first_air_date_lte.isoformat()
        if with_watch_providers:
            params["with_watch_providers"] = "|".join(map(str, with_watch_providers))
            params["watch_region"] = watch_region or self.region
            params["with_watch_monetization_types"] = "flatrate"
        if with_status is not None:
            params["with_status"] = with_status

        response = await self.get("/discover/tv", params=params)
        response.raise_for_status()

        series = [
            self._parse_series(item)
            for item in response.json().get("results", [])[:limit]
        ]
        self._log_items("Discover Series", series, params)
        return series

    # =========================================================================
    # Airing / Now Playing
    # =========================================================================

    async def get_airing_today(self, limit: int = 20) -> list[Series]:
        """Get series airing today."""
        response = await self.get("/tv/airing_today", params=self._params())
        response.raise_for_status()

        return [
            self._parse_series(item)
            for item in response.json().get("results", [])[:limit]
        ]

    async def get_on_the_air(self, limit: int = 20) -> list[Series]:
        """Get series currently on the air (next 7 days)."""
        response = await self.get("/tv/on_the_air", params=self._params())
        response.raise_for_status()

        return [
            self._parse_series(item)
            for item in response.json().get("results", [])[:limit]
        ]

    # =========================================================================
    # Details
    # =========================================================================

    async def get_movie_details(self, tmdb_id: int) -> Optional[Movie]:
        """Get movie details by TMDb ID."""
        response = await self.get(
            f"/movie/{tmdb_id}",
            params=self._params(append_to_response="external_ids"),
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return self._parse_movie_details(response.json())

    async def get_series_details(self, tmdb_id: int) -> Optional[Series]:
        """Get TV series details by TMDb ID."""
        response = await self.get(
            f"/tv/{tmdb_id}",
            params=self._params(append_to_response="external_ids"),
        )

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return self._parse_series_details(response.json())

    # =========================================================================
    # Search
    # =========================================================================

    async def search_movies(
        self,
        query: str,
        year: Optional[int] = None,
        limit: int = 10,
    ) -> list[Movie]:
        """Search for movies."""
        params = self._params(query=query)
        if year:
            params["year"] = year

        response = await self.get("/search/movie", params=params)
        response.raise_for_status()

        return [
            self._parse_movie(item)
            for item in response.json().get("results", [])[:limit]
        ]

    async def search_series(
        self,
        query: str,
        year: Optional[int] = None,
        limit: int = 10,
    ) -> list[Series]:
        """Search for TV series."""
        params = self._params(query=query)
        if year:
            params["first_air_date_year"] = year

        response = await self.get("/search/tv", params=params)
        response.raise_for_status()

        return [
            self._parse_series(item)
            for item in response.json().get("results", [])[:limit]
        ]

    # =========================================================================
    # Parsers
    # =========================================================================

    def _parse_movie(self, data: dict[str, Any]) -> Movie:
        """Parse movie from API response."""
        release_date = None
        year = None
        if data.get("release_date"):
            try:
                release_date = date.fromisoformat(data["release_date"])
                year = release_date.year
            except ValueError:
                pass

        # Get genre IDs (available in discover/list endpoints)
        genre_ids = data.get("genre_ids", [])

        return Movie(
            title=data.get("title", "Unknown"),
            year=year,
            tmdb_id=data.get("id"),
            overview=data.get("overview"),
            genres=genre_ids,  # Store genre IDs for filtering
            original_language=data.get("original_language"),
            vote_average=data.get("vote_average"),
            vote_count=data.get("vote_count"),
            popularity=data.get("popularity"),
            release_date=release_date,
            poster_path=data.get("poster_path"),
            backdrop_path=data.get("backdrop_path"),
        )

    def _parse_movie_details(self, data: dict[str, Any]) -> Movie:
        """Parse movie from details endpoint."""
        movie = self._parse_movie(data)

        # Add additional fields
        movie.genres = [g["name"] for g in data.get("genres", [])]
        movie.runtime = data.get("runtime")
        movie.budget = data.get("budget")
        movie.revenue = data.get("revenue")
        movie.tagline = data.get("tagline")
        movie.status = data.get("status")

        # External IDs
        external_ids = data.get("external_ids", {})
        movie.imdb_id = external_ids.get("imdb_id")

        # Collection
        if data.get("belongs_to_collection"):
            movie.belongs_to_collection = data["belongs_to_collection"].get("name")

        return movie

    def _parse_series(self, data: dict[str, Any]) -> Series:
        """Parse TV series from API response."""
        first_air_date = None
        year = None
        if data.get("first_air_date"):
            try:
                first_air_date = date.fromisoformat(data["first_air_date"])
                year = first_air_date.year
            except ValueError:
                pass

        # Get genre IDs (available in discover/list endpoints)
        genre_ids = data.get("genre_ids", [])

        return Series(
            title=data.get("name", "Unknown"),
            year=year,
            tmdb_id=data.get("id"),
            overview=data.get("overview"),
            genres=genre_ids,  # Store genre IDs for filtering
            original_language=data.get("original_language"),
            original_country=data.get("origin_country", [None])[0],
            vote_average=data.get("vote_average"),
            vote_count=data.get("vote_count"),
            popularity=data.get("popularity"),
            first_air_date=first_air_date,
            poster_path=data.get("poster_path"),
            backdrop_path=data.get("backdrop_path"),
        )

    def _parse_series_details(self, data: dict[str, Any]) -> Series:
        """Parse TV series from details endpoint."""
        series = self._parse_series(data)

        # Add additional fields
        series.genres = [g["name"] for g in data.get("genres", [])]
        series.number_of_seasons = data.get("number_of_seasons")
        series.number_of_episodes = data.get("number_of_episodes")
        series.episode_run_time = data.get("episode_run_time", [])
        series.in_production = data.get("in_production", False)
        series.status = data.get("status")
        series.networks = [n["name"] for n in data.get("networks", [])]

        # Last air date
        if data.get("last_air_date"):
            try:
                series.last_air_date = date.fromisoformat(data["last_air_date"])
            except ValueError:
                pass

        # External IDs
        external_ids = data.get("external_ids", {})
        series.imdb_id = external_ids.get("imdb_id")
        series.tvdb_id = external_ids.get("tvdb_id")

        return series
