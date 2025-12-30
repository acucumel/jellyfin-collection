"""Discord webhook client for notifications."""

from datetime import datetime
from typing import Any, Optional

import httpx
from loguru import logger


class DiscordWebhook:
    """Client for sending Discord webhook notifications."""

    def __init__(
        self,
        default_url: Optional[str] = None,
        error_url: Optional[str] = None,
        run_start_url: Optional[str] = None,
        run_end_url: Optional[str] = None,
        changes_url: Optional[str] = None,
    ):
        """
        Initialize Discord webhook client.

        Args:
            default_url: Default webhook URL
            error_url: Webhook URL for errors
            run_start_url: Webhook URL for run start notifications
            run_end_url: Webhook URL for run end notifications
            changes_url: Webhook URL for change notifications
        """
        self.default_url = default_url
        self.error_url = error_url or default_url
        self.run_start_url = run_start_url or default_url
        self.run_end_url = run_end_url or default_url
        self.changes_url = changes_url or default_url

    def _get_url(self, event_type: str) -> Optional[str]:
        """Get webhook URL for event type."""
        urls = {
            "error": self.error_url,
            "run_start": self.run_start_url,
            "run_end": self.run_end_url,
            "changes": self.changes_url,
        }
        return urls.get(event_type, self.default_url)

    async def _send(
        self,
        url: str,
        content: Optional[str] = None,
        embeds: Optional[list[dict[str, Any]]] = None,
        username: str = "Jellyfin Collection",
    ) -> bool:
        """Send webhook message."""
        if not url:
            logger.debug("No webhook URL configured, skipping notification")
            return False

        payload: dict[str, Any] = {"username": username}

        if content:
            payload["content"] = content
        if embeds:
            payload["embeds"] = embeds

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(url, json=payload)

                if response.status_code == 204:
                    logger.debug("Discord notification sent successfully")
                    return True
                else:
                    logger.warning(f"Discord webhook returned {response.status_code}")
                    return False

        except Exception as e:
            logger.error(f"Failed to send Discord notification: {e}")
            return False

    # =========================================================================
    # Event Notifications
    # =========================================================================

    async def send_run_start(
        self,
        libraries: list[str],
        scheduled: bool = False,
    ) -> bool:
        """Send run start notification."""
        url = self._get_url("run_start")
        if not url:
            return False

        embed = {
            "title": "Collection Update Started",
            "description": f"Processing {len(libraries)} libraries",
            "color": 3447003,  # Blue
            "fields": [
                {
                    "name": "Libraries",
                    "value": "\n".join(f"- {lib}" for lib in libraries) or "All",
                    "inline": False,
                },
                {
                    "name": "Trigger",
                    "value": "Scheduled" if scheduled else "Manual",
                    "inline": True,
                },
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        return await self._send(url, embeds=[embed])

    async def send_run_end(
        self,
        duration_seconds: float,
        collections_updated: int,
        items_added: int,
        items_removed: int,
        errors: int = 0,
    ) -> bool:
        """Send run end notification."""
        url = self._get_url("run_end")
        if not url:
            return False

        # Format duration
        minutes = int(duration_seconds // 60)
        seconds = int(duration_seconds % 60)
        duration_str = f"{minutes}m {seconds}s" if minutes > 0 else f"{seconds}s"

        # Color based on errors
        color = 15158332 if errors > 0 else 3066993  # Red or Green

        embed = {
            "title": "Collection Update Completed",
            "color": color,
            "fields": [
                {
                    "name": "Duration",
                    "value": duration_str,
                    "inline": True,
                },
                {
                    "name": "Collections Updated",
                    "value": str(collections_updated),
                    "inline": True,
                },
                {
                    "name": "Items Added",
                    "value": str(items_added),
                    "inline": True,
                },
                {
                    "name": "Items Removed",
                    "value": str(items_removed),
                    "inline": True,
                },
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        if errors > 0:
            embed["fields"].append(
                {
                    "name": "Errors",
                    "value": str(errors),
                    "inline": True,
                }
            )

        return await self._send(url, embeds=[embed])

    async def send_error(
        self,
        title: str,
        message: str,
        traceback: Optional[str] = None,
    ) -> bool:
        """Send error notification."""
        url = self._get_url("error")
        if not url:
            return False

        embed = {
            "title": f"Error: {title}",
            "description": message[:2000],  # Discord limit
            "color": 15158332,  # Red
            "timestamp": datetime.utcnow().isoformat(),
        }

        if traceback:
            # Truncate traceback if too long
            tb = traceback[:1000] if len(traceback) > 1000 else traceback
            embed["fields"] = [
                {
                    "name": "Traceback",
                    "value": f"```\n{tb}\n```",
                    "inline": False,
                }
            ]

        return await self._send(url, embeds=[embed])

    async def send_collection_changes(
        self,
        collection_name: str,
        library: str,
        added: list[str],
        removed: list[str],
    ) -> bool:
        """Send collection changes notification."""
        url = self._get_url("changes")
        if not url:
            return False

        if not added and not removed:
            return True  # Nothing to report

        embed = {
            "title": f"Collection Updated: {collection_name}",
            "description": f"Library: {library}",
            "color": 16776960,  # Yellow
            "timestamp": datetime.utcnow().isoformat(),
            "fields": [],
        }

        if added:
            added_str = "\n".join(f"+ {item}" for item in added[:10])
            if len(added) > 10:
                added_str += f"\n... and {len(added) - 10} more"
            embed["fields"].append(
                {
                    "name": f"Added ({len(added)})",
                    "value": added_str or "None",
                    "inline": False,
                }
            )

        if removed:
            removed_str = "\n".join(f"- {item}" for item in removed[:10])
            if len(removed) > 10:
                removed_str += f"\n... and {len(removed) - 10} more"
            embed["fields"].append(
                {
                    "name": f"Removed ({len(removed)})",
                    "value": removed_str or "None",
                    "inline": False,
                }
            )

        return await self._send(url, embeds=[embed])

    async def send_media_requested(
        self,
        title: str,
        year: Optional[int],
        media_type: str,
        destination: str,  # "Radarr" or "Sonarr"
        collection: str,
    ) -> bool:
        """Send notification when media is requested in Radarr/Sonarr."""
        url = self._get_url("changes")
        if not url:
            return False

        year_str = f" ({year})" if year else ""

        embed = {
            "title": f"Media Requested: {title}{year_str}",
            "description": f"Added to {destination}",
            "color": 10181046,  # Purple
            "fields": [
                {
                    "name": "Type",
                    "value": media_type.capitalize(),
                    "inline": True,
                },
                {
                    "name": "Collection",
                    "value": collection,
                    "inline": True,
                },
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        return await self._send(url, embeds=[embed])
