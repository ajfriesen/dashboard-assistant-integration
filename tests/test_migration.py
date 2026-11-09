"""Migrating config entries made by earlier versions of the integration.

Before 1.3 the device's home was an option of the entry: 1.1 (release 1.0.0)
kept a dashboard as "dashboard", 1.2 (1.1.0-rc.1) a dashboard, tab or website
as "home". The home is now the first page, which the device keeps, so the
option moves into the device's page list the first time the device is reached.
"""

from __future__ import annotations

from typing import Any

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dashboard_assistant.const import (
    CONF_CERT_FINGERPRINT,
    CONF_KIOSK_PROVISIONED,
    CONF_KIOSK_URL,
    DOMAIN,
)

from .conftest import BASE, FINGERPRINT, HOST, KIOSK_HA_URL, PORT, TOKEN, mock_daemon
from .test_options_flow import _page_writes, _with_pages, dashboards  # noqa: F401

HA = KIOSK_HA_URL
STOCK = {"name": "Home Assistant", "url": "http://homeassistant.local:8123"}
TODO = {"name": "ToDo", "url": "http://ha.example:8123/todo"}
GRAFANA = {"name": "Grafana", "url": "http://grafana.lan"}


async def _migrate(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    state: dict[str, Any],
    minor_version: int,
    options: dict[str, str],
) -> MockConfigEntry:
    mock_daemon(aioclient_mock, device_info, state)
    for path in ("kiosk_login", "pages"):
        aioclient_mock.post(
            f"{BASE}/{path}", json=state, headers={"Content-Type": "application/json"}
        )
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        minor_version=minor_version,
        unique_id=device_info["node_id"],
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_TOKEN: TOKEN,
            CONF_CERT_FINGERPRINT: FINGERPRINT,
            CONF_KIOSK_PROVISIONED: True,
            CONF_KIOSK_URL: HA,
        },
        options=options,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.mark.parametrize(
    ("minor_version", "options", "pages", "written"),
    [
        # The stock first page (Home Assistant's .local address) becomes the
        # chosen dashboard, named after it.
        (
            1,
            {"dashboard": "dashboard-kitchen"},
            [STOCK, TODO],
            [{"name": "Kitchen", "url": f"{HA}/dashboard-kitchen"}, TODO],
        ),
        # Any other first page stays; the old home goes in front of it.
        (
            1,
            {},
            [GRAFANA, TODO],
            [{"name": "Home Assistant", "url": HA}, GRAFANA, TODO],
        ),
        (
            2,
            {"home": "dashboard-kitchen/lights"},
            [GRAFANA],
            [{"name": "Kitchen › Lights", "url": f"{HA}/dashboard-kitchen/lights"}, GRAFANA],
        ),
        (
            2,
            {"home": "https://pokypow.com"},
            [STOCK, GRAFANA],
            [{"name": "pokypow.com", "url": "https://pokypow.com"}, GRAFANA],
        ),
    ],
)
async def test_the_old_home_becomes_the_first_page(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,  # noqa: F811
    minor_version: int,
    options: dict[str, str],
    pages: list[dict[str, str]],
    written: list[dict[str, str]],
) -> None:
    """So updating changes neither where the device starts nor where Home goes."""
    entry = await _migrate(
        hass, aioclient_mock, device_info, _with_pages(device_state, pages), minor_version, options
    )

    assert _page_writes(aioclient_mock) == [written]
    assert dict(entry.options) == {}
    assert (entry.version, entry.minor_version) == (1, 3)
    assert "legacy_home" not in entry.data


async def test_a_home_already_first_is_left_alone(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,  # noqa: F811
) -> None:
    state = _with_pages(device_state, [{"name": "Home Assistant", "url": f"{HA}/"}, TODO])

    entry = await _migrate(hass, aioclient_mock, device_info, state, 1, {"dashboard": "default"})

    assert _page_writes(aioclient_mock) == []
    assert "legacy_home" not in entry.data


async def test_the_old_home_waits_for_a_device_that_refuses_the_pages(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,  # noqa: F811
) -> None:
    """Kept on the entry, it is tried again on the next setup."""
    state = _with_pages(device_state, [GRAFANA])
    mock_daemon(aioclient_mock, device_info, state)
    aioclient_mock.post(f"{BASE}/kiosk_login", json=state)
    aioclient_mock.post(f"{BASE}/pages", status=500)
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
            CONF_KIOSK_URL: HA,
        },
        options={"dashboard": "dashboard-kitchen"},
    )
    entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.data["legacy_home"] == "dashboard-kitchen"
    assert dict(entry.options) == {}
