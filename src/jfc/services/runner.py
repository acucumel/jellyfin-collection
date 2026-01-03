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
from jfc.clients.signal import SignalClient
from jfc.clients.signal import NotificationContext as SignalNotificationContext
from jfc.clients.signal import TrendingItem as SignalTrendingItem
from jfc.clients.telegram import NotificationContext, TelegramClient, TrendingItem
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
from jfc.services.trakt_auth import TraktAuth


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
        self.trakt_auth: Optional[TraktAuth] = None
        if settings.trakt.client_id:
            # Initialize Trakt auth handler for token management
            self.trakt_auth = TraktAuth(
                client_id=settings.trakt.client_id,
                client_secret=settings.trakt.client_secret,
                data_dir=settings.get_data_path(),
            )
            # Note: TraktClient will be initialized in run() with valid token

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

        # Initialize Telegram client (if configured)
        self.telegram: Optional[TelegramClient] = None
        if settings.telegram.is_configured:
            self.telegram = TelegramClient(
                bot_token=settings.telegram.bot_token,
                openai_api_key=settings.openai.api_key if settings.openai.enabled else None,
            )
            logger.info(f"Telegram notifications enabled ({len(settings.telegram.notifications)} notification(s))")

        # Initialize Signal client (if configured)
        self.signal: Optional[SignalClient] = None
        if settings.signal.is_configured:
            self.signal = SignalClient(
                api_url=settings.signal.api_url,
                phone_number=settings.signal.phone_number,
                openai_api_key=settings.openai.api_key if settings.openai.enabled else None,
            )
            logger.info(f"Signal notifications enabled ({len(settings.signal.notifications)} notification(s))")

        # Initialize parser
        self.parser = KometaParser(settings.config_path)

        # Initialize poster generator (if OpenAI configured)
        self.poster_generator: Optional[PosterGenerator] = None
        if settings.openai.api_key and settings.openai.enabled:
            self.poster_generator = PosterGenerator(
                api_key=settings.openai.api_key,
                output_dir=settings.get_posters_path(),
                cache_dir=settings.get_cache_path(),
                templates_dir=settings.get_templates_path(),
                poster_history_limit=settings.openai.poster_history_limit,
                prompt_history_limit=settings.openai.prompt_history_limit,
                logo_text=settings.openai.poster_logo_text,
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
            output_dir=settings.get_reports_path(),
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
        force_posters: bool | None = None,
        posters_only: bool = False,
        ignore_schedule: bool = False,
    ) -> RunReport:
        """
        Run collection updates.

        Args:
            libraries: Optional list of library names to process
            collections: Optional list of collection names to process
            scheduled: Whether this is a scheduled run
            force_posters: Force regeneration of all posters
            posters_only: Only generate posters, skip collection sync
            ignore_schedule: Ignore individual collection schedules and process all

        Returns:
            RunReport with detailed statistics
        """
        # Apply env var default if force_posters not explicitly set
        if force_posters is None:
            force_posters = self.settings.openai.force_regenerate

        # Initialize Trakt client with valid token (auto-refresh if needed)
        if self.trakt_auth and not self.trakt:
            access_token = await self.trakt_auth.get_valid_token()
            if access_token:
                self.trakt = TraktClient(
                    client_id=self.settings.trakt.client_id,
                    client_secret=self.settings.trakt.client_secret,
                    access_token=access_token,
                )
                # Update builder with Trakt client
                self.builder.trakt = self.trakt
                logger.info("Trakt client initialized with valid token")
            else:
                logger.warning("Trakt not authenticated. Run 'jfc trakt-auth' to authenticate.")

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

        # Store trending items for Telegram notification
        # Key: "films" or "series", Value: list of TrendingItem
        trending_items: dict[str, list[TrendingItem]] = {"films": [], "series": []}

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

                # Check schedule (skip if ignore_schedule is True)
                if scheduled and not ignore_schedule and not self._should_run_today(config.schedule):
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

                    # Collect trending items for Telegram notification
                    if self.telegram and "tendances" in config.name.lower():
                        category = "series" if media_type == MediaType.SERIES else "films"
                        # Use collection.items (matched items) for availability info
                        matched_ids = {i.tmdb_id for i in collection.items if i.matched}

                        # Take more items to ensure we have enough after filtering
                        for item in collection.source_items[:20]:
                            # Convert genres to strings
                            genre_strs = []
                            if item.genres:
                                for g in item.genres[:2]:
                                    if isinstance(g, int):
                                        from jfc.services.poster_generator import TMDB_GENRES
                                        genre_strs.append(TMDB_GENRES.get(g, ""))
                                    else:
                                        genre_strs.append(str(g))
                            genre_strs = [g for g in genre_strs if g]  # Remove empty

                            trending_items[category].append(TrendingItem(
                                title=item.title,
                                year=item.year,
                                genres=genre_strs if genre_strs else None,
                                poster_url=TelegramClient.build_poster_url(item.poster_path),
                                tmdb_id=item.tmdb_id,
                                available=item.tmdb_id in matched_ids,
                            ))

                    # Sync to Jellyfin (or just posters if posters_only mode)
                    added, removed, poster_path = await self.builder.sync_collection(
                        collection=collection,
                        report=col_report,
                        media_type=media_type,
                        add_missing_to_arr=not posters_only,  # Skip arr sync in posters_only mode
                        force_poster=force_posters,
                        posters_only=posters_only,
                    )

                    col_report.success = True
                    library_report.collections.append(col_report)

                    # Send rich collection report with poster
                    await self.discord.send_collection_report(
                        collection_name=config.name,
                        library=library_name,
                        source_provider=col_report.source_provider,
                        items_fetched=col_report.items_fetched,
                        items_after_filters=col_report.items_after_filter,
                        items_matched=col_report.items_matched,
                        items_missing=col_report.items_missing,
                        match_rate=col_report.match_rate,
                        items_added=added,
                        items_removed=removed,
                        radarr_requests=col_report.items_sent_to_radarr,
                        sonarr_requests=col_report.items_sent_to_sonarr,
                        matched_titles=col_report.matched_titles,
                        added_titles=col_report.added_titles,
                        missing_titles=col_report.missing_titles,
                        radarr_titles=col_report.radarr_titles,
                        sonarr_titles=col_report.sonarr_titles,
                        poster_path=poster_path,
                        success=True,
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

        # Process Telegram notifications by trigger
        if self.telegram:
            # Build context for notifications
            context = NotificationContext(
                trigger="trending",
                films=trending_items["films"],
                series=trending_items["series"],
                duration_seconds=run_report.duration_seconds,
                collections_updated=run_report.successful_collections,
                items_added=run_report.total_items_added,
                items_removed=run_report.total_items_removed,
            )

            # Process "trending" trigger notifications
            for notification in self.settings.telegram.get_notifications_by_trigger("trending"):
                try:
                    await self.telegram.process_notification(notification, context)
                except Exception as e:
                    logger.warning(f"Telegram notification '{notification.name}' failed: {e}")

            # Process "run_end" trigger notifications
            context.trigger = "run_end"
            for notification in self.settings.telegram.get_notifications_by_trigger("run_end"):
                try:
                    await self.telegram.process_notification(notification, context)
                except Exception as e:
                    logger.warning(f"Telegram notification '{notification.name}' failed: {e}")

        # Process Signal notifications by trigger
        if self.signal:
            # Build context for Signal notifications (using Signal's dataclasses)
            signal_films = [
                SignalTrendingItem(
                    title=f.title,
                    year=f.year,
                    genres=f.genres,
                    poster_url=f.poster_url,
                    tmdb_id=f.tmdb_id,
                    available=f.available,
                )
                for f in trending_items["films"]
            ]
            signal_series = [
                SignalTrendingItem(
                    title=s.title,
                    year=s.year,
                    genres=s.genres,
                    poster_url=s.poster_url,
                    tmdb_id=s.tmdb_id,
                    available=s.available,
                )
                for s in trending_items["series"]
            ]

            signal_context = SignalNotificationContext(
                trigger="trending",
                films=signal_films,
                series=signal_series,
                duration_seconds=run_report.duration_seconds,
                collections_updated=run_report.successful_collections,
                items_added=run_report.total_items_added,
                items_removed=run_report.total_items_removed,
            )

            # Process "trending" trigger notifications
            for notification in self.settings.signal.get_notifications_by_trigger("trending"):
                try:
                    await self.signal.process_notification(notification, signal_context)
                except Exception as e:
                    logger.warning(f"Signal notification '{notification.name}' failed: {e}")

            # Process "run_end" trigger notifications
            signal_context.trigger = "run_end"
            for notification in self.settings.signal.get_notifications_by_trigger("run_end"):
                try:
                    await self.signal.process_notification(notification, signal_context)
                except Exception as e:
                    logger.warning(f"Signal notification '{notification.name}' failed: {e}")

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
