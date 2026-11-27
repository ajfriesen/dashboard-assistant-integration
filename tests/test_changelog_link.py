"""The update dialog links to the changelog, not to one release's page.

A release's notes list only what changed since the tag before it, promoted or
not. Updating 1.2.0 -> 1.3.1 skipped the never-promoted 1.3.0, so the 1.3.1
page left out everything 1.3.0 changed. The changelog at the offered tag lists
every release up to it, newest first.
"""

from __future__ import annotations

import copy
from typing import Any

from homeassistant.core import HomeAssistant

from .conftest import setup_device

UPDATE = "update.dashboard_assistant_d7bbb4_system_update"


def on_120(info):
    return {**info, "version": "1.2.0"}


def offering(state, latest, url=None):
    state = copy.deepcopy(state)
    state["update"].update(installed_version="1.2.0", latest_version=latest)
    if url:
        state["update"]["release_url"] = url
    return state


async def test_the_link_is_the_changelog_at_the_offered_release(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    state = offering(
        device_state,
        "1.3.1",
        "https://github.com/ajfriesen/DashboardAssistant/releases/tag/v1.3.1",
    )
    await setup_device(hass, aioclient_mock, on_120(device_info), state)

    assert hass.states.get(UPDATE).attributes["release_url"] == (
        "https://github.com/ajfriesen/DashboardAssistant/blob/v1.3.1/CHANGELOG.md"
    )


async def test_a_device_with_another_release_source_links_to_its_changelog(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    state = offering(
        device_state, "2.0.0", "https://github.com/someone/fork/releases/tag/v2.0.0"
    )
    await setup_device(hass, aioclient_mock, on_120(device_info), state)

    assert hass.states.get(UPDATE).attributes["release_url"] == (
        "https://github.com/someone/fork/blob/v2.0.0/CHANGELOG.md"
    )


async def test_a_device_that_sends_no_link_still_gets_the_changelog(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    await setup_device(
        hass, aioclient_mock, on_120(device_info), offering(device_state, "1.3.1")
    )

    assert hass.states.get(UPDATE).attributes["release_url"] == (
        "https://github.com/ajfriesen/DashboardAssistant/blob/v1.3.1/CHANGELOG.md"
    )


async def test_a_link_that_is_not_a_github_release_is_kept(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> None:
    state = offering(device_state, "1.3.1", "https://example.org/releases/1.3.1")
    await setup_device(hass, aioclient_mock, on_120(device_info), state)

    assert (
        hass.states.get(UPDATE).attributes["release_url"]
        == "https://example.org/releases/1.3.1"
    )
