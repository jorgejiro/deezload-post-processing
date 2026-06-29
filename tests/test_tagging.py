"""Tests for deezload.tagging: apply_tags, save_cover, collect_mp3s, extract_parts."""

import io
import zipfile
from pathlib import Path

import pytest
from mutagen.id3 import (
    APIC,
    COMM,
    ID3,
    TALB,
    TCMP,
    TCOM,
    TIT2,
    TPOS,
    TPE1,
    TPE2,
    TRCK,
    TYER,
)

from deezload.naming import ZipPart
from deezload.tagging import apply_tags, collect_mp3s, extract_parts, save_cover

PLAYLIST_ID = "7EAqBCOVkDZcbccjxZmgjp"

# Minimal 1×1 JPEG used as a fake embedded cover (tiny but valid JPEG structure).
_TINY_JPEG = (
    b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    b"\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t"
    b"\x08\n\x0c\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a"
    b"\x1f\x1e\x1d\x1a\x1c\x1c $.' \",#\x1c\x1c(7),01444\x1f'9=82<.342\x1e"
    b"\xff\xc0\x00\x0b\x08\x00\x01\x00\x01\x01\x01\x11\x00\xff\xc4\x00"
    b"\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00\x00"
    b"\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00"
    b"\x08\x01\x01\x00\x00?\x00\xf5\x0f\xff\xd9"
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mp3(path: Path, **frames) -> Path:
    """Create a minimal ID3-only file at *path* with optional initial frames."""
    tags = ID3()
    for frame in frames.values():
        tags.add(frame)
    tags.save(str(path), v2_version=3)
    return path


def _read_tags(path: Path) -> ID3:
    return ID3(str(path))


# ---------------------------------------------------------------------------
# apply_tags — written fields
# ---------------------------------------------------------------------------


class TestApplyTagsWrittenFields:
    def test_album_is_set(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3")
        apply_tags(mp3, album="My Playlist", album_artist="Various Artists", track_number=1, total_tracks=10)
        assert str(_read_tags(mp3)["TALB"]) == "My Playlist"

    def test_albumartist_is_set(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3")
        apply_tags(mp3, album="X", album_artist="Various Artists", track_number=1, total_tracks=5)
        assert str(_read_tags(mp3)["TPE2"]) == "Various Artists"

    def test_compilation_flag_is_1(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3")
        apply_tags(mp3, album="X", album_artist="VA", track_number=1, total_tracks=1)
        assert str(_read_tags(mp3)["TCMP"]) == "1"

    def test_tracknumber_format_n_of_total(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3")
        apply_tags(mp3, album="X", album_artist="VA", track_number=5, total_tracks=23)
        assert str(_read_tags(mp3)["TRCK"]) == "5/23"

    def test_tracknumber_first_track(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3")
        apply_tags(mp3, album="X", album_artist="VA", track_number=1, total_tracks=12)
        assert str(_read_tags(mp3)["TRCK"]) == "1/12"

    def test_tracknumber_last_track(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3")
        apply_tags(mp3, album="X", album_artist="VA", track_number=12, total_tracks=12)
        assert str(_read_tags(mp3)["TRCK"]) == "12/12"

    def test_overwrites_existing_album(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3", album=TALB(encoding=3, text="Old Album"))
        apply_tags(mp3, album="New Playlist", album_artist="VA", track_number=1, total_tracks=1)
        assert str(_read_tags(mp3)["TALB"]) == "New Playlist"

    def test_overwrites_existing_albumartist(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3", aa=TPE2(encoding=3, text="Original Artist"))
        apply_tags(mp3, album="X", album_artist="Various Artists", track_number=1, total_tracks=1)
        assert str(_read_tags(mp3)["TPE2"]) == "Various Artists"


# ---------------------------------------------------------------------------
# apply_tags — cleared fields
# ---------------------------------------------------------------------------


class TestApplyTagsClearedFields:
    def test_comment_is_removed(self, tmp_path):
        mp3 = _make_mp3(
            tmp_path / "t.mp3",
            comm=COMM(encoding=3, lang="eng", desc="", text="Some comment"),
        )
        apply_tags(mp3, album="X", album_artist="VA", track_number=1, total_tracks=1)
        assert "COMM::" not in _read_tags(mp3) and not any(
            k.startswith("COMM") for k in _read_tags(mp3)
        )

    def test_composer_is_removed(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3", comp=TCOM(encoding=3, text="Bach"))
        apply_tags(mp3, album="X", album_artist="VA", track_number=1, total_tracks=1)
        assert "TCOM" not in _read_tags(mp3)

    def test_discnumber_is_removed(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3", disc=TPOS(encoding=3, text="1/2"))
        apply_tags(mp3, album="X", album_artist="VA", track_number=1, total_tracks=1)
        assert "TPOS" not in _read_tags(mp3)

    def test_no_error_when_cleared_fields_absent(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3")
        # Should not raise even if COMM/TCOM/TPOS were never present.
        apply_tags(mp3, album="X", album_artist="VA", track_number=1, total_tracks=1)


# ---------------------------------------------------------------------------
# apply_tags — untouched fields
# ---------------------------------------------------------------------------


class TestApplyTagsUntouchedFields:
    def test_artist_is_preserved(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3", artist=TPE1(encoding=3, text="Daft Punk"))
        apply_tags(mp3, album="X", album_artist="VA", track_number=1, total_tracks=1)
        assert str(_read_tags(mp3)["TPE1"]) == "Daft Punk"

    def test_title_is_preserved(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3", title=TIT2(encoding=3, text="Get Lucky"))
        apply_tags(mp3, album="X", album_artist="VA", track_number=1, total_tracks=1)
        assert str(_read_tags(mp3)["TIT2"]) == "Get Lucky"

    def test_year_is_preserved(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3", year=TYER(encoding=3, text="2013"))
        apply_tags(mp3, album="X", album_artist="VA", track_number=1, total_tracks=1)
        loaded = _read_tags(mp3)
        # mutagen normalises TYER (ID3v2.3) → TDRC (ID3v2.4) on load
        year_frame = loaded.get("TDRC") or loaded.get("TYER")
        assert year_frame is not None
        assert str(year_frame) == "2013"

    def test_embedded_cover_is_preserved(self, tmp_path):
        # APIC frames are keyed as "APIC:<desc>" in mutagen.
        apic = APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=_TINY_JPEG)
        mp3 = _make_mp3(tmp_path / "t.mp3", apic=apic)
        apply_tags(mp3, album="X", album_artist="VA", track_number=1, total_tracks=1)
        loaded = _read_tags(mp3)
        apic_keys = [k for k in loaded if k.startswith("APIC")]
        assert apic_keys, "APIC frame was removed by apply_tags"
        assert loaded[apic_keys[0]].data == _TINY_JPEG

    def test_no_new_apic_added_when_absent(self, tmp_path):
        mp3 = _make_mp3(tmp_path / "t.mp3")
        apply_tags(mp3, album="X", album_artist="VA", track_number=1, total_tracks=1)
        assert "APIC:" not in _read_tags(mp3)

    def test_works_on_file_with_no_existing_id3(self, tmp_path):
        # Write a file with no ID3 header at all (bare bytes).
        mp3 = tmp_path / "bare.mp3"
        mp3.write_bytes(b"\xff\xfb\x90\x00" * 10)
        apply_tags(mp3, album="Y", album_artist="VA", track_number=2, total_tracks=5)
        assert str(_read_tags(mp3)["TALB"]) == "Y"


# ---------------------------------------------------------------------------
# save_cover
# ---------------------------------------------------------------------------


class TestSaveCover:
    def test_creates_cover_jpg(self, tmp_path):
        path = save_cover(_TINY_JPEG, tmp_path)
        assert path == tmp_path / "cover.jpg"
        assert path.exists()

    def test_cover_bytes_match(self, tmp_path):
        save_cover(_TINY_JPEG, tmp_path)
        assert (tmp_path / "cover.jpg").read_bytes() == _TINY_JPEG

    def test_overwrites_existing_cover(self, tmp_path):
        (tmp_path / "cover.jpg").write_bytes(b"old")
        save_cover(b"new content", tmp_path)
        assert (tmp_path / "cover.jpg").read_bytes() == b"new content"


# ---------------------------------------------------------------------------
# extract_parts + collect_mp3s
# ---------------------------------------------------------------------------


def _make_zip(zip_path: Path, mp3_names: list[str]) -> Path:
    """Create a ZIP at *zip_path* containing empty files with the given names."""
    with zipfile.ZipFile(zip_path, "w") as zf:
        for name in mp3_names:
            zf.writestr(name, b"")
    return zip_path


def _make_zip_part(zip_path: Path, mp3_names: list[str], part_index: int | None) -> ZipPart:
    _make_zip(zip_path, mp3_names)
    return ZipPart(path=zip_path, playlist_id=PLAYLIST_ID, part_index=part_index)


class TestExtractParts:
    def test_single_part_creates_subdir(self, tmp_path):
        zp = _make_zip_part(tmp_path / f"{PLAYLIST_ID}.zip", ["a.mp3"], None)
        extract_parts([zp], tmp_path / "out")
        assert (tmp_path / "out" / "000" / "a.mp3").exists()

    def test_two_parts_each_in_own_subdir(self, tmp_path):
        zp0 = _make_zip_part(tmp_path / f"00. {PLAYLIST_ID}.zip", ["a.mp3", "b.mp3"], 0)
        zp1 = _make_zip_part(tmp_path / f"01. {PLAYLIST_ID}.zip", ["c.mp3"], 1)
        out = tmp_path / "out"
        extract_parts([zp0, zp1], out)
        assert (out / "000" / "a.mp3").exists()
        assert (out / "000" / "b.mp3").exists()
        assert (out / "001" / "c.mp3").exists()

    def test_no_filename_collision_across_parts(self, tmp_path):
        # Both parts contain a file named "track.mp3".
        zp0 = _make_zip_part(tmp_path / f"00. {PLAYLIST_ID}.zip", ["track.mp3"], 0)
        zp1 = _make_zip_part(tmp_path / f"01. {PLAYLIST_ID}.zip", ["track.mp3"], 1)
        out = tmp_path / "out"
        extract_parts([zp0, zp1], out)
        assert (out / "000" / "track.mp3").exists()
        assert (out / "001" / "track.mp3").exists()


class TestCollectMp3s:
    def test_single_part_alphabetical_order(self, tmp_path):
        zp = _make_zip_part(tmp_path / f"{PLAYLIST_ID}.zip", ["c.mp3", "a.mp3", "b.mp3"], None)
        out = tmp_path / "out"
        extract_parts([zp], out)
        mp3s = collect_mp3s(out, [zp])
        assert [p.name for p in mp3s] == ["a.mp3", "b.mp3", "c.mp3"]

    def test_two_parts_part_order_before_alpha(self, tmp_path):
        # Part 0 contains z.mp3; part 1 contains a.mp3.
        # Part ordering takes precedence: z.mp3 must come before a.mp3.
        zp0 = _make_zip_part(tmp_path / f"00. {PLAYLIST_ID}.zip", ["z.mp3"], 0)
        zp1 = _make_zip_part(tmp_path / f"01. {PLAYLIST_ID}.zip", ["a.mp3"], 1)
        out = tmp_path / "out"
        extract_parts([zp0, zp1], out)
        mp3s = collect_mp3s(out, [zp0, zp1])
        assert [p.name for p in mp3s] == ["z.mp3", "a.mp3"]

    def test_case_insensitive_sort_within_part(self, tmp_path):
        zp = _make_zip_part(tmp_path / f"{PLAYLIST_ID}.zip", ["B.mp3", "a.mp3", "C.mp3"], None)
        out = tmp_path / "out"
        extract_parts([zp], out)
        mp3s = collect_mp3s(out, [zp])
        assert [p.name for p in mp3s] == ["a.mp3", "B.mp3", "C.mp3"]

    def test_non_mp3_files_excluded(self, tmp_path):
        zp = _make_zip_part(tmp_path / f"{PLAYLIST_ID}.zip", ["a.mp3", "cover.jpg", "b.mp3"], None)
        out = tmp_path / "out"
        extract_parts([zp], out)
        mp3s = collect_mp3s(out, [zp])
        assert all(p.suffix == ".mp3" for p in mp3s)
        assert len(mp3s) == 2

    def test_empty_part_yields_no_mp3s(self, tmp_path):
        zp = _make_zip_part(tmp_path / f"{PLAYLIST_ID}.zip", ["readme.txt"], None)
        out = tmp_path / "out"
        extract_parts([zp], out)
        assert collect_mp3s(out, [zp]) == []
