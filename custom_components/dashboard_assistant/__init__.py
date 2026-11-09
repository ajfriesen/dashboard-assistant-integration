"""The Dashboard Assistant integration."""

from __future__ import annotations

import asyncio

from homeassistant.const import (
    CONF_HOST,
    CONF_PORT,
    CONF_TOKEN,
    EVENT_CORE_CONFIG_UPDATE,
    Platform,
)
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    DashboardAssistantAuthError,
    DashboardAssistantCertMismatchError,
    DashboardAssistantClient,
    DashboardAssistantError,
)
from .const import CONF_CERT_FINGERPRINT, CONF_LEGACY_HOME, HA_DEFAULT_PAGE, LOGGER
from .coordinator import (
    DashboardAssistantConfigEntry,
    DashboardAssistantCoordinator,
)
from .provision import (
    async_apply_legacy_home,
    async_deprovision_kiosk_login,
    async_ensure_kiosk_username,
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


async def async_migrate_entry(
    hass: HomeAssistant, entry: DashboardAssistantConfigEntry
) -> bool:
    """Bring an entry made by an earlier version up to date.

    → 1.3: the device's home was an option of the entry, "dashboard" in 1.1
    (release 1.0.0) and "home" in 1.2 (1.1.0-rc.1); without one it was Home
    Assistant's default dashboard. It is now the device's first page, which the
    device keeps, so it waits in the entry's data (CONF_LEGACY_HOME) until setup
    reaches the device (async_apply_legacy_home).
    """
    if entry.version > 1:
        return False  # made by a newer version; refuse rather than guess
    if entry.minor_version < 3:
        options = dict(entry.options)
        legacy = options.pop("home", None) or options.pop("dashboard", None)
        options.pop("dashboard", None)
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_LEGACY_HOME: legacy or HA_DEFAULT_PAGE},
            options=options,
            minor_version=3,
        )
        LOGGER.debug("Migrated entry %s to 1.3", entry.entry_id)
    return True


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
        entry.data[CONF_CERT_FINGERPRINT],
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

    # An entry made before 1.3 kept the device's home as an option; it is now
    # the first page. Before the login below, which for an older device
    # carries that page.
    try:
        await async_apply_legacy_home(hass, entry, coordinator)
    except DashboardAssistantError:
        LOGGER.warning(
            "Could not make the device's old home its first page; trying again on the next setup",
            exc_info=True,
        )

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Self-healing kiosk-login provisioning: create a dedicated HA user + token
    # and push it to the device so its browser signs in without anyone typing
    # credentials on the kiosk. Provisioning needs the device reachable, and every
    # entity — so any manual retry — is unavailable while it is not, which is why a
    # one-shot at setup or a manual button couldn't recover a failed attempt.
    # Instead we re-attempt on each healthy coordinator refresh until the login has
    # actually landed on the device (CONF_KIOSK_PROVISIONED). The same path
    # re-pushes it when the URL it carried (CONF_KIOSK_URL) is out of date: Home
    # Assistant's own URL changed in its network settings, which reloads
    # nothing, so that one is caught from the event; or, for a device older
    # than home_is_first_page, its first page changed, caught from the
    # coordinator's update.
    # async_provision_kiosk_login is idempotent (reuses the recorded user/token),
    # and the lock keeps overlapping refreshes from provisioning twice.
    provision_lock = asyncio.Lock()

    async def _ensure_kiosk_login() -> None:
        if kiosk_login_is_current(hass, entry) or provision_lock.locked():
            return
        async with provision_lock:
            if kiosk_login_is_current(hass, entry):
                return
            try:
                await async_provision_kiosk_login(hass, entry, client)
            except Exception:  # noqa: BLE001
                LOGGER.debug(
                    "Kiosk-login provisioning failed; retrying on the next healthy update",
                    exc_info=True,
                )

    @callback
    def _reprovision_if_needed(_event: Event | None = None) -> None:
        if coordinator.last_update_success and not kiosk_login_is_current(hass, entry):
            entry.async_create_background_task(
                hass, _ensure_kiosk_login(), "dashboard_assistant_provision"
            )

    entry.async_on_unload(coordinator.async_add_listener(_reprovision_if_needed))
    entry.async_on_unload(
        hass.bus.async_listen(EVENT_CORE_CONFIG_UPDATE, _reprovision_if_needed)
    )
    # Attempt immediately — the first refresh above already succeeded, so the
    # device is reachable and a healthy one is signed in before setup returns.
    await _ensure_kiosk_login()
    await async_ensure_kiosk_username(hass, entry, info)

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
