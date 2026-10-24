"""Config and options flow for Fuel Forecast."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

try:  # Home Assistant 2026.10+
    import probatio as vol
except ImportError:  # older Home Assistant versions
    import voluptuous as vol

from homeassistant.components.sensor import DOMAIN as SENSOR_DOMAIN
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, CONF_NAME
from homeassistant.helpers import selector
from homeassistant.helpers.schema_config_entry_flow import (
    SchemaCommonFlowHandler,
    SchemaConfigFlowHandler,
    SchemaFlowError,
    SchemaFlowFormStep,
)

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
)


def _percent() -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0, max=100, step=1, unit_of_measurement="%", mode=selector.NumberSelectorMode.BOX
        )
    )


OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_STATIONS): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=SENSOR_DOMAIN, multiple=True)
        ),
        vol.Required(CONF_MIN_SAVING, default=DEFAULT_MIN_SAVING): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=0, max=50, step=0.5, mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Required(CONF_HORIZON, default=DEFAULT_HORIZON): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=3, max=48, step=1, unit_of_measurement="h", mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Optional(CONF_TANK_SIZE): selector.NumberSelector(
            selector.NumberSelectorConfig(
                min=1, max=500, step=1, mode=selector.NumberSelectorMode.BOX
            )
        ),
        vol.Optional(CONF_FUEL_LEVEL_ENTITY): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=SENSOR_DOMAIN)
        ),
        vol.Required(CONF_NO_NEED_LEVEL, default=DEFAULT_NO_NEED_LEVEL): _percent(),
        vol.Required(CONF_URGENT_LEVEL, default=DEFAULT_URGENT_LEVEL): _percent(),
    }
)

CONFIG_SCHEMA = vol.Schema({vol.Required(CONF_NAME): selector.TextSelector()}).extend(
    OPTIONS_SCHEMA.schema
)


async def _validate(
    handler: SchemaCommonFlowHandler, user_input: dict[str, Any]
) -> dict[str, Any]:
    """All stations must report prices in the same unit."""
    hass = handler.parent_handler.hass
    units = set()
    for entity_id in user_input[CONF_STATIONS]:
        state = hass.states.get(entity_id)
        if state is None:
            raise SchemaFlowError("station_not_found")
        if unit := state.attributes.get(ATTR_UNIT_OF_MEASUREMENT):
            units.add(unit)
    if len(units) > 1:
        raise SchemaFlowError("mixed_units")
    if user_input[CONF_URGENT_LEVEL] >= user_input[CONF_NO_NEED_LEVEL]:
        raise SchemaFlowError("levels")
    return user_input


CONFIG_FLOW = {"user": SchemaFlowFormStep(CONFIG_SCHEMA, validate_user_input=_validate)}
OPTIONS_FLOW = {"init": SchemaFlowFormStep(OPTIONS_SCHEMA, validate_user_input=_validate)}


class ConfigFlowHandler(SchemaConfigFlowHandler, domain=DOMAIN):
    """Set up a group of stations to forecast."""

    config_flow = CONFIG_FLOW
    options_flow = OPTIONS_FLOW
    options_flow_reloads = True

    def async_config_entry_title(self, options: Mapping[str, Any]) -> str:
        return cast(str, options[CONF_NAME])
