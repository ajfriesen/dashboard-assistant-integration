"""Page selector."""

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
    """Set up the page selector."""
    async_add_entities([PageSelect(entry.runtime_data)])


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
