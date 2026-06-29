"""ZIP extraction, MP3 metadata tagging, and cover art saving."""

import logging
import zipfile
from pathlib import Path

from mutagen.id3 import (
    ID3,
    ID3NoHeaderError,
    TALB,
    TCMP,
    TCOM,
    TPOS,
    TPE2,
    TRCK,
)

from deezload.naming import ZipPart

log = logging.getLogger(__name__)


def extract_parts(parts: list[ZipPart], dest_dir: Path) -> None:
    """Extract each ZIP part into a numbered subdirectory of *dest_dir*.

    Each part is extracted to ``dest_dir/<NNN>/`` so that files from
    different parts never collide, even if they share a filename.
    """
    for part in parts:
        idx = part.part_index if part.part_index is not None else 0
        sub = dest_dir / f"{idx:03d}"
        sub.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(part.path) as zf:
            zf.extractall(sub)
        log.debug("Extracted part %s to %s", part.path.name, sub)


def collect_mp3s(dest_dir: Path, parts: list[ZipPart]) -> list[Path]:
    """Return MP3 paths from *dest_dir* in correct playback order.

    Order: ascending part index, then case-insensitive alphabetical
    by filename within each part.  ``parts`` must already be sorted
    (as returned by :func:`~deezload.naming.group_zips`).
    """
    mp3s: list[Path] = []
    for part in parts:
        idx = part.part_index if part.part_index is not None else 0
        sub = dest_dir / f"{idx:03d}"
        part_mp3s = sorted(sub.rglob("*.mp3"), key=lambda p: p.name.lower())
        mp3s.extend(part_mp3s)
    return mp3s


def apply_tags(
    mp3_path: Path,
    *,
    album: str,
    album_artist: str,
    track_number: int,
    total_tracks: int,
) -> None:
    """Apply compilation metadata to *mp3_path* in-place (ID3v2.3).

    Written fields:   album, albumartist, compilation flag, tracknumber.
    Cleared fields:   comment, composer, disc number.
    Untouched fields: title, artist, year, embedded cover art (APIC),
                      and any other existing frames.
    """
    try:
        tags = ID3(str(mp3_path))
    except ID3NoHeaderError:
        tags = ID3()

    tags.setall("TALB", [TALB(encoding=3, text=album)])
    tags.setall("TPE2", [TPE2(encoding=3, text=album_artist)])
    tags.setall("TCMP", [TCMP(encoding=0, text="1")])
    tags.setall("TRCK", [TRCK(encoding=3, text=f"{track_number}/{total_tracks}")])

    tags.delall("COMM")
    tags.delall("TCOM")
    tags.delall("TPOS")

    tags.save(str(mp3_path), v2_version=3)


def save_cover(cover_data: bytes, dest_dir: Path) -> Path:
    """Write *cover_data* as ``cover.jpg`` inside *dest_dir*.

    Returns the path of the written file.
    """
    cover_path = dest_dir / "cover.jpg"
    cover_path.write_bytes(cover_data)
    log.debug("Saved cover to %s (%d bytes)", cover_path, len(cover_data))
    return cover_path
