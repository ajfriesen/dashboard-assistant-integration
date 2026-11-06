"""Config flow: a device is added from discovery, and pairs with no token typed."""

from __future__ import annotations

from collections.abc import Iterator
from ipaddress import ip_address
from typing import Any
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dashboard_assistant.api import DashboardAssistantConnectionError
from custom_components.dashboard_assistant.const import CONF_CERT_FINGERPRINT, DOMAIN

from .conftest import (
    BASE,
    DISCOVERY_BASE,
    DISCOVERY_PORT,
    FINGERPRINT,
    HOST,
    PORT,
    TOKEN,
)

FETCH_FINGERPRINT = "custom_components.dashboard_assistant.config_flow.async_fetch_fingerprint"


@pytest.fixture
def fetch_fingerprint() -> Iterator[AsyncMock]:
    """The TLS handshake that reads the device's certificate, which the mock
    HTTP layer cannot do."""
    with patch(FETCH_FINGERPRINT, AsyncMock(return_value=FINGERPRINT)) as fetch:
        yield fetch


def _discovery() -> ZeroconfServiceInfo:
    """A zeroconf announcement shaped like the daemon's avahi service file."""
    return ZeroconfServiceInfo(
        ip_address=ip_address(HOST),
        ip_addresses=[ip_address(HOST)],
        hostname="dashboard-assistant-d7bbb4.local.",
        name="Dashboard Assistant on d7bbb4._dashboard-assistant._tcp.local.",
        port=DISCOVERY_PORT,
        type="_dashboard-assistant._tcp.local.",
        properties={},
    )


