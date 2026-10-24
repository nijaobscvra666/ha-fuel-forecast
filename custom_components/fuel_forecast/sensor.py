"""Sensors: best price now, expected lowest price, recommendation, saving."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant

try:  # Home Assistant 2025.2+
    from homeassistant.helpers.entity_platform import (
        AddConfigEntryEntitiesCallback as AddEntitiesCallback,
    )
except ImportError:
    from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import FuelForecastConfigEntry
from .coordinator import FuelForecastCoordinator
from .entity import FuelForecastEntity
from .model.forecast import Recommendation, Result


@dataclass(frozen=True, kw_only=True)
class FuelForecastSensorDescription(SensorEntityDescription):
    value: Callable[[Result], Any]
    # Price-like sensors take the unit of the source sensors.
    price_unit: bool = False
    attributes: Callable[[FuelForecastCoordinator, Result], dict[str, Any]] | None = None


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(value, digits)


SENSORS = (
    FuelForecastSensorDescription(
        key="best_price_now",
        state_class=SensorStateClass.MEASUREMENT,
        price_unit=True,
        suggested_display_precision=3,
        value=lambda r: _round(r.best_now_price),
        attributes=lambda c, r: {
            "station": c.station_name(r.best_now_station),
            "entity_id": r.best_now_station,
        },
    ),
    FuelForecastSensorDescription(
        key="lowest_price",
        price_unit=True,
        suggested_display_precision=3,
        value=lambda r: _round(r.lowest_price),
        attributes=lambda c, r: {
            "station": c.station_name(r.lowest_station),
            "entity_id": r.lowest_station,
            "forecast": [
                {"time": p.time.isoformat(), "price": round(p.price, 3)}
                for p in r.forecast
            ],
        },
    ),
    FuelForecastSensorDescription(
        key="lowest_time",
        device_class=SensorDeviceClass.TIMESTAMP,
        value=lambda r: r.lowest_time,
    ),
    FuelForecastSensorDescription(
        key="recommendation",
        device_class=SensorDeviceClass.ENUM,
        options=[r.value for r in Recommendation],
        value=lambda r: r.recommendation.value,
        attributes=lambda c, r: {"urgent": r.urgent},
    ),
    FuelForecastSensorDescription(
        key="saving_per_litre",
        price_unit=True,
        suggested_display_precision=3,
        value=lambda r: _round(r.saving_per_litre),
    ),
    FuelForecastSensorDescription(
        key="saving_per_fill",
        price_unit=True,
        suggested_display_precision=2,
        value=lambda r: _round(r.saving_per_fill, 2),
    ),
    FuelForecastSensorDescription(
        key="coverage",
        native_unit_of_measurement=PERCENTAGE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=0,
        value=lambda r: round(r.coverage * 100),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FuelForecastConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        FuelForecastSensor(entry.runtime_data, description) for description in SENSORS
    )


class FuelForecastSensor(FuelForecastEntity, SensorEntity):
    entity_description: FuelForecastSensorDescription
    # The 24 h forecast list is for cards, not worth storing in the history.
    _unrecorded_attributes = frozenset({"forecast"})

    def __init__(
        self, coordinator: FuelForecastCoordinator, description: FuelForecastSensorDescription
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_unit_of_measurement(self) -> str | None:
        if self.entity_description.price_unit:
            return self.coordinator.unit
        return self.entity_description.native_unit_of_measurement

    @property
    def native_value(self) -> Any:
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.attributes is None:
            return None
        return self.entity_description.attributes(self.coordinator, self.coordinator.data)
