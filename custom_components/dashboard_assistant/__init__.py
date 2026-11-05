"""The Dashboard Assistant integration."""

from __future__ import annotations

import asyncio

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    DashboardAssistantAuthError,
    DashboardAssistantCertMismatchError,
    DashboardAssistantClient,
    DashboardAssistantError,
)
from .const import CONF_CERT_FINGERPRINT, LOGGER
from .coordinator import (
    DashboardAssistantConfigEntry,
    DashboardAssistantCoordinator,
)
from .provision import (
    async_deprovision_kiosk_login,
    async_provision_kiosk_login,
    kiosk_login_is_current,
)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.IMAGE,
    Platform.LIGHT,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.UPDATE,
]


async def async_setup_entry(
    hass: HomeAssistant, entry: DashboardAssistantConfigEntry
) -> bool:
    """Set up Dashboard Assistant from a config entry."""
    session = async_get_clientsession(hass)
    client = DashboardAssistantClient(
        session,
        entry.data[CONF_HOST],
        entry.data[CONF_PORT],
        entry.data[CONF_TOKEN],
        # .get, not [], and no config-entry migration: an entry written before
        # TLS has no pin, and absent is exactly the right meaning -- talk
        # cleartext to a device that may also predate TLS. A migration could not
        # invent a fingerprint anyway without contacting the device.
        entry.data.get(CONF_CERT_FINGERPRINT),
    )

    try:
        info = await client.async_get_info()
    except (DashboardAssistantCertMismatchError, DashboardAssistantAuthError) as err:
        # The device is reachable but no longer accepts this entry: benignly, it
        # was factory-reset, which regenerates its token and its certificate.
        # Nobody can type the new token, so there is nothing to ask for, and
        # retrying would never succeed. Deleting the entry lets discovery offer
        # the device again, and it pairs.
        raise ConfigEntryError(
            f"{err}. If the device was factory-reset, delete this entry; "
            "Home Assistant then discovers the device again and pairs with it"
        ) from err
    except DashboardAssistantError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = DashboardAssistantCoordinator(hass, entry, client, info)
    await coordinator.async_config_entry_first_refresh()
    coordinator.start_stream()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Self-healing kiosk-login provisioning: create a dedicated HA user + token
    # and push it to the device so its browser signs in without anyone typing
    # credentials on the kiosk. Provisioning needs the device reachable, and every
    # entity — so any manual retry — is unavailable while it is not, which is why a
    # one-shot at setup or a manual button couldn't recover a failed attempt.
    # Instead we re-attempt on each healthy coordinator refresh until the login has
    # actually landed on the device (CONF_KIOSK_PROVISIONED), then stop. The same
    # path re-pushes it when the dashboard option changed (CONF_KIOSK_DASHBOARD):
    # the options flow reloads the entry, and setup finds the login out of date.
    # async_provision_kiosk_login is idempotent (reuses the recorded user/token),
    # and the lock keeps overlapping refreshes from provisioning twice.
    provision_lock = asyncio.Lock()

    async def _ensure_kiosk_login() -> None:
        if kiosk_login_is_current(entry) or provision_lock.locked():
            return
        async with provision_lock:
            if kiosk_login_is_current(entry):
                return
            try:
                await async_provision_kiosk_login(hass, entry, client)
            except Exception:  # noqa: BLE001
                LOGGER.debug(
                    "Kiosk-login provisioning failed; retrying on the next healthy update",
                    exc_info=True,
                )

    @callback
    def _reprovision_if_needed() -> None:
        if coordinator.last_update_success and not kiosk_login_is_current(entry):
            entry.async_create_background_task(
                hass, _ensure_kiosk_login(), "dashboard_assistant_provision"
            )

    if not kiosk_login_is_current(entry):
        entry.async_on_unload(coordinator.async_add_listener(_reprovision_if_needed))
        # Attempt immediately — the first refresh above already succeeded, so the
        # device is reachable and a healthy one is signed in before setup returns.
        await _ensure_kiosk_login()

    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: DashboardAssistantConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(
    hass: HomeAssistant, entry: DashboardAssistantConfigEntry
) -> None:
    """Delete the auto-created kiosk user when the integration is removed."""
    await async_deprovision_kiosk_login(hass, entry)
