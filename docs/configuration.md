# Configuration Guide

Complete reference for all JFC configuration options.

## Table of Contents

- [Environment Variables](#environment-variables)
- [Kometa YAML Configuration](#kometa-yaml-configuration)
- [Collection Builders](#collection-builders)
- [Filters](#filters)
- [Scheduling](#scheduling)

## Environment Variables

### Core Services (Required)

| Variable | Description | Default | Example |
|----------|-------------|---------|---------|
| `JELLYFIN_URL` | Jellyfin server URL | - | `http://jellyfin:8096` |
| `JELLYFIN_API_KEY` | Jellyfin API key | - | `abc123...` |
| `TMDB_API_KEY` | TMDb API key | - | `e0293eb...` |
| `TMDB_LANGUAGE` | TMDb language code | `fr` | `en`, `fr`, `de` |
| `TMDB_REGION` | TMDb region code | `FR` | `US`, `FR`, `GB` |

### Radarr Integration (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `RADARR_URL` | Radarr server URL | `http://localhost:7878` |
| `RADARR_API_KEY` | Radarr API key | - |
| `RADARR_ROOT_FOLDER` | Root folder for movies | `/movies` |
| `RADARR_QUALITY_PROFILE` | Quality profile name | `HD-1080p` |
| `RADARR_DEFAULT_TAG` | Tag for added movies | `jfc` |

### Sonarr Integration (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `SONARR_URL` | Sonarr server URL | `http://localhost:8989` |
| `SONARR_API_KEY` | Sonarr API key | - |
| `SONARR_ROOT_FOLDER` | Root folder for series | `/tv` |
| `SONARR_QUALITY_PROFILE` | Quality profile name | `HD-1080p` |
| `SONARR_DEFAULT_TAG` | Tag for added series | `jfc` |

### Trakt Integration (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `TRAKT_CLIENT_ID` | Trakt application client ID | - |
| `TRAKT_CLIENT_SECRET` | Trakt application client secret | - |

**Note:** Access tokens are managed automatically. Run `jfc trakt-auth` to authenticate via OAuth Device Code flow. Tokens are stored securely in `/data/trakt_tokens.json` and refreshed automatically when expired.

#### Trakt Authentication Commands

```bash
# Authenticate with Trakt (interactive - shows code to enter on trakt.tv)
jfc trakt-auth

# Check authentication status
jfc trakt-status

# Logout and revoke tokens
jfc trakt-logout
```

### Discord Notifications (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `DISCORD_WEBHOOK_URL` | Default webhook URL | - |
| `DISCORD_WEBHOOK_ERROR` | Webhook for errors | Falls back to default |
| `DISCORD_WEBHOOK_RUN_START` | Webhook for run start | Falls back to default |
| `DISCORD_WEBHOOK_RUN_END` | Webhook for run end | Falls back to default |
| `DISCORD_WEBHOOK_CHANGES` | Webhook for collection updates | Falls back to default |

### OpenAI / AI Posters (Optional)

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | OpenAI API key | - |
| `OPENAI_ENABLED` | Enable AI poster generation | `false` |
| `OPENAI_EXPLICIT_REFS` | Include titles in visual signatures | `false` |
| `OPENAI_POSTER_HISTORY_LIMIT` | Keep N old posters | `5` |
| `OPENAI_PROMPT_HISTORY_LIMIT` | Keep N prompt files | `10` |

### Scheduler

| Variable | Description | Default |
|----------|-------------|---------|
| `SCHEDULER_COLLECTIONS_CRON` | Cron for daily sync | `0 3 * * *` |
| `SCHEDULER_POSTERS_CRON` | Cron for poster regen | `0 4 1 * *` |
| `SCHEDULER_RUN_ON_START` | Sync on startup | `true` |
| `SCHEDULER_TIMEZONE` | Timezone for cron | `Europe/Paris` |

### Application

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging level | `INFO` |
| `DRY_RUN` | Preview mode | `false` |

**Note:** Paths are fixed for Docker: `/config` (read-only), `/data`, `/logs`. Use bind mounts in your docker-compose.yml.

## Kometa YAML Configuration

JFC uses the same YAML format as Kometa/Plex Meta Manager.

### Basic Structure

```yaml
# config.yml
libraries:
  Films:                          # Must match Jellyfin library name
    collection_files:
      - file: config/Films.yml    # Path to collection definitions

  Séries:
    collection_files:
      - file: config/Series.yml
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

For the scheduler daemon:

| Expression | Meaning |
|------------|---------|
| `0 3 * * *` | Daily at 3:00 AM |
| `0 */6 * * *` | Every 6 hours |
| `0 4 1 * *` | 1st of month at 4:00 AM |
| `0 3 * * 0` | Every Sunday at 3:00 AM |

## Data Directories

```
/config/                    # Configuration (read-only)
├── config.yml              # Main config
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
└── reports/                # Run reports
    └── report_xxx.md

/logs/                      # Application logs
├── jfc.log
└── error.log
```

## Next Steps

- [Kometa Migration](kometa-migration.md) - Migrate existing configs
- [AI Poster Generation](ai-posters.md) - Setup AI posters
