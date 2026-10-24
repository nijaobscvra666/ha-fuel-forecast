"""Fuel Forecast: learns when fuel is cheapest from existing price sensors."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import FuelForecastCoordinator

PLATFORMS = [Platform.BINARY_SENSOR, Platform.SENSOR]

type FuelForecastConfigEntry = ConfigEntry[FuelForecastCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: FuelForecastConfigEntry) -> bool:
    coordinator = FuelForecastCoordinator(hass, entry)
    await coordinator.async_setup()
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: FuelForecastConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        await entry.runtime_data.async_shutdown()
    return unloaded


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the learned profiles together with the entry."""
    await FuelForecastCoordinator(hass, entry).async_remove_store()
