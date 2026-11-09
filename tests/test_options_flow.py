"""The options flow: the device's home, and its pages.

The home is where the device starts and where its Home button goes: Home
Assistant's default dashboard, another dashboard, one of a dashboard's tabs, or
any website. It is a preference, not connection data, so it lives in the options
flow (Configure on the integration card) rather than in the config flow. Saving
it reloads the entry, which pushes the new URL to the device with the kiosk
login.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.components.lovelace.const import LOVELACE_DATA, ConfigNotFound
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dashboard_assistant.const import (
    CONF_CERT_FINGERPRINT,
    CONF_HOME,
    CONF_KIOSK_HOME_URL,
    CONF_KIOSK_PROVISIONED,
    CONF_KIOSK_URL,
    CONF_PAGES,
    DEFAULT_HOME,
    DOMAIN,
)
from custom_components.dashboard_assistant.provision import home_url

from .conftest import BASE, FINGERPRINT, HOST, PORT, TOKEN, mock_daemon

HA_URL = "http://ha.example:8123"


def _dashboard(
    url_path: str | None,
    title: str,
    *,
    require_admin: bool = False,
    views: list[dict[str, Any]] | None = None,
) -> Any:
    """A dashboard as Home Assistant keeps it; ``views=None`` has no saved config."""

    async def async_load(force: bool) -> dict[str, Any]:
        if views is None:
            raise ConfigNotFound
        return {"views": views}

    return SimpleNamespace(
        url_path=url_path,
        config=None
        if url_path is None
        else {"url_path": url_path, "title": title, "require_admin": require_admin},
        async_load=async_load,
    )


@pytest.fixture
async def dashboards(hass: HomeAssistant) -> None:
    """Home Assistant's dashboard registry: the default one plus two more.

    The default one is the built-in Overview with two tabs; Kitchen has two
    tabs, one without a path, which Home Assistant then addresses by position.
    """
    hass.data[LOVELACE_DATA] = SimpleNamespace(
        dashboards={
            None: _dashboard(None, "Overview", views=[{"title": "Home", "path": "home"}, {"title": "Energy", "path": "energy"}]),
            "dashboard-kitchen": _dashboard(
                "dashboard-kitchen",
                "Kitchen",
                views=[{"title": "Lights", "path": "lights"}, {"title": "Climate"}],
            ),
            "dashboard-admin": _dashboard(
                "dashboard-admin", "Admin", require_admin=True, views=[{"path": "x"}]
            ),
            "dashboard-auto": _dashboard("dashboard-auto", "Auto"),
        }
    )
    await hass.config.async_update(internal_url=HA_URL)


def _kiosk_logins(aioclient_mock: Any) -> list[dict[str, Any]]:
    return [
        json.loads(data) if isinstance(data, (str, bytes)) else dict(data)
        for method, url, data, _ in aioclient_mock.mock_calls
        if method == "POST" and str(url).endswith("/kiosk_login")
    ]


def _pushed_urls(aioclient_mock: Any) -> list[tuple[str, str]]:
    """(ha_url, home_url) of each kiosk login sent to the device."""
    return [(login["ha_url"], login["home_url"]) for login in _kiosk_logins(aioclient_mock)]


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
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_TOKEN: TOKEN,
            CONF_CERT_FINGERPRINT: FINGERPRINT,
            **data,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_options_offer_the_dashboards_and_tabs_the_kiosk_can_open(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    """Home Assistant's default, then every dashboard a non-admin user can open,
    each followed by its tabs; and any other address can be typed in.

    The kiosk signs in as a non-admin user, so an admin-only dashboard would
    only ever show it an error. A dashboard without saved tabs (one Home
    Assistant generates) is offered whole.
    """
    entry = await _setup(
        hass, aioclient_mock, device_info, device_state, **{CONF_KIOSK_PROVISIONED: True, CONF_KIOSK_URL: HA_URL, CONF_KIOSK_HOME_URL: HA_URL}
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    selector = result["data_schema"].schema[CONF_HOME].config
    assert [(o["value"], o["label"]) for o in selector["options"]] == [
        (DEFAULT_HOME, "Home Assistant default"),
        ("lovelace/home", "Overview › Home"),
        ("lovelace/energy", "Overview › Energy"),
        ("dashboard-auto", "Auto"),
        ("dashboard-kitchen", "Kitchen"),
        ("dashboard-kitchen/lights", "Kitchen › Lights"),
        ("dashboard-kitchen/1", "Kitchen › Climate"),
    ]
    assert selector["custom_value"] is True


async def test_choosing_a_dashboard_makes_it_the_devices_home(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    entry = await _setup(
        hass, aioclient_mock, device_info, device_state, **{CONF_KIOSK_PROVISIONED: True, CONF_KIOSK_URL: HA_URL, CONF_KIOSK_HOME_URL: HA_URL}
    )
    assert _kiosk_logins(aioclient_mock) == []

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_HOME: "dashboard-kitchen"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options[CONF_HOME] == "dashboard-kitchen"
    assert _pushed_urls(aioclient_mock) == [(HA_URL, f"{HA_URL}/dashboard-kitchen")]


@pytest.mark.parametrize(
    ("home", "url"),
    [
        ("dashboard-kitchen/lights", f"{HA_URL}/dashboard-kitchen/lights"),
        ("lovelace/energy", f"{HA_URL}/lovelace/energy"),
        # Typed in: a path on Home Assistant, a page on it, or any website.
        ("/dashboard-kitchen/1", f"{HA_URL}/dashboard-kitchen/1"),
        (f"{HA_URL}/dashboard-kitchen/lights", f"{HA_URL}/dashboard-kitchen/lights"),
        ("https://www.windy.com/?rain", "https://www.windy.com/?rain"),
    ],
)
async def test_a_tab_or_any_website_can_be_the_home(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
    home: str,
    url: str,
) -> None:
    """Sign-in still goes to Home Assistant's own URL, whatever the home is.

    The device signs in only on the ha_url origin, so a home on another site
    is shown signed out and never handed the token.
    """
    entry = await _setup(
        hass, aioclient_mock, device_info, device_state, **{CONF_KIOSK_PROVISIONED: True, CONF_KIOSK_URL: HA_URL, CONF_KIOSK_HOME_URL: HA_URL}
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_HOME: home}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _pushed_urls(aioclient_mock) == [(HA_URL, url)]


@pytest.mark.parametrize("home", ["ftp://files.lan", "https://", "  "])
async def test_a_home_that_is_not_a_website_is_refused_in_the_form(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
    home: str,
) -> None:
    entry = await _setup(
        hass, aioclient_mock, device_info, device_state, **{CONF_KIOSK_PROVISIONED: True, CONF_KIOSK_URL: HA_URL, CONF_KIOSK_HOME_URL: HA_URL}
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_HOME: home}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_HOME: "invalid_home"}
    assert _kiosk_logins(aioclient_mock) == []


async def test_an_unchanged_entry_is_not_pushed_again(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    """A login for the URL Home Assistant would send now is not sent again."""
    await _setup(
        hass, aioclient_mock, device_info, device_state, **{CONF_KIOSK_PROVISIONED: True, CONF_KIOSK_URL: HA_URL, CONF_KIOSK_HOME_URL: HA_URL}
    )
    assert _kiosk_logins(aioclient_mock) == []


async def test_a_new_home_assistant_url_is_pushed_to_the_device(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    """Changing Home Assistant's URL in its own settings re-points the device.

    Nothing in the integration's options changes, so no reload happens; without
    this the device keeps opening the old URL until Home Assistant restarts.
    """
    await _setup(
        hass, aioclient_mock, device_info, device_state, **{CONF_KIOSK_PROVISIONED: True, CONF_KIOSK_URL: HA_URL, CONF_KIOSK_HOME_URL: HA_URL}
    )
    assert _kiosk_logins(aioclient_mock) == []

    await hass.config.async_update(internal_url="http://ha-new.example:8123")
    await hass.async_block_till_done()

    assert _pushed_urls(aioclient_mock) == [
        ("http://ha-new.example:8123", "http://ha-new.example:8123")
    ]


async def test_the_default_home_is_home_assistants_own_url(
    hass: HomeAssistant, dashboards: None
) -> None:
    assert home_url(hass, HA_URL, DEFAULT_HOME) == HA_URL


async def test_a_deleted_dashboard_falls_back_to_the_default(
    hass: HomeAssistant, dashboards: None
) -> None:
    """A dead link would leave the device on an error page; so would a tab of it."""
    assert home_url(hass, HA_URL, "dashboard-gone") == HA_URL
    assert home_url(hass, HA_URL, "dashboard-gone/lights") == HA_URL
    assert home_url(hass, HA_URL, "dashboard-kitchen") == f"{HA_URL}/dashboard-kitchen"


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
        hass, aioclient_mock, device_info, device_state, **{CONF_KIOSK_PROVISIONED: True, CONF_KIOSK_URL: HA_URL, CONF_KIOSK_HOME_URL: HA_URL}
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
            CONF_HOME: DEFAULT_HOME,
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
    # The device keeps the one copy of the list; a second one in the entry
    # could only drift from it.
    assert entry.options == {CONF_HOME: DEFAULT_HOME}


async def test_saving_only_the_home_leaves_the_pages_alone(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    entry = await _setup_with_pages(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_HOME: "dashboard-kitchen"}
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
        {CONF_HOME: DEFAULT_HOME, CONF_PAGES: [{"name": "Bad", "url": url}]},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PAGES: "invalid_url"}
    assert _page_writes(aioclient_mock) == []
