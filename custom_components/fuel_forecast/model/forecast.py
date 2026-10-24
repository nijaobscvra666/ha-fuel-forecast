"""Turn station profiles and current prices into a forecast and a recommendation.

Pure Python, no Home Assistant imports.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, tzinfo
from enum import StrEnum

from statistics import median

from .profile import MAX_PLAUSIBLE_CHANGE, StationProfile, bucket_of

# Below this share of learned buckets the forecast is not trusted.
MIN_COVERAGE = 0.5


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

    Each station's expected price = current price shifted by the difference
    between the learned deviation of the target hour and of the current hour.
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
            if dev_now is None or dev_then is None:
                continue
            expected = price - dev_now + dev_then
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
    lowest = min(points, key=lambda p: p.price, default=None)
    if lowest is None or lowest.price >= best_now_price:
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
    elif saving >= settings.min_saving:
        result.recommendation = Recommendation.WAIT
    else:
        result.recommendation = Recommendation.FILL_NOW
    return result
