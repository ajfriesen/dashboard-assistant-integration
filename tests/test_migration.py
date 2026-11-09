"""Migrating config entries made by earlier versions of the integration."""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dashboard_assistant.const import (
    CONF_CERT_FINGERPRINT,
    CONF_HOME,
    CONF_KIOSK_PROVISIONED,
    CONF_KIOSK_URL,
    DOMAIN,
)

from .conftest import BASE, FINGERPRINT, HOST, KIOSK_HA_URL, PORT, TOKEN, mock_daemon


@pytest.mark.parametrize(
    ("options", "migrated"),
    [
        # 1.0.0 kept the chosen dashboard as "dashboard"; it is now the home.
        ({"dashboard": "dashboard-kitchen"}, {CONF_HOME: "dashboard-kitchen"}),
        ({"dashboard": "default"}, {CONF_HOME: "default"}),
        # Never configured: nothing to carry over.
        ({}, {}),
    ],
)
async def test_the_chosen_dashboard_becomes_the_home(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    options: dict[str, str],
    migrated: dict[str, str],
) -> None:
    mock_daemon(aioclient_mock, device_info, device_state)
    aioclient_mock.post(
        f"{BASE}/kiosk_login",
        json={"applied": ["token"]},
        headers={"Content-Type": "application/json"},
    )
    await hass.config.async_update(internal_url=KIOSK_HA_URL)
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=1,
        unique_id=device_info["node_id"],
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_TOKEN: TOKEN,
            CONF_CERT_FINGERPRINT: FINGERPRINT,
            CONF_KIOSK_PROVISIONED: True,
            CONF_KIOSK_URL: KIOSK_HA_URL,
        },
        options=options,
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert dict(entry.options) == migrated
    assert (entry.version, entry.minor_version) == (1, 2)
