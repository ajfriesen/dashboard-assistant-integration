"""Config flow for Dashboard Assistant."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import (
    DashboardAssistantAuthError,
    DashboardAssistantClient,
    DashboardAssistantError,
    DashboardAssistantPairingClosedError,
    async_identify,
    async_pair,
)
from .const import DEFAULT_PORT, DOMAIN


class DashboardAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dashboard Assistant."""

    VERSION = 1

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._name: str | None = None

    async def _validate(
        self, host: str, port: int, token: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Return (info, error_code)."""
        session = async_get_clientsession(self.hass)
        client = DashboardAssistantClient(session, host, port, token)
        try:
            info = await client.async_get_info()
        except DashboardAssistantAuthError:
            return None, "invalid_auth"
        except DashboardAssistantError:
            return None, "cannot_connect"
        return info, None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manual host + token entry."""
        errors: dict[str, str] = {}
        if user_input is not None:
            info, error = await self._validate(
                user_input[CONF_HOST],
                user_input[CONF_PORT],
                user_input[CONF_TOKEN],
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(info["node_id"])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info.get("name") or "Dashboard Assistant",
                    data=user_input,
                )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_HOST): str,
                    vol.Required(CONF_PORT, default=DEFAULT_PORT): int,
                    vol.Required(CONF_TOKEN): str,
                }
            ),
            errors=errors,
        )

    async def async_step_zeroconf(
        self, discovery_info: ZeroconfServiceInfo
    ) -> ConfigFlowResult:
        """Handle a device discovered over mDNS."""
        self._host = discovery_info.host
        self._port = discovery_info.port or DEFAULT_PORT
        self._name = discovery_info.name.removesuffix("._dashboard-assistant._tcp.local.")

        # Identify the device to key discovery on its stable node id — so every
        # address it's announced at (IPv4/IPv6/…) and any later DHCP change map to
        # one entry — and to title the card with its friendly name rather than the
        # raw mDNS instance name ("Dashboard Assistant on <host>").
        #
        # The device's API can be briefly unready right at boot, so retry a little.
        # If it still can't be reached, abort instead of falling back to an
        # address-based id: an address-keyed flow would not de-duplicate against
        # the node-id one, showing a spurious second card. HA re-fires discovery
        # when the device re-announces.
        ident = None
        session = async_get_clientsession(self.hass)
        for attempt in range(3):
            try:
                ident = await async_identify(session, self._host, self._port)
                break
            except DashboardAssistantError:
                if attempt < 2:
                    await asyncio.sleep(2)
        if not ident or not ident.get("node_id"):
            return self.async_abort(reason="cannot_connect")

        self._name = ident.get("name") or self._name
        await self.async_set_unique_id(ident["node_id"])
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: self._host, CONF_PORT: self._port}
        )
        self.context["title_placeholders"] = {"name": self._name or self._host}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer typing-free pairing, or manual token entry as a fallback."""
        return self.async_show_menu(
            step_id="zeroconf_confirm",
            menu_options=["pair", "manual"],
            description_placeholders={"name": self._name or self._host},
        )

    async def async_step_pair(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fetch the token from the device without anyone typing it.

        Attempts pairing immediately — a fresh device pairs openly, so choosing
        this option just works with no further click. An already-set-up device
        needs its Config → Pair window opened; then this form's Retry re-attempts.
        Pairing is attempted on every entry (menu pick and Retry alike), so it
        never gets stuck on an empty confirm form.
        """
        errors: dict[str, str] = {}
        assert self._host is not None
        session = async_get_clientsession(self.hass)
        try:
            result = await async_pair(session, self._host, self._port)
        except DashboardAssistantPairingClosedError:
            errors["base"] = "pairing_closed"
        except DashboardAssistantError:
            errors["base"] = "cannot_connect"
        else:
            token = result["token"]
            info, error = await self._validate(self._host, self._port, token)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(
                    info["node_id"], raise_on_progress=False
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info.get("name") or self._name or "Dashboard Assistant",
                    data={
                        CONF_HOST: self._host,
                        CONF_PORT: self._port,
                        CONF_TOKEN: token,
                    },
                )

        return self.async_show_form(
            step_id="pair",
            data_schema=vol.Schema({}),
            description_placeholders={"name": self._name or self._host},
            errors=errors,
        )

    async def async_step_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Fallback: type the token shown on the device's Config → Info screen."""
        errors: dict[str, str] = {}
        assert self._host is not None
        if user_input is not None:
            info, error = await self._validate(
                self._host, self._port, user_input[CONF_TOKEN]
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(info["node_id"], raise_on_progress=False)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=info.get("name") or self._name or "Dashboard Assistant",
                    data={
                        CONF_HOST: self._host,
                        CONF_PORT: self._port,
                        CONF_TOKEN: user_input[CONF_TOKEN],
                    },
                )

        return self.async_show_form(
            step_id="manual",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            description_placeholders={"name": self._name or self._host},
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication when the token is rejected."""
        self._host = entry_data[CONF_HOST]
        self._port = entry_data[CONF_PORT]
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect a new token for an existing entry."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            info, error = await self._validate(
                reauth_entry.data[CONF_HOST],
                reauth_entry.data[CONF_PORT],
                user_input[CONF_TOKEN],
            )
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(info["node_id"])
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates={CONF_TOKEN: user_input[CONF_TOKEN]},
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({vol.Required(CONF_TOKEN): str}),
            errors=errors,
        )
