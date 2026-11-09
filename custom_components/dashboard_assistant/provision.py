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

import secrets
from datetime import timedelta

from homeassistant.auth.const import GROUP_ID_USER
from homeassistant.auth.models import TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN, User
from homeassistant.auth.providers import homeassistant as auth_ha
from homeassistant.components.lovelace.const import DOMAIN as LOVELACE_DOMAIN
from homeassistant.components.lovelace.const import LOVELACE_DATA
from homeassistant.core import HomeAssistant
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .api import DashboardAssistantClient
from .const import (
    CONF_DASHBOARD,
    CONF_KIOSK_PROVISIONED,
    CONF_KIOSK_REFRESH_TOKEN_ID,
    CONF_KIOSK_URL,
    CONF_KIOSK_USER_ID,
    DEFAULT_DASHBOARD,
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
    # Give every tablet its own HA user so the user list makes it obvious which
    # login belongs to which display. The device's reported name is NOT unique —
    # every tablet reports the same "Dashboard Assistant" — so always suffix a
    # per-device id (the short MAC, falling back to the node id) unless the name
    # already carries it. Without this the HA user list shows several identically
    # named users and you can't tell which login belongs to which tablet. The
    # short MAC also matches the device card's MAC connection, so user and device
    # cross-reference. The token carries the same label.
    info = await client.async_get_info()
    mac_short = _mac_short(info)
    base_name = info.get("name") or KIOSK_USER_NAME
    if mac_short.lower() in base_name.lower():
        user_name = base_name
    else:
        user_name = f"{base_name} ({mac_short})"
    token_label = user_name

    # Reuse the recorded user if it still exists, else create a non-admin one.
    # When reusing, keep its name in sync with the MAC-based name so tablets that
    # were provisioned under the old shared name get migrated on the next run.
    user = None
    if user_id := entry.data.get(CONF_KIOSK_USER_ID):
        user = await hass.auth.async_get_user(user_id)
    if user is None:
        # async_create_user makes the user active on its own — it takes no
        # is_active kwarg (passing one raises TypeError).
        user = await hass.auth.async_create_user(
            user_name, group_ids=[GROUP_ID_USER]
        )
    elif user.name != user_name:
        await hass.auth.async_update_user(user, name=user_name)
    await _async_ensure_username(hass, user, _kiosk_username(mac_short))

    # Reuse the recorded long-lived refresh token if it still exists, else create
    # one, labelled with the MAC. The access token below is derived from it and is
    # what the kiosk stores.
    refresh_token = None
    if rt_id := entry.data.get(CONF_KIOSK_REFRESH_TOKEN_ID):
        # async_get_refresh_token is sync (returns RefreshToken | None), unlike
        # async_create_refresh_token below — awaiting it raises "'RefreshToken'
        # object can't be awaited".
        refresh_token = hass.auth.async_get_refresh_token(rt_id)
    if refresh_token is None:
        refresh_token = await hass.auth.async_create_refresh_token(
            user,
            client_name=token_label,
            token_type=TOKEN_TYPE_LONG_LIVED_ACCESS_TOKEN,
            access_token_expiration=_TOKEN_LIFETIME,
        )

    # Record the HA user + token id *before* pushing to the device. The push can
    # fail (device briefly offline), and the self-healing retry in __init__ must
    # reuse this same user rather than create a second one — otherwise a flaky
    # push would spawn duplicate "Dashboard Assistant" users. Only write when
    # something changed so re-pushes don't churn the entry.
    if (
        entry.data.get(CONF_KIOSK_USER_ID) != user.id
        or entry.data.get(CONF_KIOSK_REFRESH_TOKEN_ID) != refresh_token.id
    ):
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_KIOSK_USER_ID: user.id,
                CONF_KIOSK_REFRESH_TOKEN_ID: refresh_token.id,
            },
        )

    access_token = hass.auth.async_create_access_token(refresh_token)

    dashboard = entry.options.get(CONF_DASHBOARD, DEFAULT_DASHBOARD)
    if dashboard != DEFAULT_DASHBOARD and dashboard not in kiosk_dashboards(hass):
        LOGGER.warning(
            "Dashboard %s no longer exists; the device shows the default one", dashboard
        )
    ha_url = wanted_kiosk_url(hass, entry)

    # If this raises, the user/token are already recorded above, so the retry
    # re-pushes without duplicating; the provisioned flag is set only once the
    # push has actually landed, and is what stops the self-healing retry loop.
    await client.async_kiosk_login(access_token, ha_url)

    if not entry.data.get(CONF_KIOSK_PROVISIONED) or entry.data.get(CONF_KIOSK_URL) != ha_url:
        hass.config_entries.async_update_entry(
            entry,
            data={**entry.data, CONF_KIOSK_PROVISIONED: True, CONF_KIOSK_URL: ha_url},
        )
    LOGGER.info("Provisioned kiosk login for user %s", user.id)


def _mac_short(info: dict) -> str:
    """The per-device id that suffixes the kiosk user's name and username."""
    mac = info.get("mac") or ""
    return mac.replace(":", "")[-6:] or info.get("node_id") or "unknown"


