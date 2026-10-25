"""Turn station profiles and current prices into a forecast and a recommendation.

Pure Python, no Home Assistant imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from enum import StrEnum

import math
from statistics import median

from .profile import MAX_PLAUSIBLE_CHANGE, StationProfile, bucket_of

# How fast the current price's own offset fades out of the forecast (hours,
# e-folding). The pattern says what is usual at a given hour; the current
# price only tells something about the next hour or two.
CURRENT_OFFSET_DECAY_H = 3.0
# Never expect a station to drop more than this below its lowest price of
# the last 24 h.
MAX_BELOW_RECENT_MIN = 0.02

# Below this share of learned buckets the forecast is not trusted.
MIN_COVERAGE = 0.5

# Hysteresis: once "wait" is recommended it stays until the saving drops
# below this share of the minimum saving (3 ct → stays "wait" down to 2 ct).
# Without it the recommendation flipped every few minutes while the saving
# hovered around the threshold (live: 2.7 / 3.0 / 3.1 / 2.8 ct in two hours).
WAIT_HOLD_SHARE = 2 / 3

# Differences below this share of the minimum saving (3 ct → 0.5 ct) are
# noise: then the cheapest time is now, or the earliest hour that is about as
# cheap as the lowest. Live, a nearly flat forecast made the cheapest time
# jump between 00:00, 06:00 and 07:00 for less than 1 ct, while the real
# price simply stayed the same.
LOWEST_TOLERANCE_SHARE = 1 / 6


class Recommendation(StrEnum):
    LEARNING = "learning"
    FILL_NOW = "fill_now"
    WAIT = "wait"
    NO_NEED = "no_need"
    # Not "unavailable": that word is reserved for HA entity availability.
    NO_PRICES = "no_prices"


@dataclass
class ForecastPoint:
    time: datetime
    price: float
    station: str


@dataclass
class Settings:
    horizon_hours: int = 24
    # Minimum saving per litre (in the price unit) that justifies waiting.
    min_saving: float = 0.03
    tank_size: float | None = None
    # Fuel level in percent, None if unknown.
    fuel_level: float | None = None
    # At or above this level no recommendation is needed.
    no_need_level: float = 60.0
    # At or below this level fill up now even if waiting would be cheaper.
    urgent_level: float = 15.0
    # Last recommendation, for the hysteresis around min_saving.
    previous: Recommendation | None = None


@dataclass
class Result:
    recommendation: Recommendation
    best_now_price: float | None = None
    best_now_station: str | None = None
    lowest_price: float | None = None
    lowest_time: datetime | None = None
    lowest_station: str | None = None
    saving_per_litre: float | None = None
    saving_per_fill: float | None = None
    # Litres the saving per fill-up is based on.
    fill_litres: float | None = None
    coverage: float = 0.0
    urgent: bool = False
    forecast: list[ForecastPoint] = field(default_factory=list)


def plausible_prices(
    current: dict[str, float], profiles: dict[str, StationProfile]
) -> dict[str, float]:
    """Drop prices that are off compared to the station's own history or to
    the other stations right now (data errors like a station reporting 0 €)."""
    prices = {
        station: price
        for station, price in current.items()
        if price > 0 and (station not in profiles or profiles[station].plausible(price))
    }
    if len(prices) >= 3:
        middle = median(prices.values())
        prices = {
            s: p for s, p in prices.items() if abs(p - middle) <= middle * MAX_PLAUSIBLE_CHANGE
        }
    return prices


def build_forecast(
    profiles: dict[str, StationProfile],
    current: dict[str, float],
    now: datetime,
    tz: tzinfo,
    horizon_hours: int,
) -> list[ForecastPoint]:
    """Cheapest expected price per coming hour across all stations.

    Each station's expected price = its trailing 24 h median + the learned
    deviation of the target hour, plus the current price's own offset from
    what is usual right now, fading out over the next hours.

    The first version shifted the current price by (deviation then - deviation
    now) only. Live on 24.10.2026 that went wrong: a station usually spikes at
    noon on Saturdays, the spike was late, so its normal noon price was taken
    as "spike already included" and the evening forecast dropped 15 ct too
    low. Anchoring on the median plus the floor below avoids that; backtests
    on real data were as good or better in every window.
    Hours without a trusted deviation are skipped for that station.
    """
    now_bucket = bucket_of(now, tz)
    start = now.replace(minute=0, second=0, microsecond=0)
    points: list[ForecastPoint] = []
    for step in range(1, horizon_hours + 1):
        moment = start + timedelta(hours=step)
        bucket = bucket_of(moment, tz)
        best: ForecastPoint | None = None
        for station, price in current.items():
            profile = profiles.get(station)
            if profile is None:
                continue
            dev_now, dev_then = profile.deviation(now_bucket), profile.deviation(bucket)
            reference, floor = profile.reference(), profile.recent_min()
            if dev_now is None or dev_then is None or reference is None:
                continue
            offset = price - (reference + dev_now)
            expected = reference + dev_then + offset * math.exp(-step / CURRENT_OFFSET_DECAY_H)
            if floor is not None:
                expected = max(expected, floor - MAX_BELOW_RECENT_MIN)
            if best is None or expected < best.price:
                best = ForecastPoint(moment, expected, station)
        if best is not None:
            points.append(best)
    return points


def recommend(
    profiles: dict[str, StationProfile],
    current: dict[str, float],
    now: datetime,
    tz: tzinfo,
    settings: Settings,
) -> Result:
    # Reported coverage: how much is learned over all stations of the group,
    # also while no prices arrive (shows that learning is not lost).
    overall = sum(p.coverage() for p in profiles.values()) / len(profiles) if profiles else 0.0
    if not current:
        return Result(Recommendation.NO_PRICES, coverage=overall)

    best_now_station = min(current, key=current.__getitem__)
    best_now_price = current[best_now_station]
    # Trust is judged on the stations that have a price right now.
    used = [profiles[s] for s in current if s in profiles]
    trusted = sum(p.coverage() for p in used) / len(current) if used else 0.0

    result = Result(
        Recommendation.LEARNING,
        best_now_price=best_now_price,
        best_now_station=best_now_station,
        coverage=overall,
    )
    if trusted < MIN_COVERAGE:
        return result

    points = build_forecast(profiles, current, now, tz, settings.horizon_hours)
    result.forecast = points
    tolerance = settings.min_saving * LOWEST_TOLERANCE_SHARE
    lowest = min(points, key=lambda p: p.price, default=None)
    if lowest is not None:
        lowest = min(
            (p for p in points if p.price <= lowest.price + tolerance),
            key=lambda p: p.time,
        )
    if lowest is None or lowest.price > best_now_price - tolerance:
        result.lowest_price, result.lowest_time, result.lowest_station = (
            best_now_price,
            now,
            best_now_station,
        )
        saving = 0.0
    else:
        result.lowest_price, result.lowest_time, result.lowest_station = (
            lowest.price,
            lowest.time,
            lowest.station,
        )
        saving = best_now_price - lowest.price

    result.saving_per_litre = saving
    litres = settings.tank_size
    if litres is not None and settings.fuel_level is not None:
        litres = litres * max(0.0, 100.0 - settings.fuel_level) / 100.0
    result.fill_litres = litres
    result.saving_per_fill = saving * litres if litres is not None else None

    level = settings.fuel_level
    if level is not None and level <= settings.urgent_level:
        result.urgent = True
        result.recommendation = Recommendation.FILL_NOW
    elif level is not None and level >= settings.no_need_level:
        result.recommendation = Recommendation.NO_NEED
    elif saving >= settings.min_saving or (
        settings.previous is Recommendation.WAIT
        and saving >= settings.min_saving * WAIT_HOLD_SHARE
    ):
        result.recommendation = Recommendation.WAIT
    else:
        result.recommendation = Recommendation.FILL_NOW
    return result
