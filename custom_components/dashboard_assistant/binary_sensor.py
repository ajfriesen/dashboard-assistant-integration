"""Battery charging binary sensor (only on devices with a battery)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
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
    """Set up the charging sensor when the device has a battery."""
    coordinator = entry.runtime_data
    if coordinator.info.get("has_battery") or coordinator.data["battery"]["present"]:
        async_add_entities([BatteryChargingSensor(coordinator)])


class BatteryChargingSensor(DashboardAssistantEntity, BinarySensorEntity):
    """Whether the battery is charging."""

    _attr_name = "Battery charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "battery_charging")

    @property
    def is_on(self) -> bool:
        return bool(self.data["battery"]["charging"])
