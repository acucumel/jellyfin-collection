"""Main runner service that orchestrates collection updates."""

import asyncio
import time
from pathlib import Path
from typing import Optional

from loguru import logger

from jfc.clients.discord import DiscordWebhook
from jfc.clients.jellyfin import JellyfinClient
from jfc.clients.radarr import RadarrClient
from jfc.clients.sonarr import SonarrClient
from jfc.clients.tmdb import TMDbClient
from jfc.clients.trakt import TraktClient
from jfc.core.config import Settings
from jfc.models.collection import CollectionSchedule, ScheduleType
from jfc.models.media import MediaType
from jfc.parsers.kometa import KometaParser
from jfc.services.collection_builder import CollectionBuilder


class Runner:
    """Main runner that orchestrates the collection update process."""

    def __init__(self, settings: Settings):
        """
        Initialize runner with settings.

        Args:
            settings: Application settings
        """
        self.settings = settings
        self.dry_run = settings.dry_run

        # Initialize clients
        self.jellyfin = JellyfinClient(
            url=settings.jellyfin.url,
            api_key=settings.jellyfin.api_key,
        )

        self.tmdb = TMDbClient(
            api_key=settings.tmdb.api_key,
            language=settings.tmdb.language,
            region=settings.tmdb.region,
        )

        self.trakt: Optional[TraktClient] = None
        if settings.trakt.client_id:
            self.trakt = TraktClient(
                client_id=settings.trakt.client_id,
                client_secret=settings.trakt.client_secret,
                access_token=settings.trakt.access_token,
            )

        self.radarr: Optional[RadarrClient] = None
        if settings.radarr.api_key:
            self.radarr = RadarrClient(
                url=settings.radarr.url,
                api_key=settings.radarr.api_key,
                root_folder=settings.radarr.root_folder,
                quality_profile=settings.radarr.quality_profile,
                default_tag=settings.radarr.default_tag,
            )

        self.sonarr: Optional[SonarrClient] = None
        if settings.sonarr.api_key:
            self.sonarr = SonarrClient(
                url=settings.sonarr.url,
                api_key=settings.sonarr.api_key,
                root_folder=settings.sonarr.root_folder,
                quality_profile=settings.sonarr.quality_profile,
                default_tag=settings.sonarr.default_tag,
            )

        self.discord = DiscordWebhook(
            default_url=settings.discord.webhook_url,
            error_url=settings.discord.webhook_error,
            run_start_url=settings.discord.webhook_run_start,
            run_end_url=settings.discord.webhook_run_end,
            changes_url=settings.discord.webhook_changes,
        )

        # Initialize parser
        self.parser = KometaParser(settings.config_path)

        # Initialize builder
        self.builder = CollectionBuilder(
            jellyfin=self.jellyfin,
            tmdb=self.tmdb,
            trakt=self.trakt,
            radarr=self.radarr,
            sonarr=self.sonarr,
            dry_run=self.dry_run,
        )

    async def run(
        self,
        libraries: Optional[list[str]] = None,
        collections: Optional[list[str]] = None,
        scheduled: bool = False,
    ) -> dict:
        """
        Run collection updates.

        Args:
            libraries: Optional list of library names to process
            collections: Optional list of collection names to process
            scheduled: Whether this is a scheduled run

        Returns:
            Run statistics
        """
        start_time = time.time()
        stats = {
            "collections_updated": 0,
            "items_added": 0,
            "items_removed": 0,
            "errors": 0,
        }

        logger.info("Starting collection update run")

        # Parse all collections
        all_collections = self.parser.get_all_collections()

        # Filter by specified libraries
        if libraries:
            all_collections = {
                k: v for k, v in all_collections.items() if k in libraries
            }

        library_names = list(all_collections.keys())

        # Send run start notification
        await self.discord.send_run_start(library_names, scheduled)

        # Get Jellyfin libraries for ID mapping
        jellyfin_libraries = await self.jellyfin.get_libraries()
        library_id_map = {lib["Name"]: lib["ItemId"] for lib in jellyfin_libraries}

        # Process each library
        for library_name, collection_configs in all_collections.items():
            logger.info(f"Processing library: {library_name}")

            # Determine media type from library name
            media_type = self._infer_media_type(library_name)

            # Get library ID
            library_id = library_id_map.get(library_name)
            if not library_id:
                logger.warning(f"Library '{library_name}' not found in Jellyfin")
                stats["errors"] += 1
                continue

            # Process collections
            for config in collection_configs:
                # Filter by specified collections
                if collections and config.name not in collections:
                    continue

                # Check schedule
                if scheduled and not self._should_run_today(config.schedule):
                    logger.debug(f"Skipping '{config.name}' - not scheduled for today")
                    continue

                try:
                    # Build collection
                    collection = await self.builder.build_collection(
                        config=config,
                        library_name=library_name,
                        library_id=library_id,
                        media_type=media_type,
                    )

                    # Sync to Jellyfin
                    added, removed = await self.builder.sync_collection(
                        collection=collection,
                        add_missing_to_arr=True,
                    )

                    stats["collections_updated"] += 1
                    stats["items_added"] += added
                    stats["items_removed"] += removed

                    # Send changes notification
                    if added > 0 or removed > 0:
                        added_titles = [
                            i.title for i in collection.items if i.matched
                        ][:added]
                        removed_titles = []  # We don't track removed titles easily

                        await self.discord.send_collection_changes(
                            collection_name=config.name,
                            library=library_name,
                            added=added_titles,
                            removed=removed_titles,
                        )

                except Exception as e:
                    logger.error(f"Error processing collection '{config.name}': {e}")
                    stats["errors"] += 1

                    await self.discord.send_error(
                        title=f"Collection Error: {config.name}",
                        message=str(e),
                    )

        # Calculate duration
        duration = time.time() - start_time

        # Send run end notification
        await self.discord.send_run_end(
            duration_seconds=duration,
            collections_updated=stats["collections_updated"],
            items_added=stats["items_added"],
            items_removed=stats["items_removed"],
            errors=stats["errors"],
        )

        logger.info(
            f"Run completed in {duration:.1f}s: "
            f"{stats['collections_updated']} collections, "
            f"+{stats['items_added']} -{stats['items_removed']} items, "
            f"{stats['errors']} errors"
        )

        return stats

    async def close(self) -> None:
        """Close all client connections."""
        await self.jellyfin.close()
        await self.tmdb.close()
        if self.trakt:
            await self.trakt.close()
        if self.radarr:
            await self.radarr.close()
        if self.sonarr:
            await self.sonarr.close()

    def _infer_media_type(self, library_name: str) -> MediaType:
        """Infer media type from library name."""
        name_lower = library_name.lower()

        if any(keyword in name_lower for keyword in ["film", "movie", "cinéma"]):
            return MediaType.MOVIE

        if any(keyword in name_lower for keyword in ["série", "series", "tv", "show", "cartoon"]):
            return MediaType.SERIES

        # Default to movies
        return MediaType.MOVIE

    def _should_run_today(self, schedule: CollectionSchedule) -> bool:
        """Check if collection should run today based on schedule."""
        from datetime import datetime

        if schedule.schedule_type == ScheduleType.DAILY:
            return True

        if schedule.schedule_type == ScheduleType.NEVER:
            return False

        today = datetime.now()

        if schedule.schedule_type == ScheduleType.WEEKLY:
            day_name = today.strftime("%A").lower()
            return day_name == (schedule.day_of_week or "sunday").lower()

        if schedule.schedule_type == ScheduleType.MONTHLY:
            return today.day == (schedule.day_of_month or 1)

        return True
