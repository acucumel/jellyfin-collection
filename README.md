# Jellyfin Collection

Kometa-compatible collection manager for Jellyfin with Sonarr/Radarr integration.

## Features

- **Kometa YAML compatibility** - Use your existing Plex Meta Manager configs
- **Jellyfin native** - Creates collections directly in Jellyfin
- **Multiple providers** - TMDb, Trakt, MDBList support
- **Sonarr/Radarr integration** - Automatically request missing media
- **Discord notifications** - Get notified of updates and errors
- **Scheduled runs** - Run on a schedule like Kometa
- **Docker ready** - Full Docker support

## Quick Start

### Docker (Recommended)

1. Copy `.env.example` to `.env` and fill in your API keys
2. Place your Kometa YAML configs in `./config/`
3. Run:

```bash
docker-compose up -d
```

### Manual Installation

```bash
pip install -e .
jfc run --config ./config
```

## Configuration

JFC reads standard Kometa YAML configuration files. Place your `config.yml` and collection files (e.g., `Films.yml`, `Series.yml`) in the config directory.

### Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `JELLYFIN_URL` | Jellyfin server URL | Yes |
| `JELLYFIN_API_KEY` | Jellyfin API key | Yes |
| `TMDB_API_KEY` | TMDb API key | Yes |
| `TRAKT_CLIENT_ID` | Trakt client ID | No |
| `RADARR_URL` | Radarr server URL | No |
| `RADARR_API_KEY` | Radarr API key | No |
| `SONARR_URL` | Sonarr server URL | No |
| `SONARR_API_KEY` | Sonarr API key | No |
| `DISCORD_WEBHOOK_URL` | Discord webhook URL | No |

See `.env.example` for full configuration options.

## CLI Commands

```bash
# Run collection updates
jfc run

# Run specific library
jfc run --library Films

# Dry run (no changes)
jfc run --dry-run

# Validate configuration
jfc validate

# List all collections
jfc list-collections

# Test connections
jfc test-connections

# Start scheduler
jfc schedule --cron "0 3 * * *"
```

## Supported Builders

| Builder | Status |
|---------|--------|
| `tmdb_trending_weekly` | Supported |
| `tmdb_trending_daily` | Supported |
| `tmdb_popular` | Supported |
| `tmdb_discover` | Supported |
| `trakt_trending` | Supported |
| `trakt_popular` | Supported |
| `trakt_chart` | Supported |
| `plex_search` | Supported (searches Jellyfin) |
| `mdblist_list` | Planned |
| `imdb_list` | Planned |

## Migration from Kometa

1. Copy your config files to the JFC config directory
2. Update library names to match your Jellyfin libraries
3. Remove Plex-specific settings
4. Run `jfc validate` to check configuration
5. Run `jfc run --dry-run` to preview changes

## License

MIT
