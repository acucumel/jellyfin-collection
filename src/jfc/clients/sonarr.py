"""Sonarr API client for TV series management."""

from typing import Any, Optional

from loguru import logger

from jfc.clients.base import BaseClient


class SonarrClient(BaseClient):
    """Client for Sonarr API v3."""

    def __init__(
        self,
        url: str,
        api_key: str,
        root_folder: str = "/tv",
        quality_profile: str = "HD-1080p",
        default_tag: str = "jfc",
    ):
        """
        Initialize Sonarr client.

        Args:
            url: Sonarr server URL
            api_key: Sonarr API key
            root_folder: Default root folder path
            quality_profile: Default quality profile name
            default_tag: Default tag for added series
        """
        super().__init__(
            base_url=url,
            api_key=api_key,
            headers={"X-Api-Key": api_key},
        )

        self.root_folder = root_folder
        self.quality_profile = quality_profile
        self.default_tag = default_tag

        # Cached IDs
        self._quality_profile_id: Optional[int] = None
        self._root_folder_id: Optional[int] = None
        self._tag_id: Optional[int] = None

    # =========================================================================
    # Configuration
    # =========================================================================

    async def get_quality_profiles(self) -> list[dict[str, Any]]:
        """Get available quality profiles."""
        response = await self.get("/api/v3/qualityprofile")
        response.raise_for_status()
        return response.json()

    async def get_quality_profile_id(self, name: str) -> Optional[int]:
        """Get quality profile ID by name."""
        if self._quality_profile_id:
            return self._quality_profile_id

        profiles = await self.get_quality_profiles()
        for profile in profiles:
            if profile["name"].lower() == name.lower():
                self._quality_profile_id = profile["id"]
                return profile["id"]

        return None

    async def get_root_folders(self) -> list[dict[str, Any]]:
        """Get configured root folders."""
        response = await self.get("/api/v3/rootfolder")
        response.raise_for_status()
        return response.json()

    async def get_root_folder_path(self, path: str) -> Optional[str]:
        """Get root folder that matches the path."""
        folders = await self.get_root_folders()
        for folder in folders:
            if folder["path"] == path or path.startswith(folder["path"]):
                return folder["path"]

        # Return first folder if path not found
        if folders:
            return folders[0]["path"]

        return None

    async def get_tags(self) -> list[dict[str, Any]]:
        """Get all tags."""
        response = await self.get("/api/v3/tag")
        response.raise_for_status()
        return response.json()

    async def get_or_create_tag(self, name: str) -> int:
        """Get tag ID by name, creating if necessary."""
        if self._tag_id:
            return self._tag_id

        tags = await self.get_tags()
        for tag in tags:
            if tag["label"].lower() == name.lower():
                self._tag_id = tag["id"]
                return tag["id"]

        # Create tag
        response = await self.post("/api/v3/tag", json={"label": name})
        response.raise_for_status()
        tag_id = response.json()["id"]
        self._tag_id = tag_id

        logger.info(f"Created Sonarr tag '{name}' with ID {tag_id}")
        return tag_id

    # =========================================================================
    # Series
    # =========================================================================

    async def get_series(self) -> list[dict[str, Any]]:
        """Get all series in Sonarr."""
        response = await self.get("/api/v3/series")
        response.raise_for_status()
        return response.json()

    async def get_series_by_tvdb_id(self, tvdb_id: int) -> Optional[dict[str, Any]]:
        """Get series by TVDB ID."""
        response = await self.get(f"/api/v3/series?tvdbId={tvdb_id}")
        response.raise_for_status()

        series_list = response.json()
        if series_list:
            return series_list[0]

        return None

    async def series_exists(self, tvdb_id: int) -> bool:
        """Check if series exists in Sonarr."""
        series = await self.get_series_by_tvdb_id(tvdb_id)
        return series is not None

    async def lookup_series(self, tvdb_id: int) -> Optional[dict[str, Any]]:
        """Lookup series details from TVDB."""
        response = await self.get(f"/api/v3/series/lookup?term=tvdb:{tvdb_id}")

        if response.status_code == 404:
            return None

        response.raise_for_status()
        results = response.json()

        if results:
            return results[0]

        return None

    async def add_series(
        self,
        tvdb_id: int,
        root_folder: Optional[str] = None,
        quality_profile: Optional[str] = None,
        tags: Optional[list[str]] = None,
        monitored: bool = True,
        season_folder: bool = True,
        series_type: str = "standard",
        search_for_missing: bool = True,
        monitor: str = "all",
    ) -> Optional[dict[str, Any]]:
        """
        Add series to Sonarr.

        Args:
            tvdb_id: TVDB ID
            root_folder: Root folder path (uses default if None)
            quality_profile: Quality profile name (uses default if None)
            tags: Tag names to apply
            monitored: Whether to monitor the series
            season_folder: Use season folders
            series_type: Series type (standard, daily, anime)
            search_for_missing: Search for missing episodes after adding
            monitor: What to monitor (all, future, missing, existing, firstSeason, latestSeason, none)

        Returns:
            Added series data or None if failed
        """
        # Check if already exists
        if await self.series_exists(tvdb_id):
            logger.debug(f"Series {tvdb_id} already exists in Sonarr")
            return await self.get_series_by_tvdb_id(tvdb_id)

        # Lookup series
        series_data = await self.lookup_series(tvdb_id)
        if not series_data:
            logger.warning(f"Series {tvdb_id} not found in TVDB")
            return None

        # Get quality profile ID
        profile_name = quality_profile or self.quality_profile
        profile_id = await self.get_quality_profile_id(profile_name)
        if not profile_id:
            logger.error(f"Quality profile '{profile_name}' not found")
            return None

        # Get root folder
        folder = await self.get_root_folder_path(root_folder or self.root_folder)
        if not folder:
            logger.error("No root folder configured in Sonarr")
            return None

        # Get tag IDs
        tag_ids = []
        for tag_name in tags or [self.default_tag]:
            tag_id = await self.get_or_create_tag(tag_name)
            tag_ids.append(tag_id)

        # Build request
        series_data.update(
            {
                "rootFolderPath": folder,
                "qualityProfileId": profile_id,
                "monitored": monitored,
                "seasonFolder": season_folder,
                "seriesType": series_type,
                "tags": tag_ids,
                "addOptions": {
                    "monitor": monitor,
                    "searchForMissingEpisodes": search_for_missing,
                    "searchForCutoffUnmetEpisodes": False,
                },
            }
        )

        response = await self.post("/api/v3/series", json=series_data)

        if response.status_code == 201:
            result = response.json()
            logger.info(f"Added series to Sonarr: {result['title']} ({result['year']})")
            return result
        else:
            logger.error(f"Failed to add series {tvdb_id}: {response.status_code} {response.text}")
            return None

    # =========================================================================
    # Status
    # =========================================================================

    async def get_status(self) -> dict[str, Any]:
        """Get Sonarr system status."""
        response = await self.get("/api/v3/system/status")
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> bool:
        """Check if Sonarr is healthy."""
        try:
            await self.get_status()
            return True
        except Exception:
            return False
