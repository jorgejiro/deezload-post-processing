"""Tests for deezload.pipeline: process_group orchestration."""

import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from mutagen.id3 import ID3, TALB, TIT2, TPE1

from deezload.naming import ZipPart
from deezload.pipeline import process_group
from deezload.spotify import PlaylistInfo

PLAYLIST_ID = "7EAqBCOVkDZcbccjxZmgjp"
PLAYLIST_NAME = "My Test Playlist"
COVER_BYTES = b"\xff\xd8\xff fake cover"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mp3_in_zip(zip_path: Path, tracks: list[str]) -> None:
    """Create a ZIP containing minimal ID3-tagged MP3 files."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name in tracks:
            # Create a minimal ID3-only file in memory.
            import io
            from mutagen.id3 import ID3
            buf = io.BytesIO()
            tags = ID3()
            tags.add(TIT2(encoding=3, text=name.replace(".mp3", "")))
            tags.add(TPE1(encoding=3, text="Test Artist"))
            tags.save(buf, v2_version=3)
            zf.writestr(name, buf.getvalue())


def _make_part(zip_path: Path, tracks: list[str], part_index: int | None) -> ZipPart:
    _make_mp3_in_zip(zip_path, tracks)
    return ZipPart(path=zip_path, playlist_id=PLAYLIST_ID, part_index=part_index)


def _make_spotify(*, name: str = PLAYLIST_NAME, cover_url: str | None = "http://cover") -> MagicMock:
    client = MagicMock()
    client.get_playlist_info.return_value = PlaylistInfo(name=name, cover_url=cover_url)
    client.download_cover.return_value = COVER_BYTES
    return client


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestProcessGroupHappyPath:
    def test_creates_output_folder(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        part = _make_part(input_dir / f"{PLAYLIST_ID}.zip", ["01 Track.mp3"], None)
        process_group(
            PLAYLIST_ID, [part],
            spotify=_make_spotify(),
            output_dir=output_dir,
            album_artist="Various Artists",
            delete_zips=False,
        )
        assert (output_dir / PLAYLIST_NAME).is_dir()

    def test_moves_mp3s_to_output_folder(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        part = _make_part(
            input_dir / f"{PLAYLIST_ID}.zip",
            ["01 First.mp3", "02 Second.mp3"],
            None,
        )
        process_group(
            PLAYLIST_ID, [part],
            spotify=_make_spotify(),
            output_dir=output_dir,
            album_artist="Various Artists",
            delete_zips=False,
        )
        dest = output_dir / PLAYLIST_NAME
        assert (dest / "01 First.mp3").exists()
        assert (dest / "02 Second.mp3").exists()

    def test_saves_cover_jpg(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        part = _make_part(input_dir / f"{PLAYLIST_ID}.zip", ["t.mp3"], None)
        process_group(
            PLAYLIST_ID, [part],
            spotify=_make_spotify(cover_url="http://cover"),
            output_dir=output_dir,
            album_artist="VA",
            delete_zips=False,
        )
        cover = output_dir / PLAYLIST_NAME / "cover.jpg"
        assert cover.exists()
        assert cover.read_bytes() == COVER_BYTES

    def test_tags_are_applied(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        part = _make_part(
            input_dir / f"{PLAYLIST_ID}.zip",
            ["01 Track.mp3", "02 Track.mp3"],
            None,
        )
        process_group(
            PLAYLIST_ID, [part],
            spotify=_make_spotify(),
            output_dir=output_dir,
            album_artist="Various Artists",
            delete_zips=False,
        )
        dest = output_dir / PLAYLIST_NAME
        tags = ID3(str(dest / "01 Track.mp3"))
        assert str(tags["TALB"]) == PLAYLIST_NAME
        assert str(tags["TPE2"]) == "Various Artists"
        assert str(tags["TRCK"]) == "1/2"
        assert str(tags["TCMP"]) == "1"

    def test_track_numbers_across_two_parts(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        part0 = _make_part(
            input_dir / f"00. {PLAYLIST_ID}.zip",
            ["a.mp3", "b.mp3"],
            0,
        )
        part1 = _make_part(
            input_dir / f"01. {PLAYLIST_ID}.zip",
            ["c.mp3"],
            1,
        )
        process_group(
            PLAYLIST_ID, [part0, part1],
            spotify=_make_spotify(),
            output_dir=output_dir,
            album_artist="VA",
            delete_zips=False,
        )
        dest = output_dir / PLAYLIST_NAME
        assert str(ID3(str(dest / "a.mp3"))["TRCK"]) == "1/3"
        assert str(ID3(str(dest / "b.mp3"))["TRCK"]) == "2/3"
        assert str(ID3(str(dest / "c.mp3"))["TRCK"]) == "3/3"

    def test_deletes_zips_when_configured(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        zip_path = input_dir / f"{PLAYLIST_ID}.zip"
        part = _make_part(zip_path, ["t.mp3"], None)
        process_group(
            PLAYLIST_ID, [part],
            spotify=_make_spotify(),
            output_dir=output_dir,
            album_artist="VA",
            delete_zips=True,
        )
        assert not zip_path.exists()

    def test_does_not_delete_zips_when_not_configured(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        zip_path = input_dir / f"{PLAYLIST_ID}.zip"
        part = _make_part(zip_path, ["t.mp3"], None)
        process_group(
            PLAYLIST_ID, [part],
            spotify=_make_spotify(),
            output_dir=output_dir,
            album_artist="VA",
            delete_zips=False,
        )
        assert zip_path.exists()


# ---------------------------------------------------------------------------
# Edge cases and error handling
# ---------------------------------------------------------------------------


class TestProcessGroupEdgeCases:
    def test_skips_if_output_folder_exists(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()
        (output_dir / PLAYLIST_NAME).mkdir()

        zip_path = input_dir / f"{PLAYLIST_ID}.zip"
        part = _make_part(zip_path, ["t.mp3"], None)
        spotify = _make_spotify()

        process_group(
            PLAYLIST_ID, [part],
            spotify=spotify,
            output_dir=output_dir,
            album_artist="VA",
            delete_zips=False,
        )
        # get_playlist_info was called to derive folder name, but no further work.
        spotify.download_cover.assert_not_called()

    def test_raises_when_zip_has_no_mp3s(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        zip_path = input_dir / f"{PLAYLIST_ID}.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("readme.txt", "no audio here")
        part = ZipPart(path=zip_path, playlist_id=PLAYLIST_ID, part_index=None)

        with pytest.raises(RuntimeError, match="No MP3 files"):
            process_group(
                PLAYLIST_ID, [part],
                spotify=_make_spotify(),
                output_dir=output_dir,
                album_artist="VA",
                delete_zips=False,
            )

    def test_cleans_up_partial_output_on_failure(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        part = _make_part(input_dir / f"{PLAYLIST_ID}.zip", ["t.mp3"], None)
        spotify = _make_spotify()
        spotify.download_cover.side_effect = RuntimeError("network error")

        with pytest.raises(RuntimeError, match="network error"):
            process_group(
                PLAYLIST_ID, [part],
                spotify=spotify,
                output_dir=output_dir,
                album_artist="VA",
                delete_zips=False,
            )
        # Partial output folder must not linger.
        assert not (output_dir / PLAYLIST_NAME).exists()

    def test_does_not_delete_zips_on_failure(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        zip_path = input_dir / f"{PLAYLIST_ID}.zip"
        part = _make_part(zip_path, ["t.mp3"], None)
        spotify = _make_spotify()
        spotify.download_cover.side_effect = RuntimeError("network error")

        with pytest.raises(RuntimeError):
            process_group(
                PLAYLIST_ID, [part],
                spotify=spotify,
                output_dir=output_dir,
                album_artist="VA",
                delete_zips=True,  # requested, but must not happen on failure
            )
        assert zip_path.exists()

    def test_no_cover_download_when_cover_url_is_none(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        part = _make_part(input_dir / f"{PLAYLIST_ID}.zip", ["t.mp3"], None)
        spotify = _make_spotify(cover_url=None)

        process_group(
            PLAYLIST_ID, [part],
            spotify=spotify,
            output_dir=output_dir,
            album_artist="VA",
            delete_zips=False,
        )
        spotify.download_cover.assert_not_called()
        assert not (output_dir / PLAYLIST_NAME / "cover.jpg").exists()

    def test_folder_name_sanitized(self, tmp_path):
        input_dir = tmp_path / "input"
        input_dir.mkdir()
        output_dir = tmp_path / "output"
        output_dir.mkdir()

        part = _make_part(input_dir / f"{PLAYLIST_ID}.zip", ["t.mp3"], None)
        process_group(
            PLAYLIST_ID, [part],
            spotify=_make_spotify(name='Rock: "Best of" 2024'),
            output_dir=output_dir,
            album_artist="VA",
            delete_zips=False,
        )
        assert (output_dir / "Rock_ _Best of_ 2024").is_dir()
