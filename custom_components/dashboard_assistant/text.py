"""Editable "Page N" slots for managing the page list."""

from __future__ import annotations

from homeassistant.components.text import TextEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import PAGE_SLOTS
from .coordinator import DashboardAssistantConfigEntry
from .entity import DashboardAssistantEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the editable page slots."""
    coordinator = entry.runtime_data
    async_add_entities(PageSlotText(coordinator, i) for i in range(PAGE_SLOTS))


class PageSlotText(DashboardAssistantEntity, TextEntity):
    """One editable slot: "Name | URL" (clearing it removes the page)."""

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:link-variant"
    _attr_native_max = 255

    def __init__(self, coordinator, index: int) -> None:
        super().__init__(coordinator, f"page_slot_{index}")
        self._index = index
        self._attr_name = f"Page {index + 1}"

    @property
    def native_value(self) -> str:
        slots = self.data["page"]["slots"]
        return slots[self._index] if self._index < len(slots) else ""

    async def async_set_value(self, value: str) -> None:
        snapshot = await self.coordinator.client.async_set_page_slot(self._index, value)
        await self._run_command(snapshot)
