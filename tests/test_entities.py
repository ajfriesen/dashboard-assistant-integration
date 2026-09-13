"""Entity creation and gating: capabilities decide which entities exist.

Guards against the class of regression where a conditional entity silently
stops being provided (the Sendspin switch and Filesystem sensor have both
been lost to exactly that).
"""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.core import HomeAssistant

from .conftest import setup_device

DEVICE_SLUG = "dashboard_assistant_d7bbb4"


async def test_conditional_entities_present(
    hass: HomeAssistant, init_integration: Any
) -> None:
    """A btrfs + Sendspin device gets its conditional entities."""
    fs = hass.states.get(f"binary_sensor.{DEVICE_SLUG}_filesystem")
    assert fs is not None
    # problem-class sensor: off means healthy (fixture has ok: true)
    assert fs.state == "off"
    assert fs.attributes["corruption_errors"] == 0
    assert fs.attributes["readonly"] is False

    sendspin = hass.states.get(f"switch.{DEVICE_SLUG}_sendspin_player")
    assert sendspin is not None
    assert sendspin.state == "on"
    assert sendspin.attributes.get("status") == "active"


async def test_core_entities_present(
    hass: HomeAssistant, init_integration: Any, device_state: dict[str, Any]
) -> None:
    """Unconditional entities exist and mirror the snapshot."""
    dark = hass.states.get(f"switch.{DEVICE_SLUG}_dark_mode")
    assert dark is not None

    display = hass.states.get(f"light.{DEVICE_SLUG}_display")
    assert display is not None
    assert display.state == "on" if device_state["display"]["on"] else "off"

    update = hass.states.get(f"update.{DEVICE_SLUG}_system_update")
    assert update is not None
    assert (
        update.attributes["installed_version"]
        == device_state["update"]["installed_version"]
    )


async def test_absent_capabilities_create_no_entities(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """An ext4 device without battery/Sendspin gets none of those entities."""
    info = copy.deepcopy(device_info)
    state = copy.deepcopy(device_state)
    info["has_btrfs"] = False
    info["has_battery"] = False
    info["has_sendspin"] = False
    state["btrfs"] = {"present": False}
    state["battery"]["present"] = False
    state.pop("sendspin", None)

    await setup_device(hass, aioclient_mock, info, state)

    assert hass.states.get(f"binary_sensor.{DEVICE_SLUG}_filesystem") is None
    assert hass.states.get(f"switch.{DEVICE_SLUG}_sendspin_player") is None
    assert hass.states.get(f"binary_sensor.{DEVICE_SLUG}_battery_charging") is None
    # core entities are unaffected
    assert hass.states.get(f"switch.{DEVICE_SLUG}_dark_mode") is not None


async def test_old_daemon_without_btrfs_key(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """A pre-btrfs daemon (no key at all) must not crash entity setup."""
    info = copy.deepcopy(device_info)
    state = copy.deepcopy(device_state)
    info.pop("has_btrfs", None)
    state.pop("btrfs", None)

    entry = await setup_device(hass, aioclient_mock, info, state)

    assert entry.state.value == "loaded"
    assert hass.states.get(f"binary_sensor.{DEVICE_SLUG}_filesystem") is None


async def test_filesystem_sensor_reports_problem(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """Nonzero error counters flip the problem sensor on."""
    state = copy.deepcopy(device_state)
    state["btrfs"].update(ok=False, corruption_errs=3)

    await setup_device(hass, aioclient_mock, device_info, state)

    fs = hass.states.get(f"binary_sensor.{DEVICE_SLUG}_filesystem")
    assert fs is not None
    assert fs.state == "on"
    assert fs.attributes["corruption_errors"] == 3
