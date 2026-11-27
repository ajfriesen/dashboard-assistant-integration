"""System update entity: installed vs latest release."""

from __future__ import annotations

import logging
import re
from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import DashboardAssistantError
from .coordinator import DashboardAssistantConfigEntry
from .entity import DashboardAssistantEntity

_LOGGER = logging.getLogger(__name__)

_DEFAULT_REPO = "https://github.com/ajfriesen/DashboardAssistant"
_GITHUB_RELEASE = re.compile(
    r"^(?P<repo>https://github\.com/[^/]+/[^/]+)/releases/tag/(?P<tag>[^/?#]+)$"
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the system update entity."""
    async_add_entities([SystemUpdate(entry.runtime_data)])


class SystemUpdate(DashboardAssistantEntity, UpdateEntity):
    """Tracks the OS release; offers Install when the image can apply updates."""

    _attr_name = "System update"
    _attr_device_class = UpdateDeviceClass.FIRMWARE
    # UpdateEntity defaults to the Config category; None puts it under Controls.
    _attr_entity_category = None

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "update")
        features = UpdateEntityFeature.PROGRESS | UpdateEntityFeature.RELEASE_NOTES
        if self._update.get("installable"):
            features |= UpdateEntityFeature.INSTALL
        self._attr_supported_features = features

    @property
    def _update(self) -> dict[str, Any]:
        # .get rather than indexing: this entity is added unconditionally, so a
        # snapshot without an "update" block would otherwise fail in __init__
        # and take the whole platform down with it.
        return self.data.get("update") or {}

    @property
    def installed_version(self) -> str | None:
        return self._update.get("installed_version")

    @property
    def latest_version(self) -> str | None:
        return self._update.get("latest_version")

    @property
    def in_progress(self) -> bool:
        return bool(self._update.get("in_progress"))

    @property
    def release_url(self) -> str | None:
        """The changelog at the offered release, rather than that release's page.

        A release's notes list only what changed since the tag before it,
        promoted or not: updating 1.2.0 -> 1.3.1 skipped the never-promoted
        1.3.0, whose changes the 1.3.1 page left out. The changelog at the
        offered tag lists every release up to it. A GitHub release link names
        the device's release source; without one, the project's is assumed.
        """
        url = self._update.get("release_url") or None
        latest = self.latest_version
        if url:
            match = _GITHUB_RELEASE.match(url)
            if not match:
                return url
            return f"{match['repo']}/blob/{match['tag']}/CHANGELOG.md"
        if latest:
            return f"{_DEFAULT_REPO}/blob/v{latest.removeprefix('v')}/CHANGELOG.md"
        return None

    @property
    def title(self) -> str | None:
        return self._update.get("title") or None

    def release_notes(self) -> str | None:
        return self._update.get("release_summary") or None

    async def async_update(self) -> None:
        """Ask the device to check for releases, then re-read its state.

        Home Assistant calls this for Settings -> Updates -> Check for updates
        (homeassistant.update_entity). A plain refresh would only re-read what
        the device already knows, and it fetches releases on its own schedule,
        so the menu item would change nothing.
        """
        try:
            await self.coordinator.client.async_check_updates()
        except DashboardAssistantError as err:
            _LOGGER.debug("check for updates failed: %s", err)
        await super().async_update()

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        await self.coordinator.client.async_install_update()
        await self.coordinator.async_request_refresh()
