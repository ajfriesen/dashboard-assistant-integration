"""Config flow: a device is added from discovery, and pairs with no token typed."""

from __future__ import annotations

import aiohttp

from ipaddress import ip_address
from typing import Any
from unittest.mock import patch

from homeassistant.const import CONF_PORT, CONF_TOKEN
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.dashboard_assistant.api import pin_for, scheme_for
from custom_components.dashboard_assistant.const import CONF_CERT_FINGERPRINT, DOMAIN

from .conftest import BASE, HOST, PORT

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


async def test_a_paired_device_is_not_offered_again(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    init_integration: Any,
) -> None:
    """Rediscovering a configured device updates its address, with no new card."""
    aioclient_mock.get(
        f"{BASE}/identify",
        json={"node_id": device_info["node_id"], "name": device_info["name"]},
        headers={"Content-Type": "application/json"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=_discovery()
    )

    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


# --- discovery and pairing ------------------------------------------------------


def _discovery(host: str = HOST, port: int = PORT) -> ZeroconfServiceInfo:
    """A zeroconf announcement shaped like the daemon's avahi service file."""
    return ZeroconfServiceInfo(
        ip_address=ip_address(host),
        ip_addresses=[ip_address(host)],
        hostname="dashboard-assistant-d7bbb4.local.",
        name="Dashboard Assistant on d7bbb4._dashboard-assistant._tcp.local.",
        port=port,
        type="_dashboard-assistant._tcp.local.",
        properties={},
    )


async def test_discovery_asks_to_confirm_the_device(
    hass: HomeAssistant, aioclient_mock: Any, device_info: dict[str, Any]
) -> None:
    """Discovery identifies the device and asks only to confirm adding it."""
    aioclient_mock.get(
        f"{BASE}/identify",
        json={"node_id": device_info["node_id"], "name": device_info["name"]},
        headers={"Content-Type": "application/json"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=_discovery()
    )

    assert result["type"] == "form"
    assert result["step_id"] == "zeroconf_confirm"
    assert result["data_schema"].schema == {}


async def test_zeroconf_aborts_when_identify_fails(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    """An unreachable device aborts rather than falling back to an address key.

    An address-keyed flow would not de-duplicate against the node-id one, so the
    user would get a spurious second card for the same device.
    """
    aioclient_mock.get(f"{BASE}/identify", exc=aiohttp.ClientError("boom"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=_discovery()
    )

    assert result["type"] == "abort"
    assert result["reason"] == "cannot_connect"


async def test_pair_creates_entry_without_typing_a_token(
    hass: HomeAssistant, aioclient_mock: Any, device_info: dict[str, Any]
) -> None:
    """The whole point of pairing: the token is fetched, never typed."""
    aioclient_mock.get(
        f"{BASE}/identify",
        json={"node_id": device_info["node_id"], "name": device_info["name"]},
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

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=_discovery()
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_TOKEN] == "paired-token"
    assert result["result"].unique_id == device_info["node_id"]


async def test_pair_reports_a_closed_window(
    hass: HomeAssistant, aioclient_mock: Any, device_info: dict[str, Any]
) -> None:
    """An already-paired device refuses, and the form says so specifically."""
    aioclient_mock.get(
        f"{BASE}/identify",
        json={"node_id": device_info["node_id"], "name": device_info["name"]},
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.post(f"{BASE}/pair", status=403)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=_discovery()
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "pairing_closed"}


# --- TLS -----------------------------------------------------------------------

TLS_PORT = 8443
FINGERPRINT = "a" * 64
TLS_BASE = f"https://{HOST}:{TLS_PORT}/api/ha"


def _tls_discovery_mocks(aioclient_mock: Any, device_info: dict[str, Any]) -> None:
    """A device that advertises TLS on identify, and answers over it."""
    aioclient_mock.get(
        f"{BASE}/identify",
        json={
            "node_id": device_info["node_id"],
            "name": device_info["name"],
            "tls_port": TLS_PORT,
            "version": device_info["version"],
        },
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.post(
        f"{TLS_BASE}/pair",
        json={"token": "paired-token", "node_id": device_info["node_id"]},
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.get(
        f"{TLS_BASE}/info",
        json=device_info,
        headers={"Content-Type": "application/json"},
    )


async def test_pairing_upgrades_to_tls_and_pins(
    hass: HomeAssistant, aioclient_mock: Any, device_info: dict[str, Any]
) -> None:
    """A device advertising tls_port is paired over TLS, and the pin is stored.

    The point of the whole exercise: the pair response and the kiosk login that
    follows it must not cross the network in the clear.
    """
    _tls_discovery_mocks(aioclient_mock, device_info)

    with patch(
        "custom_components.dashboard_assistant.config_flow.async_fetch_fingerprint",
        return_value=FINGERPRINT,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "zeroconf"}, data=_discovery()
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {}
        )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_CERT_FINGERPRINT] == FINGERPRINT
    assert result["data"][CONF_PORT] == TLS_PORT
    # and the traffic actually went to the TLS endpoint
    assert any(str(call[1]).startswith(TLS_BASE) for call in aioclient_mock.mock_calls)


async def test_device_without_tls_stays_cleartext(
    hass: HomeAssistant, aioclient_mock: Any, device_info: dict[str, Any]
) -> None:
    """A device that predates TLS still pairs, with no pin recorded.

    The integration and the OS update independently, so this skew is normal and
    must not be a setup failure.
    """
    aioclient_mock.get(
        f"{BASE}/identify",
        json={"node_id": device_info["node_id"], "name": device_info["name"]},
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.post(
        f"{BASE}/pair",
        json={"token": "paired-token"},
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.get(
        f"{BASE}/info", json=device_info, headers={"Content-Type": "application/json"}
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=_discovery()
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {}
    )

    assert result["type"] == "create_entry"
    assert result["data"].get(CONF_CERT_FINGERPRINT) is None


async def test_certificate_mismatch_is_reported_as_itself(
    hass: HomeAssistant, aioclient_mock: Any, device_info: dict[str, Any]
) -> None:
    """A changed certificate must not read as "device offline".

    ServerFingerprintMismatch subclasses ClientError, so without explicit
    handling this surfaces as a generic connection failure and the user goes
    looking for a network fault.
    """
    _tls_discovery_mocks(aioclient_mock, device_info)
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE}/identify",
        json={
            "node_id": device_info["node_id"],
            "name": device_info["name"],
            "tls_port": TLS_PORT,
        },
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.post(
        f"{TLS_BASE}/pair",
        json={"token": "paired-token"},
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.get(
        f"{TLS_BASE}/info",
        exc=aiohttp.ServerFingerprintMismatch(b"expected", b"got", HOST, TLS_PORT),
    )

    with patch(
        "custom_components.dashboard_assistant.config_flow.async_fetch_fingerprint",
        return_value=FINGERPRINT,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "zeroconf"}, data=_discovery()
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {}
        )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "cert_mismatch"}


def test_pin_helpers_pick_scheme_and_fingerprint() -> None:
    """The mock drops ``ssl``, so the pin argument is asserted directly here."""
    assert scheme_for(None) == "http"
    assert scheme_for(FINGERPRINT) == "https"
    assert pin_for(None) is False
    pin = pin_for(FINGERPRINT)
    assert isinstance(pin, aiohttp.Fingerprint)
    assert pin.fingerprint == bytes.fromhex(FINGERPRINT)


# --- after a factory reset ----------------------------------------------------
#
# A reset regenerates the device's token and certificate. Nobody can type the
# new token (it never leaves the device except through pairing), so the entry
# stops with an error instead of asking for one: deleting it lets discovery
# offer the device again, and it pairs.


async def _setup_against(
    hass: HomeAssistant, aioclient_mock: Any, info_mock: dict[str, Any]
) -> Any:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from .conftest import TOKEN

    aioclient_mock.get(f"{BASE}/info", **info_mock)
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="da_555d31459f86",
        data={"host": HOST, CONF_PORT: PORT, CONF_TOKEN: TOKEN},
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
