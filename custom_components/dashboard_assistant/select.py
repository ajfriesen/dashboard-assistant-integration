"""Page and display-rotation selectors."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DashboardAssistantConfigEntry
from .entity import DashboardAssistantEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the page and rotation selectors."""
    async_add_entities(
        [
            PageSelect(entry.runtime_data),
            RotationSelect(entry.runtime_data),
        ]
    )


class PageSelect(DashboardAssistantEntity, SelectEntity):
    """Jump the kiosk to one of the configured pages."""

    _attr_name = "Page"
    _attr_icon = "mdi:web"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "page")

    @property
    def options(self) -> list[str]:
        return list(self.data["page"]["options"])

    @property
    def current_option(self) -> str | None:
        return self.data["page"]["current"] or None

    async def async_select_option(self, option: str) -> None:
        snapshot = await self.coordinator.client.async_set_page(select=option)
        await self._run_command(snapshot)


class RotationSelect(DashboardAssistantEntity, SelectEntity):
    """Rotate the kiosk display to one of 0/90/180/270°.

    The daemon reports the current angle and the supported angles as integer
    degrees (see daemon/rotation.go); we render them with a degree sign for the
    dropdown and strip it back to an int when a choice is picked.
    """

    _attr_name = "Rotation"
    _attr_icon = "mdi:screen-rotation"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "rotation")

    @property
    def options(self) -> list[str]:
        return [f"{deg}°" for deg in self.data["rotation"]["options"]]

    @property
    def current_option(self) -> str | None:
        return f"{self.data['rotation']['current']}°"

    async def async_select_option(self, option: str) -> None:
        degrees = int(option.rstrip("°"))
        snapshot = await self.coordinator.client.async_set_rotation(degrees)
        await self._run_command(snapshot)
