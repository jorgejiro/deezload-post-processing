"""Scans /input for ZIP groups, evaluates completeness, and triggers the pipeline."""

import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from deezload.naming import ZipPart, group_zips


class Readiness(Enum):
    READY = "ready"
    TOO_SMALL = "too_small"    # total size below MIN_TOTAL_SIZE_MB
    INCOMPLETE = "incomplete"  # size heuristic says more parts are incoming
    UNSTABLE = "unstable"      # a part changed within STABLE_MINUTES


@dataclass(frozen=True)
class PartStats:
    size: int    # bytes
    mtime: float  # Unix timestamp


def evaluate_group(
    parts: list[ZipPart],
    part_stats: list[PartStats],
    *,
    part_size_threshold_bytes: int,
    min_total_size_bytes: int,
    stable_seconds: float,
    now: float,
) -> Readiness:
    """Pure readiness check for a sorted list of ZipParts.

    ``parts`` and ``part_stats`` must be parallel lists of equal length,
    with ``parts`` sorted ascending by part index (as returned by
    :func:`~deezload.naming.group_zips`).
    """
    if not parts:
        return Readiness.INCOMPLETE

    total_size = sum(s.size for s in part_stats)
    if total_size < min_total_size_bytes:
        return Readiness.TOO_SMALL

    for stats in part_stats:
        if (now - stats.mtime) < stable_seconds:
            return Readiness.UNSTABLE

    # A single file with no numeric prefix is an explicit single-file export.
    if len(parts) == 1 and parts[0].part_index is None:
        return Readiness.READY

    # Multi-part groups must include part 0 (index 0 or None treated as 0).
    effective_indices = {p.part_index if p.part_index is not None else 0 for p in parts}
    if 0 not in effective_indices:
        return Readiness.INCOMPLETE

    if len(parts) == 1:
        # Single numbered part with index 0 — no intermediates.
        return Readiness.READY

    # Every part except the last must be at or above the threshold size;
    # a sub-threshold intermediate signals the part is still downloading.
    for stats in part_stats[:-1]:
        if stats.size < part_size_threshold_bytes:
            return Readiness.INCOMPLETE

    # If the last part is also at/above threshold and the group is stable
    # (already verified above), temporal stability is our signal to proceed.
    return Readiness.READY


def scan_input_dir(
    input_dir: Path,
    *,
    part_size_threshold_bytes: int,
    min_total_size_bytes: int,
    stable_seconds: float,
) -> dict[str, Readiness]:
    """Return a readiness verdict for every playlist group found in *input_dir*."""
    now = time.time()
    groups = group_zips(p for p in input_dir.iterdir() if p.is_file())
    result: dict[str, Readiness] = {}
    for playlist_id, parts in groups.items():
        stats = [
            PartStats(size=p.path.stat().st_size, mtime=p.path.stat().st_mtime)
            for p in parts
        ]
        result[playlist_id] = evaluate_group(
            parts,
            stats,
            part_size_threshold_bytes=part_size_threshold_bytes,
            min_total_size_bytes=min_total_size_bytes,
            stable_seconds=stable_seconds,
            now=now,
        )
    return result
