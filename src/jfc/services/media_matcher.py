"""Service for matching media items between providers and Jellyfin library."""

from typing import Optional

from loguru import logger

from jfc.clients.jellyfin import JellyfinClient
from jfc.models.media import LibraryItem, MediaItem, MediaType


class MediaMatcher:
    """Service for matching media items to Jellyfin library."""

    def __init__(self, jellyfin: JellyfinClient):
        """
        Initialize media matcher.

        Args:
            jellyfin: Jellyfin API client
        """
        self.jellyfin = jellyfin
        self._cache: dict[int, Optional[LibraryItem]] = {}  # tmdb_id -> LibraryItem
        self._library_loaded: dict[str, bool] = {}  # library_id -> loaded
        self._library_items: dict[str, dict[int, LibraryItem]] = {}  # library_id -> {tmdb_id -> item}

    async def _ensure_library_loaded(self, library_id: str, media_type: Optional[MediaType] = None) -> None:
        """Load all items from a library into cache."""
        if library_id in self._library_loaded:
            return

        logger.info(f"[Jellyfin] Loading library {library_id} into cache...")

        items = await self.jellyfin.get_library_items(
            library_id=library_id,
            media_type=media_type,
            limit=10000,
        )

        # Index by TMDb ID
        self._library_items[library_id] = {}
        for item in items:
            if item.tmdb_id:
                self._library_items[library_id][item.tmdb_id] = item

        self._library_loaded[library_id] = True
        logger.info(
            f"[Jellyfin] Loaded {len(items)} items from library, "
            f"{len(self._library_items[library_id])} with TMDb IDs"
        )

    async def find_in_library(
        self,
        item: MediaItem,
        library_id: Optional[str] = None,
    ) -> Optional[LibraryItem]:
        """
        Find a media item in Jellyfin library.

        Args:
            item: Media item to find
            library_id: Optional library ID to search in

        Returns:
            LibraryItem if found, None otherwise
        """
        year_str = f" ({item.year})" if item.year else ""
        tmdb_str = f"tmdb:{item.tmdb_id}" if item.tmdb_id else "no-tmdb"

        # Ensure library is loaded into cache
        if library_id:
            await self._ensure_library_loaded(library_id, item.media_type)

        # Check global cache first (for cross-library lookups)
        if item.tmdb_id and item.tmdb_id in self._cache:
            cached = self._cache[item.tmdb_id]
            if cached:
                logger.debug(f"[Jellyfin] Cache hit: [{tmdb_str}] {item.title}{year_str} -> {cached.title}")
            return cached

        # Try to find by TMDb ID in library cache (most reliable and fast)
        if item.tmdb_id and library_id and library_id in self._library_items:
            lib_item = self._library_items[library_id].get(item.tmdb_id)
            if lib_item:
                self._cache[item.tmdb_id] = lib_item
                logger.debug(
                    f"[Jellyfin] FOUND: [{tmdb_str}] {item.title}{year_str} "
                    f"-> {lib_item.title} ({lib_item.year})"
                )
                return lib_item

        # Fall back to search by title and year (for items without TMDb ID)
        if not item.tmdb_id:
            logger.debug(f"[Jellyfin] Searching by title (no TMDb ID): '{item.title}'{year_str}")
            results = await self.jellyfin.search_items(
                query=item.title,
                media_type=item.media_type,
                limit=5,
            )

            # Find best match
            for lib_item in results:
                if self._is_match(item, lib_item):
                    logger.debug(
                        f"[Jellyfin] FOUND by title: {item.title}{year_str} "
                        f"-> {lib_item.title} ({lib_item.year})"
                    )
                    return lib_item

        # Not found
        if item.tmdb_id:
            self._cache[item.tmdb_id] = None

        logger.debug(f"[Jellyfin] NOT FOUND: [{tmdb_str}] {item.title}{year_str}")
        return None

    async def batch_find(
        self,
        items: list[MediaItem],
        library_id: Optional[str] = None,
    ) -> dict[int, Optional[LibraryItem]]:
        """
        Find multiple items in library.

        Args:
            items: List of media items to find
            library_id: Optional library ID to search in

        Returns:
            Dictionary mapping TMDb IDs to LibraryItems (or None if not found)
        """
        results = {}

        for item in items:
            if not item.tmdb_id:
                continue

            lib_item = await self.find_in_library(item, library_id)
            results[item.tmdb_id] = lib_item

        found = sum(1 for v in results.values() if v is not None)
        logger.info(f"Matched {found}/{len(items)} items in library")

        return results

    def _is_match(self, item: MediaItem, lib_item: LibraryItem) -> bool:
        """
        Check if library item matches the media item.

        Args:
            item: Source media item
            lib_item: Library item to check

        Returns:
            True if items match
        """
        # Check TMDb ID first (exact match)
        if item.tmdb_id and lib_item.tmdb_id:
            return item.tmdb_id == lib_item.tmdb_id

        # Check IMDB ID
        if item.imdb_id and lib_item.imdb_id:
            return item.imdb_id == lib_item.imdb_id

        # Check TVDB ID (for series)
        if item.tvdb_id and lib_item.tvdb_id:
            return item.tvdb_id == lib_item.tvdb_id

        # Fall back to title + year comparison
        title_match = self._normalize_title(item.title) == self._normalize_title(lib_item.title)

        if not title_match:
            return False

        # If titles match, check year (allow 1 year difference for release date variations)
        if item.year and lib_item.year:
            return abs(item.year - lib_item.year) <= 1

        # Title matches, no year to compare
        return True

    def _normalize_title(self, title: str) -> str:
        """Normalize title for comparison."""
        # Lowercase
        title = title.lower()

        # Remove common articles
        for article in ["the ", "a ", "an ", "le ", "la ", "les ", "un ", "une "]:
            if title.startswith(article):
                title = title[len(article) :]

        # Remove special characters
        title = "".join(c for c in title if c.isalnum() or c.isspace())

        # Normalize whitespace
        title = " ".join(title.split())

        return title

    def clear_cache(self) -> None:
        """Clear the match cache."""
        self._cache.clear()
        logger.debug("Media matcher cache cleared")
