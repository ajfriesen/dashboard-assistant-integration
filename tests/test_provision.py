"""The device's Home Assistant user, as provisioning creates it.

Music Assistant signs the device in through Home Assistant's Ingress, and the
Supervisor only names the user to it (X-Remote-User-Name) when the user has a
username, which in Home Assistant means a username/password login. Without one,
Music Assistant shows "Couldn't sign in through Home Assistant".
"""

from __future__ import annotations

from typing import Any

from homeassistant.auth.providers.homeassistant import HassAuthProvider
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.dashboard_assistant.const import CONF_KIOSK_USER_ID, DOMAIN
from custom_components.dashboard_assistant.provision import (
    async_deprovision_kiosk_login,
    async_ensure_kiosk_username,
    async_provision_kiosk_login,
)

from .conftest import KIOSK_HA_URL

USERNAME = "dashboard-assistant-d7bbb4"


class FakeDevice:
    """The two daemon calls provisioning makes."""

    def __init__(self) -> None:
        self.logins: list[tuple[str, str | None]] = []

    async def async_get_info(self) -> dict[str, Any]:
        return {"name": "Dashboard Assistant", "mac": "88:a2:9e:d7:bb:b4"}

    async def async_kiosk_login(self, token: str, url: str | None) -> None:
        self.logins.append((token, url))


async def _entry(hass: HomeAssistant, **data: Any) -> MockConfigEntry:
    await hass.config.async_update(internal_url=KIOSK_HA_URL)
    entry = MockConfigEntry(domain=DOMAIN, minor_version=3, data=data)
    entry.add_to_hass(hass)
    return entry


def _username(hass: HomeAssistant, user_id: str) -> str | None:
    user = hass.auth._store._users[user_id]  # noqa: SLF001
    return next(
        (
            c.data.get("username")
            for c in user.credentials
            if c.auth_provider_type == "homeassistant"
        ),
        None,
    )


async def test_new_user_gets_a_username(
    hass: HomeAssistant, local_auth: HassAuthProvider
) -> None:
    """A freshly provisioned user can be named to Music Assistant."""
    entry = await _entry(hass)

    await async_provision_kiosk_login(hass, entry, FakeDevice())

    assert _username(hass, entry.data[CONF_KIOSK_USER_ID]) == USERNAME


async def test_existing_user_without_login_gets_one(
    hass: HomeAssistant, local_auth: HassAuthProvider
) -> None:
    """Re-provisioning gives a username to a user created before this fix."""
    user = await hass.auth.async_create_user("Dashboard Assistant (d7bbb4)")
    entry = await _entry(hass, **{CONF_KIOSK_USER_ID: user.id})

    await async_provision_kiosk_login(hass, entry, FakeDevice())
    await async_provision_kiosk_login(hass, entry, FakeDevice())

    assert entry.data[CONF_KIOSK_USER_ID] == user.id
    assert _username(hass, user.id) == USERNAME
    assert len(user.credentials) == 1


async def test_already_provisioned_user_gets_one_without_reprovisioning(
    hass: HomeAssistant, local_auth: HassAuthProvider
) -> None:
    """Setup backfills the username even when the device's login is current.

    Provisioning only reruns for a stale login, so a device provisioned before
    usernames existed would otherwise never get one.
    """
    user = await hass.auth.async_create_user("Dashboard Assistant (d7bbb4)")
    entry = await _entry(hass, **{CONF_KIOSK_USER_ID: user.id})
    device = FakeDevice()

    await async_ensure_kiosk_username(hass, entry, await device.async_get_info())

    assert _username(hass, user.id) == USERNAME
    assert device.logins == []


async def test_removing_the_integration_frees_the_username(
    hass: HomeAssistant, local_auth: HassAuthProvider
) -> None:
    """Adding the device again can take the same username."""
    entry = await _entry(hass)
    await async_provision_kiosk_login(hass, entry, FakeDevice())

    await async_deprovision_kiosk_login(hass, entry)

    assert USERNAME not in {u["username"] for u in local_auth.data.users}
