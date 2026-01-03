"""Telegram bot client for notifications with AI-generated messages."""

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

import httpx
from loguru import logger
from openai import AsyncOpenAI

if TYPE_CHECKING:
    from jfc.core.config import TelegramNotification


# =============================================================================
# DATA MODELS
# =============================================================================


@dataclass
class TrendingItem:
    """Item in a trending collection."""

    title: str
    year: Optional[int] = None
    genres: Optional[list[str]] = None
    poster_url: Optional[str] = None  # Full TMDb poster URL
    tmdb_id: Optional[int] = None
    available: bool = False  # Available in Jellyfin


@dataclass
class NotificationContext:
    """Context data passed to GPT for message generation."""

    trigger: str  # "trending", "new_items", "run_end"
    films: list[TrendingItem] = field(default_factory=list)
    series: list[TrendingItem] = field(default_factory=list)
    # Stats for run_end trigger
    duration_seconds: float = 0
    collections_updated: int = 0
    items_added: int = 0
    items_removed: int = 0

    def to_context_string(self) -> str:
        """Convert context to string for GPT prompt."""
        lines = [f"TRIGGER: {self.trigger}", ""]

        if self.films:
            lines.append("FILMS TENDANCES:")
            for i, f in enumerate(self.films[:10], 1):
                status = "✓ disponible" if f.available else "✗ non disponible"
                genres = f", genres: {', '.join(f.genres)}" if f.genres else ""
                year = f" ({f.year})" if f.year else ""
                lines.append(f"  {i}. {f.title}{year} [{status}]{genres}")
            lines.append("")

        if self.series:
            lines.append("SÉRIES TENDANCES:")
            for i, s in enumerate(self.series[:10], 1):
                status = "✓ disponible" if s.available else "✗ non disponible"
                genres = f", genres: {', '.join(s.genres)}" if s.genres else ""
                year = f" ({s.year})" if s.year else ""
                lines.append(f"  {i}. {s.title}{year} [{status}]{genres}")
            lines.append("")

        if self.trigger == "run_end":
            lines.append("STATISTIQUES DU RUN:")
            minutes = int(self.duration_seconds // 60)
            seconds = int(self.duration_seconds % 60)
            lines.append(f"  Durée: {minutes}m {seconds}s")
            lines.append(f"  Collections mises à jour: {self.collections_updated}")
            lines.append(f"  Items ajoutés: {self.items_added}")
            lines.append(f"  Items retirés: {self.items_removed}")

        return "\n".join(lines)


# =============================================================================
# TELEGRAM CLIENT
# =============================================================================


class TelegramClient:
    """Client for sending Telegram bot notifications with AI-generated messages."""

    API_BASE = "https://api.telegram.org/bot{token}"
    TMDB_POSTER_BASE = "https://image.tmdb.org/t/p/w500"
    GPT_MODEL = "gpt-5.1"

    def __init__(
        self,
        bot_token: str,
        openai_api_key: Optional[str] = None,
    ):
        """
        Initialize Telegram client.

        Args:
            bot_token: Telegram bot token from @BotFather
            openai_api_key: OpenAI API key for AI message generation
        """
        self.bot_token = bot_token
        self.api_base = self.API_BASE.format(token=bot_token)

        # OpenAI client for AI message generation
        self.openai: Optional[AsyncOpenAI] = None
        if openai_api_key:
            self.openai = AsyncOpenAI(api_key=openai_api_key)

    # =========================================================================
    # TELEGRAM API METHODS
    # =========================================================================

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
        chat_id: str,
        text: str,
        thread_id: Optional[int] = None,
        parse_mode: str = "HTML",
        disable_preview: bool = True,
    ) -> bool:
        """
        Send a text message.

        Args:
            chat_id: Chat ID to send to
            text: Message text (HTML or Markdown)
            thread_id: Optional thread/topic ID
            parse_mode: HTML or Markdown
            disable_preview: Disable link previews
        """
        data: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
            "disable_web_page_preview": disable_preview,
        }

        if thread_id:
            data["message_thread_id"] = thread_id

        result = await self._request("sendMessage", data)
        return result is not None

    async def send_media_group(
        self,
        chat_id: str,
        items: list[TrendingItem],
        thread_id: Optional[int] = None,
        caption: Optional[str] = None,
    ) -> bool:
        """
        Send a media group (multiple photos).

        Args:
            chat_id: Chat ID to send to
            items: List of TrendingItem with poster URLs
            thread_id: Optional thread/topic ID
            caption: Optional caption for the first photo

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
            media_item: dict[str, Any] = {
                "type": "photo",
                "media": item.poster_url,
            }

            # Add caption to first item only
            if i == 0 and caption:
                media_item["caption"] = caption[:1024]  # Telegram limit
                media_item["parse_mode"] = "HTML"

            media.append(media_item)

        data: dict[str, Any] = {
            "chat_id": chat_id,
            "media": json.dumps(media),
        }

        if thread_id:
            data["message_thread_id"] = thread_id

        result = await self._request("sendMediaGroup", data)
        return result is not None

    # =========================================================================
    # AI MESSAGE GENERATION
    # =========================================================================

    async def generate_ai_message(
        self,
        prompt: str,
        context: NotificationContext,
    ) -> Optional[str]:
        """
        Generate a notification message using GPT-5.1.

        Args:
            prompt: User-defined prompt describing the style/tone
            context: Context data (trending items, stats, etc.)

        Returns:
            Generated message or None if failed
        """
        if not self.openai:
            logger.warning("OpenAI not configured, cannot generate AI message")
            return None

        full_prompt = f"""Tu es un assistant qui génère des messages de notification Telegram.

