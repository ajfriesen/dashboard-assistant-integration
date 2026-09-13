"""Shared fixtures: a fake daemon behind aioclient_mock, fed by real payloads.

The JSON in fixtures/ was captured from a live device (`/api/ha/state` and
`/api/ha/info` of a btrfs-root Pi 5 with Sendspin), so entity tests exercise
the exact shapes the daemon serves rather than hand-rolled approximations.
Refresh them by re-capturing from a device when the daemon's payload grows.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dashboard_assistant.const import (
    CONF_KIOSK_PROVISIONED,
    DOMAIN,
)

FIXTURES = Path(__file__).parent / "fixtures"

HOST = "192.0.2.10"
PORT = 8081
TOKEN = "test-token"
BASE = f"http://{HOST}:{PORT}/api/ha"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Allow loading the custom integration from custom_components/."""
    return


def load_fixture_json(name: str) -> dict[str, Any]:
    """Parse a JSON payload from tests/fixtures."""
    return json.loads((FIXTURES / name).read_text())


@pytest.fixture
def device_info() -> dict[str, Any]:
    """The /api/ha/info payload (capability flags)."""
    return load_fixture_json("info.json")


@pytest.fixture
def device_state() -> dict[str, Any]:
    """The /api/ha/state payload (full snapshot)."""
    return load_fixture_json("state.json")


def mock_daemon(
    aioclient_mock: Any, info: dict[str, Any], state: dict[str, Any]
) -> None:
    """Wire the fake daemon endpoints the integration touches during setup.

    The SSE endpoint answers 401 so the coordinator's stream loop exits
    cleanly (auth errors end the loop; anything else would retry forever and
    leave a lingering background task in the test).
    """
    aioclient_mock.get(f"{BASE}/info", json=info, headers={"Content-Type": "application/json"})
    aioclient_mock.get(f"{BASE}/state", json=state, headers={"Content-Type": "application/json"})
    aioclient_mock.get(f"{BASE}/events", status=401)


async def setup_device(
    hass: HomeAssistant,
    aioclient_mock: Any,
    info: dict[str, Any],
    state: dict[str, Any],
) -> MockConfigEntry:
    """Set up a config entry against the fake daemon and settle HA."""
    mock_daemon(aioclient_mock, info, state)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=info.get("name") or "Dashboard Assistant",
        unique_id=info["node_id"],
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_TOKEN: TOKEN,
            # Skip the kiosk-login provisioning path — it talks to HA's auth
            # internals and is out of scope for entity/command tests.
            CONF_KIOSK_PROVISIONED: True,
        },
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    device_state: dict[str, Any],
) -> MockConfigEntry:
    """A fully set up integration against the captured device payloads."""
    return await setup_device(hass, aioclient_mock, device_info, device_state)
