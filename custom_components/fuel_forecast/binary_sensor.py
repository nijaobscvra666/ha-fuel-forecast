"""Good moment to fill up."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant

try:  # Home Assistant 2025.2+
    from homeassistant.helpers.entity_platform import (
        AddConfigEntryEntitiesCallback as AddEntitiesCallback,
    )
except ImportError:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FuelForecastConfigEntry
from .entity import FuelForecastEntity
from .model.forecast import Recommendation


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FuelForecastConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([GoodWindowSensor(entry.runtime_data, "good_window")])


class GoodWindowSensor(FuelForecastEntity, BinarySensorEntity):
    """On while filling up now is the recommendation."""

    @property
    def is_on(self) -> bool:
        return self.coordinator.data.recommendation == Recommendation.FILL_NOW

    @property
    def extra_state_attributes(self) -> dict:
        data = self.coordinator.data
        return {
            "station": self.coordinator.station_name(data.best_now_station),
            "price": data.best_now_price,
            "urgent": data.urgent,
        }
