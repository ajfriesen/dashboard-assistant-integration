"""Dark-mode switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import DashboardAssistantConfigEntry
from .entity import DashboardAssistantEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DashboardAssistantConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the dark-mode switch."""
    async_add_entities([DarkModeSwitch(entry.runtime_data)])


class DarkModeSwitch(DashboardAssistantEntity, SwitchEntity):
    """ON drives the frontend into its dark theme, OFF back to light."""

    _attr_name = "Dark mode"
    _attr_icon = "mdi:theme-light-dark"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "theme")

    @property
    def is_on(self) -> bool:
        return bool(self.data["theme"]["dark"])

    async def async_turn_on(self, **kwargs: Any) -> None:
        snapshot = await self.coordinator.client.async_set_theme(True)
        await self._run_command(snapshot)

    async def async_turn_off(self, **kwargs: Any) -> None:
        snapshot = await self.coordinator.client.async_set_theme(False)
        await self._run_command(snapshot)
