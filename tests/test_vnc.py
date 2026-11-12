"""VNC: a switch for remote access to the kiosk, and its auto-close timeout.

The password changes every session and must never reach the recorder's
history or a diagnostics download.
"""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.core import HomeAssistant

from custom_components.dashboard_assistant.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.dashboard_assistant.switch import VncSwitch

from .conftest import BASE, HOST, setup_device
from .test_commands import DEVICE_SLUG, last_request_json

SWITCH = f"switch.{DEVICE_SLUG}_vnc"
TIMEOUT = f"number.{DEVICE_SLUG}_vnc_timeout"

VNC_ON = {
    "on": True,
    "username": "dashboard",
    "password": "s3cretPassw0",
    "port": 5900,
    "timeout": 15,
    "closes_at": 1_800_000_000,
}


async def test_vnc_entities_when_off(
    hass: HomeAssistant, init_integration: Any
) -> None:
    switch = hass.states.get(SWITCH)
    assert switch is not None
    assert switch.state == "off"
    assert "password" not in switch.attributes

    timeout = hass.states.get(TIMEOUT)
    assert timeout is not None
    assert float(timeout.state) == 15


async def test_vnc_switch_shows_how_to_connect_when_on(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    state = copy.deepcopy(device_state)
    state["vnc"] = VNC_ON
    await setup_device(hass, aioclient_mock, device_info, state)

    switch = hass.states.get(SWITCH)
    assert switch.state == "on"
    assert switch.attributes["address"] == f"{HOST}:5900"
    assert switch.attributes["username"] == "dashboard"
    assert switch.attributes["password"] == "s3cretPassw0"
    assert switch.attributes["closes_at"] == "2027-01-15T08:00:00+00:00"


def test_vnc_password_stays_out_of_the_recorder() -> None:
    assert "password" in VncSwitch._unrecorded_attributes


async def test_no_vnc_entities_on_builds_without_it(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    info = copy.deepcopy(device_info)
    state = copy.deepcopy(device_state)
    info["has_vnc"] = False
    state.pop("vnc")
    await setup_device(hass, aioclient_mock, info, state)

    assert hass.states.get(SWITCH) is None
    assert hass.states.get(TIMEOUT) is None


async def test_vnc_entities_drive_daemon(
    hass: HomeAssistant, init_integration: Any, aioclient_mock: Any, device_state: Any
) -> None:
    aioclient_mock.post(f"{BASE}/vnc", json=device_state, headers={"Content-Type": "application/json"})

    await hass.services.async_call("switch", "turn_on", {"entity_id": SWITCH}, blocking=True)
    assert last_request_json(aioclient_mock) == {"on": True}

    await hass.services.async_call("switch", "turn_off", {"entity_id": SWITCH}, blocking=True)
    assert last_request_json(aioclient_mock) == {"on": False}

    await hass.services.async_call(
        "number", "set_value", {"entity_id": TIMEOUT, "value": 60}, blocking=True
    )
    assert last_request_json(aioclient_mock) == {"timeout": 60}


async def test_diagnostics_redact_the_vnc_password(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    state = copy.deepcopy(device_state)
    state["vnc"] = VNC_ON
    entry = await setup_device(hass, aioclient_mock, device_info, state)

    diag = await async_get_config_entry_diagnostics(hass, entry)
    assert diag["state"]["vnc"]["password"] == "**REDACTED**"
