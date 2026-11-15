"""The options menu, and its region form: the device's timezone and language.

The device keeps the one copy, so the form starts from what it reports and
saving writes straight back to it. A language change restarts the kiosk on the
device, so only what the user changed is sent. A device whose OS has no region
yet reports none, and its options go straight to its pages.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.dashboard_assistant.const import CONF_LOCALE, CONF_TIMEZONE

from .conftest import BASE
from .test_options_flow import _setup

DEVICE_REGION = {"timezone": "UTC", "locale": "en-US"}


@pytest.fixture
def region_state(device_state: dict[str, Any]) -> dict[str, Any]:
    """A device on an OS with a region, still on its defaults."""
    return {**device_state, "region": dict(DEVICE_REGION)}


def _region_writes(aioclient_mock: Any) -> list[dict[str, str]]:
    return [
        json.loads(data) if isinstance(data, (str, bytes)) else dict(data)
        for method, url, data, _ in aioclient_mock.mock_calls
        if method == "POST" and str(url).endswith("/region")
    ]


def _mock_region(aioclient_mock: Any, state: dict[str, Any], region: dict[str, str]) -> None:
    aioclient_mock.post(
        f"{BASE}/region",
        json={**state, "region": region},
        headers={"Content-Type": "application/json"},
    )


async def _open_region(hass: HomeAssistant, entry: Any) -> dict[str, Any]:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "region"}
    )


def _default(result: dict[str, Any], field: str) -> Any:
    return next(k for k in result["data_schema"].schema if k == field).default()


async def test_an_older_device_goes_straight_to_its_pages(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    entry = await _setup(hass, aioclient_mock, device_info, device_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "pages"


async def test_a_device_with_a_region_offers_a_menu(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    entry = await _setup(hass, aioclient_mock, device_info, region_state)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["pages", "region"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "pages"}
    )
    assert result["step_id"] == "pages"


async def test_the_region_form_starts_from_the_device(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    """The device's en-US is shown as Home Assistant's closest language, and
    Home Assistant's own settings are named for comparison."""
    await hass.config.async_update(time_zone="Europe/Berlin", language="de")
    entry = await _setup(hass, aioclient_mock, device_info, region_state)

    result = await _open_region(hass, entry)

    assert result["step_id"] == "region"
    assert _default(result, CONF_TIMEZONE) == "UTC"
    assert _default(result, CONF_LOCALE) == "en"
    assert result["description_placeholders"] == {
        "ha_timezone": "Europe/Berlin",
        "ha_language": "de",
    }
    timezones = result["data_schema"].schema[CONF_TIMEZONE].config["options"]
    assert "Europe/Berlin" in timezones and "UTC" in timezones
    assert "EST5EDT" not in timezones


async def test_saving_an_unchanged_region_writes_nothing(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    """Above all, the language shown as en must not go back as a change from
    en-US: that would restart the kiosk for nothing."""
    entry = await _setup(hass, aioclient_mock, device_info, region_state)

    result = await _open_region(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TIMEZONE: "UTC", CONF_LOCALE: "en"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _region_writes(aioclient_mock) == []


async def test_a_new_timezone_keeps_the_device_locale(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    wanted = {"timezone": "Europe/Berlin", "locale": "en-US"}
    _mock_region(aioclient_mock, region_state, wanted)

    result = await _open_region(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TIMEZONE: "Europe/Berlin", CONF_LOCALE: "en"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _region_writes(aioclient_mock) == [wanted]
    # The device's answer is the new state at once, not on the next poll; and
    # nothing is kept in the entry, which could only drift from the device.
    assert entry.runtime_data.data["region"] == wanted
    assert entry.options == {}


async def test_a_new_language_is_sent(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    _mock_region(aioclient_mock, region_state, {"timezone": "UTC", "locale": "de"})

    result = await _open_region(hass, entry)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TIMEZONE: "UTC", CONF_LOCALE: "de"}
    )

    assert _region_writes(aioclient_mock) == [{"timezone": "UTC", "locale": "de"}]


async def test_an_unreachable_device_keeps_the_form_and_the_choice(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    aioclient_mock.post(f"{BASE}/region", status=500)

    result = await _open_region(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TIMEZONE: "Europe/Berlin", CONF_LOCALE: "de"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert _default(result, CONF_TIMEZONE) == "Europe/Berlin"
    assert _default(result, CONF_LOCALE) == "de"
