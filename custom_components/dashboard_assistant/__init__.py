"""The Dashboard Assistant integration."""

from __future__ import annotations

from homeassistant.const import CONF_HOST, CONF_PORT, CONF_TOKEN, Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import (
    DashboardAssistantAuthError,
    DashboardAssistantClient,
    DashboardAssistantError,
)
from .const import CONF_KIOSK_USER_ID, LOGGER
from .coordinator import (
    DashboardAssistantConfigEntry,
    DashboardAssistantCoordinator,
)
from .provision import (
    async_deprovision_kiosk_login,
    async_provision_kiosk_login,
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
    Platform.TEXT,
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
    )

    try:
        info = await client.async_get_info()
    except DashboardAssistantAuthError as err:
        raise ConfigEntryAuthFailed(str(err)) from err
    except DashboardAssistantError as err:
        raise ConfigEntryNotReady(str(err)) from err

    coordinator = DashboardAssistantCoordinator(hass, entry, client, info)
    await coordinator.async_config_entry_first_refresh()
    coordinator.start_stream()

    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # Auto-provision the kiosk login the first time only: create a dedicated HA
    # user + long-lived token and hand it to the device so its browser signs in
    # without anyone typing credentials on the kiosk. A failure here (e.g. the
    # kiosk is briefly offline) must not fail the whole integration — the entities
    # still work, and the re-provision button retries.
    if not entry.data.get(CONF_KIOSK_USER_ID):
        try:
            await async_provision_kiosk_login(hass, entry, client)
        except Exception:  # noqa: BLE001
            LOGGER.exception("Failed to provision kiosk login; use the button to retry")

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
