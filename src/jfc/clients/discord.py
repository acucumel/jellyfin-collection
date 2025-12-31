"""Discord webhook client for notifications."""

import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

import httpx
from loguru import logger

if TYPE_CHECKING:
    from jfc.models.report import CollectionReport, RunReport


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

    async def _send_with_file(
        self,
        url: str,
        embeds: list[dict[str, Any]],
        file_path: Path,
        username: str = "Jellyfin Collection",
    ) -> bool:
        """
        Send webhook message with file attachment.

        Args:
            url: Webhook URL
            embeds: List of embed objects
            file_path: Path to the file to attach
            username: Bot username to display
        """
        if not url:
            logger.debug("No webhook URL configured, skipping notification")
            return False

        if not file_path.exists():
            logger.warning(f"File not found for Discord upload: {file_path}")
            return await self._send(url, embeds=embeds, username=username)

        try:
            # Prepare multipart form data
            payload = {
                "username": username,
                "embeds": embeds,
            }

            # Read the file
            with open(file_path, "rb") as f:
                file_content = f.read()

            # Create multipart form
            files = {
                "file": (file_path.name, file_content, "image/png"),
            }

            # payload_json must be sent as form field, not JSON body
            data = {
                "payload_json": json.dumps(payload),
            }

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(url, data=data, files=files)

                if response.status_code == 200:
                    logger.debug(f"Discord notification with image sent successfully")
                    return True
                else:
                    logger.warning(f"Discord webhook returned {response.status_code}: {response.text}")
                    return False

        except Exception as e:
            logger.error(f"Failed to send Discord notification with file: {e}")
            # Fallback to sending without file
            return await self._send(url, embeds=embeds, username=username)

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
        radarr_requests: int = 0,
        sonarr_requests: int = 0,
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
                    "name": "Collections",
                    "value": str(collections_updated),
                    "inline": True,
                },
                {
                    "name": "Changes",
                    "value": f"+{items_added} / -{items_removed}",
                    "inline": True,
                },
            ],
            "timestamp": datetime.utcnow().isoformat(),
        }

        if radarr_requests > 0 or sonarr_requests > 0:
            arr_str = []
            if radarr_requests > 0:
                arr_str.append(f"Radarr: {radarr_requests}")
            if sonarr_requests > 0:
                arr_str.append(f"Sonarr: {sonarr_requests}")
            embed["fields"].append(
                {
                    "name": "Requests",
                    "value": " | ".join(arr_str),
                    "inline": True,
                }
            )

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
        items_fetched: int = 0,
        items_matched: int = 0,
        items_missing: int = 0,
        match_rate: float = 0.0,
        source_provider: str = "",
        radarr_titles: Optional[list[str]] = None,
        sonarr_titles: Optional[list[str]] = None,
    ) -> bool:
        """Send collection changes notification."""
        url = self._get_url("changes")
        if not url:
            return False

        # Determine if there's any interesting info to report
        has_changes = added or removed
        has_arr_requests = (radarr_titles and len(radarr_titles) > 0) or (sonarr_titles and len(sonarr_titles) > 0)

        if not has_changes and not has_arr_requests:
            return True  # Nothing to report

        # Color based on match rate
        if match_rate >= 90:
            color = 3066993  # Green
        elif match_rate >= 70:
            color = 16776960  # Yellow
        else:
            color = 15105570  # Orange

        embed = {
            "title": f"{collection_name}",
            "description": f"**Library:** {library}\n**Source:** {source_provider}",
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "fields": [
                {
                    "name": "Stats",
                    "value": f"Fetched: {items_fetched} | Matched: {items_matched} | Missing: {items_missing}",
                    "inline": False,
                },
                {
                    "name": "Match Rate",
                    "value": f"{match_rate:.1f}%",
                    "inline": True,
                },
            ],
        }

        if has_changes:
            changes_str = f"+{len(added)} / -{len(removed)}"
            embed["fields"].append(
                {
                    "name": "Collection Changes",
                    "value": changes_str,
                    "inline": True,
                }
            )

        if added:
            added_str = "\n".join(f"+ {item}" for item in added[:8])
            if len(added) > 8:
                added_str += f"\n*... and {len(added) - 8} more*"
            embed["fields"].append(
                {
                    "name": f"Added ({len(added)})",
                    "value": added_str or "None",
                    "inline": False,
                }
            )

        if removed:
            removed_str = "\n".join(f"- {item}" for item in removed[:8])
            if len(removed) > 8:
                removed_str += f"\n*... and {len(removed) - 8} more*"
            embed["fields"].append(
                {
                    "name": f"Removed ({len(removed)})",
                    "value": removed_str or "None",
                    "inline": False,
                }
            )

        if radarr_titles:
            radarr_str = "\n".join(f"• {item}" for item in radarr_titles[:5])
            if len(radarr_titles) > 5:
                radarr_str += f"\n*... and {len(radarr_titles) - 5} more*"
            embed["fields"].append(
                {
                    "name": f"Sent to Radarr ({len(radarr_titles)})",
                    "value": radarr_str,
                    "inline": False,
                }
            )

        if sonarr_titles:
            sonarr_str = "\n".join(f"• {item}" for item in sonarr_titles[:5])
            if len(sonarr_titles) > 5:
                sonarr_str += f"\n*... and {len(sonarr_titles) - 5} more*"
            embed["fields"].append(
                {
                    "name": f"Sent to Sonarr ({len(sonarr_titles)})",
                    "value": sonarr_str,
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

    async def send_collection_report(
        self,
        collection_name: str,
        library: str,
        source_provider: str,
        items_fetched: int,
        items_after_filters: int,
        items_matched: int,
        items_missing: int,
        match_rate: float,
        items_added: int,
        items_removed: int,
        radarr_requests: int = 0,
        sonarr_requests: int = 0,
        matched_titles: Optional[list[str]] = None,
        added_titles: Optional[list[str]] = None,
        missing_titles: Optional[list[str]] = None,
        radarr_titles: Optional[list[str]] = None,
        sonarr_titles: Optional[list[str]] = None,
        poster_path: Optional[Path] = None,
        success: bool = True,
        error_message: Optional[str] = None,
    ) -> bool:
        """
        Send rich collection report notification with poster image.

        Args:
            collection_name: Name of the collection
            library: Library name (Films, Séries, Cartoons)
            source_provider: Data source (TMDb Trending, Trakt Popular, etc.)
            items_fetched: Number of items fetched from source
            items_after_filters: Items remaining after filters applied
            items_matched: Items found in Jellyfin library
            items_missing: Items not in library
            match_rate: Percentage of items matched
            items_added: Items added to collection
            items_removed: Items removed from collection
            radarr_requests: Number of requests sent to Radarr
            sonarr_requests: Number of requests sent to Sonarr
            matched_titles: All titles matched in Jellyfin library
            added_titles: Titles newly added to collection
            missing_titles: Titles not in library
            radarr_titles: Titles sent to Radarr
            sonarr_titles: Titles sent to Sonarr
            poster_path: Path to generated poster image
            success: Whether the sync was successful
            error_message: Error message if failed
        """
        url = self._get_url("changes")
        if not url:
            return False

        # Skip if nothing interesting happened
        if items_added == 0 and items_removed == 0 and radarr_requests == 0 and sonarr_requests == 0:
            logger.debug(f"No changes for {collection_name}, skipping Discord notification")
            return True

        # Color based on status and match rate
        if not success:
            color = 15158332  # Red - error
        elif match_rate >= 90:
            color = 3066993  # Green - excellent
        elif match_rate >= 70:
            color = 16776960  # Yellow - good
        elif match_rate >= 50:
            color = 15105570  # Orange - moderate
        else:
            color = 15158332  # Red - poor

        # Library emoji
        library_emoji = {
            "Films": "🎬",
            "Séries": "📺",
            "Cartoons": "🎨",
        }.get(library, "📁")

        # Build embed
        embed: dict[str, Any] = {
            "author": {
                "name": f"{library_emoji} {library}",
            },
            "title": collection_name,
            "color": color,
            "timestamp": datetime.utcnow().isoformat(),
            "fields": [],
            "footer": {
                "text": f"Source: {source_provider}",
            },
        }

        # Add error message if failed
        if not success and error_message:
            embed["description"] = f"❌ **Error:** {error_message[:200]}"
            return await self._send(url, embeds=[embed])

        # Stats summary line
        stats_parts = [f"📊 {items_fetched} fetched"]
        if items_after_filters != items_fetched:
            stats_parts.append(f"🔍 {items_after_filters} filtered")
        stats_parts.append(f"✅ {items_matched} matched ({match_rate:.0f}%)")
        if items_missing > 0:
            stats_parts.append(f"❌ {items_missing} missing")

        embed["description"] = " → ".join(stats_parts)

        # Build unified item list
        added_set = set(added_titles or [])
        radarr_set = set(radarr_titles or [])
        sonarr_set = set(sonarr_titles or [])

        item_lines: list[str] = []

        # Add matched items (in library)
        for title in (matched_titles or []):
            if title in added_set:
                item_lines.append(f"✅ {title} `(new)`")
            else:
                item_lines.append(f"✅ {title}")

        # Add missing items
        for title in (missing_titles or []):
            if title in radarr_set:
                item_lines.append(f"❌ {title} `→ Radarr`")
            elif title in sonarr_set:
                item_lines.append(f"❌ {title} `→ Sonarr`")
            else:
                item_lines.append(f"❌ {title} `(missing)`")

        # Format item list field (Discord limit: 1024 chars per field)
        if item_lines:
            total_items = len(item_lines)
            # Show up to 15 items, then truncate
            max_items = 15
            display_lines = item_lines[:max_items]
            items_text = "\n".join(display_lines)

            if total_items > max_items:
                items_text += f"\n*... +{total_items - max_items} more*"

            # Truncate if still too long
            if len(items_text) > 1020:
                items_text = items_text[:1020] + "..."

            embed["fields"].append({
                "name": f"📋 Collection ({total_items} items)",
                "value": items_text,
                "inline": False,
            })

        # Summary of changes (inline fields)
        if items_added > 0 or items_removed > 0:
            changes_parts = []
            if items_added > 0:
                changes_parts.append(f"+{items_added} added")
            if items_removed > 0:
                changes_parts.append(f"-{items_removed} removed")
            embed["fields"].append({
                "name": "📝 Changes",
                "value": " / ".join(changes_parts),
                "inline": True,
            })

        if radarr_requests > 0:
            embed["fields"].append({
                "name": "🎥 Radarr",
                "value": f"{radarr_requests} requested",
                "inline": True,
            })

        if sonarr_requests > 0:
            embed["fields"].append({
                "name": "📺 Sonarr",
                "value": f"{sonarr_requests} requested",
                "inline": True,
            })

        # If poster exists, attach it as the main image
        if poster_path and poster_path.exists():
            embed["image"] = {"url": f"attachment://{poster_path.name}"}
            return await self._send_with_file(url, embeds=[embed], file_path=poster_path)
        else:
            return await self._send(url, embeds=[embed])
