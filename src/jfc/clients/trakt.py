"""Trakt API client."""

from typing import Any, Optional

from loguru import logger

from jfc.clients.base import BaseClient
from jfc.models.media import MediaItem, MediaType, Movie, Series


class TraktClient(BaseClient):
    """Client for Trakt API v2."""

    BASE_URL = "https://api.trakt.tv"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        access_token: Optional[str] = None,
    ):
        """
        Initialize Trakt client.

        Args:
            client_id: Trakt application client ID
            client_secret: Trakt application client secret
            access_token: OAuth access token (for authenticated requests)
        """
        headers = {
            "trakt-api-key": client_id,
            "trakt-api-version": "2",
        }

        if access_token:
            headers["Authorization"] = f"Bearer {access_token}"

        super().__init__(base_url=self.BASE_URL, headers=headers)

        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token

    def _log_items(
        self,
        source: str,
        items: list[MediaItem],
        params: Optional[dict[str, Any]] = None,
    ) -> None:
        """Log fetched items with their IDs and titles."""
        if params:
            logger.info(f"[Trakt] {source}: params={params}")

        logger.info(f"[Trakt] {source}: fetched {len(items)} items")
        for item in items:
            year_str = f" ({item.year})" if item.year else ""
            tmdb_str = f"tmdb:{item.tmdb_id}" if item.tmdb_id else ""
            imdb_str = f"imdb:{item.imdb_id}" if item.imdb_id else ""
            ids = ", ".join(filter(None, [tmdb_str, imdb_str]))
            logger.debug(f"  - [{ids}] {item.title}{year_str}")

    # =========================================================================
    # Charts
    # =========================================================================

    async def get_trending_movies(self, limit: int = 20) -> list[Movie]:
        """Get trending movies."""
        params = {"limit": limit, "extended": "full"}
        response = await self.get("/movies/trending", params=params)
        response.raise_for_status()

        movies = [
            self._parse_movie(item["movie"])
            for item in response.json()
        ]
        self._log_items("Trending Movies", movies, params)
        return movies

    async def get_trending_series(self, limit: int = 20) -> list[Series]:
        """Get trending TV series."""
        params = {"limit": limit, "extended": "full"}
        response = await self.get("/shows/trending", params=params)
        response.raise_for_status()

        series = [
            self._parse_series(item["show"])
            for item in response.json()
        ]
        self._log_items("Trending Series", series, params)
        return series

    async def get_popular_movies(self, limit: int = 20) -> list[Movie]:
        """Get popular movies."""
        params = {"limit": limit, "extended": "full"}
        response = await self.get("/movies/popular", params=params)
        response.raise_for_status()

        movies = [self._parse_movie(item) for item in response.json()]
        self._log_items("Popular Movies", movies, params)
        return movies

    async def get_popular_series(self, limit: int = 20) -> list[Series]:
        """Get popular TV series."""
        params = {"limit": limit, "extended": "full"}
        response = await self.get("/shows/popular", params=params)
        response.raise_for_status()

        series = [self._parse_series(item) for item in response.json()]
        self._log_items("Popular Series", series, params)
        return series

    async def get_watched_movies(
        self,
        period: str = "weekly",
        limit: int = 20,
    ) -> list[Movie]:
        """
        Get most watched movies.

        Args:
            period: Time period (daily, weekly, monthly, yearly, all)
            limit: Maximum results

        Returns:
            List of most watched movies
        """
        params = {"limit": limit, "extended": "full"}
        response = await self.get(f"/movies/watched/{period}", params=params)
        response.raise_for_status()

        movies = [
            self._parse_movie(item["movie"])
            for item in response.json()
        ]
        self._log_items(f"Watched Movies ({period})", movies, params)
        return movies

    async def get_watched_series(
        self,
        period: str = "weekly",
        limit: int = 20,
    ) -> list[Series]:
        """
        Get most watched TV series.

        Args:
            period: Time period (daily, weekly, monthly, yearly, all)
            limit: Maximum results

        Returns:
            List of most watched series
        """
        params = {"limit": limit, "extended": "full"}
        response = await self.get(f"/shows/watched/{period}", params=params)
        response.raise_for_status()

        series = [
            self._parse_series(item["show"])
            for item in response.json()
        ]
        self._log_items(f"Watched Series ({period})", series, params)
        return series

    # =========================================================================
    # Lists
    # =========================================================================

    async def get_list(
        self,
        user: str,
        list_id: str,
        media_type: Optional[MediaType] = None,
    ) -> list[MediaItem]:
        """
        Get items from a Trakt list.

        Args:
            user: Trakt username
            list_id: List slug
            media_type: Filter by type

        Returns:
            List of media items
        """
        response = await self.get(
            f"/users/{user}/lists/{list_id}/items",
            params={"extended": "full"},
        )
        response.raise_for_status()

        items = []
        for item in response.json():
            item_type = item.get("type")

            if item_type == "movie":
                if media_type is None or media_type == MediaType.MOVIE:
                    items.append(self._parse_movie(item["movie"]))
            elif item_type == "show":
                if media_type is None or media_type == MediaType.SERIES:
                    items.append(self._parse_series(item["show"]))

        return items

    # =========================================================================
    # Search
    # =========================================================================

    async def search(
        self,
        query: str,
        media_type: MediaType = MediaType.MOVIE,
        limit: int = 10,
    ) -> list[MediaItem]:
        """
        Search for movies or shows.

        Args:
            query: Search query
            media_type: Type to search for
            limit: Maximum results

        Returns:
            List of search results
        """
        type_str = "movie" if media_type == MediaType.MOVIE else "show"

        response = await self.get(
            f"/search/{type_str}",
            params={"query": query, "limit": limit, "extended": "full"},
        )
        response.raise_for_status()

        items = []
        for result in response.json():
            if type_str == "movie":
                items.append(self._parse_movie(result["movie"]))
            else:
                items.append(self._parse_series(result["show"]))

        return items

    # =========================================================================
    # Parsers
    # =========================================================================

    def _parse_movie(self, data: dict[str, Any]) -> Movie:
        """Parse movie from Trakt response."""
        ids = data.get("ids", {})

        return Movie(
            title=data.get("title", "Unknown"),
            year=data.get("year"),
            tmdb_id=ids.get("tmdb"),
            imdb_id=ids.get("imdb"),
            overview=data.get("overview"),
            genres=data.get("genres", []),
            vote_average=data.get("rating"),
            vote_count=data.get("votes"),
            runtime=data.get("runtime"),
            tagline=data.get("tagline"),
            status=data.get("status"),
        )

    def _parse_series(self, data: dict[str, Any]) -> Series:
        """Parse TV series from Trakt response."""
        ids = data.get("ids", {})

        return Series(
            title=data.get("title", "Unknown"),
            year=data.get("year"),
            tmdb_id=ids.get("tmdb"),
            imdb_id=ids.get("imdb"),
            tvdb_id=ids.get("tvdb"),
            overview=data.get("overview"),
            genres=data.get("genres", []),
            vote_average=data.get("rating"),
            vote_count=data.get("votes"),
            status=data.get("status"),
            networks=[data.get("network")] if data.get("network") else [],
        )
