"""Filename parsing, playlist ID extraction, and folder-name sanitization."""

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

_SPOTIFY_ID_PAT = r"[0-9A-Za-z]{22}"

# Matches a Spotify URL or URI and captures the playlist ID.
_URL_RE = re.compile(
    rf"(?:https?://open\.spotify\.com/playlist/|spotify:playlist:)({_SPOTIFY_ID_PAT})"
)

# Matches the stem of a ZIP filename: optional "NN. " prefix then the 22-char ID.
# Used with re.fullmatch so the entire stem must be consumed.
_STEM_RE = re.compile(rf"(?:(\d+)\.\s+)?({_SPOTIFY_ID_PAT})")

# Characters forbidden in FAT32 / NTFS / common Linux FS folder names.
_UNSAFE_CHARS_RE = re.compile(r'[\\/:*?"<>|]')


@dataclass(frozen=True)
class ZipPart:
    path: Path
    playlist_id: str
    # None = single-file playlist (no numeric prefix present)
    part_index: int | None


def extract_playlist_id(text: str) -> tuple[str | None, int | None]:
    """Return (playlist_id, part_index) parsed from *text*, or (None, None).

    Accepted formats:
    - ``7EAqBCOVkDZcbccjxZmgjp`` or ``7EAqBCOVkDZcbccjxZmgjp.zip``
    - ``00. 7EAqBCOVkDZcbccjxZmgjp.zip``
    - ``https://open.spotify.com/playlist/7EAqBCOVkDZcbccjxZmgjp[?...]``
    - ``spotify:playlist:7EAqBCOVkDZcbccjxZmgjp``
    """
    # Strip .zip extension (case-insensitive) before further analysis.
    stem = text[:-4] if text.lower().endswith(".zip") else text

    # URL / URI takes priority — search anywhere inside the string.
    m = _URL_RE.search(stem)
    if m:
        return m.group(1), None

    # Bare ID or "NN. ID" — the entire stem must match (fullmatch).
    m = _STEM_RE.fullmatch(stem.strip())
    if m:
        part_index = int(m.group(1)) if m.group(1) is not None else None
        return m.group(2), part_index

    return None, None


def group_zips(paths: Iterable[Path]) -> dict[str, list[ZipPart]]:
    """Group .zip files by playlist ID.

    Returns a dict mapping ``playlist_id -> [ZipPart, ...]`` where each list
    is sorted ascending by ``part_index`` (``None`` sorts as 0).
    Files whose names cannot be parsed are silently skipped.
    """
    groups: dict[str, list[ZipPart]] = {}
    for path in paths:
        if path.suffix.lower() != ".zip":
            continue
        playlist_id, part_index = extract_playlist_id(path.name)
        if playlist_id is None:
            continue
        groups.setdefault(playlist_id, []).append(
            ZipPart(path=path, playlist_id=playlist_id, part_index=part_index)
        )

    for parts in groups.values():
        parts.sort(key=lambda p: p.part_index if p.part_index is not None else 0)

    return groups


def sanitize_folder_name(name: str) -> str:
    """Replace filesystem-unsafe characters and strip leading/trailing dots and spaces."""
    sanitized = _UNSAFE_CHARS_RE.sub("_", name)
    sanitized = sanitized.strip(". ")
    return sanitized or "_"
