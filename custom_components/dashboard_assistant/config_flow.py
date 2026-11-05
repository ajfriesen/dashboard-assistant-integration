"""Config flow for Dashboard Assistant."""

from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import urlparse

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigEntryState,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    ObjectSelector,
    ObjectSelectorConfig,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)
from homeassistant.helpers.service_info.zeroconf import ZeroconfServiceInfo

from .api import (
    DashboardAssistantAuthError,
    DashboardAssistantCertMismatchError,
    DashboardAssistantClient,
    DashboardAssistantError,
    DashboardAssistantPairingClosedError,
    async_fetch_fingerprint,
    async_identify,
    async_pair,
)
from .const import (
    CONF_CERT_FINGERPRINT,
    CONF_DASHBOARD,
    CONF_PAGES,
    DEFAULT_DASHBOARD,
    DEFAULT_PORT,
    DOMAIN,
)
from .provision import kiosk_dashboards


class DashboardAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dashboard Assistant."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Which dashboard the device shows, and its pages."""
        return DashboardAssistantOptionsFlow()

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._name: str | None = None
        # Pinned once, at the first contact with the device, and carried into the
        # entry. None means the device advertised no TLS port, i.e. it predates
        # TLS support and this entry stays cleartext.
        self._fingerprint: str | None = None

    async def _validate(
        self, host: str, port: int, token: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Return (info, error_code)."""
        session = async_get_clientsession(self.hass)
        client = DashboardAssistantClient(
            session, host, port, token, self._fingerprint
        )
        try:
            info = await client.async_get_info()
        except DashboardAssistantAuthError:
            return None, "invalid_auth"
        except DashboardAssistantCertMismatchError:
            return None, "cert_mismatch"
        except DashboardAssistantError:
            return None, "cannot_connect"
        return info, None

    async def _upgrade_to_tls(self, ident: dict[str, Any]) -> None:
        """Pin the device's certificate, if it offers TLS.

        The identify response is cleartext, so the advertised port is a hint, not
        an assurance -- the pin itself comes from the handshake. A device that
        advertises no TLS port predates it, and the entry stays cleartext rather
        than failing to set up.
        """
        tls_port = ident.get("tls_port")
        if not tls_port:
            return
        try:
            self._fingerprint = await async_fetch_fingerprint(
                self.hass, self._host, int(tls_port)
            )
            self._port = int(tls_port)
        except DashboardAssistantError:
            self._fingerprint = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Devices are added from discovery, where they pair with no token typed.

        There is nothing to ask for here: the token never leaves the device
        except through pairing.
        """
        return self.async_abort(reason="discovery_only")

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

        # Pin the certificate before anything secret moves: the pair call below
        # hands over the device token, and kiosk_login later pushes a long-lived
        # Home Assistant credential.
        await self._upgrade_to_tls(ident)

        await self.async_set_unique_id(ident["node_id"])
        # Deliberately NOT updating the fingerprint here. This path rewrites entry
        # data on rediscovery with no user interaction, so a spoofed mDNS record
        # could otherwise silently re-pin a configured device. A device whose
        # certificate really changed (a factory reset) is deleted and re-added.
        self._abort_if_unique_id_configured(
            updates={CONF_HOST: self._host, CONF_PORT: self._port}
        )
        self.context["title_placeholders"] = {"name": self._name or self._host}
        return await self.async_step_zeroconf_confirm()

    async def async_step_zeroconf_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm adding the discovered device, then fetch its token by pairing.

        A fresh device pairs openly, so confirming just works. An already-paired
        device refuses, and has to be factory-reset before Submit can succeed.
        """
        errors: dict[str, str] = {}
        if user_input is not None:
            assert self._host is not None
            session = async_get_clientsession(self.hass)
            try:
                result = await async_pair(
                    session, self._host, self._port, self._fingerprint
                )
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
                            CONF_CERT_FINGERPRINT: self._fingerprint,
                        },
                    )

        return self.async_show_form(
            step_id="zeroconf_confirm",
            data_schema=vol.Schema({}),
            description_placeholders={"name": self._name or self._host},
            errors=errors,
        )


class DashboardAssistantOptionsFlow(OptionsFlowWithReload):
    """Pick the dashboard the device shows, and edit its pages.

    Preferences rather than connection data, so they live here and not in the
    config flow: pairing stays one click, and both can change at any time.

    The two are kept differently. The dashboard is stored in the entry's
    options; saving reloads the entry, and setup pushes the kiosk login again
    with the new dashboard's URL (see kiosk_login_is_current). The pages are
    not stored here at all: the device keeps the one copy of its page list,
    so the form starts from what the device reports and saving writes the list
    straight back to it.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        if entry.state is not ConfigEntryState.LOADED:
            # The pages come from the device, so there is nothing to show.
            return self.async_abort(reason="device_unavailable")
        coordinator = entry.runtime_data

        errors: dict[str, str] = {}
        if user_input is not None:
            pages = user_input.get(CONF_PAGES, [])
            if error := _check_pages(pages):
                errors[CONF_PAGES] = error
            else:
                try:
                    await _write_pages(coordinator, pages)
                except DashboardAssistantError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(
                        data={CONF_DASHBOARD: user_input[CONF_DASHBOARD]}
                    )

        dashboards = [
            SelectOptionDict(value=DEFAULT_DASHBOARD, label="Home Assistant default")
        ]
        dashboards += [
            SelectOptionDict(value=url_path, label=title)
            for url_path, title in sorted(
                kiosk_dashboards(self.hass).items(), key=lambda item: item[1].lower()
            )
        ]
        if user_input is not None:
            current = user_input[CONF_DASHBOARD]
            pages = user_input.get(CONF_PAGES, [])
        else:
            current = entry.options.get(CONF_DASHBOARD, DEFAULT_DASHBOARD)
            pages = _device_pages(coordinator.data)
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_DASHBOARD, default=current): SelectSelector(
                        SelectSelectorConfig(
                            options=dashboards, mode=SelectSelectorMode.DROPDOWN
                        )
                    ),
                    vol.Optional(CONF_PAGES, default=pages): ObjectSelector(
                        ObjectSelectorConfig(
                            fields={
                                "name": {"selector": {"text": {}}},
                                "url": {
                                    "required": True,
                                    "selector": {"text": {"type": "url"}},
                                },
                            },
                            multiple=True,
                            label_field="name",
                            description_field="url",
                            translation_key=CONF_PAGES,
                        )
                    ),
                }
            ),
            errors=errors,
        )


def _device_pages(data: dict[str, Any]) -> list[dict[str, str]]:
    """The device's page list, as it reports it."""
    return [{"name": p["name"], "url": p["url"]} for p in data["page"]["list"]]


def _clean(pages: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {"name": str(p.get("name", "")).strip(), "url": str(p.get("url", "")).strip()}
        for p in pages
    ]


def _check_pages(pages: list[dict[str, Any]]) -> str | None:
    """The same check the device makes, so a refusal keeps the user in the form."""
    for page in _clean(pages):
        url = urlparse(page["url"])
        if url.scheme not in ("http", "https") or not url.netloc:
            return "invalid_url"
    return None


async def _write_pages(coordinator: Any, pages: list[dict[str, Any]]) -> None:
    """Make the device's page list exactly ``pages``, in order."""
    wanted = _clean(pages)
    if wanted == _device_pages(coordinator.data):
        return  # saving only the dashboard should not rewrite the pages
    snapshot = await coordinator.client.async_set_pages(wanted)
    coordinator.async_set_updated_data(snapshot)
