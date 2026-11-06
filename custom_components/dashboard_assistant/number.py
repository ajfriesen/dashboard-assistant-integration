"""Browser zoom and screen saver timeout as numbers."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DashboardAssistantConfigEntry
from .entity import DashboardAssistantEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the zoom and screen saver timeout numbers."""
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = [ZoomNumber(coordinator)]
    if "screensaver" in coordinator.data:
        entities.append(ScreensaverTimeoutNumber(coordinator))
    async_add_entities(entities)


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


class ScreensaverTimeoutNumber(DashboardAssistantEntity, NumberEntity):
    """Minutes without a touch before the screen saver starts; 0 = never.

    The ceiling mirrors screensaverMaxTimeout in daemon/screensaver.go.
    """

    _attr_name = "Screen saver timeout"
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 0
    _attr_native_max_value = 240
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "screensaver_timeout")

    @property
    def native_value(self) -> float:
        return float(self.data["screensaver"]["timeout"])

    async def async_set_native_value(self, value: float) -> None:
        snapshot = await self.coordinator.client.async_set_screensaver(
            timeout=int(value)
        )
        await self._run_command(snapshot)
