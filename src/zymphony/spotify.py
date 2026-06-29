"""Spotify OAuth (Authorization Code + refresh token) and playlist metadata fetching."""

import http.server
import logging
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path
from threading import Event

import requests
import spotipy
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import CacheFileHandler, SpotifyOAuth

log = logging.getLogger(__name__)

SCOPES = "playlist-read-private playlist-read-collaborative"
TOKEN_FILENAME = "spotify_token.json"
_BOOTSTRAP_TIMEOUT_S = 300  # 5 min to complete browser auth


@dataclass
class PlaylistInfo:
    name: str
    cover_url: str | None  # URL of the largest image; None if playlist has no art


def _token_path(config_dir: str) -> Path:
    return Path(config_dir) / TOKEN_FILENAME


def _make_oauth(config) -> SpotifyOAuth:
    return SpotifyOAuth(
        client_id=config.spotify_client_id,
        client_secret=config.spotify_client_secret,
        redirect_uri=config.spotify_redirect_uri,
        scope=SCOPES,
        cache_handler=CacheFileHandler(cache_path=str(_token_path(config.config_dir))),
        open_browser=False,
    )


def bootstrap_auth(config, *, force: bool = False) -> None:
    """Interactive one-time OAuth bootstrap.  Saves refresh token to /config.

    Run this once on any machine with a browser.  After this, the service
    renews the access token automatically and never needs re-authorization.

    Pass ``force=True`` to override an existing cached token.
    """
    oauth = _make_oauth(config)

    if not force:
        cached = oauth.get_cached_token()
        if cached:
            token_file = _token_path(config.config_dir)
            log.info("Spotify token already present at %s", token_file)
            print(
                f"Token already present at {token_file}.\n"
                "Pass --force to re-authorize."
            )
            return

    auth_url = oauth.get_authorize_url()
    parsed = urllib.parse.urlparse(config.spotify_redirect_uri)
    port = parsed.port or 8888
    callback_path = parsed.path or "/callback"

    captured: dict = {}
    done = Event()

    class _Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            req_path = urllib.parse.urlparse(self.path).path
            if req_path == callback_path:
                params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
                if "code" in params:
                    captured["code"] = params["code"][0]
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.end_headers()
                    self.wfile.write(
                        b"<h2>Authorization successful!"
                        b" You can close this window.</h2>"
                    )
                    done.set()
                    return
            self.send_response(404)
            self.end_headers()

        def log_message(self, *_):
            pass  # suppress default access log

    server = http.server.HTTPServer(("", port), _Handler)
    server.timeout = 2  # short poll so we check `done` frequently

    print(f"\nOpen this URL in your browser to authorize Zymphony:\n\n  {auth_url}\n")
    try:
        webbrowser.open(auth_url)
        print("(Browser opened automatically.  If nothing happened, copy the URL above.)")
    except Exception:
        print("(Headless environment — copy the URL above into your browser.)")

    print(f"Waiting for the callback on port {port} (timeout: {_BOOTSTRAP_TIMEOUT_S}s)...")
    elapsed = 0
    while not done.is_set() and elapsed < _BOOTSTRAP_TIMEOUT_S:
        server.handle_request()
        elapsed += server.timeout
    server.server_close()

    if "code" not in captured:
        raise TimeoutError(
            f"No authorization code received within {_BOOTSTRAP_TIMEOUT_S}s.  "
            "Make sure the Redirect URI registered in your Spotify app settings "
            f"matches '{config.spotify_redirect_uri}'."
        )

    oauth.get_access_token(captured["code"], as_dict=True, check_cache=False)
    token_file = _token_path(config.config_dir)
    log.info("Spotify refresh token saved to %s", token_file)
    print(f"\nSuccess!  Token saved to {token_file}.")
    print("You can now start the service; re-authorization is not needed.")


class SpotifyClient:
    """Thin wrapper around spotipy for the subset of the API we use."""

    def __init__(self, config):
        token_file = _token_path(config.config_dir)
        if not token_file.exists():
            raise FileNotFoundError(
                f"Spotify token not found at {token_file}.  "
                "Run 'zymphony auth' first."
            )
        # Verify readability before handing to spotipy; an unreadable token
        # causes spotipy to silently fall back to interactive auth (which fails
        # in a headless container).
        try:
            token_file.read_text()
        except OSError as exc:
            raise PermissionError(
                f"Cannot read Spotify token at {token_file}: {exc}.  "
                "Check that the file is owned by the service user (PUID/PGID)."
            ) from exc
        self._sp = spotipy.Spotify(auth_manager=_make_oauth(config))

    def get_playlist_info(self, playlist_id: str) -> PlaylistInfo:
        """Return name and highest-resolution cover URL for *playlist_id*.

        Falls back to (playlist_id, no cover) when the API returns 404.  This
        happens with Spotify-generated algorithmic playlists (Discover Weekly,
        Daily Mix, etc.) and with playlists that belong to a different account.
        """
        try:
            # market="from_token" makes Spotify use the country of the
            # authenticated account, which is required for editorial/regional
            # playlists (e.g. "Los 90 España") that return 404 without it.
            data = self._sp.playlist(playlist_id, fields="name,images", market="from_token")
        except SpotifyException as exc:
            if exc.http_status == 404:
                log.warning(
                    "Spotify API returned 404 for playlist %s — "
                    "using playlist ID as album name and skipping cover art.  "
                    "This can happen with algorithmic playlists (Discover Weekly, "
                    "Daily Mix) or playlists owned by a different account.",
                    playlist_id,
                )
                return PlaylistInfo(name=playlist_id, cover_url=None)
            raise
        name: str = data["name"]
        images: list = data.get("images") or []
        # Spotify returns images sorted largest first.
        cover_url = images[0]["url"] if images else None
        return PlaylistInfo(name=name, cover_url=cover_url)

    def download_cover(self, cover_url: str) -> bytes:
        """Download and return the raw image bytes at *cover_url*."""
        resp = requests.get(cover_url, timeout=30)
        resp.raise_for_status()
        return resp.content
