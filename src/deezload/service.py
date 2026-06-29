"""Main service entry point: CLI dispatcher, scan loop, and signal handling."""

import argparse
import logging
import signal
import sys
from pathlib import Path
from threading import Event

from deezload.config import load_config
from deezload.pipeline import process_group
from deezload.scanner import Readiness, scan_input_dir
from deezload.spotify import SpotifyClient, TOKEN_FILENAME, bootstrap_auth

log = logging.getLogger(__name__)


def _run_service(config) -> None:
    spotify = SpotifyClient(config)

    stop = Event()

    def _handle_signal(sig, _frame):
        log.info("Signal %s received, shutting down after current cycle.", sig)
        stop.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    input_dir = Path(config.input_dir)
    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    log.info(
        "Service started — scanning %s every %ds.",
        input_dir,
        config.scan_interval_seconds,
    )

    while not stop.is_set():
        _scan_cycle(config, spotify, input_dir, output_dir)
        stop.wait(config.scan_interval_seconds)

    log.info("Service stopped.")


def _scan_cycle(config, spotify: SpotifyClient, input_dir: Path, output_dir: Path) -> None:
    log.debug("Starting scan cycle.")
    try:
        verdicts = scan_input_dir(
            input_dir,
            part_size_threshold_bytes=config.part_size_threshold_mb * 1024 * 1024,
            min_total_size_bytes=config.min_total_size_mb * 1024 * 1024,
            stable_seconds=config.stable_minutes * 60,
        )
    except OSError as exc:
        log.error("Cannot scan input directory %s: %s", input_dir, exc)
        return

    from deezload.naming import group_zips

    groups = group_zips(p for p in input_dir.iterdir() if p.is_file())

    ready_count = sum(1 for v in verdicts.values() if v is Readiness.READY)
    if ready_count:
        log.info("%d group(s) ready to process.", ready_count)

    for playlist_id, readiness in verdicts.items():
        if readiness is not Readiness.READY:
            log.debug("Playlist %s: %s", playlist_id, readiness.value)
            continue

        parts = groups[playlist_id]
        try:
            process_group(
                playlist_id,
                parts,
                spotify=spotify,
                output_dir=output_dir,
                album_artist=config.album_artist,
                delete_zips=config.delete_zips_after,
            )
        except Exception:
            log.exception(
                "Failed to process playlist %s — will retry next cycle.", playlist_id
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="deezload",
        description="Post-process Spotify playlist ZIPs into tagged compilations.",
    )
    sub = parser.add_subparsers(dest="cmd")
    auth_parser = sub.add_parser("auth", help="Authorize with Spotify (run once).")
    auth_parser.add_argument(
        "--force",
        action="store_true",
        help="Re-authorize even if a token already exists.",
    )
    args = parser.parse_args()

    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.cmd == "auth":
        bootstrap_auth(config, force=getattr(args, "force", False))
        return

    token_file = Path(config.config_dir) / TOKEN_FILENAME
    if not token_file.exists():
        log.error(
            "Spotify token not found at %s.  Run 'deezload auth' first.", token_file
        )
        sys.exit(1)

    _run_service(config)
