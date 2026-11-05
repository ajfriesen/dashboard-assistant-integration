"""The options flow: which dashboard the device shows.

The dashboard is a preference, not connection data, so it lives in the options
flow (Configure on the integration card) rather than in the config flow. Saving
it reloads the entry, which pushes the new URL to the device with the kiosk
login.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dashboard_assistant.const import (
    CONF_DASHBOARD,
    CONF_KIOSK_PROVISIONED,
    CONF_PAGES,
    DEFAULT_DASHBOARD,
    DOMAIN,
)
from custom_components.dashboard_assistant.provision import kiosk_url

from .conftest import BASE, HOST, PORT, TOKEN, mock_daemon

HA_URL = "http://ha.example:8123"


def _dashboard(url_path: str, title: str, *, require_admin: bool = False) -> Any:
    return SimpleNamespace(
        url_path=url_path,
        config={"url_path": url_path, "title": title, "require_admin": require_admin},
    )


@pytest.fixture
async def dashboards(hass: HomeAssistant) -> None:
    """Home Assistant's dashboard registry: the default one plus two more."""
    hass.data[LOVELACE_DATA] = SimpleNamespace(
        dashboards={
            None: SimpleNamespace(url_path=None, config=None),
            "dashboard-kitchen": _dashboard("dashboard-kitchen", "Kitchen"),
            "dashboard-admin": _dashboard("dashboard-admin", "Admin", require_admin=True),
        }
    )
    await hass.config.async_update(internal_url=HA_URL)


def _kiosk_logins(aioclient_mock: Any) -> list[dict[str, Any]]:
    return [
        json.loads(data) if isinstance(data, (str, bytes)) else dict(data)
        for method, url, data, _ in aioclient_mock.mock_calls
        if method == "POST" and str(url).endswith("/kiosk_login")
    ]


async def _setup(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    **data: Any,
) -> MockConfigEntry:
    mock_daemon(aioclient_mock, device_info, device_state)
    aioclient_mock.post(
        f"{BASE}/kiosk_login",
        json={"applied": ["token"]},
        headers={"Content-Type": "application/json"},
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=device_info["node_id"],
        data={CONF_HOST: HOST, CONF_PORT: PORT, CONF_TOKEN: TOKEN, **data},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_options_offer_the_dashboards_the_kiosk_can_open(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    """Home Assistant's default, plus every dashboard a non-admin user can open.

    The kiosk signs in as a non-admin user, so an admin-only dashboard would
    only ever show it an error.
    """
    entry = await _setup(
        hass, aioclient_mock, device_info, device_state, **{CONF_KIOSK_PROVISIONED: True}
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    selector = result["data_schema"].schema[CONF_DASHBOARD].config
    values = [option["value"] for option in selector["options"]]
    assert values == [DEFAULT_DASHBOARD, "dashboard-kitchen"]


async def test_choosing_a_dashboard_pushes_its_url_to_the_device(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    entry = await _setup(
        hass, aioclient_mock, device_info, device_state, **{CONF_KIOSK_PROVISIONED: True}
    )
    assert _kiosk_logins(aioclient_mock) == []

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_DASHBOARD: "dashboard-kitchen"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_DASHBOARD] == "dashboard-kitchen"
    logins = _kiosk_logins(aioclient_mock)
    assert [login["ha_url"] for login in logins] == [f"{HA_URL}/dashboard-kitchen"]


async def test_an_unchanged_entry_is_not_pushed_again(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    """An entry from before the option existed keeps working with no re-push."""
    await _setup(
        hass, aioclient_mock, device_info, device_state, **{CONF_KIOSK_PROVISIONED: True}
    )
    assert _kiosk_logins(aioclient_mock) == []


async def test_the_default_dashboard_is_home_assistants_own_url(
    hass: HomeAssistant, dashboards: None
) -> None:
    assert kiosk_url(hass, HA_URL, DEFAULT_DASHBOARD) == HA_URL


async def test_a_deleted_dashboard_falls_back_to_the_default(
    hass: HomeAssistant, dashboards: None
) -> None:
    """A dead link would leave the device on an error page."""
    assert kiosk_url(hass, HA_URL, "dashboard-gone") == HA_URL
    assert kiosk_url(hass, HA_URL, "dashboard-kitchen") == f"{HA_URL}/dashboard-kitchen"


def _page_writes(aioclient_mock: Any) -> list[list[dict[str, str]]]:
    return [
        (json.loads(data) if isinstance(data, (str, bytes)) else dict(data))["pages"]
        for method, url, data, _ in aioclient_mock.mock_calls
        if method == "POST" and str(url).endswith("/pages")
    ]


async def _setup_with_pages(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> MockConfigEntry:
    aioclient_mock.post(
        f"{BASE}/pages",
        json=device_state,
        headers={"Content-Type": "application/json"},
    )
    return await _setup(
        hass, aioclient_mock, device_info, device_state, **{CONF_KIOSK_PROVISIONED: True}
    )


async def test_options_show_the_pages_the_device_has(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    """The device owns its page list, so the form starts from what it reports."""
    entry = await _setup_with_pages(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    marker = next(k for k in result["data_schema"].schema if k == CONF_PAGES)
    assert marker.default() == device_state["page"]["list"]


async def test_saving_pages_sends_the_whole_list_to_the_device(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    """Any website, in order, in one call: the device replaces its list."""
    entry = await _setup_with_pages(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_DASHBOARD: DEFAULT_DASHBOARD,
            CONF_PAGES: [
                {"name": "Weather | Windy", "url": " https://www.windy.com "},
                {"url": "http://nvr.lan/live"},
            ],
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _page_writes(aioclient_mock) == [
        [
            {"name": "Weather | Windy", "url": "https://www.windy.com"},
            {"name": "", "url": "http://nvr.lan/live"},
        ]
    ]
    # The device stays the one place the list lives: a seed file can replace it
    # too, and a copy in the entry would go stale the moment one did.
    assert entry.options == {CONF_DASHBOARD: DEFAULT_DASHBOARD}


async def test_saving_only_the_dashboard_leaves_the_pages_alone(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    entry = await _setup_with_pages(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_DASHBOARD: "dashboard-kitchen"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _page_writes(aioclient_mock) == []


@pytest.mark.parametrize(
    "url", ["ftp://files.lan", "homeassistant.local:8123", "https://"]
)
async def test_a_page_that_is_not_a_website_is_refused_in_the_form(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
    url: str,
) -> None:
    """The device would refuse it too; saying so here keeps the user in the form."""
    entry = await _setup_with_pages(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_DASHBOARD: DEFAULT_DASHBOARD, CONF_PAGES: [{"name": "Bad", "url": url}]},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PAGES: "invalid_url"}
    assert _page_writes(aioclient_mock) == []
