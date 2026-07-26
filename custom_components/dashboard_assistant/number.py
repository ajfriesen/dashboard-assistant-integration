"""Browser zoom as a number slider."""

from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DashboardAssistantConfigEntry
from .entity import DashboardAssistantEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the zoom number."""
    async_add_entities([ZoomNumber(entry.runtime_data)])


class ZoomNumber(DashboardAssistantEntity, NumberEntity):
    """Absolute browser zoom (25..400 %, in 5 % steps)."""

    _attr_name = "Zoom"
    _attr_icon = "mdi:magnify-plus"
    _attr_native_min_value = 25
    _attr_native_max_value = 400
    _attr_native_step = 5
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "zoom")

    @property
    def native_value(self) -> float:
        return float(self.data["zoom"])

    async def async_set_native_value(self, value: float) -> None:
        snapshot = await self.coordinator.client.async_set_zoom(int(value))
        await self._run_command(snapshot)
