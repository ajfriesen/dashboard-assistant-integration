"""Command round-trips: HA service calls become the right daemon requests."""

from __future__ import annotations

import json
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from .conftest import BASE, setup_device

DEVICE_SLUG = "dashboard_assistant_d7bbb4"


def last_request_json(aioclient_mock: Any) -> dict[str, Any]:
    """Decode the body of the most recent mocked request."""
    method, url, data, headers = aioclient_mock.mock_calls[-1]
    return json.loads(data) if isinstance(data, (str, bytes)) else dict(data)


async def test_sendspin_switch_drives_daemon(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any, device_state: Any
) -> None:
    aioclient_mock.post(f"{BASE}/sendspin", json=device_state, headers={"Content-Type": "application/json"})

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": f"switch.{DEVICE_SLUG}_sendspin_player"},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"on": False}

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": f"switch.{DEVICE_SLUG}_sendspin_player"},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"on": True}


async def test_screensaver_entities_drive_daemon(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any, device_state: Any
) -> None:
    aioclient_mock.post(f"{BASE}/screensaver", json=device_state, headers={"Content-Type": "application/json"})

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": f"switch.{DEVICE_SLUG}_screen_saver"},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"active": True}

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": f"switch.{DEVICE_SLUG}_screen_saver"},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"active": False}

    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": f"select.{DEVICE_SLUG}_screen_saver_style", "option": "logo"},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"name": "logo"}

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": f"number.{DEVICE_SLUG}_screen_saver_timeout", "value": 0},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"timeout": 0}


async def test_display_light_drives_daemon(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any, device_state: Any
) -> None:
    aioclient_mock.post(f"{BASE}/display", json=device_state, headers={"Content-Type": "application/json"})

    await hass.services.async_call(
        "light",
        "turn_off",
        {"entity_id": f"light.{DEVICE_SLUG}_display"},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"on": False}

    # Turning on with brightness sends both, power implied by the daemon.
    await hass.services.async_call(
        "light",
        "turn_on",
        {"entity_id": f"light.{DEVICE_SLUG}_display", "brightness": 255},
        blocking=True,
    )
    body = last_request_json(aioclient_mock)
    assert body["on"] is True
    assert body["brightness"] == 100


async def test_dark_mode_switch_drives_daemon(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any, device_state: Any
) -> None:
    aioclient_mock.post(f"{BASE}/theme", json=device_state, headers={"Content-Type": "application/json"})

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": f"switch.{DEVICE_SLUG}_dark_mode"},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"dark": True}


# --- recovery -----------------------------------------------------------------
#
# Recovery runs from Home Assistant, behind the device token: the device serves
# nothing unauthenticated that could roll it back or reset it.


async def test_roll_back_boots_the_generation_before_the_current_one(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any
) -> None:
    """The fixture device runs generation 6, so rolling back boots 5."""
    aioclient_mock.post(
        f"{BASE}/rollback",
        json={"status": "rebooting", "generation": 5},
        headers={"Content-Type": "application/json"},
    )

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": f"button.{DEVICE_SLUG}_roll_back"},
        blocking=True,
    )

    assert last_request_json(aioclient_mock) == {"generation": 5}


async def test_roll_back_refuses_with_nothing_to_go_back_to(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """A freshly flashed device has one generation, and no earlier one to boot.

    The button stays available, because available means the device answers;
    the press is refused with the reason, and nothing reaches the device.
    """
    device_state["generation_list"] = device_state["generation_list"][:1]
    device_state["generations"] = 1
    await setup_device(hass, aioclient_mock, device_info, device_state)
    entity_id = f"button.{DEVICE_SLUG}_roll_back"
    calls_before = len(aioclient_mock.mock_calls)

    assert hass.states.get(entity_id).state != "unavailable"
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "button", "press", {"entity_id": entity_id}, blocking=True
        )
    assert len(aioclient_mock.mock_calls) == calls_before


async def test_factory_reset_removes_the_entry(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any
) -> None:
    """A reset regenerates the device token, so the entry could never work again.

    Removing it is what lets discovery offer the device again once it is back
    on the network, where it pairs with no token typed.
    """
    aioclient_mock.post(
        f"{BASE}/reset",
        json={"status": "resetting"},
        headers={"Content-Type": "application/json"},
    )

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": f"button.{DEVICE_SLUG}_factory_reset"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert hass.config_entries.async_get_entry(init_integration.entry_id) is None
