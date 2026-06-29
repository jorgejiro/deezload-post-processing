"""Tests for deezload.scanner: completeness heuristic (evaluate_group)."""

from pathlib import Path

import pytest

from deezload.naming import ZipPart
from deezload.scanner import PartStats, Readiness, evaluate_group

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

PLAYLIST_ID = "7EAqBCOVkDZcbccjxZmgjp"

_MB = 1024 * 1024
_GB = 1024 * _MB

# Default thresholds matching config defaults.
THRESHOLD = 1000 * _MB   # 1000 MB
MIN_TOTAL = 100 * _MB    # 100 MB
STABLE_S = 5 * 60        # 5 minutes in seconds
NOW = 1_000_000.0        # arbitrary fixed timestamp


def _part(part_index: int | None, *, size: int, age_s: float = STABLE_S + 1) -> tuple[ZipPart, PartStats]:
    """Build a (ZipPart, PartStats) pair. age_s is seconds since last modification."""
    name = f"{PLAYLIST_ID}.zip" if part_index is None else f"{part_index:02d}. {PLAYLIST_ID}.zip"
    zp = ZipPart(path=Path(name), playlist_id=PLAYLIST_ID, part_index=part_index)
    ps = PartStats(size=size, mtime=NOW - age_s)
    return zp, ps


