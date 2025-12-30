"""Service for building collections from Kometa configurations."""

import random
import time
from datetime import date
from typing import Any, Optional

from loguru import logger

from jfc.clients.jellyfin import JellyfinClient
from jfc.clients.radarr import RadarrClient
from jfc.clients.sonarr import SonarrClient
from jfc.clients.tmdb import TMDbClient
from jfc.clients.trakt import TraktClient
from jfc.core.config import get_settings
from jfc.models.collection import Collection, CollectionConfig, CollectionItem, CollectionOrder
from jfc.models.media import MediaItem, MediaType, Movie, Series
from jfc.models.report import CollectionReport
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
    ) -> tuple[Collection, CollectionReport]:
        """
        Build a collection from configuration.

        Args:
            config: Collection configuration
            library_name: Name of the Jellyfin library
            library_id: Jellyfin library ID
            media_type: Type of media (movie/series)

        Returns:
            Tuple of (Built collection with items, Collection report)
        """
        start_time = time.time()
        logger.info(f"Building collection: {config.name}")

        # Initialize report
        report = CollectionReport(
            name=config.name,
            library=library_name,
            schedule=config.schedule.schedule_type.value,
            source_provider=self._get_source_provider(config),
        )

        # Fetch items from providers
        items = await self._fetch_items(config, media_type)
        report.items_fetched = len(items)
        report.fetched_titles = [item.title for item in items]

        # Apply filters
        filtered_items = self._apply_filters(items, config)
        report.items_after_filter = len(filtered_items)

        # Match items to library
        collection_items = []
        for item in filtered_items:
            lib_item = await self.matcher.find_in_library(item, library_id)

            collection_item = CollectionItem(
                title=item.title,
                year=item.year,
                tmdb_id=item.tmdb_id,
                imdb_id=item.imdb_id,
                tvdb_id=item.tvdb_id,
                jellyfin_id=lib_item.jellyfin_id if lib_item else None,
                media_type=item.media_type.value,  # "movie" or "series"
                matched=lib_item is not None,
                in_library=lib_item is not None,
            )
            collection_items.append(collection_item)

            # Track matched/missing titles
            if lib_item:
                report.matched_titles.append(item.title)
            else:
                report.missing_titles.append(item.title)

        collection = Collection(
            config=config,
            library_name=library_name,
            items=collection_items,
        )
        collection.update_stats()

        # Update report stats
        report.items_matched = collection.matched_items
        report.items_missing = collection.missing_items
        report.calculate_match_rate()
        report.duration_seconds = time.time() - start_time

        logger.info(
            f"Collection '{config.name}': {collection.matched_items}/{collection.total_items} "
            f"items matched, {collection.missing_items} missing"
        )

        return collection, report

    def _get_source_provider(self, config: CollectionConfig) -> str:
        """Determine the primary source provider from config."""
        sources = []
        if config.tmdb_trending_weekly or config.tmdb_trending_daily:
            sources.append("TMDb Trending")
        if config.tmdb_popular:
            sources.append("TMDb Popular")
        if config.tmdb_discover:
            sources.append("TMDb Discover")
        if config.trakt_trending:
            sources.append("Trakt Trending")
        if config.trakt_popular:
            sources.append("Trakt Popular")
        if config.trakt_chart:
            chart = config.trakt_chart.get("chart", "unknown")
            sources.append(f"Trakt {chart.capitalize()}")
        if config.plex_search:
            sources.append("Library Search")
        return ", ".join(sources) if sources else "Unknown"

    async def sync_collection(
        self,
        collection: Collection,
        report: CollectionReport,
        add_missing_to_arr: bool = True,
    ) -> tuple[int, int]:
        """
        Sync collection to Jellyfin.

        Args:
            collection: Collection to sync
            report: Collection report to update with sync info
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

        report.collection_existed = existing is not None

        if existing:
            collection.jellyfin_id = existing["Id"]
        else:
            collection.jellyfin_id = await self.jellyfin.create_collection(
                collection.config.name
            )

        # Get current items in collection
        current_ids = set(await self.jellyfin.get_collection_items(collection.jellyfin_id))

        # Sort items according to collection_order
        sorted_items = self._sort_items_for_collection(
            collection.items,
            collection.config.collection_order,
        )

        # Get target items in sorted order (only matched ones)
        target_ids_list = [
            item.jellyfin_id for item in sorted_items if item.jellyfin_id
        ]
        target_ids = set(target_ids_list)

        # Calculate changes
        to_add = target_ids - current_ids
        to_remove = current_ids - target_ids

        # Track added/removed titles for report
        added_jellyfin_ids = to_add
        for item in collection.items:
            if item.jellyfin_id in added_jellyfin_ids:
                report.added_titles.append(item.title)

        # Determine if we need to reorder (clear and re-add all)
        # Jellyfin displays items in the order they were added
        needs_reorder = (
            collection.config.collection_order != CollectionOrder.CUSTOM
            and (to_add or to_remove or not existing)
        )

        if needs_reorder and target_ids_list:
            # Clear all items and re-add in sorted order
            if current_ids:
                await self.jellyfin.remove_from_collection(
                    collection.jellyfin_id, list(current_ids)
                )
            await self.jellyfin.add_to_collection(
                collection.jellyfin_id, target_ids_list
            )
            logger.info(
                f"Reordered '{collection.config.name}' ({len(target_ids_list)} items, "
                f"order={collection.config.collection_order.value})"
            )
        else:
            # Simple add/remove (no reordering needed)
            if to_add:
                await self.jellyfin.add_to_collection(collection.jellyfin_id, list(to_add))
                logger.info(f"Added {len(to_add)} items to '{collection.config.name}'")

            if to_remove:
                await self.jellyfin.remove_from_collection(collection.jellyfin_id, list(to_remove))
                logger.info(f"Removed {len(to_remove)} items from '{collection.config.name}'")

        # Update report
        report.items_added_to_collection = len(to_add)
        report.items_removed_from_collection = len(to_remove)

        # Update metadata (including DisplayOrder for Jellyfin sorting)
        display_order = self._get_jellyfin_display_order(collection.config.collection_order)
        await self.jellyfin.update_collection_metadata(
            collection.jellyfin_id,
            overview=collection.config.summary,
            sort_name=collection.config.sort_title,
            display_order=display_order,
        )

        # Upload poster if configured
        if collection.config.poster:
            await self._upload_poster(collection)

        # Add missing items to Radarr/Sonarr
        if add_missing_to_arr:
            radarr_count, sonarr_count = await self._add_missing_to_arr(collection, report)
            report.items_sent_to_radarr = radarr_count
            report.items_sent_to_sonarr = sonarr_count

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

            # Language filter (e.g., exclude Japanese anime)
            if filters.original_language_not and item.original_language:
                if item.original_language in filters.original_language_not:
                    logger.debug(f"Filtered out '{item.title}': language={item.original_language}")
                    continue

            # Genre filters (genres stored as list of IDs)
            if filters.without_genres and item.genres:
                # item.genres can be list of ints or list of strings
                item_genre_ids = [
                    g if isinstance(g, int) else int(g) if str(g).isdigit() else 0
                    for g in item.genres
                ]
                if any(g in item_genre_ids for g in filters.without_genres):
                    logger.debug(f"Filtered out '{item.title}': excluded genre")
                    continue

            if filters.with_genres and item.genres:
                item_genre_ids = [
                    g if isinstance(g, int) else int(g) if str(g).isdigit() else 0
                    for g in item.genres
                ]
                if not any(g in item_genre_ids for g in filters.with_genres):
                    logger.debug(f"Filtered out '{item.title}': missing required genre")
                    continue

            filtered.append(item)

        # Apply limit
        if config.limit:
            filtered = filtered[: config.limit]

        return filtered

    def _sort_items_for_collection(
        self,
        items: list[CollectionItem],
        order: CollectionOrder,
    ) -> list[CollectionItem]:
        """
        Sort collection items according to specified order.

        For 'custom' order, items are kept in their original source order.
        For other orders, items are sorted and will be added to Jellyfin
        in that order (achieving the desired display order).

        Args:
            items: Collection items to sort
            order: Sort order to apply

        Returns:
            Sorted list of items
        """
        if order == CollectionOrder.CUSTOM:
            # Keep original order from source
            return items

        if order == CollectionOrder.RANDOM:
            shuffled = items.copy()
            random.shuffle(shuffled)
            return shuffled

        # Define sort key functions
        def sort_key_name(x: CollectionItem) -> str:
            return (x.sort_name or x.title).lower()

        def sort_key_premiere(x: CollectionItem) -> tuple:
            # Use year as fallback, sort descending (newest first)
            d = x.premiere_date or (date(x.year, 1, 1) if x.year else date.min)
            return (d, x.title)

        def sort_key_rating(x: CollectionItem) -> tuple:
            # Sort descending (highest first) - use negative
            return (-(x.community_rating or 0), x.title)

        def sort_key_critic(x: CollectionItem) -> tuple:
            return (-(x.critic_rating or 0), x.title)

        def sort_key_created(x: CollectionItem) -> tuple:
            return (x.date_created or date.min, x.title)

        sort_keys = {
            CollectionOrder.SORT_NAME: sort_key_name,
            CollectionOrder.PREMIERE_DATE: sort_key_premiere,
            CollectionOrder.COMMUNITY_RATING: sort_key_rating,
            CollectionOrder.CRITIC_RATING: sort_key_critic,
            CollectionOrder.DATE_CREATED: sort_key_created,
        }

        key_func = sort_keys.get(order)
        if key_func:
            # Descending for dates (newest first)
            reverse = order in {
                CollectionOrder.PREMIERE_DATE,
                CollectionOrder.DATE_CREATED,
            }
            return sorted(items, key=key_func, reverse=reverse)

        return items

    def _get_jellyfin_display_order(self, order: CollectionOrder) -> str:
        """
        Map CollectionOrder to Jellyfin DisplayOrder value.

        Jellyfin DisplayOrder values:
        - "Default" - Default order (insertion order)
        - "SortName" - Alphabetical by sort name
        - "PremiereDate" - By release/premiere date
        - "DateCreated" - By date added to library
        - "CommunityRating" - By community rating

        Args:
            order: Collection order enum

        Returns:
            Jellyfin DisplayOrder string value
        """
        order_mapping = {
            CollectionOrder.CUSTOM: "Default",
            CollectionOrder.SORT_NAME: "SortName",
            CollectionOrder.PREMIERE_DATE: "PremiereDate",
            CollectionOrder.DATE_CREATED: "DateCreated",
            CollectionOrder.COMMUNITY_RATING: "CommunityRating",
            CollectionOrder.CRITIC_RATING: "CommunityRating",  # Jellyfin uses same field
            CollectionOrder.RANDOM: "Default",  # No random in Jellyfin, use default
        }
        return order_mapping.get(order, "Default")

    async def _upload_poster(self, collection: Collection) -> bool:
        """
        Upload poster image for collection if configured.

        Args:
            collection: Collection with poster config

        Returns:
            True if poster was uploaded successfully
        """
        if not collection.config.poster or not collection.jellyfin_id:
            return False

        settings = get_settings()
        poster_path = settings.get_posters_path() / collection.config.poster

        try:
            success = await self.jellyfin.upload_collection_poster(
                collection.jellyfin_id,
                poster_path,
            )
            if success:
                logger.success(f"✓ Uploaded poster for '{collection.config.name}'")
            return success
        except FileNotFoundError:
            logger.warning(
                f"⚠ Poster file not found for '{collection.config.name}': {poster_path}"
            )
            return False
        except ValueError as e:
            logger.warning(f"⚠ Invalid poster for '{collection.config.name}': {e}")
            return False
        except Exception as e:
            logger.error(f"✗ Failed to upload poster for '{collection.config.name}': {e}")
            return False

    async def _add_missing_to_arr(
        self,
        collection: Collection,
        report: CollectionReport,
    ) -> tuple[int, int]:
        """Add missing items to Radarr/Sonarr.

        Uses library-level settings from collection config if available,
        otherwise falls back to client defaults.

        Returns:
            Tuple of (radarr_count, sonarr_count)
        """
        missing = [item for item in collection.items if not item.in_library]
        radarr_count = 0
        sonarr_count = 0

        if not missing:
            return (0, 0)

        # Get library-level settings (item-level tag takes priority over library-level)
        config = collection.config

        for item in missing:
            # Use media_type to determine Sonarr vs Radarr
            is_series = item.media_type == "series"

            if is_series and self.sonarr:
                # Sonarr settings: item_sonarr_tag > sonarr_tag > client default
                tag = config.item_sonarr_tag or config.sonarr_tag
                tags = [tag] if tag else None

                # Get tvdb_id - fetch from TMDb if not already available
                tvdb_id = item.tvdb_id
                if not tvdb_id and item.tmdb_id:
                    # Fetch series details from TMDb to get tvdb_id
                    series_details = await self.tmdb.get_series_details(item.tmdb_id)
                    if series_details:
                        tvdb_id = series_details.tvdb_id

                if not tvdb_id:
                    logger.warning(f"Cannot add '{item.title}' to Sonarr: no TVDB ID found")
                    continue

                try:
                    await self.sonarr.add_series(
                        tvdb_id=tvdb_id,
                        root_folder=config.sonarr_root_folder,
                        quality_profile=config.sonarr_quality_profile,
                        tags=tags,
                    )
                    sonarr_count += 1
                    report.sonarr_titles.append(item.title)
                except Exception as e:
                    logger.warning(f"Failed to add '{item.title}' to Sonarr: {e}")

            elif not is_series and self.radarr and item.tmdb_id:
                # Radarr settings: item_radarr_tag > radarr_tag > client default
                tag = config.item_radarr_tag or config.radarr_tag
                tags = [tag] if tag else None

                try:
                    await self.radarr.add_movie(
                        tmdb_id=item.tmdb_id,
                        root_folder=config.radarr_root_folder,
                        quality_profile=config.radarr_quality_profile,
                        tags=tags,
                    )
                    radarr_count += 1
                    report.radarr_titles.append(item.title)
                except Exception as e:
                    logger.warning(f"Failed to add '{item.title}' to Radarr: {e}")

        return (radarr_count, sonarr_count)
