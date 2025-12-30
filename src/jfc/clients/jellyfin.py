"""Jellyfin API client for managing collections and media."""

import base64
import mimetypes
from pathlib import Path
from typing import Any, Optional

from loguru import logger

from jfc.clients.base import BaseClient
from jfc.models.media import LibraryItem, MediaType

# Supported image formats for posters
SUPPORTED_IMAGE_FORMATS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}


class JellyfinClient(BaseClient):
    """Client for Jellyfin API."""

    def __init__(self, url: str, api_key: str):
        """
        Initialize Jellyfin client.

        Args:
            url: Jellyfin server URL
            api_key: Jellyfin API key
        """
        super().__init__(
            base_url=url,
            api_key=api_key,
            headers={"X-Emby-Token": api_key},
        )

    # =========================================================================
    # Libraries
    # =========================================================================

    async def get_libraries(self) -> list[dict[str, Any]]:
        """Get all media libraries."""
        response = await self.get("/Library/VirtualFolders")
        response.raise_for_status()
        return response.json()

    async def get_library_items(
        self,
        library_id: str,
        media_type: Optional[MediaType] = None,
        limit: int = 1000,
        start_index: int = 0,
    ) -> list[LibraryItem]:
        """
        Get items from a library.

        Args:
            library_id: Library (parent) ID
            media_type: Filter by media type
            limit: Maximum items to return
            start_index: Pagination offset

        Returns:
            List of library items
        """
        params = {
            "ParentId": library_id,
            "Limit": limit,
            "StartIndex": start_index,
            "Recursive": True,
            "Fields": "ProviderIds,Path,Overview",
        }

        if media_type == MediaType.MOVIE:
            params["IncludeItemTypes"] = "Movie"
        elif media_type == MediaType.SERIES:
            params["IncludeItemTypes"] = "Series"

        response = await self.get("/Items", params=params)
        response.raise_for_status()

        items = []
        for item in response.json().get("Items", []):
            provider_ids = item.get("ProviderIds", {})
            items.append(
                LibraryItem(
                    jellyfin_id=item["Id"],
                    title=item["Name"],
                    year=item.get("ProductionYear"),
                    media_type=self._map_item_type(item.get("Type", "")),
                    tmdb_id=int(provider_ids["Tmdb"]) if provider_ids.get("Tmdb") else None,
                    imdb_id=provider_ids.get("Imdb"),
                    tvdb_id=int(provider_ids["Tvdb"]) if provider_ids.get("Tvdb") else None,
                    library_id=library_id,
                    library_name=item.get("ParentIndexNumber", "Unknown"),
                    path=item.get("Path"),
                )
            )

        return items

    async def search_items(
        self,
        query: str,
        media_type: Optional[MediaType] = None,
        limit: int = 20,
    ) -> list[LibraryItem]:
        """
        Search for items across all libraries.

        Args:
            query: Search query
            media_type: Filter by media type
            limit: Maximum results

        Returns:
            List of matching items
        """
        params = {
            "searchTerm": query,
            "Limit": limit,
            "Recursive": True,
            "Fields": "ProviderIds,Path",
        }

        if media_type == MediaType.MOVIE:
            params["IncludeItemTypes"] = "Movie"
        elif media_type == MediaType.SERIES:
            params["IncludeItemTypes"] = "Series"

        response = await self.get("/Items", params=params)
        response.raise_for_status()

        items = []
        for item in response.json().get("Items", []):
            provider_ids = item.get("ProviderIds", {})
            items.append(
                LibraryItem(
                    jellyfin_id=item["Id"],
                    title=item["Name"],
                    year=item.get("ProductionYear"),
                    media_type=self._map_item_type(item.get("Type", "")),
                    tmdb_id=int(provider_ids["Tmdb"]) if provider_ids.get("Tmdb") else None,
                    imdb_id=provider_ids.get("Imdb"),
                    tvdb_id=int(provider_ids["Tvdb"]) if provider_ids.get("Tvdb") else None,
                    library_id=item.get("ParentId", ""),
                    library_name="",
                    path=item.get("Path"),
                )
            )

        return items

    async def find_by_tmdb_id(
        self,
        tmdb_id: int,
        media_type: Optional[MediaType] = None,
        library_id: Optional[str] = None,
    ) -> Optional[LibraryItem]:
        """
        Find item by TMDb ID.

        Args:
            tmdb_id: TMDb ID
            media_type: Filter by media type
            library_id: Filter by library ID

        Returns:
            Library item if found
        """
        params = {
            "Recursive": True,
            "Fields": "ProviderIds,Path",
        }

        if library_id:
            params["ParentId"] = library_id

        if media_type == MediaType.MOVIE:
            params["IncludeItemTypes"] = "Movie"
        elif media_type == MediaType.SERIES:
            params["IncludeItemTypes"] = "Series"

        # Try different provider ID formats for Jellyfin compatibility
        # Format 1: HasTmdbId with specific search
        params["HasTmdbId"] = True

        response = await self.get("/Items", params=params)
        response.raise_for_status()

        items = response.json().get("Items", [])

        # Filter results to find exact TMDb ID match
        for item in items:
            provider_ids = item.get("ProviderIds", {})
            item_tmdb_id = provider_ids.get("Tmdb")

            if item_tmdb_id and str(item_tmdb_id) == str(tmdb_id):
                logger.debug(
                    f"[Jellyfin] TMDb lookup: {tmdb_id} -> found '{item['Name']}' ({item.get('ProductionYear')})"
                )
                return LibraryItem(
                    jellyfin_id=item["Id"],
                    title=item["Name"],
                    year=item.get("ProductionYear"),
                    media_type=self._map_item_type(item.get("Type", "")),
                    tmdb_id=int(item_tmdb_id),
                    imdb_id=provider_ids.get("Imdb"),
                    tvdb_id=int(provider_ids["Tvdb"]) if provider_ids.get("Tvdb") else None,
                    library_id=item.get("ParentId", ""),
                    library_name="",
                    path=item.get("Path"),
                )

        logger.debug(f"[Jellyfin] TMDb lookup: {tmdb_id} -> not found in library")
        return None

    # =========================================================================
    # Collections
    # =========================================================================

    async def get_collections(self, library_id: Optional[str] = None) -> list[dict[str, Any]]:
        """
        Get all collections.

        Args:
            library_id: Filter by library ID

        Returns:
            List of collections
        """
        params = {
            "IncludeItemTypes": "BoxSet",
            "Recursive": True,
            "Fields": "ChildCount",
        }

        if library_id:
            params["ParentId"] = library_id

        response = await self.get("/Items", params=params)
        response.raise_for_status()

        return response.json().get("Items", [])

    async def get_collection(self, collection_id: str) -> Optional[dict[str, Any]]:
        """Get collection details."""
        # Use /Items endpoint with Ids filter (more reliable than /Items/{id})
        params = {
            "Ids": collection_id,
            "Fields": "Overview,SortName,DisplayOrder",
        }
        response = await self.get("/Items", params=params)
        if response.status_code == 200:
            items = response.json().get("Items", [])
            return items[0] if items else None
        return None

    async def get_collection_items(self, collection_id: str) -> list[str]:
        """
        Get item IDs in a collection.

        Args:
            collection_id: Collection ID

        Returns:
            List of item IDs
        """
        params = {
            "ParentId": collection_id,
            "Fields": "ProviderIds",
        }

        response = await self.get("/Items", params=params)
        response.raise_for_status()

        return [item["Id"] for item in response.json().get("Items", [])]

    async def create_collection(
        self,
        name: str,
        item_ids: Optional[list[str]] = None,
    ) -> str:
        """
        Create a new collection.

        Args:
            name: Collection name
            item_ids: Optional initial item IDs

        Returns:
            Collection ID
        """
        params = {"Name": name}
        if item_ids:
            params["Ids"] = ",".join(item_ids)

        response = await self.post("/Collections", params=params)
        response.raise_for_status()

        collection_id = response.json().get("Id")
        logger.info(f"Created collection '{name}' with ID: {collection_id}")

        return collection_id

    async def add_to_collection(
        self,
        collection_id: str,
        item_ids: list[str],
    ) -> bool:
        """
        Add items to a collection.

        Args:
            collection_id: Collection ID
            item_ids: Item IDs to add

        Returns:
            True if successful
        """
        if not item_ids:
            return True

        response = await self.post(
            f"/Collections/{collection_id}/Items",
            params={"Ids": ",".join(item_ids)},
        )

        if response.status_code == 204:
            logger.debug(f"Added {len(item_ids)} items to collection {collection_id}")
            return True

        logger.error(f"Failed to add items to collection: {response.status_code}")
        return False

    async def remove_from_collection(
        self,
        collection_id: str,
        item_ids: list[str],
    ) -> bool:
        """
        Remove items from a collection.

        Args:
            collection_id: Collection ID
            item_ids: Item IDs to remove

        Returns:
            True if successful
        """
        if not item_ids:
            return True

        response = await self.delete(
            f"/Collections/{collection_id}/Items",
            params={"Ids": ",".join(item_ids)},
        )

        if response.status_code == 204:
            logger.debug(f"Removed {len(item_ids)} items from collection {collection_id}")
            return True

        logger.error(f"Failed to remove items from collection: {response.status_code}")
        return False

    async def delete_collection(self, collection_id: str) -> bool:
        """
        Delete a collection.

        Args:
            collection_id: Collection ID

        Returns:
            True if successful
        """
        response = await self.delete(f"/Items/{collection_id}")

        if response.status_code == 204:
            logger.info(f"Deleted collection {collection_id}")
            return True

        logger.error(f"Failed to delete collection: {response.status_code}")
        return False

    async def update_collection_metadata(
        self,
        collection_id: str,
        name: Optional[str] = None,
        overview: Optional[str] = None,
        sort_name: Optional[str] = None,
        display_order: Optional[str] = None,
    ) -> bool:
        """
        Update collection metadata.

        Args:
            collection_id: Collection ID
            name: New name
            overview: New description
            sort_name: Sort title
            display_order: Display order for items (e.g., "SortName", "PremiereDate", "DateCreated")

        Returns:
            True if successful
        """
        # First get current item data
        collection = await self.get_collection(collection_id)
        if not collection:
            return False

        # Update fields
        if name:
            collection["Name"] = name
        if overview:
            collection["Overview"] = overview
        if sort_name:
            collection["SortName"] = sort_name
        if display_order:
            collection["DisplayOrder"] = display_order

        response = await self.post(f"/Items/{collection_id}", json=collection)

        if response.status_code == 204:
            logger.debug(f"Updated metadata for collection {collection_id}")
            return True

        logger.error(f"Failed to update collection metadata: {response.status_code}")
        return False

    async def upload_collection_poster(
        self,
        collection_id: str,
        image_path: Path,
    ) -> bool:
        """
        Upload a poster image for a collection.

        Args:
            collection_id: Collection ID
            image_path: Path to the image file

        Returns:
            True if successful

        Raises:
            FileNotFoundError: If image file doesn't exist
            ValueError: If image format is not supported
        """
        if not image_path.exists():
            raise FileNotFoundError(f"Poster image not found: {image_path}")

        suffix = image_path.suffix.lower()
        if suffix not in SUPPORTED_IMAGE_FORMATS:
            raise ValueError(
                f"Unsupported image format: {suffix}. "
                f"Supported formats: {', '.join(SUPPORTED_IMAGE_FORMATS)}"
            )

        # Determine content type
        content_type = mimetypes.guess_type(str(image_path))[0]
        if not content_type:
            # Fallback mapping
            content_type_map = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
            }
            content_type = content_type_map.get(suffix, "image/jpeg")

        # Read and base64 encode image data
        # Jellyfin API requires base64-encoded image in the body, not raw binary
        # See: https://github.com/jellyfin/jellyfin/issues/12447
        image_data = image_path.read_bytes()
        b64_image = base64.b64encode(image_data).decode("utf-8")

        # Upload to Jellyfin - body is base64 string with image Content-Type
        response = await self.post_binary(
            f"/Items/{collection_id}/Images/Primary",
            content=b64_image.encode("utf-8"),
            content_type=content_type,
        )

        if response.status_code == 204:
            logger.info(f"Uploaded poster for collection {collection_id}")
            return True

        # Jellyfin may return 400 even on successful uploads (known bug)
        # Verify by checking if the image was actually uploaded
        if response.status_code == 400:
            images_response = await self.get(f"/Items/{collection_id}/Images")
            if images_response.status_code == 200:
                images = images_response.json()
                # Check if a Primary image now exists
                for img in images:
                    if img.get("ImageType") == "Primary":
                        logger.info(
                            f"Uploaded poster for collection {collection_id} "
                            "(API returned 400 but image was saved)"
                        )
                        return True

        logger.error(
            f"Failed to upload poster: {response.status_code} - {response.text}"
        )
        return False

    # =========================================================================
    # Helpers
    # =========================================================================

    def _map_item_type(self, jellyfin_type: str) -> MediaType:
        """Map Jellyfin item type to MediaType."""
        mapping = {
            "Movie": MediaType.MOVIE,
            "Series": MediaType.SERIES,
            "Season": MediaType.SEASON,
            "Episode": MediaType.EPISODE,
        }
        return mapping.get(jellyfin_type, MediaType.MOVIE)