def _eval(
    pairs: list[tuple[ZipPart, PartStats]],
    *,
    threshold: int = THRESHOLD,
    min_total: int = MIN_TOTAL,
    stable_s: float = STABLE_S,
) -> Readiness:
    parts, stats = zip(*pairs) if pairs else ([], [])
    return evaluate_group(
        list(parts),
        list(stats),
        part_size_threshold_bytes=threshold,
        min_total_size_bytes=min_total,
        stable_seconds=stable_s,
        now=NOW,
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    def test_empty_group_is_incomplete(self):
        assert _eval([]) == Readiness.INCOMPLETE

    def test_total_below_min_is_too_small(self):
        pair = _part(None, size=MIN_TOTAL - 1)
        assert _eval([pair]) == Readiness.TOO_SMALL

    def test_total_exactly_at_min_is_not_too_small(self):
        pair = _part(None, size=MIN_TOTAL)
        assert _eval([pair]) != Readiness.TOO_SMALL

    def test_unstable_file_returns_unstable(self):
        pair = _part(None, size=MIN_TOTAL, age_s=STABLE_S - 1)
        assert _eval([pair]) == Readiness.UNSTABLE

    def test_unstable_check_fires_before_size_heuristic(self):
        # Even if the size heuristic would say INCOMPLETE, unstable takes priority.
        pairs = [
            _part(1, size=_GB, age_s=STABLE_S + 10),   # stable intermediate
            _part(2, size=500 * _MB, age_s=STABLE_S - 1),  # unstable last
        ]
        assert _eval(pairs) == Readiness.UNSTABLE

    def test_exactly_stable_is_stable(self):
        # mtime = NOW - STABLE_S means age equals the threshold; that is just
        # barely NOT within the window, so it counts as stable.
        pair = _part(None, size=MIN_TOTAL, age_s=STABLE_S)
        assert _eval([pair]) != Readiness.UNSTABLE


# ---------------------------------------------------------------------------
# Single-file playlists
# ---------------------------------------------------------------------------


class TestSingleFilePlaylists:
    def test_single_file_no_index_ready(self):
        pair = _part(None, size=500 * _MB)
        assert _eval([pair]) == Readiness.READY

    def test_single_file_with_index_0_ready(self):
        pair = _part(0, size=500 * _MB)
        assert _eval([pair]) == Readiness.READY

    def test_single_file_large_also_ready_when_stable(self):
        # A ≥1 GB single file that's stable is assumed complete.
        pair = _part(None, size=_GB + 1)
        assert _eval([pair]) == Readiness.READY


# ---------------------------------------------------------------------------
# Multi-part playlists
# ---------------------------------------------------------------------------


class TestMultiPartPlaylists:
    def test_two_parts_large_then_small_ready(self):
        pairs = [
            _part(0, size=_GB),
            _part(1, size=500 * _MB),
        ]
        assert _eval(pairs) == Readiness.READY

    def test_three_parts_two_large_one_small_ready(self):
        pairs = [
            _part(0, size=_GB),
            _part(1, size=_GB),
            _part(2, size=300 * _MB),
        ]
        assert _eval(pairs) == Readiness.READY

    def test_intermediate_below_threshold_is_incomplete(self):
        # Part 0 is below threshold → a full part is still downloading.
        pairs = [
            _part(0, size=500 * _MB),  # below 1000 MB threshold
            _part(1, size=200 * _MB),
        ]
        assert _eval(pairs) == Readiness.INCOMPLETE

    def test_missing_part_0_is_incomplete(self):
        # Only have parts 1 and 2; part 0 hasn't arrived yet.
        pairs = [
            _part(1, size=_GB),
            _part(2, size=500 * _MB),
        ]
        assert _eval(pairs) == Readiness.INCOMPLETE

    def test_last_part_at_or_above_threshold_still_ready_when_stable(self):
        # Edge case: last part happens to be exactly 1 GB.
        # Temporal stability (already verified) covers this.
        pairs = [
            _part(0, size=_GB),
            _part(1, size=_GB),  # at threshold, not below
        ]
        assert _eval(pairs) == Readiness.READY

    def test_two_parts_both_unstable(self):
        pairs = [
            _part(0, size=_GB, age_s=1),
            _part(1, size=500 * _MB, age_s=1),
        ]
        assert _eval(pairs) == Readiness.UNSTABLE

    def test_mixed_stability_one_unstable_returns_unstable(self):
        pairs = [
            _part(0, size=_GB, age_s=STABLE_S + 10),
            _part(1, size=500 * _MB, age_s=1),
        ]
        assert _eval(pairs) == Readiness.UNSTABLE

    def test_five_parts_happy_path(self):
        pairs = [
            _part(0, size=_GB),
            _part(1, size=_GB),
            _part(2, size=_GB),
            _part(3, size=_GB),
            _part(4, size=200 * _MB),
        ]
        assert _eval(pairs) == Readiness.READY

    def test_five_parts_middle_below_threshold(self):
        pairs = [
            _part(0, size=_GB),
            _part(1, size=_GB),
            _part(2, size=400 * _MB),  # incomplete intermediate
            _part(3, size=_GB),
            _part(4, size=200 * _MB),
        ]
        assert _eval(pairs) == Readiness.INCOMPLETE

    def test_none_index_mixed_with_indexed_parts(self):
        # None-index sorts as 0; paired with an explicit part 1, the
        # None-index part acts as the first (intermediate) part.
        # It's above threshold, so the group is READY.
        pairs = [
            _part(None, size=_GB),   # sorts as index 0
            _part(1, size=300 * _MB),
        ]
        assert _eval(pairs) == Readiness.READY

    def test_none_index_as_intermediate_below_threshold(self):
        pairs = [
            _part(None, size=500 * _MB),  # intermediate, below threshold
            _part(1, size=300 * _MB),
        ]
        assert _eval(pairs) == Readiness.INCOMPLETE

    def test_custom_threshold(self):
        # With a lower threshold (500 MB), a 600 MB intermediate is OK.
        pairs = [
            _part(0, size=600 * _MB),
            _part(1, size=200 * _MB),
        ]
        assert _eval(pairs, threshold=500 * _MB) == Readiness.READY

    def test_custom_min_total(self):
        # With a higher min_total, a group that passes the default minimum fails.
        pairs = [
            _part(0, size=150 * _MB),
        ]
        assert _eval(pairs, min_total=200 * _MB) == Readiness.TOO_SMALL
