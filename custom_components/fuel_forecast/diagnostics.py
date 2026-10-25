"""Diagnostics: what has been learned, without any location data."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from . import FuelForecastConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: FuelForecastConfigEntry
) -> dict[str, Any]:
    coordinator = entry.runtime_data
    data = coordinator.data
    return {
        "options": {
            **{
                k: v
                for k, v in entry.options.items()
                if k not in ("name", "stations", "fuel_level_entity")
            },
            "stations": len(entry.options.get("stations", [])),
            # The entity id of the car may contain its name or plate.
            "fuel_level_entity": bool(entry.options.get("fuel_level_entity")),
        },
        "unit": coordinator.unit,
        "imported_from_statistics": coordinator.imported_from_statistics,
        "stations": {
            # Index instead of entity_id: entity ids often contain street names.
            f"station_{i}": {
                "coverage": round(p.coverage(), 3),
                "samples_24h": len(p.recent),
                "weights": [round(b.weight, 1) for b in p.buckets],
                "deviations": [round(b.mean, 4) for b in p.buckets],
            }
            for i, p in enumerate(coordinator.profiles.values())
        },
        "result": {
            "recommendation": data.recommendation.value,
            "coverage": round(data.coverage, 3),
            "saving_per_litre": data.saving_per_litre,
            "forecast_points": len(data.forecast),
        },
    }
