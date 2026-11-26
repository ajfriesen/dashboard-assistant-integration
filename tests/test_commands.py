"""Command round-trips: HA service calls become the right daemon requests."""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest
from homeassistant.auth.const import GROUP_ID_ADMIN, GROUP_ID_USER
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.dashboard_assistant.const import CONF_KIOSK_USER_ID

from .conftest import BASE, setup_device

DEVICE_SLUG = "dashboard_assistant_d7bbb4"


def last_request_json(aioclient_mock: Any) -> dict[str, Any]:
    """Decode the body of the most recent mocked request."""
    method, url, data, headers = aioclient_mock.mock_calls[-1]
    return json.loads(data) if isinstance(data, (str, bytes)) else dict(data)


async def test_sendspin_switch_drives_daemon(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any, device_state: Any
) -> None:
    aioclient_mock.post(
        f"{BASE}/sendspin",
        json=device_state,
        headers={"Content-Type": "application/json"},
    )

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
    aioclient_mock.post(
        f"{BASE}/screensaver",
        json=device_state,
        headers={"Content-Type": "application/json"},
    )

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

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": f"number.{DEVICE_SLUG}_screen_saver_brightness", "value": 20},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"brightness": 20}


async def test_display_light_drives_daemon(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any, device_state: Any
) -> None:
    aioclient_mock.post(
        f"{BASE}/display",
        json=device_state,
        headers={"Content-Type": "application/json"},
    )

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


async def test_audio_output_select_drives_daemon(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any, device_state: Any
) -> None:
    """The select shows descriptions and sends the sink's node name."""
    aioclient_mock.post(
        f"{BASE}/audio", json=device_state, headers={"Content-Type": "application/json"}
    )

    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": f"select.{DEVICE_SLUG}_audio_output",
            "option": "USB Audio Analog Stereo",
        },
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {
        "output": "alsa_output.usb-Generic_USB_Audio-00.analog-stereo"
    }


