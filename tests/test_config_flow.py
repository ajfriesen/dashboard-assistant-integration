"""Config flow: manual entry validates against the device and dedupes."""

from __future__ import annotations

import aiohttp

from typing import Any

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import HomeAssistant

from custom_components.dashboard_assistant.const import DOMAIN

from .conftest import BASE, HOST, PORT, TOKEN

USER_INPUT = {CONF_HOST: HOST, CONF_PORT: PORT, CONF_TOKEN: TOKEN}


async def test_user_flow_creates_entry(
    hass: HomeAssistant, aioclient_mock: Any, device_info: dict[str, Any]
) -> None:
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
    assert result["data"] == USER_INPUT
    assert result["result"].unique_id == device_info["node_id"]


async def test_user_flow_bad_token(
    hass: HomeAssistant, aioclient_mock: Any
) -> None:
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
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] == "abort"
    assert result["reason"] == "already_configured"
