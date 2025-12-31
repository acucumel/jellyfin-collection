# API Reference & Technical Documentation

Technical documentation for developers and advanced users.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                           CLI (cli.py)                          │
│                    run | schedule | validate                    │
└─────────────────────────┬───────────────────────────────────────┘
                          │
┌─────────────────────────▼───────────────────────────────────────┐
│                      Runner (runner.py)                         │
│              Orchestrates the update process                    │
└─────────────────────────┬───────────────────────────────────────┘
                          │
          ┌───────────────┼───────────────┐
          │               │               │
          ▼               ▼               ▼
┌─────────────────┐ ┌───────────┐ ┌─────────────────┐
│ CollectionBuilder│ │ Matcher   │ │ PosterGenerator │
│  builds items   │ │ matches   │ │  creates art    │
└────────┬────────┘ └─────┬─────┘ └────────┬────────┘
         │                │                │
         ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────┐
│                        API Clients                              │
│   Jellyfin  │  TMDb  │  Trakt  │  Radarr  │  Sonarr  │  OpenAI │
└─────────────────────────────────────────────────────────────────┘
```

## Core Components

### CLI (`src/jfc/cli.py`)

Entry point for all commands:

```python
# Available commands
jfc run        # Run collection sync
jfc schedule   # Start scheduler daemon
jfc validate   # Validate configuration
jfc list-collections
jfc test-connections
jfc generate-poster
jfc version
```

### Runner (`src/jfc/services/runner.py`)

Main orchestrator that:
1. Runs startup checks (API connectivity, credits)
2. Parses Kometa YAML configurations
3. Processes each library/collection
4. Coordinates builder, matcher, and poster generator
5. Sends Discord notifications
6. Generates reports

### CollectionBuilder (`src/jfc/services/collection_builder.py`)

Builds collections from configuration:

```python
async def build_collection(
    config: CollectionConfig,
    library_name: str,
    library_id: str,
    media_type: MediaType,
) -> tuple[Collection, CollectionReport]:
    """
    1. Fetch items from source (TMDb, Trakt, etc.)
    2. Apply filters
    3. Match against Jellyfin library
    4. Return collection with matched items
    """

async def sync_collection(
    collection: Collection,
    report: CollectionReport,
    media_type: MediaType,
    add_missing_to_arr: bool = True,
    force_poster: bool = False,
) -> tuple[int, int, Optional[Path]]:
    """
    1. Create/update Jellyfin collection
    2. Sync items (add/remove)
    3. Send missing to Radarr/Sonarr
    4. Generate/upload poster
    Returns: (added_count, removed_count, poster_path)
    """
```

### MediaMatcher (`src/jfc/services/media_matcher.py`)

Matches provider items to Jellyfin library:

```python
async def match_items(
    items: list[MediaItem],
    library_items: dict[int, LibraryItem],
) -> MatchResult:
    """
    Matching priority:
    1. TMDb ID (exact match)
    2. IMDb ID (exact match)
    3. Title + Year (fuzzy match)
    """
```

### PosterGenerator (`src/jfc/services/poster_generator.py`)

AI poster generation:

```python
async def generate_poster(
    config: CollectionConfig,
    items: list[MediaItem],
    category: str,
    library: str = "default",
    force_regenerate: bool = False,
) -> Optional[Path]:
    """
    1. Build visual signatures from items
    2. Generate prompt using AI
    3. Generate image via OpenAI API
    4. Save to disk with history
    5. Return path to poster
    """
```

## API Clients

### JellyfinClient (`src/jfc/clients/jellyfin.py`)

```python
class JellyfinClient:
    async def get_libraries() -> list[dict]
    async def get_library_items(library_id: str) -> list[dict]
    async def get_collection(collection_id: str) -> dict
    async def create_collection(name: str, library_id: str) -> str
    async def add_to_collection(collection_id: str, item_ids: list[str])
    async def remove_from_collection(collection_id: str, item_ids: list[str])
    async def upload_collection_poster(collection_id: str, image_path: Path)
```

### TMDbClient (`src/jfc/clients/tmdb.py`)

```python
class TMDbClient:
    async def get_trending_movies(limit: int) -> list[dict]
    async def get_trending_shows(limit: int) -> list[dict]
    async def get_popular_movies(limit: int) -> list[dict]
    async def discover_movies(params: dict) -> list[dict]
    async def search_movie(title: str, year: int) -> Optional[dict]
```

### TraktClient (`src/jfc/clients/trakt.py`)

```python
class TraktClient:
    async def get_trending_movies(limit: int) -> list[dict]
    async def get_popular_movies(limit: int) -> list[dict]
    async def get_chart(chart: str, media_type: str, limit: int) -> list[dict]
```

### RadarrClient / SonarrClient

```python
class RadarrClient:
    async def health_check() -> bool
    async def search_movie(tmdb_id: int) -> Optional[dict]
    async def add_movie(tmdb_id: int, title: str) -> bool

class SonarrClient:
    async def health_check() -> bool
    async def search_series(tvdb_id: int) -> Optional[dict]
    async def add_series(tvdb_id: int, title: str) -> bool
