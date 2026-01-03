"""Telegram bot client for notifications."""

import json
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from loguru import logger


@dataclass
class TrendingItem:
    """Item in a trending collection."""

    title: str
    year: Optional[int] = None
    genres: Optional[list[str]] = None
    poster_url: Optional[str] = None  # Full TMDb poster URL
    tmdb_id: Optional[int] = None


class TelegramClient:
    """Client for sending Telegram bot notifications."""

    API_BASE = "https://api.telegram.org/bot{token}"
    TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w500"

    def __init__(
        self,
        bot_token: str,
        chat_id: str,
        trending_thread_id: Optional[int] = None,
    ):
        """
        Initialize Telegram client.

        Args:
            bot_token: Telegram bot token from @BotFather
            chat_id: Chat ID to send messages to
            trending_thread_id: Optional thread/topic ID for trending notifications
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.trending_thread_id = trending_thread_id
        self.api_base = self.API_BASE.format(token=bot_token)

    async def _request(
        self,
        method: str,
        data: Optional[dict[str, Any]] = None,
        files: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """Make API request to Telegram."""
        url = f"{self.api_base}/{method}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if files:
                    response = await client.post(url, data=data, files=files)
                else:
                    response = await client.post(url, json=data)

                if response.status_code == 200:
                    result = response.json()
                    if result.get("ok"):
                        return result.get("result")
                    else:
                        logger.warning(f"Telegram API error: {result.get('description')}")
                else:
                    logger.warning(f"Telegram request failed: {response.status_code} - {response.text}")

        except Exception as e:
            logger.error(f"Failed to send Telegram request: {e}")

        return None

    async def send_message(
        self,
        text: str,
        thread_id: Optional[int] = None,
        parse_mode: str = "HTML",
        disable_preview: bool = True,
    ) -> bool:
        """
        Send a text message.

        Args:
            text: Message text (HTML or Markdown)
            thread_id: Optional thread/topic ID
            parse_mode: HTML or Markdown
            disable_preview: Disable link previews
        """
        data: dict[str, Any] = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        }

        if thread_id:
            data["message_thread_id"] = thread_id

        result = await self._request("sendMessage", data)
        return result is not None

    async def send_photo(
        self,
        photo_url: str,
        caption: Optional[str] = None,
        thread_id: Optional[int] = None,
        parse_mode: str = "HTML",
    ) -> bool:
        """
        Send a photo by URL.

        Args:
            photo_url: URL of the photo
            caption: Optional caption
            thread_id: Optional thread/topic ID
            parse_mode: HTML or Markdown
        """
        data: dict[str, Any] = {
            "chat_id": self.chat_id,
            "photo": photo_url,
        }

        if caption:
            data["caption"] = caption
            data["parse_mode"] = parse_mode

        if thread_id:
            data["message_thread_id"] = thread_id

        result = await self._request("sendPhoto", data)
        return result is not None

    async def send_media_group(
        self,
        items: list[TrendingItem],
        thread_id: Optional[int] = None,
    ) -> bool:
        """
        Send a media group (multiple photos).

        Args:
            items: List of TrendingItem with poster URLs
            thread_id: Optional thread/topic ID

        Note: Telegram supports max 10 items per media group.
        """
        if not items:
            return False

        # Filter items with valid poster URLs (max 10)
        valid_items = [i for i in items if i.poster_url][:10]

        if not valid_items:
            logger.debug("No items with poster URLs for media group")
            return False

        media = []
        for i, item in enumerate(valid_items):
            # Build caption for first item only (Telegram shows it for the group)
            caption = None
            if i == 0:
                lines = []
                for idx, it in enumerate(valid_items, 1):
                    genre_str = f" • {', '.join(it.genres[:2])}" if it.genres else ""
                    year_str = f" ({it.year})" if it.year else ""
                    lines.append(f"{idx}. <b>{it.title}</b>{year_str}{genre_str}")
                caption = "\n".join(lines)

            media_item: dict[str, Any] = {
                "type": "photo",
                "media": item.poster_url,
            }

            if caption:
                media_item["caption"] = caption
                media_item["parse_mode"] = "HTML"

            media.append(media_item)

        data: dict[str, Any] = {
            "chat_id": self.chat_id,
            "media": json.dumps(media),
        }

        if thread_id:
            data["message_thread_id"] = thread_id

        result = await self._request("sendMediaGroup", data)
        return result is not None

    async def send_trending_notification(
        self,
        films: list[TrendingItem],
        series: list[TrendingItem],
    ) -> bool:
        """
        Send trending notification with films and series.

        Args:
            films: Top trending films
            series: Top trending series
        """
        thread_id = self.trending_thread_id

        # Build header message
        header_lines = [
            "📊 <b>Tendances du jour</b>",
            "",
        ]

        if films:
            header_lines.append(f"🎬 <b>Films</b> ({len(films)} titres)")
        if series:
            header_lines.append(f"📺 <b>Séries</b> ({len(series)} titres)")

        # Send header
        header_text = "\n".join(header_lines)
        await self.send_message(header_text, thread_id=thread_id)

        success = True

        # Send films media group
        if films:
            films_header = "🎬 <b>Top Films</b>"
            await self.send_message(films_header, thread_id=thread_id)

            if not await self.send_media_group(films, thread_id=thread_id):
                # Fallback to text list if media group fails
                await self._send_text_list(films, "Films", thread_id)
                success = False

        # Send series media group
        if series:
            series_header = "📺 <b>Top Séries</b>"
            await self.send_message(series_header, thread_id=thread_id)

            if not await self.send_media_group(series, thread_id=thread_id):
                # Fallback to text list if media group fails
                await self._send_text_list(series, "Séries", thread_id)
                success = False

        return success

    async def _send_text_list(
        self,
        items: list[TrendingItem],
        category: str,
        thread_id: Optional[int] = None,
    ) -> bool:
        """Send items as text list (fallback if media group fails)."""
        lines = [f"<b>{category}</b>", ""]

        for idx, item in enumerate(items[:10], 1):
            genre_str = f" • {', '.join(item.genres[:2])}" if item.genres else ""
            year_str = f" ({item.year})" if item.year else ""
            lines.append(f"{idx}. <b>{item.title}</b>{year_str}{genre_str}")

        text = "\n".join(lines)
        return await self.send_message(text, thread_id=thread_id)

    @classmethod
    def build_poster_url(cls, poster_path: Optional[str]) -> Optional[str]:
        """
        Build full TMDb poster URL from path.

        Args:
            poster_path: TMDb poster path (e.g., "/abc123.jpg")

        Returns:
            Full URL or None
        """
        if not poster_path:
            return None
        return f"{cls.TMDB_POSTER_BASE}{poster_path}"
