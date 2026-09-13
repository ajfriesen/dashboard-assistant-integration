"""Command round-trips: HA service calls become the right daemon requests."""

from __future__ import annotations

import json
from typing import Any

from homeassistant.core import HomeAssistant

from .conftest import BASE

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