```

### DiscordWebhook (`src/jfc/clients/discord.py`)

```python
class DiscordWebhook:
    async def send_run_start(libraries: list[str], scheduled: bool)
    async def send_run_end(duration: float, collections: int, ...)
    async def send_collection_report(
        collection_name: str,
        library: str,
        matched_titles: list[str],
        added_titles: list[str],
        missing_titles: list[str],
        poster_path: Optional[Path],
        ...
    )
    async def send_error(title: str, message: str)
```

## Data Models

### MediaItem (`src/jfc/models/media.py`)

```python
class MediaItem(BaseModel):
    title: str
    year: Optional[int]
    tmdb_id: Optional[int]
    imdb_id: Optional[str]
    tvdb_id: Optional[int]
    media_type: MediaType  # MOVIE or SERIES
    overview: Optional[str]
    poster_path: Optional[str]
    vote_average: Optional[float]
```

### CollectionConfig (`src/jfc/models/collection.py`)

```python
class CollectionConfig(BaseModel):
    name: str
    summary: Optional[str]
    poster: Optional[str]
    schedule: CollectionSchedule
    sync_mode: str = "sync"

    # Builders
    tmdb_trending_weekly: Optional[int]
    tmdb_trending_daily: Optional[int]
    tmdb_popular: Optional[int]
    tmdb_discover: Optional[dict]
    trakt_trending: Optional[int]
    trakt_chart: Optional[dict]
    plex_search: Optional[dict]

    # Filters
    filters: Optional[dict]
```

### Collection (`src/jfc/models/collection.py`)

```python
class Collection(BaseModel):
    name: str
    config: CollectionConfig
    items: list[MediaItem]           # All fetched items
    matched_items: list[LibraryItem] # Items found in Jellyfin
    jellyfin_id: Optional[str]       # Jellyfin collection ID
```

## Configuration

### Settings (`src/jfc/core/config.py`)

Uses Pydantic Settings for environment variable parsing:

```python
class Settings(BaseSettings):
    # Loaded from environment variables
    jellyfin_url: str
    jellyfin_api_key: str
    tmdb_api_key: str
    # ... etc

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # Nested settings accessed via properties
    @property
    def jellyfin(self) -> JellyfinSettings: ...

    @property
    def openai(self) -> OpenAISettings: ...
```

### KometaParser (`src/jfc/parsers/kometa.py`)

Parses Kometa YAML configurations:

```python
class KometaParser:
    def __init__(self, config_path: Path):
        self.config_path = config_path

    def parse_config(self) -> dict:
        """Parse main config.yml"""

    def get_all_collections(self) -> dict[str, list[CollectionConfig]]:
        """Returns {library_name: [collection_configs]}"""

    def parse_collection_file(self, file_path: Path) -> list[CollectionConfig]:
        """Parse a single collection YAML file"""
```

## Scheduler

### Scheduler (`src/jfc/core/scheduler.py`)

APScheduler wrapper for cron-based scheduling:

```python
class Scheduler:
    def __init__(self, timezone: str = "Europe/Paris"):
        self._scheduler = AsyncIOScheduler(timezone=timezone)

    def add_cron_job(
        self,
        name: str,
        func: Callable,
        cron_expression: str,
    ) -> str:
        """Add a cron-scheduled job. Returns job ID."""

    def list_jobs(self) -> list[dict]:
        """List all scheduled jobs with next run times."""
```

## Error Handling

### Startup Checks (`src/jfc/services/startup.py`)

```python
class StartupService:
    async def run_startup(matcher: MediaMatcher) -> bool:
        """
        Checks:
        1. Jellyfin connectivity
        2. TMDb API access
        3. Trakt API (if configured)
        4. Radarr/Sonarr (if configured)
        5. OpenAI credits (if enabled)

        Returns False if critical services fail.
        """
```

### Discord Error Notifications

Errors are sent to Discord when configured:

```python
await discord.send_error(
    title="Collection Error: Trending Movies",
    message="Failed to fetch from TMDb: 429 Too Many Requests"
)
```

## Extending JFC

### Adding a New Builder

1. Add builder field to `CollectionConfig` model
2. Implement fetch method in `CollectionBuilder`
3. Update `KometaParser` to parse the new builder

### Adding a New API Client

1. Create client in `src/jfc/clients/`
2. Inherit from `BaseClient` for common HTTP logic
3. Add to `Runner.__init__` initialization
4. Add to `StartupService` for connectivity check

## Testing

Run tests:

```bash
# All tests
pytest

# Specific test file
pytest tests/test_parser.py -v

# With coverage
pytest --cov=jfc --cov-report=html
```

## Logging

Configured via loguru:

```python
from loguru import logger

logger.debug("Detailed info")
logger.info("General info")
logger.success("Operation succeeded")
logger.warning("Something might be wrong")
logger.error("Something failed")
```

Log files:
- `logs/jfc.log` - All logs (DEBUG+)
- `logs/error.log` - Errors only
