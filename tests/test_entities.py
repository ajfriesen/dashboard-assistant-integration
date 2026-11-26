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

    saver = hass.states.get(f"switch.{DEVICE_SLUG}_screen_saver")
    assert saver is not None
    assert saver.state == "off"

    style = hass.states.get(f"select.{DEVICE_SLUG}_screen_saver_style")
    assert style is not None
    assert style.state == "clock"
    assert style.attributes["options"] == ["clock", "logo"]

    timeout = hass.states.get(f"number.{DEVICE_SLUG}_screen_saver_timeout")
    assert timeout is not None
    assert float(timeout.state) == 10

    dim = hass.states.get(f"number.{DEVICE_SLUG}_screen_saver_brightness")
    assert dim is not None
    assert float(dim.state) == 15
    assert dim.attributes["unit_of_measurement"] == "%"
    assert dim.attributes["min"] == 0
    assert dim.attributes["max"] == 100

    audio = hass.states.get(f"select.{DEVICE_SLUG}_audio_output")
    assert audio is not None
    assert audio.state == "Built-in Audio HDMI"
    assert audio.attributes["options"] == [
        "Built-in Audio HDMI",
        "USB Audio Analog Stereo",
    ]

    mic = hass.states.get(f"select.{DEVICE_SLUG}_audio_input")
    assert mic is not None
    assert mic.state == "USB Audio Mono"
    assert mic.attributes["options"] == ["USB Audio Mono", "ReSpeaker 4 Mic Array"]

    bar = hass.states.get(f"switch.{DEVICE_SLUG}_button_bar")
    assert bar is not None
    assert bar.state == "on"


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
    state.pop("screensaver", None)  # an OS build from before screen savers
    state.pop("audio", None)  # no audio stack, or an OS build before the select
    state.pop("bar", None)  # an OS build that cannot hide its bar

    await setup_device(hass, aioclient_mock, info, state)

    assert hass.states.get(f"binary_sensor.{DEVICE_SLUG}_filesystem") is None
    assert hass.states.get(f"switch.{DEVICE_SLUG}_sendspin_player") is None
    assert hass.states.get(f"binary_sensor.{DEVICE_SLUG}_battery_charging") is None
    assert hass.states.get(f"switch.{DEVICE_SLUG}_screen_saver") is None
    assert hass.states.get(f"select.{DEVICE_SLUG}_screen_saver_style") is None
    assert hass.states.get(f"number.{DEVICE_SLUG}_screen_saver_timeout") is None
    assert hass.states.get(f"number.{DEVICE_SLUG}_screen_saver_brightness") is None
    assert hass.states.get(f"select.{DEVICE_SLUG}_audio_output") is None
    assert hass.states.get(f"select.{DEVICE_SLUG}_audio_input") is None
    assert hass.states.get(f"switch.{DEVICE_SLUG}_button_bar") is None
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


