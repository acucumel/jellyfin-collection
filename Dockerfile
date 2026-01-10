# =============================================================================
# JELLYFIN COLLECTION - DOCKERFILE
# =============================================================================

FROM python:3.11-slim AS base

# Labels
LABEL maintainer="4lx69"
LABEL description="Kometa-compatible collection manager for Jellyfin"

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# -----------------------------------------------------------------------------
# Dependencies stage
# -----------------------------------------------------------------------------
FROM base AS dependencies

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy source and install package
COPY pyproject.toml README.md ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

# -----------------------------------------------------------------------------
# Production stage
# -----------------------------------------------------------------------------
FROM base AS production

# Install gosu for proper privilege dropping
RUN apt-get update && apt-get install -y --no-install-recommends \
    gosu \
    && rm -rf /var/lib/apt/lists/* \
    && gosu nobody true

# Copy installed packages from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Create directories (ownership will be set by entrypoint based on PUID/PGID)
RUN mkdir -p /config /data /logs

# Copy application
COPY src/ ./src/

# Copy entrypoint script
COPY docker-entrypoint.sh /usr/local/bin/
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Volumes
VOLUME ["/config", "/data", "/logs"]

# Environment defaults for PUID/PGID
ENV PUID=1000 \
    PGID=1000

# Healthcheck
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD pgrep -f "jfc.cli" || exit 1

# Entrypoint handles user creation and privilege drop
ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]

# Default command: run scheduler daemon
CMD ["python", "-m", "jfc.cli", "schedule"]