def _mock_device(
    aioclient_mock: Any, device_info: dict[str, Any], *, tls_port: int | None = PORT
) -> None:
    """A device on the network: identify in the clear, the rest over TLS."""
    ident = {"node_id": device_info["node_id"], "name": device_info["name"]}
    if tls_port:
        ident["tls_port"] = tls_port
    aioclient_mock.get(
        f"{DISCOVERY_BASE}/identify",
        json=ident,
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.post(
        f"{BASE}/pair",
        json={"token": "paired-token", "node_id": device_info["node_id"]},
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.get(
        f"{BASE}/info", json=device_info, headers={"Content-Type": "application/json"}
    )


async def _discover(hass: HomeAssistant) -> dict[str, Any]:
    return await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=_discovery()
    )


async def test_adding_by_hand_points_to_discovery(hass: HomeAssistant) -> None:
    """A device is only ever added from discovery, which pairs it with no token.

    Add integration has nothing to ask for: the token never leaves the device
    except through pairing, so there is nothing a user could type.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )

    assert result["type"] == "abort"
    assert result["reason"] == "discovery_only"


async def test_discovery_asks_to_confirm_the_device(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    fetch_fingerprint: AsyncMock,
) -> None:
    _mock_device(aioclient_mock, device_info)

    result = await _discover(hass)

    assert result["type"] == "form"
    assert result["step_id"] == "zeroconf_confirm"
    assert result["data_schema"].schema == {}


async def test_confirming_pairs_over_tls_without_typing_a_token(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    fetch_fingerprint: AsyncMock,
) -> None:
    """The token is fetched, never typed, and never crosses the network in the clear."""
    _mock_device(aioclient_mock, device_info)

    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == "create_entry"
    assert result["result"].unique_id == device_info["node_id"]
    assert result["data"][CONF_TOKEN] == "paired-token"
    assert result["data"][CONF_PORT] == PORT
    assert result["data"][CONF_CERT_FINGERPRINT] == FINGERPRINT
    pair_calls = [c for c in aioclient_mock.mock_calls if str(c[1]).endswith("/pair")]
    assert [str(c[1]) for c in pair_calls] == [f"{BASE}/pair"]


async def test_confirming_pins_the_certificate_the_device_has_now(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    fetch_fingerprint: AsyncMock,
) -> None:
    """A card left waiting must not pair against a certificate that has changed.

    Home Assistant discovered the bench device, then it was factory-reset, which
    gives it a new certificate; every Retry on the old card failed the pin
    before any request reached the device. The certificate is read again when
    the user confirms, which is the moment trust is actually given.
    """
    _mock_device(aioclient_mock, device_info)
    fetch_fingerprint.side_effect = ["b" * 64, FINGERPRINT]

    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == "create_entry"
    assert result["data"][CONF_CERT_FINGERPRINT] == FINGERPRINT


async def test_a_device_without_tls_is_not_offered(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    fetch_fingerprint: AsyncMock,
) -> None:
    """Pairing hands over the device token, which is never sent in the clear."""
    _mock_device(aioclient_mock, device_info, tls_port=None)

    result = await _discover(hass)

    assert result["type"] == "abort"
    assert result["reason"] == "tls_required"


async def test_a_device_whose_certificate_cannot_be_read_is_not_offered(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    fetch_fingerprint: AsyncMock,
) -> None:
    _mock_device(aioclient_mock, device_info)
    fetch_fingerprint.side_effect = DashboardAssistantConnectionError("refused")

    result = await _discover(hass)

    assert result["type"] == "abort"
    assert result["reason"] == "cannot_connect"


async def test_discovery_aborts_when_identify_fails(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """An unreachable device aborts rather than falling back to an address key.

    An address-keyed flow would not de-duplicate against the node-id one, so the
    user would get a spurious second card for the same device.
    """
    aioclient_mock.get(f"{DISCOVERY_BASE}/identify", exc=aiohttp.ClientError("boom"))

    result = await _discover(hass)

    assert result["type"] == "abort"
    assert result["reason"] == "cannot_connect"


async def test_a_paired_device_is_not_offered_again(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    init_integration: Any,
    fetch_fingerprint: AsyncMock,
) -> None:
    """Rediscovering a configured device updates its address, with no new card."""
    _mock_device(aioclient_mock, device_info)

    result = await _discover(hass)

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


async def test_pairing_reports_a_closed_window(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    fetch_fingerprint: AsyncMock,
) -> None:
    """An already-paired device refuses, and the form says so specifically."""
    aioclient_mock.get(
        f"{DISCOVERY_BASE}/identify",
        json={"node_id": device_info["node_id"], "tls_port": PORT},
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.post(f"{BASE}/pair", status=403)

    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == "form"
    assert result["errors"] == {"base": "pairing_closed"}


async def test_certificate_mismatch_is_reported_as_itself(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    fetch_fingerprint: AsyncMock,
) -> None:
    """A changed certificate must not read as "device offline".

    ServerFingerprintMismatch subclasses ClientError, so without explicit
    handling this surfaces as a generic connection failure and the user goes
    looking for a network fault.
    """
    aioclient_mock.get(
        f"{DISCOVERY_BASE}/identify",
        json={"node_id": device_info["node_id"], "tls_port": PORT},
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.post(
        f"{BASE}/pair",
        exc=aiohttp.ServerFingerprintMismatch(b"expected", b"got", HOST, PORT),
    )

    result = await _discover(hass)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cert_mismatch"}


# --- after a factory reset ----------------------------------------------------
#
# A reset regenerates the device's token and certificate. Nobody can type the
# new token (it never leaves the device except through pairing), so the entry
# stops with an error instead of asking for one: deleting it lets discovery
# offer the device again, and it pairs.


async def _setup_against(
    hass: HomeAssistant, aioclient_mock: Any, info_mock: dict[str, Any]
) -> MockConfigEntry:
    aioclient_mock.get(f"{BASE}/info", **info_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="da_555d31459f86",
        data={
            CONF_HOST: HOST,
            CONF_PORT: PORT,
            CONF_TOKEN: TOKEN,
            CONF_CERT_FINGERPRINT: FINGERPRINT,
        },
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_a_rejected_token_stops_the_entry_without_asking_for_one(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    entry = await _setup_against(hass, aioclient_mock, {"status": 401})

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert hass.config_entries.flow.async_progress() == []


async def test_a_changed_certificate_stops_the_entry_without_asking_for_a_token(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    entry = await _setup_against(
        hass,
        aioclient_mock,
        {"exc": aiohttp.ServerFingerprintMismatch(b"expected", b"got", HOST, PORT)},
    )

    assert entry.state is ConfigEntryState.SETUP_ERROR
    assert hass.config_entries.flow.async_progress() == []