INSTRUCTIONS DU STYLE:
{prompt}

CONTEXTE (données à utiliser):
{context.to_context_string()}

RÈGLES:
- Génère UNIQUEMENT le message, pas d'explications
- Utilise le format HTML pour Telegram (<b>gras</b>, <i>italique</i>, etc.)
- Reste concis (max 500 caractères pour le message principal)
- Si le contexte mentionne "disponible", concentre-toi sur ces items
- Utilise des emojis si approprié au style demandé

MESSAGE:"""

        try:
            response = await self.openai.chat.completions.create(
                model=self.GPT_MODEL,
                messages=[{"role": "user", "content": full_prompt}],
                max_completion_tokens=300,
                reasoning_effort="low",
            )

            content = response.choices[0].message.content
            if content:
                return content.strip()

        except Exception as e:
            logger.error(f"Failed to generate AI message: {e}")

        return None

    # =========================================================================
    # NOTIFICATION PROCESSING
    # =========================================================================

    async def process_notification(
        self,
        notification: "TelegramNotification",
        context: NotificationContext,
    ) -> bool:
        """
        Process a notification configuration and send to Telegram.

        Args:
            notification: Notification configuration
            context: Context data for the notification

        Returns:
            True if successful
        """
        chat_id = notification.chat_id
        thread_id = notification.thread_id

        # Filter items based on only_available setting
        films = context.films
        series = context.series

        if notification.only_available:
            films = [f for f in films if f.available]
            series = [s for s in series if s.available]

        # Check minimum items
        total_items = len(films) + len(series)
        if total_items < notification.min_items:
            logger.debug(
                f"Notification '{notification.name}' skipped: "
                f"{total_items} items < {notification.min_items} min"
            )
            return True  # Not an error, just skipped

        # Generate AI message if prompt is provided
        message: Optional[str] = None
        if notification.prompt and self.openai:
            # Create filtered context for AI
            filtered_context = NotificationContext(
                trigger=context.trigger,
                films=films,
                series=series,
                duration_seconds=context.duration_seconds,
                collections_updated=context.collections_updated,
                items_added=context.items_added,
                items_removed=context.items_removed,
            )
            message = await self.generate_ai_message(notification.prompt, filtered_context)

        # Fallback to default message if AI failed or no prompt
        if not message:
            message = self._build_default_message(films, series, context.trigger)

        # Send the message
        success = await self.send_message(chat_id, message, thread_id=thread_id)

        # Send media groups if configured
        if notification.include_posters and success:
            if films:
                films_caption = self._build_list_caption(films, "Films")
                await self.send_media_group(chat_id, films, thread_id=thread_id, caption=films_caption)

            if series:
                series_caption = self._build_list_caption(series, "Séries")
                await self.send_media_group(chat_id, series, thread_id=thread_id, caption=series_caption)

        logger.info(f"Telegram notification '{notification.name}' sent to {chat_id}")
        return success

    def _build_default_message(
        self,
        films: list[TrendingItem],
        series: list[TrendingItem],
        trigger: str,
    ) -> str:
        """Build default message when AI is not available."""
        lines = ["📊 <b>Mise à jour des collections</b>", ""]

        if films:
            lines.append(f"🎬 <b>{len(films)} films</b> en tendance")
        if series:
            lines.append(f"📺 <b>{len(series)} séries</b> en tendance")

        return "\n".join(lines)

    def _build_list_caption(self, items: list[TrendingItem], category: str) -> str:
        """Build caption for media group."""
        lines = [f"<b>{category}</b>", ""]

        for idx, item in enumerate(items[:10], 1):
            year_str = f" ({item.year})" if item.year else ""
            genre_str = f" • {', '.join(item.genres[:2])}" if item.genres else ""
            lines.append(f"{idx}. <b>{item.title}</b>{year_str}{genre_str}")

        return "\n".join(lines)

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

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
