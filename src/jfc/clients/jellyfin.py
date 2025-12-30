"""Jellyfin API client for managing collections and media."""

from typing import Any, Optional

from loguru import logger

from jfc.clients.base import BaseClient
from jfc.models.media import LibraryItem, MediaType


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
    ) -> Optional[LibraryItem]:
        """
        Find item by TMDb ID.

        Args:
            tmdb_id: TMDb ID
            media_type: Filter by media type

        Returns:
            Library item if found
        """
        params = {
            "AnyProviderIdEquals": f"Tmdb.{tmdb_id}",
            "Recursive": True,
            "Fields": "ProviderIds,Path",
            "Limit": 1,
        }

        if media_type == MediaType.MOVIE:
            params["IncludeItemTypes"] = "Movie"
        elif media_type == MediaType.SERIES:
            params["IncludeItemTypes"] = "Series"

        response = await self.get("/Items", params=params)
        response.raise_for_status()

        items = response.json().get("Items", [])
        if items:
            item = items[0]
            provider_ids = item.get("ProviderIds", {})
            return LibraryItem(
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
        response = await self.get(f"/Items/{collection_id}")
        if response.status_code == 200:
            return response.json()
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
    ) -> bool:
        """
        Update collection metadata.

        Args:
            collection_id: Collection ID
            name: New name
            overview: New description
            sort_name: Sort title

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

        response = await self.post(f"/Items/{collection_id}", json=collection)

        if response.status_code == 204:
            logger.debug(f"Updated metadata for collection {collection_id}")
            return True

        logger.error(f"Failed to update collection metadata: {response.status_code}")
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
