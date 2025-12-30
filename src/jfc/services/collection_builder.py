"""Service for building collections from Kometa configurations."""

from datetime import date
from typing import Any, Optional

from loguru import logger

from jfc.clients.jellyfin import JellyfinClient
from jfc.clients.radarr import RadarrClient
from jfc.clients.sonarr import SonarrClient
from jfc.clients.tmdb import TMDbClient
from jfc.clients.trakt import TraktClient
from jfc.models.collection import Collection, CollectionConfig, CollectionItem
from jfc.models.media import MediaItem, MediaType, Movie, Series
from jfc.services.media_matcher import MediaMatcher


class CollectionBuilder:
    """Builds and updates collections in Jellyfin from Kometa configurations."""

    def __init__(
        self,
        jellyfin: JellyfinClient,
        tmdb: TMDbClient,
        trakt: Optional[TraktClient] = None,
        radarr: Optional[RadarrClient] = None,
        sonarr: Optional[SonarrClient] = None,
        dry_run: bool = False,
    ):
        """
        Initialize collection builder.

        Args:
            jellyfin: Jellyfin API client
            tmdb: TMDb API client
            trakt: Optional Trakt API client
            radarr: Optional Radarr client for adding missing movies
            sonarr: Optional Sonarr client for adding missing series
            dry_run: If True, don't make any changes
        """
        self.jellyfin = jellyfin
        self.tmdb = tmdb
        self.trakt = trakt
        self.radarr = radarr
        self.sonarr = sonarr
        self.dry_run = dry_run

        self.matcher = MediaMatcher(jellyfin)

    async def build_collection(
        self,
        config: CollectionConfig,
        library_name: str,
        library_id: str,
        media_type: MediaType,
    ) -> Collection:
        """
        Build a collection from configuration.

        Args:
            config: Collection configuration
            library_name: Name of the Jellyfin library
            library_id: Jellyfin library ID
            media_type: Type of media (movie/series)

        Returns:
            Built collection with items
        """
        logger.info(f"Building collection: {config.name}")

        # Fetch items from providers
        items = await self._fetch_items(config, media_type)

        # Apply filters
        items = self._apply_filters(items, config)

        # Match items to library
        collection_items = []
        for item in items:
            lib_item = await self.matcher.find_in_library(item, library_id)

            collection_item = CollectionItem(
                title=item.title,
                year=item.year,
                tmdb_id=item.tmdb_id,
                imdb_id=item.imdb_id,
                tvdb_id=item.tvdb_id,
                jellyfin_id=lib_item.jellyfin_id if lib_item else None,
                matched=lib_item is not None,
                in_library=lib_item is not None,
            )
            collection_items.append(collection_item)

        collection = Collection(
            config=config,
            library_name=library_name,
            items=collection_items,
        )
        collection.update_stats()

        logger.info(
            f"Collection '{config.name}': {collection.matched_items}/{collection.total_items} "
            f"items matched, {collection.missing_items} missing"
        )

        return collection

    async def sync_collection(
        self,
        collection: Collection,
        add_missing_to_arr: bool = True,
    ) -> tuple[int, int]:
        """
        Sync collection to Jellyfin.

        Args:
            collection: Collection to sync
            add_missing_to_arr: Whether to add missing items to Radarr/Sonarr

        Returns:
            Tuple of (items_added, items_removed)
        """
        if self.dry_run:
            logger.info(f"[DRY RUN] Would sync collection: {collection.config.name}")
            return (0, 0)

        # Get or create Jellyfin collection
        jellyfin_collections = await self.jellyfin.get_collections()
        existing = next(
            (c for c in jellyfin_collections if c["Name"] == collection.config.name),
            None,
        )

        if existing:
            collection.jellyfin_id = existing["Id"]
        else:
            collection.jellyfin_id = await self.jellyfin.create_collection(
                collection.config.name
            )

        # Get current items in collection
        current_ids = set(await self.jellyfin.get_collection_items(collection.jellyfin_id))

        # Get target items (only matched ones)
        target_ids = {
            item.jellyfin_id for item in collection.items if item.jellyfin_id
        }

        # Calculate changes
        to_add = target_ids - current_ids
        to_remove = current_ids - target_ids

        # Apply changes
        if to_add:
            await self.jellyfin.add_to_collection(collection.jellyfin_id, list(to_add))
            logger.info(f"Added {len(to_add)} items to '{collection.config.name}'")

        if to_remove:
            await self.jellyfin.remove_from_collection(collection.jellyfin_id, list(to_remove))
            logger.info(f"Removed {len(to_remove)} items from '{collection.config.name}'")

        # Update metadata
        await self.jellyfin.update_collection_metadata(
            collection.jellyfin_id,
            overview=collection.config.summary,
            sort_name=collection.config.sort_title,
        )

        # Add missing items to Radarr/Sonarr
        if add_missing_to_arr:
            await self._add_missing_to_arr(collection)

        return (len(to_add), len(to_remove))

    async def _fetch_items(
        self,
        config: CollectionConfig,
        media_type: MediaType,
    ) -> list[MediaItem]:
        """Fetch items from configured providers."""
        items: list[MediaItem] = []

        # TMDb Trending
        if config.tmdb_trending_weekly:
            if media_type == MediaType.MOVIE:
                items.extend(
                    await self.tmdb.get_trending_movies("week", config.tmdb_trending_weekly)
                )
            else:
                items.extend(
                    await self.tmdb.get_trending_series("week", config.tmdb_trending_weekly)
                )

        if config.tmdb_trending_daily:
            if media_type == MediaType.MOVIE:
                items.extend(
                    await self.tmdb.get_trending_movies("day", config.tmdb_trending_daily)
                )
            else:
                items.extend(
                    await self.tmdb.get_trending_series("day", config.tmdb_trending_daily)
                )

        # TMDb Popular
        if config.tmdb_popular:
            if media_type == MediaType.MOVIE:
                items.extend(await self.tmdb.get_popular_movies(config.tmdb_popular))
            else:
                items.extend(await self.tmdb.get_popular_series(config.tmdb_popular))

        # TMDb Discover
        if config.tmdb_discover:
            discover_items = await self._fetch_tmdb_discover(config.tmdb_discover, media_type)
            items.extend(discover_items)

        # Trakt
        if self.trakt:
            if config.trakt_trending:
                if media_type == MediaType.MOVIE:
                    items.extend(
                        await self.trakt.get_trending_movies(config.trakt_trending)
                    )
                else:
                    items.extend(
                        await self.trakt.get_trending_series(config.trakt_trending)
                    )

            if config.trakt_popular:
                if media_type == MediaType.MOVIE:
                    items.extend(
                        await self.trakt.get_popular_movies(config.trakt_popular)
                    )
                else:
                    items.extend(
                        await self.trakt.get_popular_series(config.trakt_popular)
                    )

            if config.trakt_chart:
                chart_items = await self._fetch_trakt_chart(config.trakt_chart, media_type)
                items.extend(chart_items)

        # Deduplicate by TMDb ID
        seen_ids: set[int] = set()
        unique_items: list[MediaItem] = []

        for item in items:
            if item.tmdb_id and item.tmdb_id not in seen_ids:
                seen_ids.add(item.tmdb_id)
                unique_items.append(item)

        return unique_items

    async def _fetch_tmdb_discover(
        self,
        discover: dict[str, Any],
        media_type: MediaType,
    ) -> list[MediaItem]:
        """Fetch items from TMDb discover endpoint."""
        limit = discover.get("limit", 20)

        if media_type == MediaType.MOVIE:
            return await self.tmdb.discover_movies(
                sort_by=discover.get("sort_by", "popularity.desc"),
                with_genres=discover.get("with_genres"),
                without_genres=discover.get("without_genres"),
                vote_average_gte=discover.get("vote_average.gte"),
                vote_average_lte=discover.get("vote_average.lte"),
                vote_count_gte=discover.get("vote_count.gte"),
                vote_count_lte=discover.get("vote_count.lte"),
                primary_release_date_gte=discover.get("primary_release_date.gte"),
                primary_release_date_lte=discover.get("primary_release_date.lte"),
                with_watch_providers=discover.get("with_watch_providers"),
                watch_region=discover.get("watch_region"),
                with_original_language=discover.get("with_original_language"),
                with_release_type=discover.get("with_release_type"),
                region=discover.get("region"),
                limit=limit,
            )
        else:
            return await self.tmdb.discover_series(
                sort_by=discover.get("sort_by", "popularity.desc"),
                with_genres=discover.get("with_genres"),
                without_genres=discover.get("without_genres"),
                vote_average_gte=discover.get("vote_average.gte"),
                vote_count_gte=discover.get("vote_count.gte"),
                vote_count_lte=discover.get("vote_count.lte"),
                first_air_date_gte=discover.get("first_air_date.gte"),
                first_air_date_lte=discover.get("first_air_date.lte"),
                with_watch_providers=discover.get("with_watch_providers"),
                watch_region=discover.get("watch_region"),
                with_status=discover.get("with_status"),
                limit=limit,
            )

    async def _fetch_trakt_chart(
        self,
        chart_config: dict[str, Any],
        media_type: MediaType,
    ) -> list[MediaItem]:
        """Fetch items from Trakt chart."""
        if not self.trakt:
            return []

        chart = chart_config.get("chart", "watched")
        period = chart_config.get("time_period", "weekly")
        limit = chart_config.get("limit", 20)

        if chart == "watched":
            if media_type == MediaType.MOVIE:
                return await self.trakt.get_watched_movies(period, limit)
            else:
                return await self.trakt.get_watched_series(period, limit)

        if chart == "trending":
            if media_type == MediaType.MOVIE:
                return await self.trakt.get_trending_movies(limit)
            else:
                return await self.trakt.get_trending_series(limit)

        if chart == "popular":
            if media_type == MediaType.MOVIE:
                return await self.trakt.get_popular_movies(limit)
            else:
                return await self.trakt.get_popular_series(limit)

        return []

    def _apply_filters(
        self,
        items: list[MediaItem],
        config: CollectionConfig,
    ) -> list[MediaItem]:
        """Apply collection filters to items."""
        filters = config.filters
        filtered = []

        for item in items:
            # Year filters
            if filters.year_gte and item.year and item.year < filters.year_gte:
                continue
            if filters.year_lte and item.year and item.year > filters.year_lte:
                continue

            # Rating filters
            if filters.vote_average_gte and item.vote_average:
                if item.vote_average < filters.vote_average_gte:
                    continue
            if filters.critic_rating_gte and item.vote_average:
                if item.vote_average < filters.critic_rating_gte:
                    continue

            # Vote count filters
            if filters.tmdb_vote_count_gte and item.vote_count:
                if item.vote_count < filters.tmdb_vote_count_gte:
                    continue

            # Country filters
            if filters.country_not and item.original_country:
                if item.original_country in filters.country_not:
                    continue
            if filters.origin_country_not and item.original_country:
                if item.original_country in filters.origin_country_not:
                    continue

            filtered.append(item)

        # Apply limit
        if config.limit:
            filtered = filtered[: config.limit]

        return filtered

    async def _add_missing_to_arr(self, collection: Collection) -> None:
        """Add missing items to Radarr/Sonarr."""
        missing = [item for item in collection.items if not item.in_library]

        if not missing:
            return

        # Determine media type from first item
        is_series = collection.items[0].tvdb_id is not None if collection.items else False

        for item in missing:
            tag = collection.config.item_radarr_tag or collection.config.item_sonarr_tag

            if is_series and self.sonarr and item.tvdb_id:
                await self.sonarr.add_series(
                    tvdb_id=item.tvdb_id,
                    tags=[tag] if tag else None,
                )
            elif not is_series and self.radarr and item.tmdb_id:
                await self.radarr.add_movie(
                    tmdb_id=item.tmdb_id,
                    tags=[tag] if tag else None,
                )
