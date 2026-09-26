"""Config flow: manual entry validates against the device and dedupes."""

from __future__ import annotations

import aiohttp

from ipaddress import ip_address
from typing import Any
from unittest.mock import patch

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from custom_components.dashboard_assistant.api import pin_for, scheme_for
from custom_components.dashboard_assistant.const import CONF_CERT_FINGERPRINT, DOMAIN

from .conftest import BASE, HOST, PORT, TOKEN

USER_INPUT = {CONF_HOST: HOST, CONF_PORT: PORT, CONF_TOKEN: TOKEN}


async def test_user_flow_creates_entry(
    hass: HomeAssistant, aioclient_mock: Any, device_info: dict[str, Any]
) -> None:
    # The user step probes identify to find out whether the device offers TLS.
    # This one answers without a tls_port, i.e. a device predating TLS.
    aioclient_mock.get(f"{BASE}/identify", json={"node_id": device_info["node_id"]})
    aioclient_mock.get(f"{BASE}/info", json=device_info, headers={"Content-Type": "application/json"})

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == "form"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] == "create_entry"
    assert result["title"] == device_info["name"]
    assert {k: v for k, v in result["data"].items() if k in USER_INPUT} == USER_INPUT
    # a device without TLS records no pin
    assert result["data"][CONF_CERT_FINGERPRINT] is None
    assert result["result"].unique_id == device_info["node_id"]


async def test_user_flow_bad_token(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    aioclient_mock.get(f"{BASE}/identify", exc=aiohttp.ClientError("no identify"))
    aioclient_mock.get(f"{BASE}/info", status=401)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_unreachable(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
    aioclient_mock.get(f"{BASE}/identify", exc=aiohttp.ClientError("boom"))
    aioclient_mock.get(f"{BASE}/info", exc=aiohttp.ClientError("boom"))

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] == "form"
    assert result["errors"] == {"base": "cannot_connect"}


async def test_duplicate_device_aborts(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    init_integration: Any,
) -> None:
    """A second flow for an already-configured node_id aborts."""
    aioclient_mock.get(f"{BASE}/identify", json={"node_id": device_info["node_id"]})
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"


# --- discovery, pairing and reauth -------------------------------------------
#
# These paths carried no coverage at all, which is awkward given they are where
# the token is obtained and where a device's identity is re-established after a
# factory reset.


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


async def test_zeroconf_offers_pair_or_manual(
    hass: HomeAssistant, aioclient_mock: Any, device_info: dict[str, Any]
) -> None:
    """Discovery identifies the device and offers the two ways in."""
    aioclient_mock.get(
        f"{BASE}/identify",
        json={"node_id": device_info["node_id"], "name": device_info["name"]},
        headers={"Content-Type": "application/json"},
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=_discovery()
    )

    assert result["type"] == "menu"
    assert set(result["menu_options"]) == {"pair", "manual"}


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
        result["flow_id"], {"next_step_id": "pair"}
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
        result["flow_id"], {"next_step_id": "pair"}
    )

    assert result["type"] == "form"
    assert result["errors"] == {"base": "pairing_closed"}


async def test_manual_entry_after_discovery(
    hass: HomeAssistant, aioclient_mock: Any, device_info: dict[str, Any]
) -> None:
    """The fallback path when pairing is not available."""
    aioclient_mock.get(
        f"{BASE}/identify",
        json={"node_id": device_info["node_id"], "name": device_info["name"]},
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.get(
        f"{BASE}/info", json=device_info, headers={"Content-Type": "application/json"}
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "zeroconf"}, data=_discovery()
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "manual"}
    )
    assert result["type"] == "form"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: TOKEN}
    )
    assert result["type"] == "create_entry"
    assert result["data"][CONF_TOKEN] == TOKEN


async def test_reauth_updates_the_token(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    init_integration: Any,
) -> None:
    """A factory reset regenerates the token; reauth is how the entry recovers."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE}/info", json=device_info, headers={"Content-Type": "application/json"}
    )

    result = await init_integration.start_reauth_flow(hass)
    assert result["type"] == "form"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "regenerated-token"}
    )

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert init_integration.data[CONF_TOKEN] == "regenerated-token"


async def test_reauth_rejects_a_different_device(
    hass: HomeAssistant,
    aioclient_mock: Any,
    device_info: dict[str, Any],
    init_integration: Any,
) -> None:
    """Reauth against a device with another node_id must not silently re-point."""
    other = dict(device_info, node_id="da_someotherdevice")
    aioclient_mock.clear_requests()
    aioclient_mock.get(
        f"{BASE}/info", json=other, headers={"Content-Type": "application/json"}
    )

    result = await init_integration.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TOKEN: "some-token"}
    )

    assert result["type"] == "abort"
    assert result["reason"] == "wrong_device"


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
            result["flow_id"], {"next_step_id": "pair"}
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
        result["flow_id"], {"next_step_id": "pair"}
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
            result["flow_id"], {"next_step_id": "pair"}
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


async def test_manual_host_entry_upgrades_to_tls(
    hass: HomeAssistant, aioclient_mock: Any, device_info: dict[str, Any]
) -> None:
    """Typing a host by hand must not silently opt out of encryption.

    The user step has no discovery, so it probes identify itself; without that a
    hand-added device would stay cleartext forever.
    """
    aioclient_mock.get(
        f"{BASE}/identify",
        json={"node_id": device_info["node_id"], "tls_port": TLS_PORT},
        headers={"Content-Type": "application/json"},
    )
    aioclient_mock.get(
        f"{TLS_BASE}/info",
        json=device_info,
        headers={"Content-Type": "application/json"},
    )

    with patch(
        "custom_components.dashboard_assistant.config_flow.async_fetch_fingerprint",
        return_value=FINGERPRINT,
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], USER_INPUT
        )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_CERT_FINGERPRINT] == FINGERPRINT
    assert result["data"][CONF_PORT] == TLS_PORT
