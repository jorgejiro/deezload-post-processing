"""Tests for deezload.naming: ID extraction, ZIP grouping, and folder sanitization."""

from pathlib import Path

import pytest

from deezload.naming import ZipPart, extract_playlist_id, group_zips, sanitize_folder_name

# A valid Spotify playlist ID used throughout the tests.
VALID_ID = "7EAqBCOVkDZcbccjxZmgjp"
OTHER_ID = "1ABcDefGHijklMNopqrStu"


# ---------------------------------------------------------------------------
# extract_playlist_id
# ---------------------------------------------------------------------------


class TestExtractPlaylistId:
    def test_bare_id_no_extension(self):
        assert extract_playlist_id(VALID_ID) == (VALID_ID, None)

    def test_bare_id_with_zip_extension(self):
        assert extract_playlist_id(f"{VALID_ID}.zip") == (VALID_ID, None)

    def test_bare_id_zip_extension_uppercase(self):
        assert extract_playlist_id(f"{VALID_ID}.ZIP") == (VALID_ID, None)

    def test_prefixed_part_00(self):
        assert extract_playlist_id(f"00. {VALID_ID}.zip") == (VALID_ID, 0)

    def test_prefixed_part_01(self):
        assert extract_playlist_id(f"01. {VALID_ID}.zip") == (VALID_ID, 1)

    def test_prefixed_part_02(self):
        assert extract_playlist_id(f"02. {VALID_ID}.zip") == (VALID_ID, 2)

    def test_prefixed_two_digit_index(self):
        assert extract_playlist_id(f"12. {VALID_ID}.zip") == (VALID_ID, 12)

    def test_prefixed_no_zip_extension(self):
        assert extract_playlist_id(f"00. {VALID_ID}") == (VALID_ID, 0)

    def test_spotify_url(self):
        url = f"https://open.spotify.com/playlist/{VALID_ID}"
        assert extract_playlist_id(url) == (VALID_ID, None)

    def test_spotify_url_with_query_params(self):
        url = f"https://open.spotify.com/playlist/{VALID_ID}?si=abc123xyz"
        assert extract_playlist_id(url) == (VALID_ID, None)

    def test_spotify_url_http(self):
        url = f"http://open.spotify.com/playlist/{VALID_ID}"
        assert extract_playlist_id(url) == (VALID_ID, None)

    def test_spotify_uri(self):
        assert extract_playlist_id(f"spotify:playlist:{VALID_ID}") == (VALID_ID, None)

    def test_empty_string(self):
        assert extract_playlist_id("") == (None, None)

    def test_id_too_short(self):
        short = VALID_ID[:-1]  # 21 chars
        assert extract_playlist_id(f"{short}.zip") == (None, None)

    def test_id_too_long(self):
        long_id = VALID_ID + "X"  # 23 chars
        assert extract_playlist_id(f"{long_id}.zip") == (None, None)

    def test_id_with_invalid_char(self):
        bad = VALID_ID[:-1] + "!"  # last char invalid
        assert extract_playlist_id(f"{bad}.zip") == (None, None)

    def test_unrelated_filename(self):
        assert extract_playlist_id("random_file.zip") == (None, None)

    def test_only_prefix_no_id(self):
        assert extract_playlist_id("00. notanid.zip") == (None, None)

    def test_id_with_extra_suffix(self):
        # Stem has more content after the ID — should not match.
        assert extract_playlist_id(f"{VALID_ID}_extra.zip") == (None, None)

    def test_prefix_with_multiple_spaces(self):
        # Extra space after dot — still parseable by \s+.
        assert extract_playlist_id(f"01.  {VALID_ID}.zip") == (VALID_ID, 1)


# ---------------------------------------------------------------------------
# group_zips
# ---------------------------------------------------------------------------


