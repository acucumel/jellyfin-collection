# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Jellyfin Collection (JFC)** is a Kometa-compatible collection manager for Jellyfin. It parses Kometa/Plex Meta Manager YAML configurations and creates collections directly in Jellyfin, with optional integration with Sonarr/Radarr to request missing media.

## Commands

### Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run locally
python -m jfc.cli run --config ./config

# Run with dry-run mode
python -m jfc.cli run --dry-run

# Validate configuration
python -m jfc.cli validate --config ./config

# List all collections
python -m jfc.cli list-collections --config ./config

# Test service connections
python -m jfc.cli test-connections

# Start scheduler (daemon mode)
python -m jfc.cli schedule --cron "0 3 * * *"
```

### Docker

```bash
# Build image
docker build -t jellyfin-collection .

# Run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f jellyfin-collection

# Run single update
docker-compose run --rm jellyfin-collection python -m jfc.cli run
```

### Code Quality

```bash
# Format code
black src/

# Lint
ruff check src/

# Type checking
mypy src/

# Run tests
pytest

# Run single test
pytest tests/test_parsers.py::test_parse_collection -v
```

## Architecture

```
src/jfc/
├── cli.py                 # Typer CLI entrypoint
├── core/                  # Core infrastructure
│   ├── config.py          # Pydantic Settings (env vars)
│   ├── logger.py          # Loguru setup
│   └── scheduler.py       # APScheduler wrapper
├── models/                # Pydantic data models
│   ├── collection.py      # Collection, CollectionConfig, filters
│   └── media.py           # MediaItem, Movie, Series, LibraryItem
├── clients/               # API clients (async httpx)
│   ├── base.py            # BaseClient with common HTTP logic
│   ├── jellyfin.py        # Jellyfin API (collections, libraries)
│   ├── tmdb.py            # TMDb API (trending, discover, search)
│   ├── trakt.py           # Trakt API (charts, lists)
│   ├── radarr.py          # Radarr API v3 (add movies)
│   ├── sonarr.py          # Sonarr API v3 (add series)
│   └── discord.py         # Discord webhooks
├── parsers/
│   └── kometa.py          # Kometa YAML config parser
└── services/              # Business logic
    ├── media_matcher.py   # Match provider items to Jellyfin library
    ├── collection_builder.py  # Build collections from configs
    └── runner.py          # Main orchestrator
```

## Key Patterns

### Configuration
- Uses `pydantic-settings` for environment variable parsing
- Nested settings classes (JellyfinSettings, TMDbSettings, etc.)
- All secrets via environment variables, never in code

### Async HTTP Clients
- All API clients inherit from `BaseClient`
- Use `httpx.AsyncClient` with context manager pattern
- Each client handles its own authentication headers

### Kometa Compatibility
- Parser in `parsers/kometa.py` reads standard Kometa YAML
- Supports templates, filters, tmdb_discover, trakt_chart
- Collection schedules: daily, weekly(sunday), monthly

### Media Matching
- `MediaMatcher` finds items in Jellyfin by TMDb ID (preferred) or title+year
- Results are cached to avoid repeated lookups
- Falls back to fuzzy title matching when IDs unavailable

### Collection Sync
- `CollectionBuilder.sync_collection()` calculates diff (add/remove)
- Uses Jellyfin BoxSet API for collection management
- Optional: sends missing items to Radarr/Sonarr

## Environment Variables

Required:
- `JELLYFIN_URL`, `JELLYFIN_API_KEY`
- `TMDB_API_KEY`

Optional providers:
- `TRAKT_CLIENT_ID`, `TRAKT_CLIENT_SECRET`, `TRAKT_ACCESS_TOKEN`
- `RADARR_URL`, `RADARR_API_KEY`
- `SONARR_URL`, `SONARR_API_KEY`
- `DISCORD_WEBHOOK_URL`

See `.env.example` for full list.

## Kometa Config Format

The parser reads standard Kometa YAML files:

```yaml
# config.yml
libraries:
  Films:
    collection_files:
    - file: config/Films.yml

# Films.yml
templates:
  film_template:
    sync_mode: sync
    schedule: daily

collections:
  "Trending Movies":
    template: {name: film_template}
    tmdb_trending_weekly: 50
    filters:
      year.gte: 2015
```

Supported builders:
- `tmdb_trending_weekly`, `tmdb_trending_daily`
- `tmdb_popular`
- `tmdb_discover` (full parameter support)
- `trakt_trending`, `trakt_popular`
- `trakt_chart` (watched, trending, popular)
- `plex_search` (searches Jellyfin library)

## Testing

```bash
# Unit tests
pytest tests/unit/

# Integration tests (requires services)
pytest tests/integration/ --integration

# With coverage
pytest --cov=jfc --cov-report=html
```
