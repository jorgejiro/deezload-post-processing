# deezload-post-processing

Docker service that watches a directory for Spotify playlist ZIPs downloaded
by Deezloader, and automatically converts them into well-tagged music
compilations ready for [Navidrome](https://www.navidrome.org/).

**What it does for each playlist:**

1. Detects when all ZIP parts have finished downloading (size + stability
   heuristic).
2. Fetches the playlist name and cover art from the Spotify API.
3. Extracts all ZIPs, tags every MP3 (`album`, `albumartist`, `tracknumber`,
   `compilation`) and writes `cover.jpg` to the output folder.
4. Moves the result to your music library and deletes the source ZIPs.

---

## Prerequisites

- Docker (Engine 24+ / Desktop 4.25+) with buildx if you build locally.
- A **Spotify Developer app** — see [Create a Spotify app](#create-a-spotify-app).
- A one-time [bootstrap](#one-time-spotify-authorization) to obtain the OAuth
  refresh token.

---

## Create a Spotify app

1. Go to <https://developer.spotify.com/dashboard> and log in.
2. Click **Create app**.  Name and description can be anything.
3. Under **Redirect URIs**, add `http://localhost:8888/callback` and save.
4. Open the app settings and note the **Client ID** and **Client Secret**.

---

## Quick start

```bash
# 1. Copy the example compose file and fill in your values
cp docker-compose.yml docker-compose.local.yml
#    Edit: SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, volume paths, PUID/PGID

# 2. Run the one-time authorization (on a machine with a browser — see below)
docker compose -f docker-compose.local.yml run --rm \
  -p 8888:8888 deezload-post deezload auth

# 3. Start the service
docker compose -f docker-compose.local.yml up -d
```

---

## One-time Spotify authorization

The service needs a **refresh token** stored in `/config/spotify_token.json`.
This token is permanent — you only do this step once.

### Option A — bootstrap on your Mac (recommended)

Run the auth command locally (not in Docker).  The browser opens automatically
and the token is written to the path you specify:

```bash
CONFIG_DIR=/path/to/config \
SPOTIFY_CLIENT_ID=your_id \
SPOTIFY_CLIENT_SECRET=your_secret \
SPOTIFY_REDIRECT_URI=http://localhost:8888/callback \
pip install deezload-post-processing && deezload auth
```

Then copy `spotify_token.json` to the NAS config volume:

```bash
scp /path/to/config/spotify_token.json \
    user@NAS_IP:/volume1/docker/deezload-post/config/
```

### Option B — bootstrap in Docker on the NAS

Expose port 8888 temporarily, set `SPOTIFY_REDIRECT_URI` to the NAS IP, and
register that URI in your Spotify app settings first:

```bash
# On the NAS via SSH:
docker run --rm -it \
  -p 8888:8888 \
  -v /volume1/docker/deezload-post/config:/config \
  -e SPOTIFY_CLIENT_ID=your_id \
  -e SPOTIFY_CLIENT_SECRET=your_secret \
  -e SPOTIFY_REDIRECT_URI=http://NAS_IP:8888/callback \
  -e CONFIG_DIR=/config \
  ghcr.io/youruser/deezload-post-processing:latest deezload auth
```

Open the printed URL in your browser, authorize, and the token is saved.

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `SPOTIFY_CLIENT_ID` | *(required)* | Spotify app client ID |
| `SPOTIFY_CLIENT_SECRET` | *(required)* | Spotify app client secret |
| `SPOTIFY_REDIRECT_URI` | `http://localhost:8888/callback` | Must match your Spotify app settings |
| `PUID` | `1000` | UID that will own output files |
| `PGID` | `1000` | GID that will own output files |
| `TZ` | `UTC` | Container timezone |
| `SCAN_INTERVAL_SECONDS` | `60` | Seconds between directory scans |
| `STABLE_MINUTES` | `5` | Minutes a file must be unchanged before processing |
| `PART_SIZE_THRESHOLD_MB` | `1000` | Size threshold separating full parts from the final part |
| `MIN_TOTAL_SIZE_MB` | `100` | Minimum total group size before considering it |
| `ALBUM_ARTIST` | `Various Artists` | Value written to the `albumartist` tag |
| `DELETE_ZIPS_AFTER` | `true` | Delete source ZIPs after successful processing |
| `LOG_LEVEL` | `INFO` | Python logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `INPUT_DIR` | `/input` | Directory to watch for ZIP files |
| `OUTPUT_DIR` | `/output` | Navidrome music library root |
| `CONFIG_DIR` | `/config` | Persistent config directory (Spotify token) |

---

## Synology DS920+ setup

### Find your PUID and PGID

SSH into your NAS and run:

```bash
id your_username
# uid=1026(your_username) gid=100(users) ...
```

Use `uid` as `PUID` and `gid` as `PGID`.

### Folder structure (example)

```
/volume1/
├── downloads/          → /input   (where Deezloader saves ZIPs)
├── music/              → /output  (Navidrome library root)
└── docker/
    └── deezload-post/
        └── config/     → /config  (Spotify token + state)
```

Create the config folder in advance:

```bash
mkdir -p /volume1/docker/deezload-post/config
```

### Via Container Manager (DSM 7.2+)

1. Open **Container Manager → Project → Create**.
2. Choose a project name (e.g. `deezload-post`).
3. Paste or import the contents of `docker-compose.yml`.
4. Edit the volume paths and credentials, then click **Next → Done**.

### Via SSH / CLI

```bash
# On the NAS
mkdir -p /volume1/docker/deezload-post
cd /volume1/docker/deezload-post

# Download or create docker-compose.yml with your values, then:
docker compose up -d
```

### Check logs

```bash
docker compose logs -f deezload-post
```

---

## Building the image

### Local build (single arch)

```bash
docker build -t deezload-post-processing:latest .
```

### Multi-arch build and push (amd64 + arm64)

```bash
# One-time setup of a multi-arch builder
docker buildx create --use --name multiarch --driver docker-container

# Build and push both architectures in one step
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t youruser/deezload-post-processing:latest \
  --push \
  .
```

---

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Lint and format
ruff check src tests
black src tests
```

### Running the auth bootstrap locally (development)

```bash
export SPOTIFY_CLIENT_ID=your_id
export SPOTIFY_CLIENT_SECRET=your_secret
export SPOTIFY_REDIRECT_URI=http://localhost:8888/callback
export CONFIG_DIR=./local-config
mkdir -p ./local-config
deezload auth
```
