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
)
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    ObjectSelector,
    ObjectSelectorConfig,
    SelectOptionDict,
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
    CONF_PAGES,
    DEFAULT_PORT,
    DOMAIN,
)
from .provision import async_ha_pages, ha_base_url, ha_page_url, ha_page_value


class DashboardAssistantConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Dashboard Assistant."""

    VERSION = 1
    # 1.3: the home became the first page (see async_migrate_entry).
    MINOR_VERSION = 3

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """The device's pages, the first of which is its home."""
        return DashboardAssistantOptionsFlow()

    def __init__(self) -> None:
        self._host: str | None = None
        self._port: int = DEFAULT_PORT
        self._name: str | None = None
        # The device's certificate, pinned when the user confirms and carried
        # into the entry.
        self._fingerprint: str | None = None

    async def _validate(
        self, host: str, port: int, token: str
    ) -> tuple[dict[str, Any] | None, str | None]:
        """Return (info, error_code)."""
        assert self._fingerprint is not None
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

        # Pairing hands over the device token, and kiosk_login later pushes a
        # long-lived Home Assistant credential, so neither may cross the network
        # in the clear. A device that offers no TLS is not offered at all.
        if not ident.get("tls_port"):
            return self.async_abort(reason="tls_required")
        self._port = int(ident["tls_port"])
        # Read the certificate now, so a device whose TLS listener is not
        # answering does not get a card that can never pair.
        try:
            self._fingerprint = await async_fetch_fingerprint(
                self.hass, self._host, self._port
            )
        except DashboardAssistantError:
            return self.async_abort(reason="cannot_connect")

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
                # Pin the certificate the device has now. A card can wait for
                # days, and a factory reset in between gives the device a new
                # one; the pin taken at discovery would then fail every Submit.
                # Confirming is the moment trust is actually given.
                self._fingerprint = await async_fetch_fingerprint(
                    self.hass, self._host, self._port
                )
                result = await async_pair(
                    session, self._host, self._port, self._fingerprint
                )
            except DashboardAssistantPairingClosedError:
                errors["base"] = "pairing_closed"
            except DashboardAssistantCertMismatchError:
                errors["base"] = "cert_mismatch"
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


class DashboardAssistantOptionsFlow(OptionsFlow):
    """Edit the device's pages, the first of which is its home.

    A preference rather than connection data, so it lives here and not in the
    config flow: pairing stays one click, and the pages can change at any time.

    Each page is a Home Assistant page, picked from its dashboards and their
    tabs, or any website. The device starts on the first page and its Home
    button goes back to it. Nothing is stored here: the device keeps the one
    copy of its page list, as names and URLs, so the form starts from what the
    device reports and saving writes the list straight back to it. No reload
    either: the coordinator's update re-pushes the login if it needs to (see
    wanted_kiosk_url).
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        entry = self.config_entry
        if entry.state is not ConfigEntryState.LOADED:
            # The pages come from the device, so there is nothing to show.
            return self.async_abort(reason="device_unavailable")
        coordinator = entry.runtime_data
        base = ha_base_url(self.hass)
        ha_pages = await async_ha_pages(self.hass)

        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            pages = user_input.get(CONF_PAGES, [])
            try:
                wanted = _to_device(pages, base, dict(ha_pages))
            except _PageError as err:
                errors[CONF_PAGES] = err.key
                placeholders["page"] = err.page
            else:
                try:
                    await _write_pages(coordinator, wanted)
                except DashboardAssistantError:
                    errors["base"] = "cannot_connect"
                else:
                    return self.async_create_entry(data={})
        else:
            pages = _to_form(
                _device_pages(coordinator.data), base, [value for value, _ in ha_pages]
            )

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_PAGES, default=pages): ObjectSelector(
                        ObjectSelectorConfig(
                            fields={
                                "name": {"selector": {"text": {}}},
                                "ha_page": {
                                    "selector": {
                                        "select": {
                                            "options": [
                                                SelectOptionDict(value=value, label=label)
                                                for value, label in ha_pages
                                            ],
                                            "mode": SelectSelectorMode.DROPDOWN,
                                        }
                                    }
                                },
                                "url": {"selector": {"text": {"type": "url"}}},
                            },
                            multiple=True,
                            label_field="name",
                            translation_key=CONF_PAGES,
                        )
                    ),
                }
            ),
            errors=errors,
            description_placeholders=placeholders,
        )


class _PageError(Exception):
    """A page the form refuses: the error's translation key, and the page it
    names (``{page}`` in the message) so the user knows which to open."""

    def __init__(self, key: str, page: str) -> None:
        super().__init__(key)
        self.key = key
        self.page = page


def _device_pages(data: dict[str, Any]) -> list[dict[str, str]]:
    """The device's page list, as it reports it."""
    return [{"name": p["name"], "url": p["url"]} for p in data["page"]["list"]]


def _to_form(
    pages: list[dict[str, str]], base: str | None, values: list[str]
) -> list[dict[str, str]]:
    """Device pages as the form shows them: a URL that is one of Home
    Assistant's pages as that page, anything else as a website."""
    shown = []
    for page in pages:
        value = ha_page_value(base, page["url"], values) if base else None
        if value is None:
            shown.append({"name": page["name"], "url": page["url"]})
        else:
            shown.append({"name": page["name"], "ha_page": value})
    return shown


def _to_device(
    pages: list[dict[str, Any]], base: str | None, labels: dict[str, str]
) -> list[dict[str, str]]:
    """Form pages as the device keeps them: a name and a URL each.

    Each needs exactly one of a Home Assistant page and a website, and a
    website the same check the device makes, so a refusal keeps the user in
    the form. An unnamed Home Assistant page is named after it.
    """
    out = []
    for position, page in enumerate(pages, start=1):
        name = str(page.get("name") or "").strip()
        ha_page = str(page.get("ha_page") or "").strip()
        url = str(page.get("url") or "").strip()
        shown = name or f"Page {position}"
        if ha_page and url:
            raise _PageError("page_has_both", shown)
        if not ha_page and not url:
            raise _PageError("page_has_neither", shown)
        if ha_page:
            if base is None:
                raise _PageError("no_ha_url", shown)
            out.append({"name": name or labels.get(ha_page, ha_page), "url": ha_page_url(base, ha_page)})
            continue
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise _PageError("invalid_url", shown)
        out.append({"name": name, "url": url})
    return out


async def _write_pages(coordinator: Any, wanted: list[dict[str, str]]) -> None:
    """Make the device's page list exactly ``wanted``, in order."""
    if wanted == _device_pages(coordinator.data):
        return  # an unchanged list should not rewrite the device's
    snapshot = await coordinator.client.async_set_pages(wanted)
    coordinator.async_set_updated_data(snapshot)
