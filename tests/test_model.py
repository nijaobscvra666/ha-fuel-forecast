"""Tests for the pure forecast model (no Home Assistant needed)."""

from __future__ import annotations

import importlib.util
import sys
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

# Load the model package directly so these tests run without Home Assistant.
_MODEL = Path(__file__).parents[1] / "custom_components" / "fuel_forecast" / "model"
_spec = importlib.util.spec_from_file_location(
    "ff_model", _MODEL / "__init__.py", submodule_search_locations=[str(_MODEL)]
)
model = importlib.util.module_from_spec(_spec)
sys.modules["ff_model"] = model
_spec.loader.exec_module(model)
from ff_model.forecast import (  # noqa: E402
    Recommendation,
    Settings,
    build_forecast,
    plausible_prices,
    recommend,
)
from ff_model.profile import (  # noqa: E402
    BUCKETS,
    MAX_WEIGHT,
    StationProfile,
    bucket_of,
)

BERLIN = ZoneInfo("Europe/Berlin")


def pattern(local_hour: int) -> float:
    """Typical German day: expensive in the morning, cheap in the evening."""
    if 6 <= local_hour < 10:
        return 0.06
    if 18 <= local_hour < 22:
        return -0.08
    return 0.0


def feed(profile: StationProfile, start: datetime, days: int, base: float, drift=0.0):
    """Sample every 10 minutes like the coordinator does."""
    moment = start
    end = start + timedelta(days=days)
    while moment < end:
        elapsed_days = (moment - start).total_seconds() / 86400
        price = base + drift * elapsed_days + pattern(moment.astimezone(BERLIN).hour)
        profile.add_sample(moment, round(price, 3), BERLIN)
        moment += timedelta(minutes=10)
    return moment


class ProfileTest(unittest.TestCase):
    def test_bucket_uses_local_time(self):
        # Monday 2026-10-26 00:30 local (CET, UTC+1) is Sunday 23:30 UTC.
        self.assertEqual(bucket_of(datetime(2026, 10, 25, 23, 30, tzinfo=UTC), BERLIN), 0)
        # One hour earlier it is still Sunday 23:30 local -> last weekend bucket.
        self.assertEqual(bucket_of(datetime(2026, 10, 25, 22, 30, tzinfo=UTC), BERLIN), 47)

    def test_learns_pattern_despite_rising_prices(self):
        profile = StationProfile()
        start = datetime(2026, 9, 7, 0, 0, tzinfo=BERLIN)  # a Monday
        # 4 weeks, prices rise 1 ct per day overall.
        feed(profile, start, 28, base=1.70, drift=0.01)
        self.assertGreater(profile.coverage(), 0.95)
        monday_20 = profile.deviation(20)
        monday_8 = profile.deviation(8)
        # Evening clearly below, morning clearly above the daily mean.
        self.assertLess(monday_20, -0.05)
        self.assertGreater(monday_8, 0.03)
        self.assertAlmostEqual(monday_8 - monday_20, 0.14, delta=0.02)

    def test_median_reference_ignores_spike(self):
        profile = StationProfile()
        start = datetime(2026, 9, 7, 0, 0, tzinfo=UTC)
        for i in range(24 * 6):
            price = 2.50 if i == 60 else 1.70
            profile.add_sample(start + timedelta(minutes=10 * i), price, BERLIN)
        self.assertEqual(profile.reference(), 1.70)

    def test_needs_reference_span_before_learning(self):
        profile = StationProfile()
        start = datetime(2026, 9, 7, 0, 0, tzinfo=BERLIN)
        feed(profile, start, 0.4, base=1.70)  # under 12 h
        self.assertEqual(profile.coverage(), 0)

    def test_weight_is_capped(self):
        profile = StationProfile()
        feed(profile, datetime(2026, 1, 5, tzinfo=BERLIN), 140, base=1.7)
        self.assertTrue(all(b.weight <= MAX_WEIGHT for b in profile.buckets))

    def test_out_of_order_sample_ignored(self):
        profile = StationProfile()
        t = datetime(2026, 9, 7, 12, tzinfo=UTC)
        profile.add_sample(t, 1.7, BERLIN)
        profile.add_sample(t - timedelta(hours=1), 1.0, BERLIN)
        self.assertEqual(len(profile.recent), 1)

    def test_roundtrip(self):
        profile = StationProfile()
        feed(profile, datetime(2026, 9, 7, tzinfo=BERLIN), 8, base=1.7)
        again = StationProfile.from_dict(profile.as_dict())
        self.assertAlmostEqual(again.coverage(), profile.coverage())
        self.assertEqual(len(again.buckets), BUCKETS)
        self.assertAlmostEqual(again.reference(), profile.reference(), places=4)

    def test_dst_change_keeps_wall_clock_hours(self):
        # Learning across the October switch to winter time must still put the
        # cheap evening into the evening buckets.
        profile = StationProfile()
        feed(profile, datetime(2026, 10, 12, tzinfo=BERLIN), 28, base=1.7)
        sunday_20 = 24 + 20
        self.assertLess(profile.deviation(sunday_20), -0.05)


class PlausibilityTest(unittest.TestCase):
    def test_zero_and_jumps_are_rejected(self):
        profile = StationProfile()
        start = datetime(2026, 9, 7, tzinfo=UTC)
        for i in range(12):
            profile.add_sample(start + timedelta(hours=i), 2.20, BERLIN)
        profile.add_sample(start + timedelta(hours=12), 0.0, BERLIN)
        profile.add_sample(start + timedelta(hours=13), 0.618, BERLIN)
        self.assertEqual(len(profile.recent), 12)
        self.assertTrue(profile.plausible(2.10))
        self.assertFalse(profile.plausible(0.618))

    def test_cross_station_filter(self):
        current = {"a": 2.20, "b": 2.18, "c": 2.25, "glitch": 0.62, "zero": 0.0}
        self.assertEqual(set(plausible_prices(current, {})), {"a", "b", "c"})

    def test_two_stations_only_drop_zero(self):
        self.assertEqual(plausible_prices({"a": 2.2, "b": 0.0}, {}), {"a": 2.2})


