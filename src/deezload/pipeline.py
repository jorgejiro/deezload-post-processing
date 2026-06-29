"""Orchestrates the full processing pipeline for a single playlist ZIP group."""

import logging
import shutil
import tempfile
from pathlib import Path

from deezload.naming import ZipPart, sanitize_folder_name
from deezload.spotify import SpotifyClient
from deezload.tagging import apply_tags, collect_mp3s, extract_parts, save_cover

log = logging.getLogger(__name__)


def process_group(
    playlist_id: str,
    parts: list[ZipPart],
    *,
    spotify: SpotifyClient,
    output_dir: Path,
    album_artist: str,
    delete_zips: bool,
) -> None:
    """Process a complete ZIP group end-to-end.

    Steps: fetch metadata → extract → tag → move to output → (delete ZIPs).

    On any failure the exception propagates unchanged and ZIPs are never
    deleted, so the group is retried on the next scan cycle.
    """
    log.info("Processing playlist %s (%d part(s))", playlist_id, len(parts))

    info = spotify.get_playlist_info(playlist_id)
    log.info("Playlist name: %r, cover: %s", info.name, info.cover_url or "none")

    folder_name = sanitize_folder_name(info.name)
    dest_dir = output_dir / folder_name

    if dest_dir.exists():
        log.warning(
            "Output folder already exists: %s — skipping to avoid overwrite.",
            dest_dir,
        )
        return

    with tempfile.TemporaryDirectory(prefix="deezload_") as tmpdir:
        tmp = Path(tmpdir)

        extract_parts(parts, tmp)
        mp3s = collect_mp3s(tmp, parts)

        if not mp3s:
            raise RuntimeError(
                f"No MP3 files found in any ZIP for playlist {playlist_id}"
            )

        total = len(mp3s)
        log.info("Tagging %d tracks as album %r", total, info.name)
        for i, mp3 in enumerate(mp3s, 1):
            apply_tags(
                mp3,
                album=info.name,
                album_artist=album_artist,
                track_number=i,
                total_tracks=total,
            )

        dest_dir.mkdir(parents=True, exist_ok=True)
        try:
            for mp3 in mp3s:
                shutil.move(str(mp3), dest_dir / mp3.name)

            if info.cover_url:
                cover_data = spotify.download_cover(info.cover_url)
                save_cover(cover_data, dest_dir)
            else:
                log.warning("Playlist %s has no cover image.", playlist_id)

        except Exception:
            # Clean up the partial output folder so the group can be retried.
            shutil.rmtree(dest_dir, ignore_errors=True)
            raise

    log.info("Output written to %s", dest_dir)

    if delete_zips:
        for part in parts:
            part.path.unlink(missing_ok=True)
            log.debug("Deleted source ZIP: %s", part.path.name)
        log.info("Deleted %d source ZIP(s).", len(parts))
