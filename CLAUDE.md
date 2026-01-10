# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Jellyfin Collection (JFC)** is a Kometa-compatible collection manager for Jellyfin. It parses Kometa/Plex Meta Manager YAML configurations and creates collections directly in Jellyfin, with optional integration with Sonarr/Radarr to request missing media and AI-powered poster generation via OpenAI.

### Key Features
- **Kometa YAML compatibility** - Reuse existing PMM/Kometa configs
- **Multiple data sources** - TMDb, Trakt, MDBList
- **Sonarr/Radarr integration** - Auto-request missing media
- **AI poster generation** - OpenAI-powered unique collection posters
- **Rich Discord notifications** - Embeds with poster images
- **Dual scheduler** - Daily sync + monthly poster regeneration

## Commands

### Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run collection sync
python -m jfc.cli run --config ./config

# Run specific library/collection
python -m jfc.cli run --library Films --collection "Trending"

# Dry-run mode (preview changes)
python -m jfc.cli run --dry-run

# Force poster regeneration
python -m jfc.cli run --force-posters

# Validate configuration
python -m jfc.cli validate --config ./config

# Test service connections
python -m jfc.cli test-connections

# Start scheduler daemon
python -m jfc.cli schedule

# Generate single poster
python -m jfc.cli generate-poster "Collection Name" --category FILMS --library Films
```

### Docker

```bash
# Build image
docker build -t jellyfin-collection .

# Run with docker-compose
docker-compose up -d

# View logs
docker-compose logs -f jellyfin-collection

# Run single sync
docker-compose exec jellyfin-collection jfc run

# Force poster regeneration
docker-compose exec jellyfin-collection jfc run --force-posters
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
pytest tests/

# With coverage
pytest --cov=jfc --cov-report=html
```

## Architecture

```
src/jfc/
├── cli.py                 # Typer CLI entrypoint
├── core/                  # Core infrastructure
│   ├── config.py          # Pydantic Settings (env vars)
│   ├── logger.py          # Loguru setup
│   └── scheduler.py       # APScheduler wrapper (dual jobs)
├── models/                # Pydantic data models
│   ├── collection.py      # Collection, CollectionConfig, filters
│   ├── media.py           # MediaItem, Movie, Series, LibraryItem
│   └── report.py          # CollectionReport, RunReport
├── clients/               # API clients (async httpx)
│   ├── base.py            # BaseClient with common HTTP logic
│   ├── jellyfin.py        # Jellyfin API (collections, libraries, posters)
│   ├── tmdb.py            # TMDb API (trending, discover, search)
│   ├── trakt.py           # Trakt API (charts, lists)
│   ├── radarr.py          # Radarr API v3 (add movies)
│   ├── sonarr.py          # Sonarr API v3 (add series)
│   └── discord.py         # Discord webhooks with file attachments
├── parsers/
│   └── kometa.py          # Kometa YAML config parser
└── services/              # Business logic
    ├── media_matcher.py       # Match provider items to Jellyfin
    ├── collection_builder.py  # Build and sync collections
    ├── poster_generator.py    # AI poster generation (OpenAI)
    ├── report_generator.py    # Run reports
    ├── startup.py             # Startup checks (connectivity, credits)
    └── runner.py              # Main orchestrator
```

## Key Patterns

### Configuration (Dual System)
- **config.yml** - Main configuration (URLs, schedules, options) - portable & versionable
- **.env** - Secrets only (API keys) - never committed
- Uses `pydantic-settings` with custom `YamlSettingsSource` for YAML support
- Priority: Environment variables > .env > config.yml > defaults
- Nested settings classes (JellyfinSettings, TMDbSettings, OpenAISettings, etc.)
- Path separation: CONFIG_PATH, DATA_PATH, LOG_PATH for Docker

### Async HTTP Clients
- All API clients inherit from `BaseClient`
- Use `httpx.AsyncClient` with context manager pattern
- Each client handles its own authentication headers

### Kometa Compatibility
- Parser in `parsers/kometa.py` reads standard Kometa YAML
- Supports templates, filters, tmdb_discover, trakt_chart
- Collection schedules: daily, weekly(sunday), monthly, never

### Media Matching
- `MediaMatcher` finds items in Jellyfin by TMDb ID (preferred) or title+year
- Results are cached to avoid repeated lookups
- Falls back to fuzzy title matching when IDs unavailable

### Collection Sync
- `CollectionBuilder.sync_collection()` calculates diff (add/remove)
- Uses Jellyfin BoxSet API for collection management
- Optional: sends missing items to Radarr/Sonarr
- Uploads AI-generated or manual posters

### AI Poster Generation
- `PosterGenerator` uses OpenAI gpt-image-1 API
- Builds visual signatures from collection items
- Generates unique prompts per category (FILMS, SÉRIES, CARTOONS)
- Maintains history with configurable retention

### Discord Notifications
- Rich embeds with poster image attachments
- Unified item list showing matched/added/missing
- Separate webhooks for different event types

## Configuration

### Secrets (.env only)
- `JELLYFIN_API_KEY` - Required
- `TMDB_API_KEY` - Required
- `TRAKT_CLIENT_ID`, `TRAKT_CLIENT_SECRET` - Optional
- `RADARR_API_KEY`, `SONARR_API_KEY` - Optional
- `OPENAI_API_KEY` - Optional

### config.yml (all other settings)
```yaml
settings:
  jellyfin:
    url: http://jellyfin:8096
  tmdb:
    language: fr
    region: FR
  openai:
    enabled: true
    missing_only: true
  radarr:
    url: http://radarr:7878
    root_folder: /movies
  sonarr:
    url: http://sonarr:8989
    root_folder: /tv
  discord:
    webhook_url: https://discord.com/...
  scheduler:
    collections_cron: "0 17 * * *"
    posters_cron: "0 4 1 * *"
    run_on_start: true
    timezone: Europe/Paris
```

See `docs/configuration.md` for full reference.

## Directory Structure

```
/config/                    # Kometa YAML configs (read-only in Docker)
├── config.yml
├── Films.yml
└── Series.yml

/data/                      # Generated data (persistent volume)
├── posters/{library}/{collection}/
│   ├── poster.png
│   ├── history/
│   └── prompts/
├── cache/
│   └── visual_signatures_cache.json
└── reports/

/logs/                      # Application logs
├── jfc.log
└── error.log
```

## Supported Builders

- `tmdb_trending_weekly`, `tmdb_trending_daily`
- `tmdb_popular`, `tmdb_now_playing`
- `tmdb_discover` (full parameter support)
- `trakt_trending`, `trakt_popular`
- `trakt_chart` (watched, trending, popular)
- `plex_search` (searches Jellyfin library)

## Testing

```bash
# All tests
pytest tests/

# Specific test
pytest tests/test_poster_generator.py -v

# With coverage
pytest --cov=jfc --cov-report=html
```

## CI/CD

- GitHub Actions workflow builds Docker images on push/tag
- Multi-platform: linux/amd64, linux/arm64
- Images pushed to ghcr.io/4lx69/jellyfin-collection
- Tags: latest (main branch), semantic versions (v1.0.0, v1.0, v1)

## AI Models

- Uses OpenAI GPT-5.1 for prompt generation (scene descriptions, visual signatures)
- Uses gpt-image-1.5 for poster image generation
- Visual signatures built from item metadata and AI analysis

## Context

- Current year: 2025
- Author: 4lx69
- License: MIT (2025-2026)
