# Installation Guide

This guide covers installing Jellyfin Collection (JFC) using Docker or manual installation.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Docker Installation (Recommended)](#docker-installation-recommended)
  - [Using Docker Compose](#using-docker-compose)
  - [Using Portainer](#using-portainer)
  - [Using Docker CLI](#using-docker-cli)
- [Manual Installation](#manual-installation)
- [First Run](#first-run)
- [Verifying Installation](#verifying-installation)

## Prerequisites

### Required

- **Jellyfin Server** with API access
- **TMDb API Key** - [Get one here](https://www.themoviedb.org/settings/api)

### Optional

- **Radarr** - For automatically requesting missing movies
- **Sonarr** - For automatically requesting missing TV shows
- **Trakt Account** - For Trakt lists and charts
- **Discord Webhook** - For notifications
- **OpenAI API Key** - For AI poster generation

## Docker Installation (Recommended)

### Using Docker Compose

1. **Create project directory**

```bash
mkdir jellyfin-collection && cd jellyfin-collection
mkdir -p config data logs
```

2. **Create `docker-compose.yml`**

```yaml
services:
  jellyfin-collection:
    image: ghcr.io/acucumel/jellyfin-collection:latest
    container_name: jellyfin-collection
    restart: unless-stopped
    environment:
      # User/Group IDs for file permissions
      - PUID=1000
      - PGID=1000

      # Secrets only - all other config is in config/config.yml
      - JELLYFIN_API_KEY=${JELLYFIN_API_KEY}
      - TMDB_API_KEY=${TMDB_API_KEY}

      # Optional secrets
      - TRAKT_CLIENT_ID=${TRAKT_CLIENT_ID:-}
      - TRAKT_CLIENT_SECRET=${TRAKT_CLIENT_SECRET:-}
      - RADARR_API_KEY=${RADARR_API_KEY:-}
      - SONARR_API_KEY=${SONARR_API_KEY:-}
      - OPENAI_API_KEY=${OPENAI_API_KEY:-}
    volumes:
      - ./config:/config:ro    # config.yml + collection YAML files
      - ./data:/data           # Generated data (posters, cache)
      - ./logs:/logs           # Application logs
    networks:
      - media-stack

networks:
  media-stack:
    external: true
```

> **Note:** All non-secret configuration (URLs, schedules, etc.) is now in `config/config.yml`.

3. **Create `config/config.yml`**

```yaml
# Main configuration - secrets are in .env
settings:
  jellyfin:
    url: http://your-jellyfin:8096

  tmdb:
    language: fr
    region: FR

  openai:
    enabled: true
    missing_only: true

  radarr:
    url: http://radarr:7878
    root_folder: /movies
    quality_profile: HD-1080p

  sonarr:
    url: http://sonarr:8989
    root_folder: /tv
    quality_profile: HD-1080p

  discord:
    webhook_url: https://discord.com/api/webhooks/xxx

  scheduler:
    collections_cron: "0 17 * * *"
    run_on_start: true
    timezone: Europe/Paris

libraries:
  Films:
    collection_files:
      - file: Films.yml
  Séries:
    collection_files:
      - file: Series.yml
```

4. **Create a collection file like `config/Films.yml`**

```yaml
collections:
  "Trending Movies":
    tmdb_trending_weekly: 20
    sync_mode: sync
    schedule: daily
```

5. **Start the container**

```bash
docker-compose up -d
```

6. **View logs**

```bash
docker-compose logs -f
```

### Using Portainer

1. Go to **Stacks** > **Add stack**

2. Select **Repository** and enter:
   - Repository URL: `https://github.com/acucumel/jellyfin-collection`
   - Compose path: `docker-compose.portainer.yml`

3. Add **Environment variables** in the Portainer UI:
   - `JELLYFIN_URL`
   - `JELLYFIN_API_KEY`
   - `TMDB_API_KEY`
   - (other optional variables)

4. Click **Deploy the stack**

### Using Docker CLI

```bash
# Create directories first
mkdir -p config data logs

# Run container
docker run -d \
  --name jellyfin-collection \
  --restart unless-stopped \
  -e JELLYFIN_URL=http://your-jellyfin:8096 \
  -e JELLYFIN_API_KEY=your_api_key \
  -e TMDB_API_KEY=your_tmdb_key \
  -v $(pwd)/config:/config:ro \
  -v $(pwd)/data:/data \
  -v $(pwd)/logs:/logs \
  ghcr.io/acucumel/jellyfin-collection:latest
```

## Manual Installation

### Requirements

- Python 3.11 or higher
- pip

### Steps

1. **Clone the repository**

```bash
git clone https://github.com/acucumel/jellyfin-collection.git
cd jellyfin-collection
```

2. **Create virtual environment (optional but recommended)**

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
# or
venv\Scripts\activate     # Windows
```

3. **Install dependencies**

```bash
pip install -e .
```

4. **Create environment file**

```bash
cp .env.example .env
nano .env  # Edit with your settings
```

5. **Create config directory**

```bash
mkdir -p config
# Add your Kometa YAML files
```

6. **Run JFC**

```bash
# Single run
jfc run --config ./config

# With scheduler
jfc schedule
```

## First Run

### 1. Test Connections

Before running a full sync, test your service connections:

```bash
# Docker
docker-compose exec jellyfin-collection jfc test-connections

# Manual
jfc test-connections
```

Expected output:

```
┏━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━┓
┃ Service    ┃ Status ┃ Details         ┃
┡━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━┩
│ Jellyfin   │ OK     │ 3 libraries     │
│ TMDb       │ OK     │ Connected       │
│ Radarr     │ OK     │ Connected       │
│ Sonarr     │ OK     │ Connected       │
│ OpenAI     │ OK     │ Credits OK      │
└────────────┴────────┴─────────────────┘
```

### 2. Validate Configuration

```bash
# Docker
docker-compose exec jellyfin-collection jfc validate

# Manual
jfc validate
```

### 3. Authenticate with Trakt (Optional)

If you use Trakt lists or charts, authenticate using the OAuth Device Code flow:

```bash
# Docker
docker-compose exec jellyfin-collection jfc trakt-auth

# Manual
jfc trakt-auth
```

This will display a code and URL. Open the URL in your browser, log into Trakt, and enter the code. Tokens are saved automatically and refreshed when needed.

### 4. Dry Run

Preview what changes will be made without actually modifying anything:

```bash
# Docker
docker-compose exec jellyfin-collection jfc run --dry-run

# Manual
jfc run --dry-run
```

### 5. Full Run

When everything looks good:

```bash
# Docker - already running with scheduler
# Manual
jfc run
```

## Verifying Installation

### Check Container Status

```bash
docker-compose ps
```

### Check Logs

```bash
# Docker
docker-compose logs -f jellyfin-collection

# Manual - check logs directory
tail -f logs/jfc.log
```

### Check Jellyfin

Open your Jellyfin server and verify that collections have been created in your libraries.

## Troubleshooting

### Container won't start

1. Check environment variables are set correctly
2. Verify config directory exists and contains valid YAML files
3. Check logs: `docker-compose logs jellyfin-collection`

### Connection errors

1. Ensure services are reachable from the container
2. Verify API keys are correct
3. Check network configuration (containers might need same Docker network)

### No collections created

1. Verify Kometa YAML syntax with `jfc validate`
2. Check library names match exactly with Jellyfin
3. Run with `--dry-run` to see what would be created

## Next Steps

- [Configuration Guide](configuration.md) - Full configuration reference
- [Kometa Migration](kometa-migration.md) - Migrate from Kometa/PMM
- [AI Poster Generation](ai-posters.md) - Setup AI posters
