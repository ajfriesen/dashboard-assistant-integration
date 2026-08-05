"""Diagnostic and telemetry sensors."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfInformation,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from .coordinator import DashboardAssistantConfigEntry, DashboardAssistantCoordinator
from .entity import DashboardAssistantEntity


@dataclass(frozen=True, kw_only=True)
class DashboardAssistantSensorDescription(SensorEntityDescription):
    """Describes a sensor and how to read it from the snapshot."""

    value_fn: Callable[[dict[str, Any]], StateType]


SENSORS: tuple[DashboardAssistantSensorDescription, ...] = (
    DashboardAssistantSensorDescription(
        key="last_touch",
        name="Last touch",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:gesture-tap",
        value_fn=lambda s: s["touch_seconds"],
    ),
    DashboardAssistantSensorDescription(
        key="mem_total",
        name="Memory total",
        native_unit_of_measurement=UnitOfInformation.MEBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        icon="mdi:memory",
        value_fn=lambda s: s["memory"]["total_mib"],
    ),
    DashboardAssistantSensorDescription(
        key="mem_used",
        name="Memory used",
        native_unit_of_measurement=UnitOfInformation.MEBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:memory",
        value_fn=lambda s: s["memory"]["used_mib"],
    ),
    DashboardAssistantSensorDescription(
        key="disk_total",
        name="Storage total",
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        icon="mdi:harddisk",
        value_fn=lambda s: s["disk"]["total_gib"],
    ),
    DashboardAssistantSensorDescription(
        key="disk_used",
        name="Storage used",
        native_unit_of_measurement=UnitOfInformation.GIBIBYTES,
        device_class=SensorDeviceClass.DATA_SIZE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:harddisk",
        value_fn=lambda s: s["disk"]["used_gib"],
    ),
    DashboardAssistantSensorDescription(
        key="generations",
        name="Generations",
        native_unit_of_measurement="generations",
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:layers-triple",
        value_fn=lambda s: s["generations"],
    ),
    DashboardAssistantSensorDescription(
        key="ip",
        name="IP address",
        icon="mdi:ip-network",
        value_fn=lambda s: s["host"]["ip"] or None,
    ),
    DashboardAssistantSensorDescription(
        key="uptime",
        name="Uptime",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:clock-outline",
        value_fn=lambda s: s["host"]["uptime"],
    ),
    DashboardAssistantSensorDescription(
        key="cpu",
        name="CPU usage",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        icon="mdi:cpu-64-bit",
        value_fn=lambda s: s["host"]["cpu"],
    ),
    DashboardAssistantSensorDescription(
        key="hostname",
        name="Hostname",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:server",
        value_fn=lambda s: s["device"]["hostname"] or None,
    ),
    DashboardAssistantSensorDescription(
        key="model",
        name="Model",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:chip",
        value_fn=lambda s: s["device"]["model"] or None,
    ),
    DashboardAssistantSensorDescription(
        key="serial",
        name="Serial number",
        entity_category=EntityCategory.DIAGNOSTIC,
        icon="mdi:barcode",
        value_fn=lambda s: s["device"]["serial"] or None,
    ),
)

BATTERY_SENSOR = DashboardAssistantSensorDescription(
    key="battery",
    name="Battery",
    native_unit_of_measurement=PERCENTAGE,
    device_class=SensorDeviceClass.BATTERY,
    state_class=SensorStateClass.MEASUREMENT,
    value_fn=lambda s: s["battery"]["level"],
)

TEMPERATURE_SENSOR = DashboardAssistantSensorDescription(
    key="temperature",
    name="Temperature",
    native_unit_of_measurement=UnitOfTemperature.CELSIUS,
    device_class=SensorDeviceClass.TEMPERATURE,
    state_class=SensorStateClass.MEASUREMENT,
    value_fn=lambda s: s["temperature"]["celsius"],
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up sensors, adding battery/temperature only where the hardware has them."""
    coordinator = entry.runtime_data
    descriptions = list(SENSORS)
    if coordinator.info.get("has_battery") or coordinator.data["battery"]["present"]:
        descriptions.append(BATTERY_SENSOR)
    if coordinator.info.get("has_temperature") or coordinator.data["temperature"]["present"]:
        descriptions.append(TEMPERATURE_SENSOR)
    async_add_entities(
        DashboardAssistantSensor(coordinator, description) for description in descriptions
    )


class DashboardAssistantSensor(DashboardAssistantEntity, SensorEntity):
    """A read-only value from the snapshot."""

    entity_description: DashboardAssistantSensorDescription

    def __init__(
        self,
        coordinator: DashboardAssistantCoordinator,
        description: DashboardAssistantSensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.data)
