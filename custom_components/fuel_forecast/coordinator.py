"""Collects prices, keeps the learned profiles and computes the forecast."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .const import (
    CONF_FUEL_LEVEL_ENTITY,
    CONF_HORIZON,
    CONF_MIN_SAVING,
    CONF_NO_NEED_LEVEL,
    CONF_STATIONS,
    CONF_TANK_SIZE,
    CONF_URGENT_LEVEL,
    DEFAULT_HORIZON,
    DEFAULT_MIN_SAVING,
    DEFAULT_NO_NEED_LEVEL,
    DEFAULT_URGENT_LEVEL,
    DOMAIN,
    SAMPLE_INTERVAL,
    STATISTICS_LOOKBACK,
    STATISTICS_WEIGHT,
    STORAGE_VERSION,
)
from .model.forecast import Result, Settings, plausible_prices, recommend
from .model.profile import StationProfile

_LOGGER = logging.getLogger(__name__)

SAVE_DELAY = 300  # seconds; the profile changes slowly, no need to write often


def _number(value: Any) -> float | None:
    if value in (None, STATE_UNAVAILABLE, STATE_UNKNOWN, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


class FuelForecastCoordinator(DataUpdateCoordinator[Result]):
    """One coordinator per config entry (= one group of stations)."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {entry.title}",
            # No update_interval: async_set_updated_data() (used on every price
            # change) would restart it, and busy stations would never be sampled.
            # Learning runs on its own timer instead, see async_setup().
        )
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}"
        )
        self.profiles: dict[str, StationProfile] = {}
        # Last known unit, so price sensors keep it while the source is down
        # (a unit flipping between None and "€" upsets the long-term statistics).
        self._last_unit: str | None = None
        self.imported_from_statistics = False

    @property
    def stations(self) -> list[str]:
        return list(self.config_entry.options[CONF_STATIONS])

    @property
    def unit(self) -> str | None:
        for entity_id in self.stations:
            if (state := self.hass.states.get(entity_id)) and (
                unit := state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
            ):
                self._last_unit = unit
                return unit
        return self._last_unit

    def station_name(self, entity_id: str | None) -> str | None:
        if entity_id is None:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return entity_id
        attrs = state.attributes
        # Tankerkönig exposes brand + street; other sources fall back to the name.
        if attrs.get("brand") and attrs.get("street"):
            street = str(attrs["street"]).strip()
            number = str(attrs.get("house_number") or "").strip()
            # Seen in real data: house_number "None", or the number already in street.
            if number.lower() in ("", "none", "null") or street.endswith(number):
                number = ""
            return " ".join(f"{attrs['brand']} {street} {number}".split())
        return state.name

    async def async_setup(self) -> None:
        """Load the stored profiles, bootstrap from statistics on first run."""
        stored = await self._store.async_load() or {}
        self._last_unit = stored.get("unit")
        self.profiles = {
            entity_id: StationProfile.from_dict(data)
            for entity_id, data in stored.get("profiles", {}).items()
        }
        missing = [s for s in self.stations if s not in self.profiles]
        if missing:
            await self._import_statistics(missing)

        self.config_entry.async_on_unload(
            async_track_state_change_event(
                self.hass,
                [*self.stations, *self._fuel_level_entity()],
                self._handle_source_change,
            )
        )
        self.config_entry.async_on_unload(
            async_track_time_interval(self.hass, self._async_sample, SAMPLE_INTERVAL)
        )

    def _fuel_level_entity(self) -> list[str]:
        entity = self.config_entry.options.get(CONF_FUEL_LEVEL_ENTITY)
        return [entity] if entity else []

    async def _import_statistics(self, entity_ids: list[str]) -> None:
        """Learn from hourly long-term statistics the recorder already has."""
        start = dt_util.utcnow() - STATISTICS_LOOKBACK
        try:
            stats = await get_instance(self.hass).async_add_executor_job(
                statistics_during_period,
                self.hass,
                start,
                None,
                set(entity_ids),
                "hour",
                None,
                {"mean", "min"},
            )
        except Exception:  # noqa: BLE001 - recorder issues must not block setup
            _LOGGER.warning("Could not read long-term statistics", exc_info=True)
            return
        tz = dt_util.get_default_time_zone()
        for entity_id in entity_ids:
            profile = self.profiles.setdefault(entity_id, StationProfile())
            for row in stats.get(entity_id, []):
                mean = row.get("mean")
                # An hour with a 0 € glitch has a distorted mean, skip it.
                if mean is None or (row.get("min") is not None and row["min"] <= 0):
                    continue
                begin = row["start"]
                if not isinstance(begin, datetime):
                    begin = dt_util.utc_from_timestamp(begin)
                profile.add_sample(
                    begin + timedelta(minutes=30), float(mean), tz, STATISTICS_WEIGHT
                )
            if stats.get(entity_id):
                self.imported_from_statistics = True
                _LOGGER.debug(
                    "Imported %s hours for %s, coverage %.0f%%",
                    len(stats[entity_id]),
                    entity_id,
                    profile.coverage() * 100,
                )
        self._save()

    def _current_prices(self) -> dict[str, float]:
        prices = {}
        for entity_id in self.stations:
            state = self.hass.states.get(entity_id)
            if state and (price := _number(state.state)) is not None:
                prices[entity_id] = price
        return plausible_prices(prices, self.profiles)

    def _fuel_level(self) -> float | None:
        """Fuel level in percent from a % sensor, or from litres and tank size."""
        entity = self.config_entry.options.get(CONF_FUEL_LEVEL_ENTITY)
        if not entity or (state := self.hass.states.get(entity)) is None:
            return None
        value = _number(state.state)
        if value is None:
            return None
        unit = (state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or "").lower()
        if unit == "%":
            return value
        tank = self.config_entry.options.get(CONF_TANK_SIZE)
        if unit in ("l", "litre", "liter", "gal") and tank:
            return 100.0 * value / tank
        return None

    def _settings(self) -> Settings:
        opts = self.config_entry.options
        return Settings(
            horizon_hours=int(opts.get(CONF_HORIZON, DEFAULT_HORIZON)),
            min_saving=float(opts.get(CONF_MIN_SAVING, DEFAULT_MIN_SAVING)) / 100,
            tank_size=opts.get(CONF_TANK_SIZE),
            fuel_level=self._fuel_level(),
            no_need_level=float(opts.get(CONF_NO_NEED_LEVEL, DEFAULT_NO_NEED_LEVEL)),
            urgent_level=float(opts.get(CONF_URGENT_LEVEL, DEFAULT_URGENT_LEVEL)),
        )

    def _compute(self) -> Result:
        return recommend(
            self.profiles,
            self._current_prices(),
            dt_util.utcnow(),
            dt_util.get_default_time_zone(),
            self._settings(),
        )

    async def _async_update_data(self) -> Result:
        return self._compute()

    async def _async_sample(self, now: datetime) -> None:
        """Every sample interval: learn from the current prices, then recompute.

        Also moves the forecast window forward when no price changes.
        """
        tz = dt_util.get_default_time_zone()
        for entity_id, price in self._current_prices().items():
            self.profiles.setdefault(entity_id, StationProfile()).add_sample(
                dt_util.as_utc(now), price, tz
            )
        self._save()
        self.async_set_updated_data(self._compute())

    @callback
    def _handle_source_change(self, event: Event[EventStateChangedData]) -> None:
        """A price or the fuel level changed: recompute without learning."""
        if self.data is not None:
            self.async_set_updated_data(self._compute())

    def _save(self) -> None:
        # Drop stations that were removed from the group.
        for entity_id in set(self.profiles) - set(self.stations):
            del self.profiles[entity_id]
        self._store.async_delay_save(
            self._data_to_store,
            SAVE_DELAY,
        )

    def _data_to_store(self) -> dict[str, Any]:
        return {
            "unit": self._last_unit,
            "profiles": {k: p.as_dict() for k, p in self.profiles.items()},
        }

    async def async_shutdown(self) -> None:
        await super().async_shutdown()
        await self._store.async_save(self._data_to_store())

    async def async_remove_store(self) -> None:
        await self._store.async_remove()