async def test_old_daemon_without_battery_key(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """A daemon reporting no battery block must not crash entity setup."""
    info = copy.deepcopy(device_info)
    state = copy.deepcopy(device_state)
    info.pop("has_battery", None)
    state.pop("battery", None)

    entry = await setup_device(hass, aioclient_mock, info, state)

    assert entry.state.value == "loaded"
    assert hass.states.get(f"sensor.{DEVICE_SLUG}_battery") is None
    assert hass.states.get(f"binary_sensor.{DEVICE_SLUG}_battery_charging") is None
    # the rest of both platforms still came up
    assert hass.states.get(f"sensor.{DEVICE_SLUG}_cpu_usage") is not None
    assert hass.states.get(f"binary_sensor.{DEVICE_SLUG}_filesystem") is not None


async def test_old_daemon_without_temperature_key(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """A daemon reporting no temperature block must not crash sensor setup."""
    info = copy.deepcopy(device_info)
    state = copy.deepcopy(device_state)
    info.pop("has_temperature", None)
    state.pop("temperature", None)

    entry = await setup_device(hass, aioclient_mock, info, state)

    assert entry.state.value == "loaded"
    assert hass.states.get(f"sensor.{DEVICE_SLUG}_temperature") is None
    assert hass.states.get(f"sensor.{DEVICE_SLUG}_cpu_usage") is not None


async def test_old_daemon_without_update_key(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """No update block: the update entity is added unconditionally, so this is
    the gate that would take a whole platform down rather than skip one entity."""
    state = copy.deepcopy(device_state)
    state.pop("update", None)

    entry = await setup_device(hass, aioclient_mock, device_info, state)

    assert entry.state.value == "loaded"
    # the entity still exists, just without a version or an Install button
    update = hass.states.get(f"update.{DEVICE_SLUG}_system_update")
    assert update is not None
    assert update.attributes.get("installed_version") is None
    # and the version picker it gates is absent
    assert hass.states.get(f"select.{DEVICE_SLUG}_target_version") is None
    # sibling entities on the same platforms are unaffected
    assert hass.states.get(f"select.{DEVICE_SLUG}_page") is not None


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


async def test_swap_sensors_tell_zram_from_the_swap_file(
    hass: HomeAssistant, init_integration: Any
) -> None:
    """zram fills first, so the swap file's use is how often RAM ran out.

    Kept in Home Assistant's history, these answer whether a 2 GB board ever
    writes swap to flash, and whether the browser was killed for memory.
    """
    expected = {
        "zram_used": "249",
        "swap_file_used": "16",
        "swapped_out": "250",
        "oom_kills": "0",
    }
    for key, value in expected.items():
        state = hass.states.get(f"sensor.{DEVICE_SLUG}_{key}")
        assert state is not None, key
        assert state.state == value, (key, state.state)


async def test_audio_output_labels_stay_unique(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """Two sinks with the same description (two identical USB DACs) stay
    tellable apart: the node name goes after the label."""
    state = copy.deepcopy(device_state)
    state["audio"]["output"] = {
        "current": "alsa_output.usb-a",
        "options": [
            {"name": "alsa_output.usb-a", "description": "USB Audio"},
            {"name": "alsa_output.usb-b", "description": "USB Audio"},
        ],
    }

    await setup_device(hass, aioclient_mock, device_info, state)

    audio = hass.states.get(f"select.{DEVICE_SLUG}_audio_output")
    assert audio.attributes["options"] == [
        "USB Audio (alsa_output.usb-a)",
        "USB Audio (alsa_output.usb-b)",
    ]
    assert audio.state == "USB Audio (alsa_output.usb-a)"


async def test_audio_input_unavailable_without_microphone(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """No microphone plugged in: the select still exists (so it fills in when
    one is), but is unavailable rather than an empty dropdown."""
    state = copy.deepcopy(device_state)
    state["audio"]["input"] = {"current": "", "options": []}

    await setup_device(hass, aioclient_mock, device_info, state)

    mic = hass.states.get(f"select.{DEVICE_SLUG}_audio_input")
    assert mic is not None
    assert mic.state == "unavailable"
    assert hass.states.get(f"select.{DEVICE_SLUG}_audio_output").state != "unavailable"


async def test_os_without_screen_saver_brightness(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """An OS from before the screen saver had its own brightness: the other
    screen saver entities, but no brightness number."""
    state = copy.deepcopy(device_state)
    del state["screensaver"]["brightness"]

    await setup_device(hass, aioclient_mock, device_info, state)

    assert hass.states.get(f"number.{DEVICE_SLUG}_screen_saver_timeout") is not None
    assert hass.states.get(f"number.{DEVICE_SLUG}_screen_saver_brightness") is None


def _with_charge(device_state: dict[str, Any], **thresholds: int) -> dict[str, Any]:
    state = copy.deepcopy(device_state)
    state["battery"] = {"present": True, "level": 77, "charging": False, **thresholds}
    return state


async def test_charge_numbers_show_what_the_battery_holds(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    state = _with_charge(device_state, charge_start=40, charge_end=80)

    await setup_device(hass, aioclient_mock, device_info, state)

    start = hass.states.get(f"number.{DEVICE_SLUG}_charge_start")
    stop = hass.states.get(f"number.{DEVICE_SLUG}_charge_stop")
    assert start is not None and float(start.state) == 40
    assert stop is not None and float(stop.state) == 80
    assert stop.attributes["min"] == 0 and stop.attributes["max"] == 100


async def test_a_battery_with_only_a_stop_threshold_gets_only_charge_stop(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    """asus-wmi has an end threshold only."""
    state = _with_charge(device_state, charge_end=100)

    await setup_device(hass, aioclient_mock, device_info, state)

    assert hass.states.get(f"number.{DEVICE_SLUG}_charge_start") is None
    assert hass.states.get(f"number.{DEVICE_SLUG}_charge_stop") is not None


async def test_no_charge_numbers_without_thresholds(
    hass: HomeAssistant, init_integration: Any
) -> None:
    """A Pi, a mini-PC, or an OS from before the thresholds."""
    assert hass.states.get(f"number.{DEVICE_SLUG}_charge_start") is None
    assert hass.states.get(f"number.{DEVICE_SLUG}_charge_stop") is None