def _kiosk_username(mac_short: str) -> str:
    return f"dashboard-assistant-{mac_short.lower()}"


async def async_ensure_kiosk_username(
    hass: HomeAssistant, entry: DashboardAssistantConfigEntry, info: dict
) -> None:
    """Give an already-provisioned kiosk user its username login.

    Provisioning only reruns when the device's login is stale, so a kiosk user
    created before usernames existed would otherwise never get one.
    """
    user_id = entry.data.get(CONF_KIOSK_USER_ID)
    if user_id and (user := await hass.auth.async_get_user(user_id)):
        await _async_ensure_username(hass, user, _kiosk_username(_mac_short(info)))


async def _async_ensure_username(hass: HomeAssistant, user: User, username: str) -> None:
    """Give the kiosk user a username/password login if it has none.

    Nobody signs in with it: the kiosk uses its token. It exists because add-ons
    opened through Ingress, Music Assistant among them, learn who is signed in
    from the X-Remote-User-Name header, and the Supervisor only sends that for a
    user with a username — which Home Assistant only keeps on a login of its
    own (homeassistant) auth provider. The password is random and thrown away.

    Done the way Home Assistant's own "add login" does it
    (config/auth_provider/homeassistant/create), and checked on every run so a
    user provisioned before this gets one too. Removing the user removes the
    login with it.
    """
    if any(c.auth_provider_type == "homeassistant" for c in user.credentials):
        return
    # An install can configure the username/password provider away (only
    # trusted_networks, say). The kiosk's token works regardless.
    provider = next(
        (p for p in hass.auth.auth_providers if isinstance(p, auth_ha.HassAuthProvider)),
        None,
    )
    if provider is None:
        LOGGER.warning(
            "Home Assistant has no username/password logins, so add-ons opened "
            "through Ingress, such as Music Assistant, cannot sign the device in"
        )
        return
    try:
        await provider.async_add_auth(username, secrets.token_urlsafe(32))
    except auth_ha.InvalidUser:
        LOGGER.warning(
            "Username %s is taken, so add-ons opened through Ingress, such as "
            "Music Assistant, cannot sign the device in",
            username,
        )
        return
    credentials = await provider.async_get_or_create_credentials({"username": username})
    await hass.auth.async_link_user(user, credentials)


async def async_deprovision_kiosk_login(
    hass: HomeAssistant, entry: DashboardAssistantConfigEntry
) -> None:
    """Remove the auto-created kiosk user when the integration is removed."""
    if user_id := entry.data.get(CONF_KIOSK_USER_ID):
        if user := await hass.auth.async_get_user(user_id):
            await hass.auth.async_remove_user(user)
            LOGGER.info("Removed kiosk user %s", user_id)


def wanted_kiosk_url(
    hass: HomeAssistant, entry: DashboardAssistantConfigEntry
) -> str | None:
    """The URL the device should open now, or None if Home Assistant has none.

    Prefers the internal (LAN) URL, since the kiosk is on the LAN, and falls
    back to whatever Home Assistant can resolve. With none configured the login
    still goes out, and the device keeps the URL it has.
    """
    try:
        base = get_url(hass, allow_internal=True, allow_external=True, prefer_external=False)
    except NoURLAvailableError:
        return None
    return kiosk_url(hass, base, entry.options.get(CONF_DASHBOARD, DEFAULT_DASHBOARD))


def kiosk_login_is_current(
    hass: HomeAssistant, entry: DashboardAssistantConfigEntry
) -> bool:
    """Whether the device holds a login for the URL Home Assistant would send.

    That URL changes with the dashboard option and with Home Assistant's own
    network settings; either one makes the login stale.
    """
    return bool(entry.data.get(CONF_KIOSK_PROVISIONED)) and entry.data.get(
        CONF_KIOSK_URL
    ) == wanted_kiosk_url(hass, entry)


def kiosk_dashboards(hass: HomeAssistant) -> dict[str, str]:
    """The dashboards the kiosk can open, as {url_path: title}.

    Leaves out Home Assistant's default dashboard, which the options offer
    separately as its bare URL, and admin-only ones: the kiosk signs in as a
    non-admin user, so it could only ever show an error for those.
    """
    data = hass.data.get(LOVELACE_DATA)
    if data is None:
        return {}
    found: dict[str, str] = {}
    for url_path, dashboard in data.dashboards.items():
        config = dashboard.config
        if not url_path or url_path == LOVELACE_DOMAIN or not config:
            continue
        if config.get("require_admin"):
            continue
        found[url_path] = config.get("title") or url_path
    return found


def kiosk_url(hass: HomeAssistant, base: str, dashboard: str) -> str:
    """The URL the device opens: Home Assistant's, plus the chosen dashboard.

    A dashboard deleted since it was chosen falls back to the default one, so
    the device does not sit on an error page. This runs on every refresh, so it
    does not log; the push does.
    """
    if dashboard == DEFAULT_DASHBOARD or dashboard not in kiosk_dashboards(hass):
        return base
    return f"{base.rstrip('/')}/{dashboard}"
