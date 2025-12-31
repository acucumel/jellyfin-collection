"""Startup service for initialization and health checks."""

from typing import Optional

import httpx
from loguru import logger

from jfc.clients.jellyfin import JellyfinClient
from jfc.clients.radarr import RadarrClient
from jfc.clients.sonarr import SonarrClient
from jfc.clients.tmdb import TMDbClient
from jfc.clients.trakt import TraktClient
from jfc.core.config import Settings
from jfc.services.media_matcher import MediaMatcher


BANNER = r"""
     ██╗███████╗ ██████╗
     ██║██╔════╝██╔════╝
     ██║█████╗  ██║
██   ██║██╔══╝  ██║
╚█████╔╝██║     ╚██████╗
 ╚════╝ ╚═╝      ╚═════╝
Jellyfin Collection Manager
"""


class StartupService:
    """Service for application startup and initialization."""

    def __init__(
        self,
        settings: Settings,
        jellyfin: JellyfinClient,
        tmdb: TMDbClient,
        trakt: Optional[TraktClient] = None,
        radarr: Optional[RadarrClient] = None,
        sonarr: Optional[SonarrClient] = None,
    ):
        self.settings = settings
        self.jellyfin = jellyfin
        self.tmdb = tmdb
        self.trakt = trakt
        self.radarr = radarr
        self.sonarr = sonarr

    def print_banner(self) -> None:
        """Print startup banner."""
        logger.info("=" * 60)
        for line in BANNER.strip().split("\n"):
            logger.info(line)
        logger.info("=" * 60)
        logger.info(f"Config path: {self.settings.config_path}")
        logger.info(f"Dry run: {self.settings.dry_run}")
        logger.info(f"Log level: {self.settings.log_level}")
        logger.info("=" * 60)

    async def check_connections(self) -> dict[str, bool]:
        """
        Check all API connections.

        Returns:
            Dictionary of service name -> connection status
        """
        results = {}

        logger.info("Checking API connections...")

        # Jellyfin (required)
        try:
            libraries = await self.jellyfin.get_libraries()
            results["Jellyfin"] = True
            logger.success(f"  ✓ Jellyfin: {len(libraries)} libraries found")
            for lib in libraries:
                logger.debug(f"       - {lib['Name']} ({lib.get('CollectionType', 'mixed')})")
        except Exception as e:
            results["Jellyfin"] = False
            logger.error(f"  ✗ Jellyfin: {e}")

        # TMDb (required)
        try:
            movies = await self.tmdb.get_popular_movies(limit=1)
            results["TMDb"] = True
            logger.success(f"  ✓ TMDb: Connected (language={self.settings.tmdb_language})")
        except Exception as e:
            results["TMDb"] = False
            logger.error(f"  ✗ TMDb: {e}")

        # Trakt (optional)
        if self.trakt and self.settings.trakt_client_id:
            try:
                movies = await self.trakt.get_trending_movies(limit=1)
                results["Trakt"] = True
                logger.success("  ✓ Trakt: Connected")
            except Exception as e:
                results["Trakt"] = False
                logger.warning(f"  ✗ Trakt: {e}")
        else:
            logger.info("  ⏭ Trakt: Not configured")

        # Radarr (optional)
        if self.radarr and self.settings.radarr_api_key:
            try:
                healthy = await self.radarr.health_check()
                results["Radarr"] = healthy
                if healthy:
                    logger.success(f"  ✓ Radarr: {self.settings.radarr_url}")
                else:
                    logger.warning("  ⚠ Radarr: Health check failed")
            except Exception as e:
                results["Radarr"] = False
                logger.warning(f"  ✗ Radarr: {e}")
        else:
            logger.info("  ⏭ Radarr: Not configured")

        # Sonarr (optional)
        if self.sonarr and self.settings.sonarr_api_key:
            try:
                healthy = await self.sonarr.health_check()
                results["Sonarr"] = healthy
                if healthy:
                    logger.success(f"  ✓ Sonarr: {self.settings.sonarr_url}")
                else:
                    logger.warning("  ⚠ Sonarr: Health check failed")
            except Exception as e:
                results["Sonarr"] = False
                logger.warning(f"  ✗ Sonarr: {e}")
        else:
            logger.info("  ⏭ Sonarr: Not configured")

        # OpenAI (optional, for poster generation)
        if self.settings.openai.enabled and self.settings.openai.api_key:
            openai_ok, openai_msg = await self._check_openai()
            results["OpenAI"] = openai_ok
            if openai_ok:
                logger.success(f"  ✓ OpenAI: {openai_msg}")
            else:
                logger.error(f"  ✗ OpenAI: {openai_msg}")
                logger.warning("    ⚠ AI poster generation will fail!")
        elif self.settings.openai.enabled:
            logger.warning("  ⚠ OpenAI: Enabled but no API key configured")
        else:
            logger.info("  ⏭ OpenAI: Not enabled")

        # Summary
        ok_count = sum(1 for v in results.values() if v)
        total_count = len(results)
        if ok_count == total_count:
            logger.success(f"✓ Connection check: {ok_count}/{total_count} services OK")
        else:
            logger.warning(f"⚠ Connection check: {ok_count}/{total_count} services OK")

        return results

    async def _check_openai(self) -> tuple[bool, str]:
        """
        Check OpenAI API connectivity and credits.

        Returns:
            Tuple of (success, message)
        """
        api_key = self.settings.openai.api_key
        if not api_key:
            return False, "No API key configured"

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                # First check: verify API key by listing models
                response = await client.get(
                    "https://api.openai.com/v1/models",
                    headers={"Authorization": f"Bearer {api_key}"},
                )

                if response.status_code == 401:
                    return False, "Invalid API key"
                elif response.status_code == 429:
                    return False, "Rate limited or quota exceeded"
                elif response.status_code != 200:
                    return False, f"API error: {response.status_code}"

                # Second check: small completion to verify credits
                # Using gpt-4o-mini which is very cheap
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "model": "gpt-4o-mini",
                        "messages": [{"role": "user", "content": "Hi"}],
                        "max_tokens": 1,
                    },
                )

                if response.status_code == 200:
                    return True, "Connected (credits OK)"
                elif response.status_code == 429:
                    error_data = response.json()
                    error_msg = error_data.get("error", {}).get("message", "Rate limited")
                    if "quota" in error_msg.lower() or "exceeded" in error_msg.lower():
                        return False, "No credits remaining"
                    return False, f"Rate limited: {error_msg}"
                elif response.status_code == 402:
                    return False, "No credits remaining (payment required)"
                else:
                    return False, f"Credit check failed: {response.status_code}"

        except httpx.TimeoutException:
            return False, "Connection timeout"
        except Exception as e:
            return False, f"Connection error: {e}"

    async def preload_libraries(self, matcher: MediaMatcher) -> dict[str, int]:
        """
        Preload all Jellyfin libraries into cache.

        Args:
            matcher: MediaMatcher instance to populate

        Returns:
            Dictionary of library name -> item count
        """
        logger.info("Preloading Jellyfin libraries into cache...")

        libraries = await self.jellyfin.get_libraries()
        stats = {}

        for lib in libraries:
            lib_name = lib["Name"]
            lib_id = lib["ItemId"]
            collection_type = lib.get("CollectionType", "")

            # Only preload movies and tvshows
            if collection_type not in ("movies", "tvshows"):
                logger.debug(f"  ⏭ {lib_name}: type={collection_type}")
                continue

            logger.info(f"  ⏳ Loading {lib_name}...")

            try:
                # Determine media type
                from jfc.models.media import MediaType
                media_type = MediaType.MOVIE if collection_type == "movies" else MediaType.SERIES

                # Load library into matcher cache
                await matcher._ensure_library_loaded(lib_id, media_type)

                item_count = len(matcher._library_items.get(lib_id, {}))
                stats[lib_name] = item_count
                logger.success(f"  ✓ {lib_name}: {item_count} items with TMDb IDs")

            except Exception as e:
                logger.error(f"  ✗ {lib_name}: {e}")
                stats[lib_name] = 0

        # Summary
        total_items = sum(stats.values())
        logger.success(f"✓ Library cache: {total_items} total items across {len(stats)} libraries")

        return stats

    async def preload_blocklists(self) -> dict[str, dict[str, int]]:
        """
        Preload Radarr/Sonarr blocklists and exclusion lists into cache.

        Returns:
            Dictionary of service name -> {blocklist: count, exclusions: count}
        """
        stats = {}

        # Radarr
        if self.radarr:
            stats["Radarr"] = {"blocklist": 0, "exclusions": 0}
            try:
                blocklist = await self.radarr.load_blocklist()
                stats["Radarr"]["blocklist"] = len(blocklist)
                if blocklist:
                    logger.info(f"  ⛔ Radarr: {len(blocklist)} blocked movies")
            except Exception as e:
                logger.warning(f"  ✗ Radarr blocklist: {e}")

            try:
                exclusions = await self.radarr.load_exclusions()
                stats["Radarr"]["exclusions"] = len(exclusions)
                if exclusions:
                    logger.info(f"  🚫 Radarr: {len(exclusions)} excluded movies")
            except Exception as e:
                logger.warning(f"  ✗ Radarr exclusions: {e}")

        # Sonarr
        if self.sonarr:
            stats["Sonarr"] = {"blocklist": 0, "exclusions": 0}
            try:
                blocklist = await self.sonarr.load_blocklist()
                stats["Sonarr"]["blocklist"] = len(blocklist)
                if blocklist:
                    logger.info(f"  ⛔ Sonarr: {len(blocklist)} blocked series")
            except Exception as e:
                logger.warning(f"  ✗ Sonarr blocklist: {e}")

            try:
                exclusions = await self.sonarr.load_exclusions()
                stats["Sonarr"]["exclusions"] = len(exclusions)
                if exclusions:
                    logger.info(f"  🚫 Sonarr: {len(exclusions)} excluded series")
            except Exception as e:
                logger.warning(f"  ✗ Sonarr exclusions: {e}")

        return stats

    async def run_startup(self, matcher: Optional[MediaMatcher] = None) -> bool:
        """
        Run full startup sequence.

        Args:
            matcher: Optional MediaMatcher to preload libraries into

        Returns:
            True if startup was successful (required services OK)
        """
        # Print banner
        self.print_banner()

        # Check connections
        results = await self.check_connections()

        # Check required services
        required_ok = results.get("Jellyfin", False) and results.get("TMDb", False)
        if not required_ok:
            logger.error("✗ Required services (Jellyfin, TMDb) are not available!")
            return False

        # Preload libraries if matcher provided
        if matcher:
            await self.preload_libraries(matcher)

        # Preload blocklists for Radarr/Sonarr
        if self.radarr or self.sonarr:
            logger.info("Preloading Radarr/Sonarr blocklists...")
            await self.preload_blocklists()

        logger.info("=" * 60)
        logger.success("🚀 Startup complete - Ready to process collections")
        logger.info("=" * 60)

        return True