class TestGroupZips:
    def _make_paths(self, names: list[str]) -> list[Path]:
        return [Path(name) for name in names]

    def test_single_part_no_prefix(self):
        paths = self._make_paths([f"{VALID_ID}.zip"])
        groups = group_zips(paths)
        assert list(groups.keys()) == [VALID_ID]
        assert len(groups[VALID_ID]) == 1
        assert groups[VALID_ID][0].part_index is None

    def test_single_part_with_00_prefix(self):
        paths = self._make_paths([f"00. {VALID_ID}.zip"])
        groups = group_zips(paths)
        assert groups[VALID_ID][0].part_index == 0

    def test_multi_part_sorted_by_index(self):
        # Supply in reverse order to confirm sorting.
        paths = self._make_paths([
            f"02. {VALID_ID}.zip",
            f"00. {VALID_ID}.zip",
            f"01. {VALID_ID}.zip",
        ])
        groups = group_zips(paths)
        indices = [p.part_index for p in groups[VALID_ID]]
        assert indices == [0, 1, 2]

    def test_two_different_playlists(self):
        paths = self._make_paths([
            f"00. {VALID_ID}.zip",
            f"00. {OTHER_ID}.zip",
        ])
        groups = group_zips(paths)
        assert set(groups.keys()) == {VALID_ID, OTHER_ID}

    def test_non_zip_files_ignored(self):
        paths = self._make_paths([
            f"{VALID_ID}.mp3",
            f"{VALID_ID}.zip",
            "cover.jpg",
        ])
        groups = group_zips(paths)
        assert list(groups.keys()) == [VALID_ID]

    def test_unrecognized_zip_names_skipped(self):
        paths = self._make_paths([
            "random_archive.zip",
            f"{VALID_ID}.zip",
        ])
        groups = group_zips(paths)
        assert list(groups.keys()) == [VALID_ID]

    def test_empty_input(self):
        assert group_zips([]) == {}

    def test_parts_carry_correct_path(self):
        p = Path(f"01. {VALID_ID}.zip")
        groups = group_zips([p])
        assert groups[VALID_ID][0].path == p

    def test_parts_carry_correct_playlist_id(self):
        p = Path(f"01. {VALID_ID}.zip")
        groups = group_zips([p])
        assert groups[VALID_ID][0].playlist_id == VALID_ID

    def test_none_part_index_sorts_before_explicit_zero(self):
        # A bare-ID zip (None index) and a prefixed-00 zip should both sort to
        # the front. Since both become key=0, the original stable order is kept.
        paths = self._make_paths([
            f"01. {VALID_ID}.zip",
            f"{VALID_ID}.zip",       # part_index = None → sorts as 0
        ])
        groups = group_zips(paths)
        assert groups[VALID_ID][0].part_index is None
        assert groups[VALID_ID][1].part_index == 1

    def test_zip_extension_case_insensitive(self):
        paths = self._make_paths([f"{VALID_ID}.ZIP"])
        groups = group_zips(paths)
        assert VALID_ID in groups


# ---------------------------------------------------------------------------
# sanitize_folder_name
# ---------------------------------------------------------------------------


class TestSanitizeFolderName:
    def test_clean_name_unchanged(self):
        assert sanitize_folder_name("My Cool Playlist") == "My Cool Playlist"

    def test_backslash_replaced(self):
        assert sanitize_folder_name("a\\b") == "a_b"

    def test_forward_slash_replaced(self):
        assert sanitize_folder_name("a/b") == "a_b"

    def test_colon_replaced(self):
        assert sanitize_folder_name("a:b") == "a_b"

    def test_asterisk_replaced(self):
        assert sanitize_folder_name("a*b") == "a_b"

    def test_question_mark_replaced(self):
        assert sanitize_folder_name("a?b") == "a_b"

    def test_double_quote_replaced(self):
        assert sanitize_folder_name('a"b') == "a_b"

    def test_angle_brackets_replaced(self):
        assert sanitize_folder_name("a<b>c") == "a_b_c"

    def test_pipe_replaced(self):
        assert sanitize_folder_name("a|b") == "a_b"

    def test_leading_dot_stripped(self):
        assert sanitize_folder_name(".hidden") == "hidden"

    def test_trailing_dot_stripped(self):
        assert sanitize_folder_name("name.") == "name"

    def test_leading_space_stripped(self):
        assert sanitize_folder_name(" name") == "name"

    def test_trailing_space_stripped(self):
        assert sanitize_folder_name("name ") == "name"

    def test_all_dots_becomes_underscore(self):
        assert sanitize_folder_name("...") == "_"

    def test_empty_string_becomes_underscore(self):
        assert sanitize_folder_name("") == "_"

    def test_unicode_name_preserved(self):
        assert sanitize_folder_name("Été 2024") == "Été 2024"

    def test_multiple_unsafe_chars(self):
        assert sanitize_folder_name('Top 10: "Best" Songs?') == "Top 10_ _Best_ Songs_"
