"""
Mock Webber API for local UI testing.

Provides a `MockWebberAPI` that implements the same async interface as
`WebberAPI` for the methods used by the Statistics widget, returning
deterministic fake data without needing a backend.
"""

import time
from random import Random

from ..api import (
    Interval,
    Statistics,
    StatisticsLimitsResponse,
    StatisticsResponse,
    Timespec,
)

# How far back in time the fake database "starts" (in seconds).
_DB_SPAN_SECONDS = 18 * 30 * 24 * 60 * 60  # ~18 months


class MockWebberAPI:
    """A fake `WebberAPI` backed by deterministic random data.

    Each interval is assigned a seed derived from its boundaries, so the
    same period selection always produces the same numbers.
    """

    async def aclose(self) -> None:
        """Interface parity with `WebberAPI`; nothing to close."""

    async def statistics_limits(self) -> StatisticsLimitsResponse:
        """Return the fake database time bounds.

        Returns: `StatisticsLimitsResponse` spanning the last ~18 months
        """
        now = int(time.time())
        return StatisticsLimitsResponse(
            first_snapshot=Timespec(now - _DB_SPAN_SECONDS, 0),
            last_snapshot=Timespec(now, 0),
        )

    def _random_for(self, interval: Interval) -> Random:
        """Create a deterministic RNG seeded from the interval boundaries."""
        seed = 0
        if interval.start is not None:
            seed = seed * 31 + interval.start.sec + interval.start.nsec
        if interval.end is not None:
            seed = seed * 31 + interval.end.sec + interval.end.nsec
        return Random(seed)

    def _stats_for(self, interval: Interval) -> Statistics:
        """Generate plausible statistics for a single interval."""
        rng = self._random_for(interval)
        return Statistics(
            interval=interval,
            snapshots=rng.randint(0, 10),
            files=rng.randint(50, 500),
            size=rng.randint(100 * 1024, 5 * 1024 * 1024),
            urls=rng.randint(0, 5),
            hosts=rng.randint(0, 5),
        )

    async def statistics(self, intervals: list[Interval]) -> StatisticsResponse:
        """Return statistics for the given intervals.

        The first entry in the returned list corresponds to the first
        interval (the overall period); its numbers are the sum of the
        sub-intervals, matching the behavior of the real API.

        Arguments:
        intervals -- the intervals to compute statistics for

        Returns: a `StatisticsResponse` with one `Statistics` per interval
        """
        if not intervals:
            return StatisticsResponse(statistics=[])

        overall_interval = intervals[0]
        sub_stats = [self._stats_for(iv) for iv in intervals[1:]]

        # Sum the sub-intervals to get the overall numbers.
        overall = Statistics(
            interval=overall_interval,
            snapshots=sum(s.snapshots for s in sub_stats),
            files=sum(s.files for s in sub_stats),
            size=sum(s.size for s in sub_stats),
            urls=sum(s.urls for s in sub_stats),
            hosts=sum(s.hosts for s in sub_stats),
        )
        return StatisticsResponse(statistics=[overall, *sub_stats])
