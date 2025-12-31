"""Radarr API client for movie management."""

from typing import Any, Optional

from loguru import logger

from jfc.clients.base import BaseClient


class RadarrClient(BaseClient):
    """Client for Radarr API v3."""

    def __init__(
        self,
        url: str,
        api_key: str,
        root_folder: str = "/movies",
        quality_profile: str = "HD-1080p",
        default_tag: str = "jfc",
    ):
        """
        Initialize Radarr client.

        Args:
            url: Radarr server URL
            api_key: Radarr API key
            root_folder: Default root folder path
            quality_profile: Default quality profile name
            default_tag: Default tag for added movies
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

        # Cached blocklist (TMDb IDs)
        self._blocklist_tmdb_ids: Optional[set[int]] = None

        # Cached exclusion list (TMDb IDs)
        self._exclusion_tmdb_ids: Optional[set[int]] = None

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

        logger.info(f"Created Radarr tag '{name}' with ID {tag_id}")
        return tag_id

    # =========================================================================
    # Blocklist
    # =========================================================================

    async def get_blocklist(self, page_size: int = 1000) -> list[dict[str, Any]]:
        """
        Get all blocklisted movies.

        Args:
            page_size: Number of items per page

        Returns:
            List of blocklist entries
        """
        response = await self.get(
            "/api/v3/blocklist",
            params={"page": 1, "pageSize": page_size},
        )
        response.raise_for_status()
        data = response.json()
        return data.get("records", [])

    async def load_blocklist(self) -> set[int]:
        """
        Load blocklist TMDb IDs into cache.

        Returns:
            Set of blocked TMDb IDs
        """
        if self._blocklist_tmdb_ids is not None:
            return self._blocklist_tmdb_ids

        blocklist = await self.get_blocklist()
        self._blocklist_tmdb_ids = set()

        for entry in blocklist:
            # Get movie details to find TMDb ID
            movie_id = entry.get("movieId")
            if movie_id:
                # Fetch movie to get TMDb ID
                try:
                    response = await self.get(f"/api/v3/movie/{movie_id}")
                    if response.status_code == 200:
                        movie = response.json()
                        tmdb_id = movie.get("tmdbId")
                        if tmdb_id:
                            self._blocklist_tmdb_ids.add(tmdb_id)
                except Exception:
                    pass

        logger.debug(f"Loaded {len(self._blocklist_tmdb_ids)} blocked movies from Radarr")
        return self._blocklist_tmdb_ids

    async def is_blocklisted(self, tmdb_id: int) -> bool:
        """
        Check if a movie is in the blocklist.

        Args:
            tmdb_id: TMDb ID to check

        Returns:
            True if movie is blocklisted
        """
        blocklist = await self.load_blocklist()
        return tmdb_id in blocklist

    # =========================================================================
    # Exclusion List
    # =========================================================================

    async def get_exclusions(self) -> list[dict[str, Any]]:
        """
        Get all exclusions (movies that should never be added).

        Returns:
            List of exclusion entries
        """
        response = await self.get("/api/v3/exclusions")
        response.raise_for_status()
        return response.json()

    async def load_exclusions(self) -> set[int]:
        """
        Load exclusion list TMDb IDs into cache.

        Returns:
            Set of excluded TMDb IDs
        """
        if self._exclusion_tmdb_ids is not None:
            return self._exclusion_tmdb_ids

        exclusions = await self.get_exclusions()
        self._exclusion_tmdb_ids = set()

        for entry in exclusions:
            tmdb_id = entry.get("tmdbId")
            if tmdb_id:
                self._exclusion_tmdb_ids.add(tmdb_id)

        logger.debug(f"Loaded {len(self._exclusion_tmdb_ids)} excluded movies from Radarr")
        return self._exclusion_tmdb_ids

    async def is_excluded(self, tmdb_id: int) -> bool:
        """
        Check if a movie is in the exclusion list.

        Args:
            tmdb_id: TMDb ID to check

        Returns:
            True if movie is excluded
        """
        exclusions = await self.load_exclusions()
        return tmdb_id in exclusions

    # =========================================================================
    # Movies
    # =========================================================================

    async def get_movies(self) -> list[dict[str, Any]]:
        """Get all movies in Radarr."""
        response = await self.get("/api/v3/movie")
        response.raise_for_status()
        return response.json()

    async def get_movie_by_tmdb_id(self, tmdb_id: int) -> Optional[dict[str, Any]]:
        """Get movie by TMDb ID."""
        response = await self.get(f"/api/v3/movie?tmdbId={tmdb_id}")
        response.raise_for_status()

        movies = response.json()
        if movies:
            return movies[0]

        return None

    async def movie_exists(self, tmdb_id: int) -> bool:
        """Check if movie exists in Radarr."""
        movie = await self.get_movie_by_tmdb_id(tmdb_id)
        return movie is not None

    async def lookup_movie(self, tmdb_id: int) -> Optional[dict[str, Any]]:
        """Lookup movie details from TMDb."""
        response = await self.get(f"/api/v3/movie/lookup/tmdb?tmdbId={tmdb_id}")

        if response.status_code == 404:
            return None

        response.raise_for_status()
        return response.json()

    async def add_movie(
        self,
        tmdb_id: int,
        root_folder: Optional[str] = None,
        quality_profile: Optional[str] = None,
        tags: Optional[list[str]] = None,
        monitored: bool = True,
        search_for_movie: bool = True,
        minimum_availability: str = "announced",
    ) -> Optional[dict[str, Any]]:
        """
        Add movie to Radarr.

        Args:
            tmdb_id: TMDb ID
            root_folder: Root folder path (uses default if None)
            quality_profile: Quality profile name (uses default if None)
            tags: Tag names to apply
            monitored: Whether to monitor the movie
            search_for_movie: Search for movie after adding
            minimum_availability: When to consider available

        Returns:
            Added movie data or None if failed
        """
        # Check if excluded (user explicitly doesn't want this movie)
        if await self.is_excluded(tmdb_id):
            logger.debug(f"Movie {tmdb_id} is in exclusion list, skipping")
            return None

        # Check if blocklisted (previously failed downloads)
        if await self.is_blocklisted(tmdb_id):
            logger.debug(f"Movie {tmdb_id} is blocklisted in Radarr, skipping")
            return None

        # Check if already exists
        if await self.movie_exists(tmdb_id):
            logger.debug(f"Movie {tmdb_id} already exists in Radarr")
            return await self.get_movie_by_tmdb_id(tmdb_id)

        # Lookup movie
        movie_data = await self.lookup_movie(tmdb_id)
        if not movie_data:
            logger.warning(f"Movie {tmdb_id} not found in TMDb")
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
            logger.error("No root folder configured in Radarr")
            return None

        # Get tag IDs
        tag_ids = []
        for tag_name in tags or [self.default_tag]:
            tag_id = await self.get_or_create_tag(tag_name)
            tag_ids.append(tag_id)

        # Build request
        movie_data.update(
            {
                "rootFolderPath": folder,
                "qualityProfileId": profile_id,
                "monitored": monitored,
                "minimumAvailability": minimum_availability,
                "tags": tag_ids,
                "addOptions": {
                    "searchForMovie": search_for_movie,
                },
            }
        )

        response = await self.post("/api/v3/movie", json=movie_data)

        if response.status_code == 201:
            result = response.json()
            logger.info(f"Added movie to Radarr: {result['title']} ({result['year']})")
            return result
        else:
            logger.error(f"Failed to add movie {tmdb_id}: {response.status_code} {response.text}")
            return None

    # =========================================================================
    # Status
    # =========================================================================

    async def get_status(self) -> dict[str, Any]:
        """Get Radarr system status."""
        response = await self.get("/api/v3/system/status")
        response.raise_for_status()
        return response.json()

    async def health_check(self) -> bool:
        """Check if Radarr is healthy."""
        try:
            await self.get_status()
            return True
        except Exception:
            return False
