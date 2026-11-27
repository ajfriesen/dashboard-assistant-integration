"""After an OS update, Home Assistant catches up with the device on its own.

The integration reads the device's version and capabilities once, at setup.
An OS update changes both while Home Assistant keeps running, so without a
reload it went on showing the old version and none of the new entities (seen
updating a device from 1.2.0 to 1.3.1: no Button bar switch until Home
Assistant was restarted).
"""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.dashboard_assistant.const import DOMAIN

from .conftest import BASE, mock_daemon, setup_device

DEVICE_SLUG = "dashboard_assistant_d7bbb4"


def at_version(info, state, version):
    info, state = copy.deepcopy(info), copy.deepcopy(state)
    info["version"] = version
    state["update"]["installed_version"] = version
    return info, state


def info_requests(aioclient_mock) -> int:
    return sum(
        1 for _, url, _, _ in aioclient_mock.mock_calls if str(url) == f"{BASE}/info"
    )


async def test_an_os_update_brings_in_the_new_version_and_entities(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    old_info, old_state = at_version(device_info, device_state, "1.2.0")
    old_state.pop("bar", None)  # 1.2.0 cannot hide its bar
    entry = await setup_device(hass, aioclient_mock, old_info, old_state)
    assert hass.states.get(f"switch.{DEVICE_SLUG}_button_bar") is None

    # The device updates itself; the daemon comes back on the new release.
    new_info, new_state = at_version(device_info, device_state, "1.3.1")
    aioclient_mock.clear_requests()
    mock_daemon(aioclient_mock, new_info, new_state)
    entry.runtime_data.async_set_updated_data(new_state)
    await hass.async_block_till_done()

    assert hass.states.get(f"switch.{DEVICE_SLUG}_button_bar") is not None
    device = dr.async_get(hass).async_get_device({(DOMAIN, device_info["node_id"])})
    assert device.sw_version == "1.3.1"


async def test_snapshots_from_the_same_release_do_not_reload(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    info, state = at_version(device_info, device_state, "1.3.1")
    entry = await setup_device(hass, aioclient_mock, info, state)
    before = info_requests(aioclient_mock)

    entry.runtime_data.async_set_updated_data(copy.deepcopy(state))
    await hass.async_block_till_done()

    assert info_requests(aioclient_mock) == before


async def test_a_daemon_that_reports_no_version_does_not_reload(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """An OS build from before update checks sends no update block at all."""
    info, state = at_version(device_info, device_state, "1.3.1")
    state.pop("update")
    entry = await setup_device(hass, aioclient_mock, info, state)
    before = info_requests(aioclient_mock)

    entry.runtime_data.async_set_updated_data(copy.deepcopy(state))
    await hass.async_block_till_done()

    assert info_requests(aioclient_mock) == before


async def test_versions_that_keep_disagreeing_reload_only_once(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """A live update that leaves the daemon running: its release checker still
    reports the version it started with, while the device info reads the new
    one. Reloading cannot settle that, so it must not repeat."""
    info, _ = at_version(device_info, device_state, "1.3.1")
    _, state = at_version(device_info, device_state, "1.2.0")
    entry = await setup_device(hass, aioclient_mock, info, state)
    for _ in range(3):
        entry.runtime_data.async_set_updated_data(copy.deepcopy(state))
        await hass.async_block_till_done()

    assert info_requests(aioclient_mock) <= 2  # setup, and one reload
