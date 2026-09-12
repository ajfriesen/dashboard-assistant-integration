"""Binary sensors: battery charging, filesystem health (each only when present)."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DashboardAssistantConfigEntry
from .entity import DashboardAssistantEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors the device's capabilities call for."""
    coordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = []
    if coordinator.info.get("has_battery") or coordinator.data["battery"]["present"]:
        entities.append(BatteryChargingSensor(coordinator))
    # .get chain rather than indexing: an older daemon's snapshot has no
    # "btrfs" key at all (ext4 devices also just report present: false).
    if coordinator.info.get("has_btrfs") or coordinator.data.get("btrfs", {}).get(
        "present"
    ):
        entities.append(FilesystemProblemSensor(coordinator))
    if entities:
        async_add_entities(entities)


class BatteryChargingSensor(DashboardAssistantEntity, BinarySensorEntity):
    """Whether the battery is charging."""

    _attr_name = "Battery charging"
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "battery_charging")

    @property
    def is_on(self) -> bool:
        return bool(self.data["battery"]["charging"])


class FilesystemProblemSensor(DashboardAssistantEntity, BinarySensorEntity):
    """Health of the btrfs root filesystem: on means problem.

    The daemon folds its signals (device error counters, root forced
    read-only) into one "ok" bit; the raw counters ride along as attributes
    for diagnosis.
    """

    _attr_name = "Filesystem"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "filesystem")

    @property
    def is_on(self) -> bool:
        return not self.data["btrfs"]["ok"]

    @property
    def extra_state_attributes(self) -> dict:
        b = self.data["btrfs"]
        return {
            "readonly": b["readonly"],
            "write_errors": b["write_errs"],
            "read_errors": b["read_errs"],
            "flush_errors": b["flush_errs"],
            "corruption_errors": b["corruption_errs"],
            "generation_errors": b["generation_errs"],
            "devices": b["devices"],
        }
