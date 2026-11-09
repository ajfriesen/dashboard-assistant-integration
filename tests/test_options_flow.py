"""The options flow: the device's pages, the first of which is its home.

Each page is a Home Assistant page, picked from its dashboards and their tabs,
or any website. The device starts on the first page and its Home button goes
back to it. The device keeps the one copy of the list, so the form starts from
what it reports and saving writes the list straight back to it.
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
    CONF_KIOSK_PROVISIONED,
    CONF_KIOSK_URL,
    CONF_PAGES,
    DOMAIN,
)

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
    """Home Assistant's dashboard registry: the default one plus three more.

    The default one is the built-in Overview with two tabs; Kitchen has two
    tabs, one without a path, which Home Assistant then addresses by position.
    """
    hass.data[LOVELACE_DATA] = SimpleNamespace(
        dashboards={
            None: _dashboard(
                None,
                "Overview",
                views=[{"title": "Home", "path": "home"}, {"title": "Energy", "path": "energy"}],
            ),
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


def _with_pages(state: dict[str, Any], pages: list[dict[str, str]]) -> dict[str, Any]:
    return {**state, "page": {**state["page"], "list": pages}}


def _kiosk_logins(aioclient_mock: Any) -> list[dict[str, Any]]:
    return [
        json.loads(data) if isinstance(data, (str, bytes)) else dict(data)
        for method, url, data, _ in aioclient_mock.mock_calls
        if method == "POST" and str(url).endswith("/kiosk_login")
    ]


def _page_writes(aioclient_mock: Any) -> list[list[dict[str, str]]]:
    return [
        (json.loads(data) if isinstance(data, (str, bytes)) else dict(data))["pages"]
        for method, url, data, _ in aioclient_mock.mock_calls
        if method == "POST" and str(url).endswith("/pages")
    ]


async def _setup(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    kiosk_url: str | None = HA_URL,
) -> MockConfigEntry:
    """Set up an entry whose device already holds a login for ``kiosk_url``."""
    mock_daemon(aioclient_mock, device_info, device_state)
    aioclient_mock.post(
        f"{BASE}/kiosk_login",
        json={"applied": ["token"]},
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.post(
        f"{BASE}/pages", json=device_state, headers={"Content-Type": "application/json"}
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        minor_version=3,
        unique_id=device_info["node_id"],
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_TOKEN: TOKEN,
            CONF_CERT_FINGERPRINT: FINGERPRINT,
            CONF_KIOSK_PROVISIONED: True,
            CONF_KIOSK_URL: kiosk_url,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


def _pages_field(result: dict[str, Any]) -> Any:
    return next(k for k in result["data_schema"].schema if k == CONF_PAGES)


async def test_the_form_has_only_pages(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    """The first page is the home, so there is no separate field for it."""
    entry = await _setup(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert list(result["data_schema"].schema) == [CONF_PAGES]


async def test_a_page_is_picked_from_the_dashboards_and_tabs_the_kiosk_can_open(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    """Home Assistant's default, the Overview's tabs, then every dashboard a
    non-admin user can open, each followed by its tabs; or a website.

    The kiosk signs in as a non-admin user, so an admin-only dashboard would
    only ever show it an error. A dashboard without saved tabs (one Home
    Assistant generates) is offered whole.
    """
    entry = await _setup(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    fields = result["data_schema"].schema[CONF_PAGES].config["fields"]
    assert list(fields) == ["name", "ha_page", "url"]
    options = fields["ha_page"]["selector"]["select"]["options"]
    assert [(o["value"], o["label"]) for o in options] == [
        ("default", "Home Assistant default"),
        ("lovelace/home", "Overview › Home"),
        ("lovelace/energy", "Overview › Energy"),
        ("dashboard-auto", "Auto"),
        ("dashboard-kitchen", "Kitchen"),
        ("dashboard-kitchen/lights", "Kitchen › Lights"),
        ("dashboard-kitchen/1", "Kitchen › Climate"),
    ]
    assert fields["url"]["selector"]["text"]["type"] == "url"


async def test_the_form_shows_home_assistant_pages_as_their_dropdown_entry(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    """The device keeps URLs; the form turns those it recognises back into
    the entries they were picked from, and shows the rest as websites."""
    state = _with_pages(
        device_state,
        [
            {"name": "Lights", "url": f"{HA_URL}/dashboard-kitchen/lights"},
            {"name": "Weather", "url": "https://www.windy.com"},
            {"name": "Home Assistant", "url": f"{HA_URL}/"},
            {"name": "Energy panel", "url": f"{HA_URL}/energy"},
        ],
    )
    entry = await _setup(hass, aioclient_mock, device_info, state)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert _pages_field(result).default() == [
        {"name": "Lights", "ha_page": "dashboard-kitchen/lights"},
        {"name": "Weather", "url": "https://www.windy.com"},
        {"name": "Home Assistant", "ha_page": "default"},
        {"name": "Energy panel", "url": f"{HA_URL}/energy"},
    ]


async def test_saving_sends_the_pages_as_urls_in_order(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    """A Home Assistant page becomes its URL, named after it unless named."""
    entry = await _setup(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_PAGES: [
                {"ha_page": "dashboard-kitchen/lights"},
                {"name": "Weather | Windy", "url": " https://www.windy.com "},
                {"name": "Overview", "ha_page": "default"},
                {"url": "http://nvr.lan/live"},
            ],
        },
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _page_writes(aioclient_mock) == [
        [
            {"name": "Kitchen › Lights", "url": f"{HA_URL}/dashboard-kitchen/lights"},
            {"name": "Weather | Windy", "url": "https://www.windy.com"},
            {"name": "Overview", "url": HA_URL},
            {"name": "", "url": "http://nvr.lan/live"},
        ]
    ]
    # The device keeps the one copy of the list; a second one in the entry
    # could only drift from it.
    assert entry.options == {}


async def test_saving_unchanged_pages_writes_nothing(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    entry = await _setup(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PAGES: _pages_field(result).default()}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _page_writes(aioclient_mock) == []


@pytest.mark.parametrize(
    ("page", "error"),
    [
        ({"name": "Bad", "url": "ftp://files.lan"}, "invalid_url"),
        ({"name": "Bad", "url": "homeassistant.local:8123"}, "invalid_url"),
        ({"name": "Bad", "url": "https://"}, "invalid_url"),
        ({"name": "Neither"}, "page_needs_one"),
        ({"name": "Both", "ha_page": "default", "url": "https://www.windy.com"}, "page_needs_one"),
    ],
)
async def test_a_page_that_is_not_one_page_is_refused_in_the_form(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
    page: dict[str, str],
    error: str,
) -> None:
    """The device would refuse a bad address too; saying so here keeps the
    user in the form."""
    entry = await _setup(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PAGES: [page]}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PAGES: error}
    assert _page_writes(aioclient_mock) == []


async def test_the_login_carries_home_assistants_own_url(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    """Whatever the pages are: the device signs in there and nowhere else."""
    state = _with_pages(
        device_state, [{"name": "Lights", "url": f"{HA_URL}/dashboard-kitchen/lights"}]
    )
    await _setup(hass, aioclient_mock, device_info, state, kiosk_url=None)

    assert [login.get("ha_url") for login in _kiosk_logins(aioclient_mock)] == [HA_URL]
    assert "home_url" not in _kiosk_logins(aioclient_mock)[0]


async def test_an_unchanged_login_is_not_pushed_again(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
) -> None:
    await _setup(hass, aioclient_mock, device_info, device_state)
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
    this the device keeps signing in on the old URL until Home Assistant restarts.
    """
    await _setup(hass, aioclient_mock, device_info, device_state)
    assert _kiosk_logins(aioclient_mock) == []

    await hass.config.async_update(internal_url="http://ha-new.example:8123")
    await hass.async_block_till_done()

    assert [login["ha_url"] for login in _kiosk_logins(aioclient_mock)] == [
        "http://ha-new.example:8123"
    ]


@pytest.mark.parametrize(
    ("first", "pushed"),
    [
        # An older device starts at, and goes Home to, the login's URL, so it
        # gets the first page when that is a Home Assistant page...
        (f"{HA_URL}/dashboard-kitchen/lights", f"{HA_URL}/dashboard-kitchen/lights"),
        # ...and Home Assistant's own URL otherwise: it must never sign in
        # anywhere else.
        ("https://www.windy.com", HA_URL),
    ],
)
async def test_an_older_device_gets_its_first_page_as_the_login_url(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
    first: str,
    pushed: str,
) -> None:
    """Until its OS is updated, a device without home_is_first_page keeps
    starting on the page the user put first."""
    info = {k: v for k, v in device_info.items() if k != "home_is_first_page"}
    state = _with_pages(device_state, [{"name": "First", "url": first}])

    await _setup(hass, aioclient_mock, info, state, kiosk_url=None)

    assert [login["ha_url"] for login in _kiosk_logins(aioclient_mock)] == [pushed]
