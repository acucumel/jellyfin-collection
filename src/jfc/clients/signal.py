"""Signal client for notifications via signal-cli-rest-api."""

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

import httpx
from loguru import logger

if TYPE_CHECKING:
    from jfc.core.config import SignalNotification


# =============================================================================
# DATA MODELS (reuse from telegram for consistency)
# =============================================================================


@dataclass
class TrendingItem:
    """Item in a trending collection."""

    title: str
    year: Optional[int] = None
    genres: Optional[list[str]] = None
    poster_url: Optional[str] = None
    tmdb_id: Optional[int] = None
    available: bool = False


@dataclass
class NotificationContext:
    """Context data passed to GPT for message generation."""

    trigger: str  # "trending", "new_items", "run_end"
    films: list[TrendingItem] = field(default_factory=list)
    series: list[TrendingItem] = field(default_factory=list)
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
# SIGNAL CLIENT
# =============================================================================


class SignalClient:
    """Client for sending Signal notifications via signal-cli-rest-api.

    Requires signal-cli-rest-api container running.
    See: https://github.com/bbernhard/signal-cli-rest-api
    """

    GPT_MODEL = "gpt-5.1"

    def __init__(
        self,
        api_url: str,
        phone_number: str,
        openai_api_key: Optional[str] = None,
    ):
        """
        Initialize Signal client.

        Args:
            api_url: URL of signal-cli-rest-api (e.g., http://signal:8080)
            phone_number: Registered Signal phone number (e.g., +33612345678)
            openai_api_key: OpenAI API key for AI message generation
        """
        self.api_url = api_url.rstrip("/")
        self.phone_number = phone_number

        # OpenAI client for AI message generation
        self.openai = None
        if openai_api_key:
            from openai import AsyncOpenAI
            self.openai = AsyncOpenAI(api_key=openai_api_key)

    # =========================================================================
    # SIGNAL API METHODS
    # =========================================================================

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        """Make API request to signal-cli-rest-api."""
        url = f"{self.api_url}{endpoint}"

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if method == "GET":
                    response = await client.get(url)
                else:
                    response = await client.post(url, json=data)

                if response.status_code in (200, 201):
                    return response.json() if response.text else {}
                else:
                    logger.warning(
                        f"Signal API error: {response.status_code} - {response.text}"
                    )

        except Exception as e:
            logger.error(f"Failed to send Signal request: {e}")

        return None

    async def health_check(self) -> bool:
        """Check if signal-cli-rest-api is available."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.api_url}/v1/about")
                return response.status_code == 200
        except Exception:
            return False

    async def send_message(
        self,
        recipient: str,
        text: str,
    ) -> bool:
        """
        Send a text message via Signal.

        Args:
            recipient: Phone number or group ID
            text: Message text

        Returns:
            True if successful
        """
        # Determine if recipient is a group or individual
        is_group = recipient.startswith("group.")

        data: dict[str, Any] = {
            "message": text,
            "number": self.phone_number,
            "text_mode": "styled",  # Support basic formatting
        }

        if is_group:
            # Group ID format: group.XXXXX
            data["recipients"] = [recipient]
        else:
            # Individual phone number
            data["recipients"] = [recipient]

        result = await self._request("POST", "/v2/send", data)
        return result is not None

    async def send_message_with_attachments(
        self,
        recipient: str,
        text: str,
        attachment_urls: list[str],
    ) -> bool:
        """
        Send a message with image attachments.

        Args:
            recipient: Phone number or group ID
            text: Message text
            attachment_urls: List of image URLs to attach

        Returns:
            True if successful
        """
        data: dict[str, Any] = {
            "message": text,
            "number": self.phone_number,
            "recipients": [recipient],
            "text_mode": "styled",
        }

        # signal-cli-rest-api supports base64 attachments or URLs
        if attachment_urls:
            # Use URL attachments (signal-cli will download them)
            data["attachments"] = attachment_urls[:10]  # Limit to 10

        result = await self._request("POST", "/v2/send", data)
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
        Generate a notification message using GPT.

        Args:
            prompt: User-defined prompt describing the style/tone
            context: Context data (trending items, stats, etc.)

        Returns:
            Generated message or None if failed
        """
        if not self.openai:
            logger.warning("OpenAI not configured, cannot generate AI message")
            return None

        full_prompt = f"""Tu es un assistant qui génère des messages de notification Signal.

INSTRUCTIONS DU STYLE:
{prompt}

CONTEXTE (données à utiliser):
{context.to_context_string()}

RÈGLES:
- Génère UNIQUEMENT le message, pas d'explications
- Signal supporte le texte simple avec emojis
- Reste concis (max 500 caractères pour le message principal)
- Si le contexte mentionne "disponible", concentre-toi sur ces items
- Utilise des emojis si approprié au style demandé
- Utilise des sauts de ligne pour la lisibilité

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
        notification: "SignalNotification",
        context: NotificationContext,
    ) -> bool:
        """
        Process a notification configuration and send to Signal.

        Args:
            notification: Notification configuration
            context: Context data for the notification

        Returns:
            True if successful
        """
        recipient = notification.recipient

        # Filter items based on only_available setting
        films = context.films
        series = context.series

        if notification.only_available:
            films = [f for f in films if f.available]
            series = [s for s in series if s.available]

        # Limit to top 5 each (after availability filter)
        films = films[:5]
        series = series[:5]

        # Check minimum items
        total_items = len(films) + len(series)
        if total_items < notification.min_items:
            logger.debug(
                f"Signal notification '{notification.name}' skipped: "
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

        # Collect poster URLs if configured
        attachment_urls: list[str] = []
        if notification.include_posters:
            for item in films + series:
                if item.poster_url:
                    attachment_urls.append(item.poster_url)

        # Send the message
        if attachment_urls:
            success = await self.send_message_with_attachments(
                recipient, message, attachment_urls
            )
        else:
            success = await self.send_message(recipient, message)

        if success:
            logger.info(f"Signal notification '{notification.name}' sent to {recipient}")

        return success

    def _build_default_message(
        self,
        films: list[TrendingItem],
        series: list[TrendingItem],
        trigger: str,
    ) -> str:
        """Build default message when AI is not available."""
        lines = ["📊 Mise à jour des collections", ""]

        if films:
            lines.append(f"🎬 {len(films)} films en tendance:")
            for i, f in enumerate(films[:5], 1):
                year = f" ({f.year})" if f.year else ""
                lines.append(f"  {i}. {f.title}{year}")
            lines.append("")

        if series:
            lines.append(f"📺 {len(series)} séries en tendance:")
            for i, s in enumerate(series[:5], 1):
                year = f" ({s.year})" if s.year else ""
                lines.append(f"  {i}. {s.title}{year}")

        return "\n".join(lines)

    # =========================================================================
    # UTILITY METHODS
    # =========================================================================

    @staticmethod
    def build_poster_url(poster_path: Optional[str]) -> Optional[str]:
        """
        Build full TMDb poster URL from path.

        Args:
            poster_path: TMDb poster path (e.g., "/abc123.jpg")

        Returns:
            Full URL or None
        """
        if not poster_path:
            return None
        return f"https://image.tmdb.org/t/p/w500{poster_path}"
