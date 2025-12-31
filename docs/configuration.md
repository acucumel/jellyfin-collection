# Configuration Guide

Complete reference for all JFC configuration options.

## Table of Contents

- [Configuration System](#configuration-system)
- [config.yml Reference](#configyml-reference)
- [Secrets (.env)](#secrets-env)
- [Kometa YAML Configuration](#kometa-yaml-configuration)
- [Collection Builders](#collection-builders)
- [Filters](#filters)
- [Scheduling](#scheduling)

## Configuration System

JFC uses a **dual configuration system** for flexibility and security:

### Priority Order (highest first)

1. **Environment variables** - Override everything
2. **`.env` file** - Secrets and local overrides
3. **`config.yml` settings** - Main configuration
4. **Default values** - Fallback

### Benefits

- **Portable** - Share `config.yml` without exposing secrets
- **Versionable** - Commit configuration to Git
- **Docker-friendly** - Minimal environment variables needed
- **Backward compatible** - Existing `.env` configs still work

## config.yml Reference

The `settings` section in `config/config.yml` contains all non-secret configuration:

```yaml
settings:
  # ---------------------------------------------------------------------------
  # JELLYFIN
  # ---------------------------------------------------------------------------
  jellyfin:
    url: http://jellyfin:8096
    # api_key: in .env (secret)

  # ---------------------------------------------------------------------------
  # TMDB
  # ---------------------------------------------------------------------------
  tmdb:
    language: fr          # ISO 639-1 language code
    region: FR            # ISO 3166-1 country code
    # api_key: in .env (secret)

  # ---------------------------------------------------------------------------
  # OPENAI (AI Poster Generation)
  # ---------------------------------------------------------------------------
  openai:
    enabled: true                 # Enable AI posters
    explicit_refs: false          # Include titles in visual signatures
    force_regenerate: false       # Regenerate all posters on every run
    missing_only: true            # Default for CLI 'regenerate-posters' command
    poster_history_limit: 5       # Keep N old posters (0=unlimited)
    prompt_history_limit: 10      # Keep N prompt files (0=unlimited)
    poster_logo_text: "NETFLEX"   # Logo text on generated posters
    # api_key: in .env (secret)
    # Note: Scheduled poster job always forces regeneration regardless of missing_only

  # ---------------------------------------------------------------------------
  # RADARR (Movies)
  # ---------------------------------------------------------------------------
  radarr:
    url: http://radarr:7878
    root_folder: /movies
    quality_profile: HD-1080p
    default_tag: jfc
    # api_key: in .env (secret)

  # ---------------------------------------------------------------------------
  # SONARR (Series)
  # ---------------------------------------------------------------------------
  sonarr:
    url: http://sonarr:8989
    root_folder: /tv
    quality_profile: HD-1080p
    default_tag: jfc
    # api_key: in .env (secret)

  # ---------------------------------------------------------------------------
  # DISCORD (Webhooks)
  # ---------------------------------------------------------------------------
  discord:
    webhook_url: ""              # Main webhook
    webhook_error: ""            # Errors (falls back to main)
    webhook_run_start: ""        # Run start notifications
    webhook_run_end: ""          # Run end notifications
    webhook_changes: ""          # Collection changes

  # ---------------------------------------------------------------------------
  # SCHEDULER
  # ---------------------------------------------------------------------------
  scheduler:
    collections_cron: "0 3 * * *"    # Daily at 3am
    posters_cron: "0 4 1 * *"        # 1st of month at 4am
    run_on_start: true               # Sync on container start
    timezone: Europe/Paris           # Timezone for cron

  # ---------------------------------------------------------------------------
  # APPLICATION
  # ---------------------------------------------------------------------------
  log_level: INFO                    # DEBUG, INFO, WARNING, ERROR
  dry_run: false                     # Preview mode (no changes)
```

## Secrets (.env)

Only API keys and secrets should be in `.env`:

```bash
# =============================================================================
# SECRETS ONLY - Configuration is in config.yml
# =============================================================================

# Required
JELLYFIN_API_KEY=your_jellyfin_api_key
TMDB_API_KEY=your_tmdb_api_key

# Optional - Trakt
TRAKT_CLIENT_ID=
TRAKT_CLIENT_SECRET=

# Optional - Radarr/Sonarr
RADARR_API_KEY=
SONARR_API_KEY=

# Optional - OpenAI
OPENAI_API_KEY=

# Optional - Overrides (uncomment to override config.yml)
# OPENAI_ENABLED=false
# SCHEDULER_TIMEZONE=UTC
```

### Trakt Authentication

Trakt tokens are managed automatically:

```bash
# Authenticate (interactive)
jfc trakt-auth

# Check status
jfc trakt-status

# Logout
jfc trakt-logout
```

Tokens are stored in `/data/trakt_tokens.json` and refreshed automatically.

## Kometa YAML Configuration

JFC uses the same YAML format as Kometa/Plex Meta Manager.

### Basic Structure

```yaml
# config.yml
libraries:
  Films:                          # Must match Jellyfin library name
    collection_files:
      - file: Films.yml           # Path to collection definitions

  Séries:
    collection_files:
      - file: Series.yml
    # Library-specific Sonarr overrides
    sonarr:
      tag: sonarr-series
      root_folder_path: /tv
```

### Collection File Example

```yaml
# Films.yml
templates:
  movie_template:
    sync_mode: sync
    schedule: daily
    sort_title: "!<<collection_name>>"

collections:
  "Trending Movies":
    template: {name: movie_template}
    tmdb_trending_weekly: 20
    summary: "Movies trending this week on TMDb"

  "Popular Movies":
    template: {name: movie_template}
    tmdb_popular: 50
    filters:
      year.gte: 2020
```

## Collection Builders

### TMDb Builders

#### `tmdb_trending_weekly` / `tmdb_trending_daily`

```yaml
collections:
  "Trending":
    tmdb_trending_weekly: 20    # Number of items
```

#### `tmdb_popular`

```yaml
collections:
  "Popular Movies":
    tmdb_popular: 50
```

#### `tmdb_discover`

Full TMDb discover API support:

```yaml
collections:
  "French Comedies 2024":
    tmdb_discover:
      with_genres: 35                    # Comedy
      with_original_language: fr
      primary_release_year: 2024
      sort_by: popularity.desc
      limit: 30
```

Available discover parameters:
- `with_genres` - Genre IDs (comma-separated)
- `with_original_language` - ISO 639-1 language code
- `primary_release_year` - Exact year
- `primary_release_date.gte/lte` - Date range
- `vote_average.gte/lte` - Rating range
- `with_runtime.gte/lte` - Runtime in minutes
- `sort_by` - Sort order
- `limit` - Max results

### Trakt Builders

#### `trakt_trending` / `trakt_popular`

```yaml
collections:
  "Trakt Trending":
    trakt_trending: 20
```

#### `trakt_chart`

```yaml
collections:
  "Most Watched This Week":
    trakt_chart:
      chart: watched
      time_period: weekly
      limit: 25
```

Chart types: `watched`, `trending`, `popular`, `recommended`

### Library Search

Search your Jellyfin library:

```yaml
collections:
  "4K Movies":
    plex_search:
      all:
        resolution: 4K
```

## Filters

Apply filters after fetching from source:

```yaml
collections:
  "Recent Trending":
    tmdb_trending_weekly: 50
    filters:
      year.gte: 2020
      vote_average.gte: 6.0
```

### Available Filters

| Filter | Description | Example |
|--------|-------------|---------|
| `year.gte` | Minimum year | `2020` |
| `year.lte` | Maximum year | `2024` |
| `year` | Exact year | `2023` |
| `vote_average.gte` | Minimum rating | `7.0` |
| `vote_average.lte` | Maximum rating | `9.0` |
| `original_language` | Language code | `en` |
| `genre` | Genre name | `Action` |
| `genre.not` | Exclude genre | `Horror` |

## Scheduling

### Schedule Types

```yaml
collections:
  "Daily Updated":
    schedule: daily
    tmdb_trending_daily: 20

  "Weekly Updated":
    schedule: weekly(sunday)
    tmdb_trending_weekly: 30

  "Monthly Updated":
    schedule: monthly(1)
    tmdb_popular: 100

  "Never Auto-Update":
    schedule: never
    # Manual updates only
```

### Cron Expressions

For the scheduler daemon (in `config.yml`):

| Expression | Meaning |
|------------|---------|
| `0 3 * * *` | Daily at 3:00 AM |
| `0 17 * * *` | Daily at 5:00 PM |
| `0 */6 * * *` | Every 6 hours |
| `0 4 1 * *` | 1st of month at 4:00 AM |
| `0 3 * * 0` | Every Sunday at 3:00 AM |

## Data Directories

```
/config/                    # Configuration (read-only in Docker)
├── config.yml              # Main config + settings
├── Films.yml               # Movie collections
└── Series.yml              # Series collections

/data/                      # Generated data
├── posters/                # AI-generated posters
│   └── Films/
│       └── Trending/
│           ├── poster.png
│           ├── history/
│           └── prompts/
├── cache/                  # API cache
│   └── visual_signatures_cache.json
├── trakt_tokens.json       # Trakt OAuth tokens
└── reports/                # Run reports
    └── report_xxx.md

/logs/                      # Application logs
├── jfc.log
└── error.log
```

## Next Steps

- [Kometa Migration](kometa-migration.md) - Migrate existing configs
- [AI Poster Generation](ai-posters.md) - Setup AI posters
