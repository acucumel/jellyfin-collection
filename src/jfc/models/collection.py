"""Collection models for Kometa-style configurations."""

from datetime import date
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SyncMode(str, Enum):
    """Collection sync mode."""

    APPEND = "append"  # Add new items, keep existing
    SYNC = "sync"  # Match collection exactly to source


class ScheduleType(str, Enum):
    """Schedule type for collections."""

    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    NEVER = "never"


class CollectionOrder(str, Enum):
    """Sort order for items within a collection.

    Note: Jellyfin displays items in the order they were added.
    To achieve custom ordering, items are cleared and re-added in sorted order.
    """

    CUSTOM = "custom"  # Keep source order (default)
    SORT_NAME = "SortName"  # Alphabetical by title
    PREMIERE_DATE = "PremiereDate"  # By release date (newest first)
    DATE_CREATED = "DateCreated"  # By date added to Jellyfin
    COMMUNITY_RATING = "CommunityRating"  # By rating (highest first)
    CRITIC_RATING = "CriticRating"  # By critic rating (highest first)
    RANDOM = "Random"  # Random order


class CollectionSchedule(BaseModel):
    """Collection schedule configuration."""

    schedule_type: ScheduleType = ScheduleType.DAILY
    day_of_week: Optional[str] = None  # For weekly schedules (e.g., "sunday")
    day_of_month: Optional[int] = None  # For monthly schedules

    @classmethod
    def from_kometa(cls, value: str | None) -> "CollectionSchedule":
        """Parse Kometa schedule format (e.g., 'daily', 'weekly(sunday)')."""
        if not value:
            return cls(schedule_type=ScheduleType.NEVER)

        value = value.lower().strip()

        if value == "daily":
            return cls(schedule_type=ScheduleType.DAILY)

        if value.startswith("weekly"):
            # Parse weekly(sunday) format
            if "(" in value:
                day = value.split("(")[1].rstrip(")")
                return cls(schedule_type=ScheduleType.WEEKLY, day_of_week=day)
            return cls(schedule_type=ScheduleType.WEEKLY, day_of_week="sunday")

        if value.startswith("monthly"):
            if "(" in value:
                day = int(value.split("(")[1].rstrip(")"))
                return cls(schedule_type=ScheduleType.MONTHLY, day_of_month=day)
            return cls(schedule_type=ScheduleType.MONTHLY, day_of_month=1)

        return cls(schedule_type=ScheduleType.NEVER)


class CollectionFilter(BaseModel):
    """Filter configuration for collections."""

    # Year filters
    year_gte: Optional[int] = None
    year_lte: Optional[int] = None

    # Rating filters
    vote_average_gte: Optional[float] = None
    vote_average_lte: Optional[float] = None
    vote_count_gte: Optional[int] = None
    vote_count_lte: Optional[int] = None
    critic_rating_gte: Optional[float] = None

    # Genre filters
    with_genres: list[int] = Field(default_factory=list)
    without_genres: list[int] = Field(default_factory=list)

    # Country filters
    country_not: list[str] = Field(default_factory=list)
    origin_country_not: list[str] = Field(default_factory=list)

    # Date filters
    release_date_gte: Optional[date] = None
    release_date_lte: Optional[date] = None
    first_air_date_gte: Optional[date] = None
    first_air_date_lte: Optional[date] = None

    # TMDb specific
    tmdb_vote_count_gte: Optional[int] = None

    # Streaming providers (OR logic with |)
    with_watch_providers: list[int] = Field(default_factory=list)
    watch_region: Optional[str] = None

    # Status filter (for series)
    with_status: Optional[int] = None  # 0=Returning, 3=Ended, etc.


class CollectionTemplate(BaseModel):
    """Template for collection defaults."""

    name: str
    sync_mode: SyncMode = SyncMode.SYNC
    visible_library: bool = True
    visible_home: bool = False
    visible_shared: bool = False
    filters: CollectionFilter = Field(default_factory=CollectionFilter)
    schedule: CollectionSchedule = Field(default_factory=CollectionSchedule)


class CollectionItem(BaseModel):
    """Item reference in a collection."""

    title: str
    year: Optional[int] = None
    tmdb_id: Optional[int] = None
    imdb_id: Optional[str] = None
    tvdb_id: Optional[int] = None
    jellyfin_id: Optional[str] = None

    # Match status
    matched: bool = False
    in_library: bool = False

    # Metadata for sorting (populated from source/Jellyfin)
    premiere_date: Optional[date] = None
    date_created: Optional[date] = None
    community_rating: Optional[float] = None
    critic_rating: Optional[float] = None
    sort_name: Optional[str] = None


class CollectionConfig(BaseModel):
    """Configuration for a single collection (from Kometa YAML)."""

    name: str
    summary: Optional[str] = None
    sort_title: Optional[str] = None

    # Poster image (filename relative to posters_path)
    poster: Optional[str] = None

    # Display options
    visible_library: bool = True
    visible_home: bool = False
    visible_shared: bool = False

    # Collection item ordering
    collection_order: CollectionOrder = CollectionOrder.CUSTOM

    # Sync options
    sync_mode: SyncMode = SyncMode.SYNC
    minimum_items: int = 1
    delete_not_scheduled: bool = False

    # Schedule
    schedule: CollectionSchedule = Field(default_factory=CollectionSchedule)

    # Filters
    filters: CollectionFilter = Field(default_factory=CollectionFilter)

    # Builder sources (Kometa-style)
    tmdb_trending_weekly: Optional[int] = None
    tmdb_trending_daily: Optional[int] = None
    tmdb_popular: Optional[int] = None
    tmdb_discover: Optional[dict[str, Any]] = None

    trakt_trending: Optional[int] = None
    trakt_popular: Optional[int] = None
    trakt_chart: Optional[dict[str, Any]] = None
    trakt_list: Optional[str] = None

    mdblist_list: Optional[str] = None

    imdb_list: Optional[str] = None

    # Plex/Jellyfin search (for existing library items)
    plex_search: Optional[dict[str, Any]] = None

    # Radarr/Sonarr tags
    item_radarr_tag: Optional[str] = None
    item_sonarr_tag: Optional[str] = None

    # Limit
    limit: Optional[int] = None

    # Template reference
    template: Optional[str] = None


class Collection(BaseModel):
    """A collection with its items."""

    config: CollectionConfig
    library_name: str
    items: list[CollectionItem] = Field(default_factory=list)

    # Jellyfin collection ID (if exists)
    jellyfin_id: Optional[str] = None

    # Stats
    total_items: int = 0
    matched_items: int = 0
    missing_items: int = 0

    def update_stats(self) -> None:
        """Update collection statistics."""
        self.total_items = len(self.items)
        self.matched_items = sum(1 for i in self.items if i.matched)
        self.missing_items = self.total_items - self.matched_items