async def test_audio_input_select_drives_daemon(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any, device_state: Any
) -> None:
    """The input select sends the source's node name as "input"."""
    aioclient_mock.post(
        f"{BASE}/audio", json=device_state, headers={"Content-Type": "application/json"}
    )

    await hass.services.async_call(
        "select",
        "select_option",
        {
            "entity_id": f"select.{DEVICE_SLUG}_audio_input",
            "option": "ReSpeaker 4 Mic Array",
        },
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {
        "input": "alsa_input.usb-Seeed_ReSpeaker-00.multichannel-input"
    }


async def test_dark_mode_switch_drives_daemon(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any, device_state: Any
) -> None:
    aioclient_mock.post(
        f"{BASE}/theme", json=device_state, headers={"Content-Type": "application/json"}
    )

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": f"switch.{DEVICE_SLUG}_dark_mode"},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"dark": True}


async def test_button_bar_switch_drives_daemon(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any, device_state: Any
) -> None:
    aioclient_mock.post(
        f"{BASE}/bar", json=device_state, headers={"Content-Type": "application/json"}
    )

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": f"switch.{DEVICE_SLUG}_button_bar"},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"visible": False}

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": f"switch.{DEVICE_SLUG}_button_bar"},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"visible": True}


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


async def _setup_with_charge(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> dict[str, Any]:
    state = copy.deepcopy(device_state)
    state["battery"] = {
        "present": True,
        "level": 77,
        "charging": False,
        "charge_start": 40,
        "charge_end": 80,
    }
    await setup_device(hass, aioclient_mock, device_info, state)
    return state


async def test_charge_numbers_drive_daemon(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    state = await _setup_with_charge(hass, aioclient_mock, device_info, device_state)
    # The device answers with what the battery accepted, which a driver may
    # have adjusted (Dell raises a start of 20 to 50).
    accepted = copy.deepcopy(state)
    accepted["battery"]["charge_start"] = 50
    aioclient_mock.post(
        f"{BASE}/battery",
        json=accepted,
        headers={"Content-Type": "application/json"},
    )

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": f"number.{DEVICE_SLUG}_charge_start", "value": 20},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"charge_start": 20}
    assert float(hass.states.get(f"number.{DEVICE_SLUG}_charge_start").state) == 50

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": f"number.{DEVICE_SLUG}_charge_stop", "value": 90},
        blocking=True,
    )
    assert last_request_json(aioclient_mock) == {"charge_end": 90}


async def test_a_start_not_below_the_stop_is_refused_with_a_reason(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    await _setup_with_charge(hass, aioclient_mock, device_info, device_state)
    aioclient_mock.post(
        f"{BASE}/battery",
        status=400,
        text='{"error":"charging has to start below where it stops"}',
    )

    with pytest.raises(ServiceValidationError) as err:
        await hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": f"number.{DEVICE_SLUG}_charge_start", "value": 90},
            blocking=True,
        )
    assert err.value.translation_key == "charge_rejected"


# --- reloading the page ------------------------------------------------------


async def test_reload_button_drives_daemon(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any
) -> None:
    aioclient_mock.post(
        f"{BASE}/reload",
        json={"status": "reloading"},
        headers={"Content-Type": "application/json"},
    )

    await hass.services.async_call(
        "button",
        "press",
        {"entity_id": f"button.{DEVICE_SLUG}_reload_page"},
        blocking=True,
    )

    assert [str(c[1]) for c in aioclient_mock.mock_calls][-1] == f"{BASE}/reload"


def _reloads(aioclient_mock: Any) -> int:
    return sum(1 for c in aioclient_mock.mock_calls if str(c[1]) == f"{BASE}/reload")


async def _kiosk_user(hass: HomeAssistant, entry: Any) -> Any:
    """The device's Home Assistant user, as provisioning records it.

    A real Home Assistant has its owner already; without one the first user
    created becomes the owner, and an owner is always an admin.
    """
    if not any(u.is_owner for u in await hass.auth.async_get_users()):
        await hass.auth.async_create_user("Owner")
    user = await hass.auth.async_create_user("Dashboard Assistant (d7bbb4)")
    hass.config_entries.async_update_entry(
        entry, data={**entry.data, CONF_KIOSK_USER_ID: user.id}
    )
    return user


async def test_making_the_device_user_an_admin_reloads_the_page(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any
) -> None:
    """Home Assistant's frontend reads the user once, when it loads, so the
    admin parts only show after a reload."""
    aioclient_mock.post(
        f"{BASE}/reload",
        json={"status": "reloading"},
        headers={"Content-Type": "application/json"},
    )
    user = await _kiosk_user(hass, init_integration)

    await hass.auth.async_update_user(user, group_ids=[GROUP_ID_ADMIN])
    await hass.async_block_till_done()
    assert _reloads(aioclient_mock) == 1

    # A change that leaves the admin flag alone does not reload.
    await hass.auth.async_update_user(user, name="Hallway")
    await hass.async_block_till_done()
    assert _reloads(aioclient_mock) == 1

    # Taking it away reloads too, so the admin parts go.
    await hass.auth.async_update_user(user, group_ids=[GROUP_ID_USER])
    await hass.async_block_till_done()
    assert _reloads(aioclient_mock) == 2


async def test_another_users_admin_change_does_not_reload(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any
) -> None:
    await _kiosk_user(hass, init_integration)
    other = await hass.auth.async_create_user("Someone else")

    await hass.auth.async_update_user(other, group_ids=[GROUP_ID_ADMIN])
    await hass.async_block_till_done()

    assert _reloads(aioclient_mock) == 0


async def test_an_os_without_reload_is_not_asked_to(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    info = {k: v for k, v in device_info.items() if k != "can_reload"}
    entry = await setup_device(hass, aioclient_mock, info, device_state)
    user = await _kiosk_user(hass, entry)

    await hass.auth.async_update_user(user, group_ids=[GROUP_ID_ADMIN])
    await hass.async_block_till_done()

    assert _reloads(aioclient_mock) == 0
    assert hass.states.get(f"button.{DEVICE_SLUG}_reload_page") is None