class RecommendTest(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 9, 7, 0, 0, tzinfo=BERLIN)
        self.cheap, self.dear = StationProfile(), StationProfile()
        feed(self.cheap, self.start, 21, base=1.65)
        feed(self.dear, self.start, 21, base=1.75)
        self.profiles = {"sensor.cheap": self.cheap, "sensor.dear": self.dear}

    def at(self, local_hour: int) -> datetime:
        return (self.start + timedelta(days=21)).replace(hour=local_hour, minute=15)

    def test_morning_says_wait_for_evening(self):
        now = self.at(8)
        current = {"sensor.cheap": 1.71, "sensor.dear": 1.81}
        result = recommend(self.profiles, current, now, BERLIN, Settings(tank_size=50))
        self.assertEqual(result.recommendation, Recommendation.WAIT)
        self.assertEqual(result.best_now_station, "sensor.cheap")
        self.assertEqual(result.lowest_station, "sensor.cheap")
        self.assertEqual(result.lowest_time.astimezone(BERLIN).hour, 18)
        self.assertAlmostEqual(result.saving_per_litre, 0.14, delta=0.02)
        self.assertAlmostEqual(result.saving_per_fill, 50 * result.saving_per_litre)

    def test_evening_says_fill_now(self):
        now = self.at(19)
        current = {"sensor.cheap": 1.57, "sensor.dear": 1.67}
        result = recommend(self.profiles, current, now, BERLIN, Settings())
        self.assertEqual(result.recommendation, Recommendation.FILL_NOW)
        self.assertEqual(result.saving_per_litre, 0.0)

    def test_fuel_level_rules(self):
        now = self.at(8)
        current = {"sensor.cheap": 1.71}
        full = recommend(self.profiles, current, now, BERLIN, Settings(fuel_level=80))
        self.assertEqual(full.recommendation, Recommendation.NO_NEED)
        empty = recommend(self.profiles, current, now, BERLIN, Settings(fuel_level=10))
        self.assertEqual(empty.recommendation, Recommendation.FILL_NOW)
        self.assertTrue(empty.urgent)
        half = recommend(
            self.profiles, current, now, BERLIN, Settings(fuel_level=50, tank_size=40)
        )
        self.assertEqual(half.recommendation, Recommendation.WAIT)
        self.assertAlmostEqual(half.saving_per_fill, 20 * half.saving_per_litre)

    def test_learning_and_unavailable(self):
        now = self.at(8)
        fresh = {"sensor.new": StationProfile()}
        result = recommend(fresh, {"sensor.new": 1.7}, now, BERLIN, Settings())
        self.assertEqual(result.recommendation, Recommendation.LEARNING)
        self.assertEqual(result.best_now_price, 1.7)
        self.assertEqual(
            recommend(self.profiles, {}, now, BERLIN, Settings()).recommendation,
            Recommendation.NO_PRICES,
        )

    def test_unknown_station_among_known_ones(self):
        # A newly added station without profile still counts for "best now".
        now = self.at(8)
        current = {"sensor.cheap": 1.71, "sensor.brand_new": 1.60}
        result = recommend(self.profiles, current, now, BERLIN, Settings())
        self.assertEqual(result.best_now_station, "sensor.brand_new")
        # The unknown station has no pattern, so only the known one is forecast.
        self.assertTrue(all(p.station == "sensor.cheap" for p in result.forecast))
        # Reported coverage covers all stations of the group.
        expected = (self.cheap.coverage() + self.dear.coverage()) / 2
        self.assertAlmostEqual(result.coverage, expected)

    def test_coverage_reported_without_prices(self):
        result = recommend(self.profiles, {}, self.at(8), BERLIN, Settings())
        self.assertEqual(result.recommendation, Recommendation.NO_PRICES)
        self.assertGreater(result.coverage, 0.9)

    def test_late_spike_does_not_drag_forecast_down(self):
        # Live 24.10.2026: a station usually spikes at noon, today the spike was
        # late. Its normal noon price must not be read as "spike included".
        def spiky(local_hour):
            return 0.15 if local_hour == 12 else 0.0
        profile = StationProfile()
        start = datetime(2026, 9, 7, tzinfo=BERLIN)
        moment = start
        while moment < start + timedelta(days=21):
            profile.add_sample(moment, 1.90 + spiky(moment.astimezone(BERLIN).hour), BERLIN)
            moment += timedelta(minutes=10)
        now = moment.replace(hour=12, minute=5)  # a Monday at 12:05, no spike yet
        for minute in range(0, 5):
            profile.add_sample(now - timedelta(minutes=5 - minute), 1.90, BERLIN)
        result = recommend({"s": profile}, {"s": 1.90}, now, BERLIN, Settings())
        # The old model expected ~1.75 later on (1.90 - 0.15) and said "wait".
        self.assertGreaterEqual(result.lowest_price, profile.recent_min() - 0.02)
        self.assertEqual(result.recommendation, Recommendation.FILL_NOW)

    def test_forecast_has_one_point_per_hour(self):
        now = self.at(8)
        points = build_forecast(self.profiles, {"sensor.cheap": 1.71}, now, BERLIN, 24)
        self.assertEqual(len(points), 24)
        self.assertEqual(points[0].time.astimezone(BERLIN).hour, 9)


if __name__ == "__main__":
    unittest.main()
