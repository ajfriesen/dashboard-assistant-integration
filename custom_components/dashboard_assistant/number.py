"""Browser zoom, screen saver timeout and brightness, VNC timeout and the battery's
charge thresholds as numbers."""

from __future__ import annotations

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .api import DashboardAssistantRejectedError
from .const import DOMAIN
from .coordinator import DashboardAssistantConfigEntry
from .entity import DashboardAssistantEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the zoom and screen saver numbers."""
    coordinator = entry.runtime_data
    entities: list[NumberEntity] = [ZoomNumber(coordinator)]
    if "screensaver" in coordinator.data:
        entities.append(ScreensaverTimeoutNumber(coordinator))
        # An OS from before the screen saver had its own brightness has no key.
        if "brightness" in coordinator.data["screensaver"]:
            entities.append(ScreensaverBrightnessNumber(coordinator))
    if "vnc" in coordinator.data:
        entities.append(VncTimeoutNumber(coordinator))
    # One number per threshold the battery has: none on a device without one
    # or an OS from before them, only the stop on some (asus-wmi).
    battery = coordinator.data.get("battery", {})
    for key in ChargeThresholdNumber.KEYS:
        if key in battery:
            entities.append(ChargeThresholdNumber(coordinator, key))
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


class ScreensaverBrightnessNumber(DashboardAssistantEntity, NumberEntity):
    """Panel brightness while the screen saver shows; 0 = leave it alone.

    The device dims to it when the screen saver starts and returns to the
    Display light's brightness when it ends.
    """

    _attr_name = "Screen saver brightness"
    _attr_icon = "mdi:brightness-4"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.SLIDER
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "screensaver_brightness")

    @property
    def native_value(self) -> float:
        return float(self.data["screensaver"]["brightness"])

    async def async_set_native_value(self, value: float) -> None:
        snapshot = await self.coordinator.client.async_set_screensaver(
            brightness=int(value)
        )
        await self._run_command(snapshot)


class VncTimeoutNumber(DashboardAssistantEntity, NumberEntity):
    """Minutes after which VNC closes by itself; 0 = never.

    Counted from when VNC was switched on. The ceiling mirrors vncMaxTimeout in
    daemon/vnc.go.
    """

    _attr_name = "VNC timeout"
    _attr_icon = "mdi:timer-lock-outline"
    _attr_native_min_value = 0
    _attr_native_max_value = 240
    _attr_native_step = 1
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES
    _attr_device_class = NumberDeviceClass.DURATION
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "vnc_timeout")

    @property
    def native_value(self) -> float:
        return float(self.data["vnc"]["timeout"])

    async def async_set_native_value(self, value: float) -> None:
        snapshot = await self.coordinator.client.async_set_vnc(timeout=int(value))
        await self._run_command(snapshot)


class ChargeThresholdNumber(DashboardAssistantEntity, NumberEntity):
    """A battery charge threshold: charging starts below Charge start and stops
    at Charge stop, for a device that is always plugged in.

    It shows what the battery holds, not what was asked for: a driver may adjust
    a value (Dell keeps the start at 50 or above), and a change made in the BIOS
    shows too. The range is the kernel's; the device refuses a start that is not
    below the stop.
    """

    KEYS = {"charge_start": "Charge start", "charge_end": "Charge stop"}

    _attr_icon = "mdi:battery-charging-80"
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_native_unit_of_measurement = "%"
    _attr_mode = NumberMode.BOX
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, key: str) -> None:
        super().__init__(coordinator, key.replace("charge_end", "charge_stop"))
        self._key = key
        self._attr_name = self.KEYS[key]

    @property
    def native_value(self) -> float | None:
        value = self.data.get("battery", {}).get(self._key)
        return None if value is None else float(value)

    async def async_set_native_value(self, value: float) -> None:
        try:
            snapshot = await self.coordinator.client.async_set_battery(
                **{self._key: int(value)}
            )
        except DashboardAssistantRejectedError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="charge_rejected",
                translation_placeholders={"reason": str(err)},
            ) from err
        await self._run_command(snapshot)
