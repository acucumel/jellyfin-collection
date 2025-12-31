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
```

2. **Download docker-compose.yml**

```bash
curl -O https://raw.githubusercontent.com/acucumel/jellyfin-collection/master/docker-compose.yml
```

3. **Create environment file**

```bash
curl -O https://raw.githubusercontent.com/acucumel/jellyfin-collection/master/.env.example
cp .env.example .env
```

4. **Edit `.env` with your settings**

```bash
nano .env
```

At minimum, set these values:

```bash
JELLYFIN_URL=http://your-jellyfin-server:8096
JELLYFIN_API_KEY=your_jellyfin_api_key
TMDB_API_KEY=your_tmdb_api_key
```

5. **Create config directory and add Kometa YAML files**

```bash
mkdir -p config
# Copy your Kometa config files here
```

6. **Start the container**

```bash
docker-compose up -d
```

7. **View logs**

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
docker run -d \
  --name jellyfin-collection \
  --restart unless-stopped \
  -e JELLYFIN_URL=http://your-jellyfin:8096 \
  -e JELLYFIN_API_KEY=your_api_key \
  -e TMDB_API_KEY=your_tmdb_key \
  -v ./config:/config:ro \
  -v jfc-data:/data \
  -v jfc-logs:/logs \
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

### 3. Dry Run

Preview what changes will be made without actually modifying anything:

```bash
# Docker
docker-compose exec jellyfin-collection jfc run --dry-run

# Manual
jfc run --dry-run
```

### 4. Full Run

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
