"""Constants for Fuel Forecast."""

from datetime import timedelta

DOMAIN = "fuel_forecast"

CONF_STATIONS = "stations"
CONF_FUEL_LEVEL_ENTITY = "fuel_level_entity"
CONF_TANK_SIZE = "tank_size"
CONF_MIN_SAVING = "min_saving"
CONF_HORIZON = "horizon"
CONF_NO_NEED_LEVEL = "no_need_level"
CONF_URGENT_LEVEL = "urgent_level"

DEFAULT_MIN_SAVING = 3.0  # cents per litre (or 1/100 of the price unit)
DEFAULT_HORIZON = 24
DEFAULT_NO_NEED_LEVEL = 60.0
DEFAULT_URGENT_LEVEL = 15.0

# One sample per station every 10 minutes keeps the learning time-weighted,
# independent of how often a price source updates.
SAMPLE_INTERVAL = timedelta(minutes=10)
# Hourly long-term statistics imported on first setup count like six samples.
STATISTICS_WEIGHT = 6.0
STATISTICS_LOOKBACK = timedelta(weeks=10)

STORAGE_VERSION = 1
