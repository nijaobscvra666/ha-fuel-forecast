"""Config flow and setup inside a real Home Assistant test instance."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fuel_forecast.const import (
    CONF_FUEL_LEVEL_ENTITY,
    CONF_HORIZON,
    CONF_MIN_SAVING,
    CONF_NO_NEED_LEVEL,
    CONF_STATIONS,
    CONF_URGENT_LEVEL,
    DOMAIN,
)

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


async def test_config_flow_creates_entry(recorder_mock, hass: HomeAssistant) -> None:
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


async def test_config_flow_rejects_mixed_units(recorder_mock, hass: HomeAssistant) -> None:
    _prices(hass, unit_b="$")
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Mixed", **OPTIONS}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "mixed_units"}


async def test_setup_creates_entities_while_learning(recorder_mock, hass: HomeAssistant) -> None:
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
    assert hass.states.get("binary_sensor.super_e5_good_time_to_fill_up").state == "off"

    # A price change is reflected right away (recompute without learning).
    _prices(hass, b="1.699")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.super_e5_best_price_now").state == "1.699"

    # A 0 € glitch must not become the best price.
    _prices(hass, a="0")
    await hass.async_block_till_done()
    assert hass.states.get("sensor.super_e5_best_price_now").state == "1.759"

    assert await hass.config_entries.async_unload(entry.entry_id)
