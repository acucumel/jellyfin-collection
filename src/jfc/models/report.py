"""Report models for run summaries."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass
class CollectionReport:
    """Report for a single collection."""

    name: str
    library: str
    schedule: str

    # Source data
    source_provider: str  # TMDb, Trakt, Library Search, etc.
    items_fetched: int = 0
    items_after_filter: int = 0

    # Library matching
    items_matched: int = 0
    items_missing: int = 0
    match_rate: float = 0.0

    # Sync changes
    items_added_to_collection: int = 0
    items_removed_from_collection: int = 0
    collection_existed: bool = False

    # Arr requests
    items_sent_to_radarr: int = 0
    items_sent_to_sonarr: int = 0
    radarr_titles: list[str] = field(default_factory=list)
    sonarr_titles: list[str] = field(default_factory=list)

    # Item lists
    fetched_titles: list[str] = field(default_factory=list)
    matched_titles: list[str] = field(default_factory=list)
    missing_titles: list[str] = field(default_factory=list)
    added_titles: list[str] = field(default_factory=list)
    removed_titles: list[str] = field(default_factory=list)

    # Status
    success: bool = True
    error_message: Optional[str] = None
    duration_seconds: float = 0.0

    def calculate_match_rate(self) -> None:
        """Calculate match rate percentage."""
        if self.items_after_filter > 0:
            self.match_rate = (self.items_matched / self.items_after_filter) * 100


@dataclass
class LibraryReport:
    """Report for a library."""

    name: str
    media_type: str
    collections: list[CollectionReport] = field(default_factory=list)

    @property
    def total_collections(self) -> int:
        return len(self.collections)

    @property
    def successful_collections(self) -> int:
        return sum(1 for c in self.collections if c.success)

    @property
    def failed_collections(self) -> int:
        return sum(1 for c in self.collections if not c.success)

    @property
    def total_items_added(self) -> int:
        return sum(c.items_added_to_collection for c in self.collections)

    @property
    def total_items_removed(self) -> int:
        return sum(c.items_removed_from_collection for c in self.collections)

    @property
    def total_radarr_requests(self) -> int:
        return sum(c.items_sent_to_radarr for c in self.collections)

    @property
    def total_sonarr_requests(self) -> int:
        return sum(c.items_sent_to_sonarr for c in self.collections)


@dataclass
class RunReport:
    """Complete report for a run."""

    run_id: str
    start_time: datetime
    end_time: Optional[datetime] = None
    scheduled: bool = False
    dry_run: bool = False

    libraries: list[LibraryReport] = field(default_factory=list)

    @property
    def duration_seconds(self) -> float:
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds()
        return 0.0

    @property
    def total_collections(self) -> int:
        return sum(lib.total_collections for lib in self.libraries)

    @property
    def successful_collections(self) -> int:
        return sum(lib.successful_collections for lib in self.libraries)

    @property
    def failed_collections(self) -> int:
        return sum(lib.failed_collections for lib in self.libraries)

    @property
    def total_items_added(self) -> int:
        return sum(lib.total_items_added for lib in self.libraries)

    @property
    def total_items_removed(self) -> int:
        return sum(lib.total_items_removed for lib in self.libraries)

    @property
    def total_radarr_requests(self) -> int:
        return sum(lib.total_radarr_requests for lib in self.libraries)

    @property
    def total_sonarr_requests(self) -> int:
        return sum(lib.total_sonarr_requests for lib in self.libraries)

    def finalize(self) -> None:
        """Finalize the report with end time."""
        self.end_time = datetime.now()
