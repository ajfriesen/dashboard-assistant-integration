"""The options menu, and its region form: the device's timezone and language.

The device keeps the one copy, so the form starts from what it reports and
saving writes straight back to it, even unchanged: the device restarts the kiosk
only when the language changes, and an unchanged save is how a timezone it
failed to apply gets applied again. A device whose OS has no region yet reports
none, and its options go straight to its pages.
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
    """The device's en-US is shown as it is, and Home Assistant's own settings
    are named for comparison."""
    await hass.config.async_update(time_zone="Europe/Berlin", language="de")
    entry = await _setup(hass, aioclient_mock, device_info, region_state)

    result = await _open_region(hass, entry)

    assert result["step_id"] == "region"
    assert _default(result, CONF_TIMEZONE) == "UTC"
    assert _default(result, CONF_LOCALE) == "en-US"
    assert "en-US" in result["data_schema"].schema[CONF_LOCALE].config["languages"]
    assert result["description_placeholders"] == {
        "ha_timezone": "Europe/Berlin",
        "ha_language": "de",
    }
    timezones = result["data_schema"].schema[CONF_TIMEZONE].config["options"]
    assert "Europe/Berlin" in timezones and "UTC" in timezones
    assert "EST5EDT" not in timezones


async def test_saving_an_unchanged_region_sends_it_again(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    """The device may report a timezone it failed to apply (timedated down at
    boot); saving the form unchanged is how the user repairs it. The device
    itself skips the kiosk restart when the language is the same."""
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    _mock_region(aioclient_mock, region_state, DEVICE_REGION)

    result = await _open_region(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TIMEZONE: "UTC", CONF_LOCALE: "en-US"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _region_writes(aioclient_mock) == [DEVICE_REGION]


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
        result["flow_id"], {CONF_TIMEZONE: "Europe/Berlin", CONF_LOCALE: "en-US"}
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


async def test_plain_english_can_replace_a_regional_locale(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    _mock_region(aioclient_mock, region_state, {"timezone": "UTC", "locale": "en"})

    result = await _open_region(hass, entry)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TIMEZONE: "UTC", CONF_LOCALE: "en"}
    )

    assert _region_writes(aioclient_mock) == [{"timezone": "UTC", "locale": "en"}]


async def test_a_retry_sends_the_language_again(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    """After a failed save, submitting the same choice again sends it again."""
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    aioclient_mock.post(f"{BASE}/region", status=500)
    choice = {CONF_TIMEZONE: "Europe/Berlin", CONF_LOCALE: "de"}

    result = await _open_region(hass, entry)
    result = await hass.config_entries.options.async_configure(result["flow_id"], choice)
    await hass.config_entries.options.async_configure(result["flow_id"], choice)

    assert _region_writes(aioclient_mock) == [
        {"timezone": "Europe/Berlin", "locale": "de"}
    ] * 2


async def test_a_legacy_timezone_on_the_device_is_offered(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    """A device on EST5EDT can still save a language-only change."""
    region_state["region"] = {"timezone": "EST5EDT", "locale": "en-US"}
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    wanted = {"timezone": "EST5EDT", "locale": "de"}
    _mock_region(aioclient_mock, region_state, wanted)

    result = await _open_region(hass, entry)
    assert "EST5EDT" in result["data_schema"].schema[CONF_TIMEZONE].config["options"]
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TIMEZONE: "EST5EDT", CONF_LOCALE: "de"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert _region_writes(aioclient_mock) == [wanted]


async def test_extra_region_fields_are_not_sent_back(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    region_state["region"] = {**DEVICE_REGION, "keyboard": "us"}
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    _mock_region(aioclient_mock, region_state, region_state["region"])

    result = await _open_region(hass, entry)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TIMEZONE: "UTC", CONF_LOCALE: "en-US"}
    )

    assert _region_writes(aioclient_mock) == [DEVICE_REGION]


async def test_a_refused_region_says_so(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    aioclient_mock.post(f"{BASE}/region", status=400, text="unsupported locale")

    result = await _open_region(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TIMEZONE: "UTC", CONF_LOCALE: "zh-Hans"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "region_rejected"}


async def test_a_missing_route_is_not_a_refused_region(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    """Only the device's 400 means the choice is wrong; a 404 (a proxy, an OS
    rolled back) or a 429 must not tell the user to pick another."""
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    aioclient_mock.post(f"{BASE}/region", status=404, text="404 page not found")

    result = await _open_region(hass, entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TIMEZONE: "Europe/Berlin", CONF_LOCALE: "en-US"}
    )

    assert result["errors"] == {"base": "cannot_connect"}


async def test_pages_after_the_device_unloads_aborts(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    """The entry unloaded (device dropped, reload) while the menu was open."""
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    await hass.config_entries.async_unload(entry.entry_id)

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "pages"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "device_unavailable"


async def test_a_partial_answer_does_not_replace_the_state(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    aioclient_mock.post(
        f"{BASE}/region", json={"ok": True}, headers={"Content-Type": "application/json"}
    )

    result = await _open_region(hass, entry)
    await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TIMEZONE: "Europe/Berlin", CONF_LOCALE: "en-US"}
    )

    assert "device" in entry.runtime_data.data


async def test_a_region_that_disappears_aborts(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    region_state: dict[str, Any],
) -> None:
    """The device rolled back to an OS without a region while the menu was open."""
    entry = await _setup(hass, aioclient_mock, device_info, region_state)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    entry.runtime_data.async_set_updated_data(
        {k: v for k, v in region_state.items() if k != "region"}
    )

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "region"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "region_unavailable"


async def test_a_null_region_goes_straight_to_the_pages(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    entry = await _setup(hass, aioclient_mock, device_info, {**device_state, "region": None})

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["step_id"] == "pages"
