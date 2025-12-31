# Jellyfin Collection (JFC)

[![Docker Build](https://github.com/acucumel/jellyfin-collection/actions/workflows/docker-build.yml/badge.svg)](https://github.com/acucumel/jellyfin-collection/actions/workflows/docker-build.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Docker Pulls](https://img.shields.io/docker/pulls/acucumel/jellyfin-collection)](https://github.com/acucumel/jellyfin-collection/pkgs/container/jellyfin-collection)

<p align="center">
  <img src="docs/doc-image-1.png" width="48%" alt="JFC Screenshot 1" />
  <img src="docs/doc-image-2.png" width="48%" alt="JFC Screenshot 2" />
</p>

**Jellyfin Collection (JFC)** is a powerful, Kometa-compatible collection manager designed specifically for [Jellyfin](https://jellyfin.org/). It automatically creates and maintains media collections by fetching trending, popular, and curated content from TMDb, Trakt, and other sources.

If you're migrating from Plex and miss [Kometa](https://github.com/Kometa-Team/Kometa) (formerly Plex Meta Manager), JFC brings the same YAML-based configuration to Jellyfin with additional features like **AI-generated posters** using OpenAI and seamless **Sonarr/Radarr integration** to automatically request missing media.

## Features

- **Kometa YAML Compatibility** - Use your existing Plex Meta Manager/Kometa configurations
- **Jellyfin Native** - Creates and manages collections directly in Jellyfin
- **Multiple Providers** - TMDb, Trakt, MDBList support for discovering content
- **Sonarr/Radarr Integration** - Automatically request missing media
- **AI Poster Generation** - Generate unique collection posters using OpenAI
- **Rich Discord Notifications** - Detailed notifications with poster images
- **Scheduled Runs** - Daily collection sync + monthly poster regeneration
- **Docker Ready** - Multi-platform images (amd64/arm64)

## Quick Start

### Docker (Recommended)

```bash
# Pull the image
docker pull ghcr.io/acucumel/jellyfin-collection:latest

# Or use docker-compose
docker-compose up -d
```

See [Installation Guide](docs/installation.md) for detailed setup instructions.

### Manual Installation

```bash
# Clone the repository
git clone https://github.com/acucumel/jellyfin-collection.git
cd jellyfin-collection

# Install dependencies
pip install -e .

# Run
jfc run --config ./config
```

## Documentation

| Document | Description |
|----------|-------------|
| [Installation Guide](docs/installation.md) | Step-by-step installation for Docker and manual setup |
| [Configuration Guide](docs/configuration.md) | Complete configuration reference |
| [Kometa Migration](docs/kometa-migration.md) | Migrate from Kometa/Plex Meta Manager |
| [AI Poster Generation](docs/ai-posters.md) | Setup and customize AI-generated posters |
| [API Reference](docs/api-reference.md) | Technical documentation and architecture |

## Configuration Overview

### Required Environment Variables

| Variable | Description |
|----------|-------------|
| `JELLYFIN_URL` | Jellyfin server URL (e.g., `http://jellyfin:8096`) |
| `JELLYFIN_API_KEY` | Jellyfin API key |
| `TMDB_API_KEY` | TMDb API key ([get one here](https://www.themoviedb.org/settings/api)) |

### Optional Integrations

| Service | Variables | Description |
|---------|-----------|-------------|
| Radarr | `RADARR_URL`, `RADARR_API_KEY` | Auto-request missing movies |
| Sonarr | `SONARR_URL`, `SONARR_API_KEY` | Auto-request missing series |
| Trakt | `TRAKT_CLIENT_ID`, `TRAKT_CLIENT_SECRET` | Trakt lists and charts |
| Discord | `DISCORD_WEBHOOK_URL` | Rich notifications with posters |
| OpenAI | `OPENAI_API_KEY`, `OPENAI_ENABLED=true` | AI poster generation |

See [.env.example](.env.example) for all configuration options.

## CLI Commands

```bash
# Run collection sync
jfc run

# Run specific library/collection
jfc run --library Films --collection "Trending Movies"

# Force poster regeneration
jfc run --force-posters

# Dry run (preview changes)
jfc run --dry-run

# Start scheduler daemon
jfc schedule

# Validate configuration
jfc validate

# List all collections
jfc list-collections

# Test service connections
jfc test-connections

# Generate a single poster
jfc generate-poster "My Collection" --category FILMS --library Films
```

## Scheduler

The scheduler runs two jobs:

| Job | Default Schedule | Description |
|-----|------------------|-------------|
| Collection Sync | Daily at 3am | Sync all collections |
| Poster Regeneration | 1st of month at 4am | Regenerate all AI posters |

Configure via environment variables:

```bash
SCHEDULER_COLLECTIONS_CRON=0 3 * * *    # Daily at 3am
SCHEDULER_POSTERS_CRON=0 4 1 * *        # 1st of month at 4am
SCHEDULER_RUN_ON_START=true             # Sync on container start
SCHEDULER_TIMEZONE=Europe/Paris
```

## Supported Builders

| Builder | Status | Description |
|---------|--------|-------------|
| `tmdb_trending_weekly` | ✅ | TMDb weekly trending |
| `tmdb_trending_daily` | ✅ | TMDb daily trending |
| `tmdb_popular` | ✅ | TMDb popular movies/shows |
| `tmdb_discover` | ✅ | TMDb discover with filters |
| `trakt_trending` | ✅ | Trakt trending |
| `trakt_popular` | ✅ | Trakt popular |
| `trakt_chart` | ✅ | Trakt charts (watched, etc.) |
| `plex_search` | ✅ | Search Jellyfin library |
| `mdblist_list` | 🚧 | MDBList lists (planned) |

## Project Structure

```
jellyfin-collection/
├── src/jfc/                 # Source code
│   ├── cli.py               # CLI commands
│   ├── core/                # Configuration, logging, scheduler
│   ├── clients/             # API clients (Jellyfin, TMDb, etc.)
│   ├── models/              # Data models
│   ├── parsers/             # Kometa YAML parser
│   └── services/            # Business logic
├── config/                  # Kometa YAML configurations
├── docs/                    # Documentation
├── tests/                   # Unit tests
└── docker-compose.yml       # Docker setup
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

MIT License

Copyright (c) 2025-2026 Alexis CUCUMEL

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.

See the [LICENSE](LICENSE) file for full details.

## Acknowledgments

- [Kometa](https://github.com/Kometa-Team/Kometa) - For the YAML configuration format inspiration
- [Jellyfin](https://jellyfin.org/) - The best open-source media server
- [OpenAI](https://openai.com/) - For AI-powered poster generation
