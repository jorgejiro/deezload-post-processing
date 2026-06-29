#!/bin/sh
set -e

PUID=${PUID:-1000}
PGID=${PGID:-1000}

# Adjust GID of the 'app' group to match PGID
current_gid=$(getent group app | cut -d: -f3)
if [ "$current_gid" != "$PGID" ]; then
    groupmod -o -g "$PGID" app
fi

# Adjust UID of the 'app' user to match PUID
current_uid=$(id -u app)
if [ "$current_uid" != "$PUID" ]; then
    usermod -o -u "$PUID" app
fi

# /config must be writable (Spotify token, processed-IDs log).
# Recursive so existing files (e.g. token written by a previous auth run with a
# different PUID) are always owned by the current app user.
chown -R app:app /config

exec gosu app "$@"
