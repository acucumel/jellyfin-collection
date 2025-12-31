#!/bin/bash
# =============================================================================
# Docker Entrypoint - Handle PUID/PGID for permission management
# =============================================================================

set -e

# Default values
PUID=${PUID:-1000}
PGID=${PGID:-1000}

echo "Starting with UID: $PUID, GID: $PGID"

# Create group if it doesn't exist
if ! getent group jfc > /dev/null 2>&1; then
    groupadd -g "$PGID" jfc
elif [ "$(getent group jfc | cut -d: -f3)" != "$PGID" ]; then
    groupmod -g "$PGID" jfc
fi

# Create user if it doesn't exist
if ! getent passwd jfc > /dev/null 2>&1; then
    useradd -u "$PUID" -g jfc -d /app -s /bin/bash jfc
elif [ "$(id -u jfc)" != "$PUID" ]; then
    usermod -u "$PUID" jfc
fi

# Fix ownership of directories
chown -R jfc:jfc /app /data /logs 2>/dev/null || true
# Config is read-only, don't chown

# Execute command as jfc user
exec gosu jfc "$@"
