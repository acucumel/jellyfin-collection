"""API clients for external services."""

from jfc.clients.base import BaseClient
from jfc.clients.discord import DiscordWebhook
from jfc.clients.jellyfin import JellyfinClient
from jfc.clients.radarr import RadarrClient
from jfc.clients.sonarr import SonarrClient
from jfc.clients.tmdb import TMDbClient
from jfc.clients.trakt import TraktClient

__all__ = [
    "BaseClient",
    "DiscordWebhook",
    "JellyfinClient",
    "RadarrClient",
    "SonarrClient",
    "TMDbClient",
    "TraktClient",
]
