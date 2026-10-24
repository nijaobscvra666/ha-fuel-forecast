"""Shared fixtures."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock, enable_custom_integrations):
    """Load custom_components/ in every test.

    recorder_mock must come before anything that sets up hass, because
    Fuel Forecast depends on the recorder.
    """
    yield
