"""Screenshot image entity."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.image import ImageEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.util import dt as dt_util

from .api import DashboardAssistantError
from .coordinator import DashboardAssistantConfigEntry, DashboardAssistantCoordinator
from .entity import DashboardAssistantEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the screenshot image."""
    async_add_entities([ScreenshotImage(hass, entry.runtime_data)])


class ScreenshotImage(DashboardAssistantEntity, ImageEntity):
    """The latest captured screenshot (refreshed by the Take screenshot button)."""

    _attr_name = "Screenshot"
    _attr_icon = "mdi:monitor-screenshot"
    _attr_content_type = "image/jpeg"

    def __init__(
        self, hass: HomeAssistant, coordinator: DashboardAssistantCoordinator
    ) -> None:
        super().__init__(coordinator, "screenshot")
        ImageEntity.__init__(self, hass)

    @property
    def image_last_updated(self) -> datetime | None:
        shot = self.data["screenshot"]
        if not shot.get("available") or not shot.get("updated_at"):
            return None
        return dt_util.utc_from_timestamp(shot["updated_at"])

    async def async_image(self) -> bytes | None:
        if not self.data["screenshot"].get("available"):
            return None
        try:
            return await self.coordinator.client.async_get_screenshot()
        except DashboardAssistantError:
            return None
