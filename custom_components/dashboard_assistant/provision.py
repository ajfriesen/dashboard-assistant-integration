"""Auto-provision a kiosk login for the device.

The whole point: nobody should have to type Home Assistant credentials on the
kiosk. This module creates a dedicated, non-admin Home Assistant user, mints a
long-lived access token for it, and hands that token (plus the dashboard URL) to
the device over the authenticated LAN API. The device stages it and relaunches
the kiosk, whose autologin injector signs the browser in.

It is idempotent: the created user and refresh-token ids are recorded on the
config entry, so a Home Assistant restart reuses them instead of piling up new
users. ``async_deprovision_kiosk_login`` removes the user when the integration is
removed, so we do not leave an orphan behind.
"""

from __future__ import annotations

from datetime import timedelta

from homeassistant.auth.const import GROUP_ID_USER
from homeassistant.auth.models import TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .api import DashboardAssistantClient
from .const import (
    CONF_KIOSK_REFRESH_TOKEN_ID,
    CONF_KIOSK_USER_ID,
    KIOSK_USER_NAME,
    LOGGER,
)
from .coordinator import DashboardAssistantConfigEntry

# Long-lived, but not literally forever, so a stale kiosk token eventually lapses.
_TOKEN_LIFETIME = timedelta(days=3650)


async def async_provision_kiosk_login(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    client: DashboardAssistantClient,
) -> None:
    """Create (or reuse) the kiosk user + token and push it to the device.

    Reuses the user and refresh token recorded on the entry when they still
    exist, so repeated calls (restarts, the re-provision button) don't create
    duplicates. A fresh access token is minted each time and sent to the device.
    """
    # The device's MAC labels this tablet's token so it's distinguishable from
    # other tablets sharing the "Dashboard Assistant" user name.
    info = await client.async_get_info()
    mac = info.get("mac") or info.get("node_id") or "unknown"
    token_label = f"{KIOSK_USER_NAME} {mac}"

    # Reuse the recorded user if it still exists, else create a non-admin one
    # sharing the "Dashboard Assistant" display name.
    user = None
    if user_id := entry.data.get(CONF_KIOSK_USER_ID):
        user = await hass.auth.async_get_user(user_id)
    if user is None:
        # async_create_user makes the user active on its own — it takes no
        # is_active kwarg (passing one raises TypeError).
        user = await hass.auth.async_create_user(
            KIOSK_USER_NAME, group_ids=[GROUP_ID_USER]
        )

    # Reuse the recorded long-lived refresh token if it still exists, else create
    # one, labelled with the MAC. The access token below is derived from it and is
    # what the kiosk stores.
    refresh_token = None
    if rt_id := entry.data.get(CONF_KIOSK_REFRESH_TOKEN_ID):
        refresh_token = await hass.auth.async_get_refresh_token(rt_id)
    if refresh_token is None:
        refresh_token = await hass.auth.async_create_refresh_token(
            user,
            client_name=token_label,
            token_type=TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN,
            access_token_expiration=_TOKEN_LIFETIME,
        )

    access_token = hass.auth.async_create_access_token(refresh_token)

    # Point the kiosk at this Home Assistant. Prefer the internal (LAN) URL — the
    # kiosk is on the LAN — and fall back to whatever HA can resolve. If none is
    # configured we still push the token and leave the device's own URL in place.
    try:
        ha_url = get_url(hass, allow_internal=True, allow_external=True, prefer_external=False)
    except NoURLAvailableError:
        ha_url = None

    await client.async_kiosk_login(access_token, ha_url)

    # Record what we created so this stays idempotent and can be cleaned up.
    hass.config_entries.async_update_entry(
        entry,
        data={
            **entry.data,
            CONF_KIOSK_USER_ID: user.id,
            CONF_KIOSK_REFRESH_TOKEN_ID: refresh_token.id,
        },
    )
    LOGGER.info("Provisioned kiosk login for user %s", user.id)


async def async_deprovision_kiosk_login(
    hass: HomeAssistant, entry: DashboardAssistantConfigEntry
) -> None:
    """Remove the auto-created kiosk user when the integration is removed."""
    if user_id := entry.data.get(CONF_KIOSK_USER_ID):
        if user := await hass.auth.async_get_user(user_id):
            await hass.auth.async_remove_user(user)
            LOGGER.info("Removed kiosk user %s", user_id)
