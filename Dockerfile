# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Install gosu (privilege-dropping tool, needed for PUID/PGID support).
# The smoke-test at the end verifies gosu is operational before the layer is committed.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/* \
    && gosu nobody true

# Create a dedicated non-root user. The entrypoint adjusts its UID/GID at
# container start to match PUID/PGID, so output files are owned correctly.
RUN groupadd -g 1000 app \
    && useradd -u 1000 -g app -M -s /sbin/nologin app

# Create the three volume mount points.
# /config must be writable by the app user (Spotify token lives here).
RUN mkdir -p /input /output /config \
    && chown app:app /config

WORKDIR /app

# Copy only what pip needs first so that code changes don't invalidate the
# dependency layer.
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir .

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

VOLUME ["/input", "/output", "/config"]

ENTRYPOINT ["/entrypoint.sh"]
CMD ["deezload"]
