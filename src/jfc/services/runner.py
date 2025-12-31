"""Main runner service that orchestrates collection updates."""

import asyncio
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from loguru import logger
from rich.console import Console

from jfc.clients.discord import DiscordWebhook
from jfc.clients.jellyfin import JellyfinClient
from jfc.clients.radarr import RadarrClient
from jfc.clients.sonarr import SonarrClient
from jfc.clients.tmdb import TMDbClient
from jfc.clients.trakt import TraktClient
from jfc.core.config import Settings
from jfc.models.collection import CollectionSchedule, ScheduleType
from jfc.models.media import MediaType
from jfc.models.report import CollectionReport, LibraryReport, RunReport
from jfc.parsers.kometa import KometaParser
from jfc.services.collection_builder import CollectionBuilder
from jfc.services.poster_generator import PosterGenerator
from jfc.services.report_generator import ReportGenerator
from jfc.services.startup import StartupService


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

        # Initialize poster generator (if OpenAI configured)
        self.poster_generator: Optional[PosterGenerator] = None
        if settings.openai.api_key and settings.openai.enabled:
            self.poster_generator = PosterGenerator(
                api_key=settings.openai.api_key,
                output_dir=settings.get_posters_path(),
            )
            logger.info("AI poster generation enabled")

        # Initialize builder
        self.builder = CollectionBuilder(
            jellyfin=self.jellyfin,
            tmdb=self.tmdb,
            trakt=self.trakt,
            radarr=self.radarr,
            sonarr=self.sonarr,
            poster_generator=self.poster_generator,
            dry_run=self.dry_run,
        )

        # Initialize report generator
        self.report_generator = ReportGenerator(
            console=Console(force_terminal=True),
            output_dir=settings.config_path / "reports",
        )

        # Initialize startup service
        self.startup = StartupService(
            settings=settings,
            jellyfin=self.jellyfin,
            tmdb=self.tmdb,
            trakt=self.trakt,
            radarr=self.radarr,
            sonarr=self.sonarr,
        )

        # Track if startup has been run
        self._startup_done = False

    async def run(
        self,
        libraries: Optional[list[str]] = None,
        collections: Optional[list[str]] = None,
        scheduled: bool = False,
    ) -> RunReport:
        """
        Run collection updates.

        Args:
            libraries: Optional list of library names to process
            collections: Optional list of collection names to process
            scheduled: Whether this is a scheduled run

        Returns:
            RunReport with detailed statistics
        """
        # Run startup sequence (only once)
        if not self._startup_done:
            startup_ok = await self.startup.run_startup(matcher=self.builder.matcher)
            self._startup_done = True

            if not startup_ok:
                logger.error("Startup failed - aborting run")
                raise RuntimeError("Startup failed: required services not available")

        # Initialize run report
        run_report = RunReport(
            run_id=str(uuid.uuid4())[:8],
            start_time=datetime.now(),
            scheduled=scheduled,
            dry_run=self.dry_run,
        )

        logger.info(f"Starting collection update run (ID: {run_report.run_id})")

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

            # Initialize library report
            library_report = LibraryReport(
                name=library_name,
                media_type=media_type.value,
            )

            # Get library ID
            library_id = library_id_map.get(library_name)
            if not library_id:
                logger.warning(f"Library '{library_name}' not found in Jellyfin")
                # Add error report for this library
                error_report = CollectionReport(
                    name="[Library Not Found]",
                    library=library_name,
                    schedule="N/A",
                    source_provider="N/A",
                    success=False,
                    error_message=f"Library '{library_name}' not found in Jellyfin",
                )
                library_report.collections.append(error_report)
                run_report.libraries.append(library_report)
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
                    collection, col_report = await self.builder.build_collection(
                        config=config,
                        library_name=library_name,
                        library_id=library_id,
                        media_type=media_type,
                    )

                    # Sync to Jellyfin
                    added, removed = await self.builder.sync_collection(
                        collection=collection,
                        report=col_report,
                        media_type=media_type,
                        add_missing_to_arr=True,
                    )

                    col_report.success = True
                    library_report.collections.append(col_report)

                    # Send changes notification (with all details)
                    has_changes = added > 0 or removed > 0
                    has_arr = col_report.items_sent_to_radarr > 0 or col_report.items_sent_to_sonarr > 0

                    if has_changes or has_arr:
                        await self.discord.send_collection_changes(
                            collection_name=config.name,
                            library=library_name,
                            added=col_report.added_titles,
                            removed=col_report.removed_titles,
                            items_fetched=col_report.items_fetched,
                            items_matched=col_report.items_matched,
                            items_missing=col_report.items_missing,
                            match_rate=col_report.match_rate,
                            source_provider=col_report.source_provider,
                            radarr_titles=col_report.radarr_titles,
                            sonarr_titles=col_report.sonarr_titles,
                        )

                except Exception as e:
                    logger.error(f"Error processing collection '{config.name}': {e}")

                    # Create error report
                    error_report = CollectionReport(
                        name=config.name,
                        library=library_name,
                        schedule=config.schedule.schedule_type.value,
                        source_provider="N/A",
                        success=False,
                        error_message=str(e),
                    )
                    library_report.collections.append(error_report)

                    await self.discord.send_error(
                        title=f"Collection Error: {config.name}",
                        message=str(e),
                    )

            run_report.libraries.append(library_report)

        # Finalize report
        run_report.finalize()

        # Send run end notification
        await self.discord.send_run_end(
            duration_seconds=run_report.duration_seconds,
            collections_updated=run_report.successful_collections,
            items_added=run_report.total_items_added,
            items_removed=run_report.total_items_removed,
            errors=run_report.failed_collections,
            radarr_requests=run_report.total_radarr_requests,
            sonarr_requests=run_report.total_sonarr_requests,
        )

        # Print and save report
        self.report_generator.print_run_report(run_report)

        try:
            self.report_generator.save_report(run_report)
        except Exception as e:
            logger.warning(f"Failed to save report: {e}")

        logger.info(
            f"Run completed in {run_report.duration_seconds:.1f}s: "
            f"{run_report.successful_collections} collections, "
            f"+{run_report.total_items_added} -{run_report.total_items_removed} items, "
            f"{run_report.failed_collections} errors"
        )

        return run_report

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
