"""Weekly price pattern of a single station.

Pure Python on purpose (no Home Assistant imports) so it can be unit tested
in isolation.

The profile does not learn absolute prices. It learns how far a station's
price usually sits above or below its own trailing 24 h median in each hour
of the day, separately for working days and weekends. That way a general rise
or fall of oil prices does not wash out the pattern ("evenings are ~8 ct
cheaper than usual").

Why 2 x 24 buckets and not all 168 hours of the week: backtests on five weeks
of real German prices (Tankerkönig, 18 stations) showed the weekly grid was
too sparse and lost money, while working day/weekend + hour saved money in
every test window. Same for the reference: median beats mean because single
price spikes do not shift it.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo

BUCKETS = 48  # 24 hours on working days + 24 hours on weekends

# Weight is capped so that old data fades out. One sample every 10 minutes
# adds 6 per hour and day, so 180 is about 30 days of memory (shorter memory
# was noisy in the backtests, longer reacted too slowly to shifts).
MAX_WEIGHT = 180.0
# A bucket is trusted after about three days of samples.
MIN_WEIGHT = 18.0

REFERENCE_WINDOW = timedelta(hours=24)
# Only learn once the trailing window spans this long, otherwise the
# reference would be the price of a single moment.
MIN_REFERENCE_SPAN = timedelta(hours=12)
# Fuel prices never move this much within a day. Larger jumps are data errors
# (seen in real Tankerkönig data: a station briefly reporting 0 €).
MAX_PLAUSIBLE_CHANGE = 0.3


def bucket_of(moment: datetime, tz: tzinfo) -> int:
    """Return 0..23 for working-day hours, 24..47 for weekend hours.

    Using the local wall clock means daylight saving time needs no special
    handling: "19:00" stays "19:00" all year round.
    """
    local = moment.astimezone(tz)
    return (24 if local.weekday() >= 5 else 0) + local.hour


@dataclass
class Bucket:
    """Weighted running mean of the deviation in one hour of the week."""

    mean: float = 0.0
    weight: float = 0.0

    def add(self, value: float, weight: float = 1.0) -> None:
        new_weight = min(self.weight + weight, MAX_WEIGHT)
        self.mean += (value - self.mean) * (weight / new_weight)
        self.weight = new_weight


@dataclass
class StationProfile:
    """Learned weekly pattern plus the trailing window for the reference."""

    buckets: list[Bucket] = field(
        default_factory=lambda: [Bucket() for _ in range(BUCKETS)]
    )
    # (timestamp in seconds, price, weight)
    recent: deque[tuple[float, float, float]] = field(default_factory=deque)

    def add_sample(
        self, moment: datetime, price: float, tz: tzinfo, weight: float = 1.0
    ) -> None:
        """Feed one observed price. Samples must arrive in time order."""
        ts = moment.timestamp()
        if (self.recent and ts < self.recent[-1][0]) or not self.plausible(price):
            return
        self.recent.append((ts, price, weight))
        cutoff = ts - REFERENCE_WINDOW.total_seconds()
        while self.recent and self.recent[0][0] < cutoff:
            self.recent.popleft()

        if ts - self.recent[0][0] < MIN_REFERENCE_SPAN.total_seconds():
            return
        reference = self.reference()
        if reference is None:
            return
        self.buckets[bucket_of(moment, tz)].add(price - reference, weight)

    def plausible(self, price: float) -> bool:
        """False for prices that are obviously wrong compared to the recent ones."""
        if price <= 0:
            return False
        reference = self.reference()
        return reference is None or abs(price - reference) <= reference * MAX_PLAUSIBLE_CHANGE

    def reference(self) -> float | None:
        """Weighted median price over the trailing window."""
        total = sum(w for _, _, w in self.recent)
        if not total:
            return None
        running = 0.0
        for _, price, weight in sorted(self.recent, key=lambda r: r[1]):
            running += weight
            if running >= total / 2:
                return price
        return None

    def deviation(self, index: int) -> float | None:
        """Learned deviation for a bucket, None if not trusted yet."""
        bucket = self.buckets[index]
        return bucket.mean if bucket.weight >= MIN_WEIGHT else None

    def coverage(self) -> float:
        """Share of the buckets (0..1) that is learned well enough."""
        return sum(b.weight >= MIN_WEIGHT for b in self.buckets) / BUCKETS

    def as_dict(self) -> dict:
        return {
            "buckets": [[round(b.mean, 5), round(b.weight, 3)] for b in self.buckets],
            "recent": [list(r) for r in self.recent],
        }

    @classmethod
    def from_dict(cls, data: dict) -> StationProfile:
        profile = cls()
        for bucket, (mean, weight) in zip(
            profile.buckets, data.get("buckets", []), strict=False
        ):
            bucket.mean, bucket.weight = float(mean), float(weight)
        profile.recent = deque(
            (float(ts), float(p), float(w)) for ts, p, w in data.get("recent", [])
        )
        return profile
