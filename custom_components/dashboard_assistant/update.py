"""System update entity: installed vs latest release."""

from __future__ import annotations

from typing import Any

from homeassistant.components.update import (
    UpdateDeviceClass,
    UpdateEntity,
    UpdateEntityFeature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DashboardAssistantConfigEntry
from .entity import DashboardAssistantEntity


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
        if self.data["update"].get("installable"):
            features |= UpdateEntityFeature.INSTALL
        self._attr_supported_features = features

    @property
    def _update(self) -> dict[str, Any]:
        return self.data["update"]

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
        return self._update.get("release_url") or None

    @property
    def title(self) -> str | None:
        return self._update.get("title") or None

    def release_notes(self) -> str | None:
        return self._update.get("release_summary") or None

    async def async_install(
        self, version: str | None, backup: bool, **kwargs: Any
    ) -> None:
        await self.coordinator.client.async_install_update()
        await self.coordinator.async_request_refresh()
