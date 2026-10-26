"""Config flow and setup inside a real Home Assistant test instance."""

from __future__ import annotations

from datetime import timedelta

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed

from custom_components.fuel_forecast.const import (
    CONF_FUEL_LEVEL_ENTITY,
    CONF_HORIZON,
    CONF_MIN_SAVING,
    CONF_NO_NEED_LEVEL,
    CONF_STATIONS,
    CONF_URGENT_LEVEL,
    DOMAIN,
)
from custom_components.fuel_forecast.coordinator import SOURCE_DEBOUNCE

STATIONS = ["sensor.station_a_e5", "sensor.station_b_e5"]
OPTIONS = {
    CONF_STATIONS: STATIONS,
    CONF_MIN_SAVING: 3.0,
    CONF_HORIZON: 24,
    CONF_NO_NEED_LEVEL: 60,
    CONF_URGENT_LEVEL: 15,
}


def _prices(hass: HomeAssistant, a: str = "1.789", b: str = "1.759", unit_b: str = "€") -> None:
    hass.states.async_set(
        STATIONS[0], a, {"unit_of_measurement": "€", "brand": "ARAL", "street": "Hauptstr.", "house_number": "1"}
    )
    hass.states.async_set(STATIONS[1], b, {"unit_of_measurement": unit_b})


async def _settle(hass: HomeAssistant) -> None:
    """Let the debounced recompute after a source change run."""
    await hass.async_block_till_done()
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=SOURCE_DEBOUNCE + 1))
    await hass.async_block_till_done()


async def test_config_flow_creates_entry(hass: HomeAssistant) -> None:
    _prices(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Super E5", **OPTIONS}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Super E5"
    assert result["options"][CONF_STATIONS] == STATIONS


async def test_config_flow_rejects_mixed_units(hass: HomeAssistant) -> None:
    _prices(hass, unit_b="$")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Mixed", **OPTIONS}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "mixed_units"}


async def test_setup_creates_entities_while_learning(hass: HomeAssistant) -> None:
    _prices(hass)
    hass.states.async_set("sensor.car_fuel_level", "42", {"unit_of_measurement": "%"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Super E5",
        options={"name": "Super E5", **OPTIONS, CONF_FUEL_LEVEL_ENTITY: "sensor.car_fuel_level"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    best = hass.states.get("sensor.super_e5_best_price_now")
    assert best is not None
    assert best.state == "1.759"
    assert best.attributes["unit_of_measurement"] == "€"
    assert hass.states.get("sensor.super_e5_recommendation").state == "learning"
    # Saving per litre is shown in cents and says what it compares.
    saving = hass.states.get("sensor.super_e5_saving_if_you_wait_per_litre")
    assert saving.attributes["unit_of_measurement"] == "ct"
    assert saving.attributes["price_now"] == 1.759
    assert "expected_time" in saving.attributes
    assert hass.states.get("binary_sensor.super_e5_good_time_to_fill_up").state == "off"

    # A price change is recomputed once the source is quiet for a moment
    # (stations update one after another; no in-between states).
    _prices(hass, b="1.699")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.super_e5_best_price_now").state == "1.759"
    await _settle(hass)
    assert hass.states.get("sensor.super_e5_best_price_now").state == "1.699"

    # A 0 € glitch must not become the best price.
    _prices(hass, a="0")
    await _settle(hass)
    assert hass.states.get("sensor.super_e5_best_price_now").state == "1.759"

    # Station names are cleaned up (real Tankerkönig data: "None", trailing spaces).
    hass.states.async_set(
        STATIONS[0], "1.659", {"unit_of_measurement": "€", "brand": "OIL!", "street": "Brückenstraße 31", "house_number": "None"}
    )
    await _settle(hass)
    assert hass.states.get("sensor.super_e5_best_price_now").attributes["station"] == "OIL! Brückenstraße 31"
    hass.states.async_set(
        STATIONS[0], "1.659", {"unit_of_measurement": "€", "brand": "ELAN", "street": "Pommernstr. ", "house_number": "16"}
    )
    await _settle(hass)
    assert hass.states.get("sensor.super_e5_best_price_now").attributes["station"] == "ELAN Pommernstr. 16"

    # Source down: price sensors keep their unit (no None <-> "€" flip in statistics).
    for station in STATIONS:
        hass.states.async_set(station, "unavailable", {})
    await _settle(hass)
    assert hass.states.get("sensor.super_e5_recommendation").state == "no_prices"
    assert hass.states.get("sensor.super_e5_best_price_now").attributes["unit_of_measurement"] == "€"

    assert await hass.config_entries.async_unload(entry.entry_id)
