# =============================================================================
# JELLYFIN COLLECTION - DOCKERFILE
# =============================================================================

FROM python:3.11-slim AS base

# Labels
LABEL maintainer="Alexis CUCUMEL"
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

# Copy installed packages from dependencies stage
COPY --from=dependencies /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=dependencies /usr/local/bin /usr/local/bin

# Create non-root user
RUN groupadd -r jfc && useradd -r -g jfc jfc

# Create directories
RUN mkdir -p /config /data /logs && \
    chown -R jfc:jfc /app /config /data /logs

# Copy application
COPY --chown=jfc:jfc src/ ./src/

# Switch to non-root user
USER jfc

# Volumes
VOLUME ["/config", "/data", "/logs"]

# Healthcheck - vérifie que le process Python tourne
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD pgrep -f "jfc.cli" || exit 1

# Default command: run scheduler daemon
# Override with: docker run ... python -m jfc.cli run (single run)
CMD ["python", "-m", "jfc.cli", "schedule"]
