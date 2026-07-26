"""Display as a dimmable light."""

from __future__ import annotations

from typing import Any

from homeassistant.components.light import ATTR_BRIGHTNESS, ColorMode, LightEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DashboardAssistantConfigEntry
from .entity import DashboardAssistantEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the display light."""
    async_add_entities([DisplayLight(entry.runtime_data)])


def _to_ha(pct: int) -> int:
    """Device 0..100 percent -> HA 0..255 brightness."""
    return round(pct * 255 / 100)


def _to_pct(brightness: int) -> int:
    """HA 0..255 brightness -> device 0..100 percent."""
    return round(brightness * 100 / 255)


class DisplayLight(DashboardAssistantEntity, LightEntity):
    """The panel/monitor: on/off drives DPMS power, brightness the backlight."""

    _attr_name = "Display"
    _attr_icon = "mdi:monitor"
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "display")

    @property
    def is_on(self) -> bool:
        return bool(self.data["display"]["on"])

    @property
    def brightness(self) -> int:
        return _to_ha(int(self.data["display"]["brightness"]))

    async def async_turn_on(self, **kwargs: Any) -> None:
        if ATTR_BRIGHTNESS in kwargs:
            snapshot = await self.coordinator.client.async_set_display(
                on=True, brightness=_to_pct(kwargs[ATTR_BRIGHTNESS])
            )
        else:
            snapshot = await self.coordinator.client.async_set_display(on=True)
        await self._run_command(snapshot)

    async def async_turn_off(self, **kwargs: Any) -> None:
        snapshot = await self.coordinator.client.async_set_display(on=False)
        await self._run_command(snapshot)
