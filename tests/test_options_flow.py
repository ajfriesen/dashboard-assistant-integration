"""The options flow: the device's pages, the first of which is its home.

Each page is a Home Assistant page, picked from its dashboards and their tabs,
or any website. The device starts on the first page and its Home button goes
back to it. The device keeps the one copy of the list, so the form starts from
what it reports and saving writes the list straight back to it.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
from homeassistant.components.frontend import DATA_PANELS
from homeassistant.components.lovelace.const import LOVELACE_DATA, ConfigNotFound
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dashboard_assistant.const import (
    CONF_CERT_FINGERPRINT,
    CONF_KIOSK_PROVISIONED,
    CONF_KIOSK_URL,
    CONF_KIOSK_USER_ID,
    CONF_PAGES,
    DOMAIN,
)

from .conftest import BASE, FINGERPRINT, HOST, PORT, TOKEN, mock_daemon

HA_URL = "http://ha.example:8123"
COMPONENT = Path(__file__).parent.parent / "custom_components" / "dashboard_assistant"


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


def _panel(url_path: str, title: str, config: dict[str, Any] | None, *, require_admin: bool = False) -> Any:
    """A sidebar panel as the frontend keeps it."""
    return SimpleNamespace(
        frontend_url_path=url_path,
        sidebar_title=title,
        config=config,
        require_admin=require_admin,
    )


@pytest.fixture
def apps(hass: HomeAssistant) -> None:
    """Sidebar panels: two apps a non-admin may open (registered the current
    and the older way), an admin-only app, and a panel that is no app."""
    hass.data.setdefault(DATA_PANELS, {}).update(
        {
            "d5369777_music_assistant": _panel(
                "d5369777_music_assistant", "Music Assistant", {"addon": "d5369777_music_assistant"}
            ),
            "a0d7b954_vscode": _panel(
                "a0d7b954_vscode", "Studio Code Server", {"addon": "a0d7b954_vscode"}, require_admin=True
            ),
            "ccab4aaf_frigate": _panel("ccab4aaf_frigate", "Frigate", {"ingress": "ccab4aaf_frigate"}),
            "energy": _panel("energy", "Energy", None),
        }
    )


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
    kiosk_group: str = GROUP_ID_USER,
) -> MockConfigEntry:
    """Set up an entry whose device already holds a login for ``kiosk_url``,
    as a user in ``kiosk_group``."""
    # The first user Home Assistant creates is its owner, and so an admin; a
    # real one always has its owner already.
    await hass.auth.async_create_user("Owner")
    user = await hass.auth.async_create_user("Dashboard Assistant", group_ids=[kiosk_group])
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
            CONF_KIOSK_USER_ID: user.id,
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


async def test_apps_the_kiosk_can_open_are_listed_after_the_dashboards(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
    apps: None,
) -> None:
    """An app's sidebar panel, such as Music Assistant's, is a Home Assistant
    page too; an admin-only one is left out, like an admin-only dashboard."""
    entry = await _setup(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    options = result["data_schema"].schema[CONF_PAGES].config["fields"]["ha_page"][
        "selector"
    ]["select"]["options"]
    assert [(o["value"], o["label"]) for o in options][-2:] == [
        ("ccab4aaf_frigate", "Frigate"),
        ("d5369777_music_assistant", "Music Assistant"),
    ]
    assert "a0d7b954_vscode" not in [o["value"] for o in options]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_PAGES: [{"ha_page": "d5369777_music_assistant"}]}
    )
    await hass.async_block_till_done()
    assert _page_writes(aioclient_mock) == [
        [{"name": "Music Assistant", "url": f"{HA_URL}/d5369777_music_assistant"}]
    ]


async def test_an_admin_kiosk_user_is_offered_admin_only_dashboards_and_apps(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
    dashboards: None,
    apps: None,
) -> None:
    """The owner may make the device's user an admin; it can then open them."""
    entry = await _setup(
        hass, aioclient_mock, device_info, device_state, kiosk_group=GROUP_ID_ADMIN
    )

    result = await hass.config_entries.options.async_init(entry.entry_id)

    values = [
        o["value"]
        for o in result["data_schema"].schema[CONF_PAGES].config["fields"]["ha_page"][
            "selector"
        ]["select"]["options"]
    ]
    assert {"dashboard-admin", "dashboard-admin/x", "a0d7b954_vscode"} <= set(values)
    assert "energy" not in values


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
    ("page", "error", "message"),
    [
        (
            {"name": "Files", "url": "ftp://files.lan"},
            "invalid_url",
            "“Files”: a website needs a full address starting with http:// or https://.",
        ),
        (
            {"url": "homeassistant.local:8123"},
            "invalid_url",
            "“Page 2”: a website needs a full address starting with http:// or https://.",
        ),
        (
            {"name": "Neither"},
            "page_has_neither",
            "“Neither” has no Home Assistant page and no website. Pick one, or remove the page.",
        ),
        (
            {"name": "Both", "ha_page": "default", "url": "https://www.windy.com"},
            "page_has_both",
            "“Both” has a Home Assistant page and a website. A page shows one of them, so clear the other.",
        ),
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
    message: str,
) -> None:
    """The message names the page and says what is wrong with it, so the user
    knows which entry to open. An unnamed page is named by its position.

    The device would refuse a bad address too; saying so here keeps the user
    in the form.
    """
    entry = await _setup(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_PAGES: [{"name": "Fine", "url": "https://www.windy.com"}, page]},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_PAGES: error}
    assert _render_error(error, result["description_placeholders"]) == message
    assert _page_writes(aioclient_mock) == []


def _render_error(key: str, placeholders: dict[str, str] | None) -> str:
    """The error as Home Assistant shows it, from both translation sources.

    strings.json and translations/en.json must agree: Home Assistant serves
    the latter, and a key missing there is shown raw.
    """
    texts = [
        json.loads((COMPONENT / name).read_text())["options"]["error"][key]
        for name in ("strings.json", "translations/en.json")
    ]
    assert texts[0] == texts[1]
    return texts[0].format(**(placeholders or {}))


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
