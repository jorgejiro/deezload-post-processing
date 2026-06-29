"""Tests for deezload.spotify: SpotifyClient (mocked API)."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from deezload.spotify import PlaylistInfo, SpotifyClient

PLAYLIST_ID = "7EAqBCOVkDZcbccjxZmgjp"
COVER_URL = "https://i.scdn.co/image/ab67616d0000b273example"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class _FakeConfig:
    spotify_client_id = "test_client_id"
    spotify_client_secret = "test_client_secret"
    spotify_redirect_uri = "http://localhost:8888/callback"

    def __init__(self, config_dir: str):
        self.config_dir = config_dir


def _fake_config(tmp_path: Path) -> _FakeConfig:
    return _FakeConfig(config_dir=str(tmp_path))


def _write_token(config_dir: Path) -> None:
    """Write a minimal valid token cache so SpotifyClient does not raise."""
    token = {
        "access_token": "fake_access_token",
        "token_type": "Bearer",
        "expires_in": 3600,
        "refresh_token": "fake_refresh_token",
        "scope": "playlist-read-private playlist-read-collaborative",
        "expires_at": 9_999_999_999,
    }
    (config_dir / "spotify_token.json").write_text(json.dumps(token))


def _make_client(tmp_path: Path) -> SpotifyClient:
    _write_token(tmp_path)
    config = _fake_config(tmp_path)
    with patch("deezload.spotify.spotipy.Spotify"):
        client = SpotifyClient(config)
    # Replace internal spotipy instance with a plain MagicMock.
    client._sp = MagicMock()
    return client


# ---------------------------------------------------------------------------
# SpotifyClient.get_playlist_info
# ---------------------------------------------------------------------------


class TestGetPlaylistInfo:
    def test_returns_name_and_cover_url(self, tmp_path):
        client = _make_client(tmp_path)
        client._sp.playlist.return_value = {
            "name": "My Playlist",
            "images": [{"url": COVER_URL, "width": 640, "height": 640}],
        }
        info = client.get_playlist_info(PLAYLIST_ID)
        assert info.name == "My Playlist"
        assert info.cover_url == COVER_URL

    def test_uses_first_image_largest_first(self, tmp_path):
        client = _make_client(tmp_path)
        client._sp.playlist.return_value = {
            "name": "P",
            "images": [
                {"url": "https://big.example.com", "width": 640},
                {"url": "https://small.example.com", "width": 300},
            ],
        }
        info = client.get_playlist_info(PLAYLIST_ID)
        assert info.cover_url == "https://big.example.com"

    def test_cover_url_none_when_images_empty(self, tmp_path):
        client = _make_client(tmp_path)
        client._sp.playlist.return_value = {"name": "P", "images": []}
        info = client.get_playlist_info(PLAYLIST_ID)
        assert info.cover_url is None

    def test_cover_url_none_when_images_key_missing(self, tmp_path):
        client = _make_client(tmp_path)
        client._sp.playlist.return_value = {"name": "P"}
        info = client.get_playlist_info(PLAYLIST_ID)
        assert info.cover_url is None

    def test_requests_only_name_and_images_fields(self, tmp_path):
        client = _make_client(tmp_path)
        client._sp.playlist.return_value = {"name": "P", "images": []}
        client.get_playlist_info(PLAYLIST_ID)
        client._sp.playlist.assert_called_once_with(PLAYLIST_ID, fields="name,images")

    def test_returns_playlist_info_dataclass(self, tmp_path):
        client = _make_client(tmp_path)
        client._sp.playlist.return_value = {"name": "X", "images": []}
        info = client.get_playlist_info(PLAYLIST_ID)
        assert isinstance(info, PlaylistInfo)


# ---------------------------------------------------------------------------
# SpotifyClient.download_cover
# ---------------------------------------------------------------------------


class TestDownloadCover:
    def test_returns_response_bytes(self, tmp_path):
        client = _make_client(tmp_path)
        fake_bytes = b"\xff\xd8\xff fake jpeg data"
        with patch("deezload.spotify.requests.get") as mock_get:
            mock_get.return_value.content = fake_bytes
            mock_get.return_value.raise_for_status = MagicMock()
            result = client.download_cover(COVER_URL)
        assert result == fake_bytes

    def test_passes_correct_url(self, tmp_path):
        client = _make_client(tmp_path)
        with patch("deezload.spotify.requests.get") as mock_get:
            mock_get.return_value.content = b""
            mock_get.return_value.raise_for_status = MagicMock()
            client.download_cover(COVER_URL)
        mock_get.assert_called_once_with(COVER_URL, timeout=30)

    def test_raises_on_http_error(self, tmp_path):
        client = _make_client(tmp_path)
        with patch("deezload.spotify.requests.get") as mock_get:
            mock_get.return_value.raise_for_status.side_effect = Exception("HTTP 404")
            with pytest.raises(Exception, match="HTTP 404"):
                client.download_cover(COVER_URL)


# ---------------------------------------------------------------------------
# SpotifyClient.__init__
# ---------------------------------------------------------------------------


class TestSpotifyClientInit:
    def test_raises_when_token_file_missing(self, tmp_path):
        config = _fake_config(tmp_path)
        with pytest.raises(FileNotFoundError, match="deezload auth"):
            SpotifyClient(config)

    def test_succeeds_when_token_file_present(self, tmp_path):
        _write_token(tmp_path)
        config = _fake_config(tmp_path)
        with patch("deezload.spotify.spotipy.Spotify"):
            client = SpotifyClient(config)
        assert client is not None
